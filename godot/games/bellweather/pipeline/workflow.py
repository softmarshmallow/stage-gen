"""Bellweather's asset build: the game's package, read by the game, written as steps.

    gnode plan pipeline/workflow.py:build --arg package=inputs/default
    gnode run  pipeline/workflow.py:build --arg package=inputs/default --live --max-usd 175 \\
        --deliver package=../../../out/bellweather/{key}

The game's reader resolves its own TOML package, unchanged, and this builder writes one group
of steps per asset. Each map composes its terrain (a model judged by the game's validator,
told what failed), paints its scrolling layers and makes them loop, paints its ground,
climbables and portals, and lays a board of the whole map out. Each actor is drawn as a
concept, a strip per state (the player's are rebased against idle) and a dialogue atlas;
the catalog, the interface sheets and the soundtrack follow. Every painting is judged by the
game's own admission and drawn again when it fails. Reviews read a board of what was made and
are evidence, never gates; ``--arg reviews=no`` leaves them out.

``--arg part=world`` (or ``content`` or ``soundtrack``) builds that part alone and outputs its
files; the whole build (``all``, the default) ends in one step that lays every published file
out at its runtime path and writes ``manifest.json``. ``godot --path godot/games/bellweather
-- --run <dir>`` plays the delivered folder.

The package must sit inside this project (the folder holding ``gnode.yaml``): its authored
references are project files, read by content.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from bellweather_pipeline.briefs import (
    MAP_REVIEW_SYSTEM,
    REVIEW_MAX_TOKENS,
    REVIEW_SYSTEM,
    ActorContent,
    CatalogFamily,
    actor_review_prompt,
    catalog_prompt,
    catalog_review_prompt,
    climbable_prompt,
    concept_prompt,
    dialogue_prompt,
    entity_id,
    layer_prompt,
    loop_prompt,
    map_prompt,
    map_review_prompt,
    material_direction,
    motion_prompt,
    portal_prompt,
    visual_prompt,
)
from bellweather_pipeline.climbable_atlas import plan_climbable_atlas
from bellweather_pipeline.input import resolve_game_package
from bellweather_pipeline.maps import PreparedGameMap
from bellweather_pipeline.motion_contract import (
    MotionActorKind,
    motion_atlas_geometry,
    motion_source_facing,
)
from bellweather_pipeline.terrain_design import terrain_artifact_path, terrain_profile
from bellweather_pipeline.validation import ResolvedGamePackage
from demo_game_tools.input_formats.sideview_content import (
    ContentReference,
    NpcContent,
    PlayerContent,
    ProjectileContent,
)
from demo_game_tools.kits.painted_terrain import (
    PaintedTerrainGround,
    painted_terrain_material_identity,
)
from demo_game_tools.kits.sideview_actor.motion_geometry import dialogue_atlas_grid
from demo_game_tools.kits.sideview_actor.motion_rebase import BASELINE_STATE
from demo_game_tools.kits.sideview_map_design import build_chunk_prompt
from demo_game_tools.kits.sideview_terrain.atlas import terrain_atlas_generation_prompt
from demo_game_tools.kits.ui_art.nodes import document_roles
from demo_game_tools.media.soundtrack.prompt import music_track_prompt
from demo_game_tools.steps.inventory import add_inventory_steps
from demo_game_tools.steps.layers import add_layer_steps
from demo_game_tools.steps.painted_terrain import add_painted_terrain_steps
from demo_game_tools.steps.rebase import add_rebase_steps
from demo_game_tools.steps.soundtrack import add_track_steps
from demo_game_tools.steps.terrain_atlas import add_atlas_steps
from demo_game_tools.steps.ui_atlas import add_ui_sheet_steps
from gnode import Group, StepRef, Workflow
from stage_gen.components.sideview_layers.publish import LayerGate

#: The game's node modules, as project paths.
MAPS = "./pipeline/nodes/maps.py"
GROUND = "./pipeline/nodes/ground.py"
LAYERS = "./pipeline/nodes/layers.py"
CONTENT = "./pipeline/nodes/content.py"
REBASE = "./pipeline/nodes/rebase.py"
SOUNDTRACK = "./pipeline/nodes/soundtrack.py"
INTERFACE = "./pipeline/nodes/interface.py"
PACKAGE = "./pipeline/nodes/package.py"

#: Draws a judged painting gets before the run stops on it.
TAKES = 6
#: Compositions a map's terrain gets: each one after the first is told what the game's
#: validator refused in the one before.
TERRAIN_COMPOSITIONS = 3
#: The most one build of the shipped package may cost, every redraw included.
BUDGET_USD = 175.0
#: What a build may be asked to make.
PARTS = ("all", "world", "content", "soundtrack")

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_REDRAW = {"regenerate": {"max": TAKES, "then": "fail"}}
#: The judge's own words reach the next composition; on the first there are none.
_TERRAIN_FEEDBACK = "${{ feedback && feedback.check.feedback || '' }}"


def _name(value: str) -> str:
    name = value.replace("-", "_")
    if not _NAME.fullmatch(name):
        raise ValueError(f"{value!r} cannot name a step: write it in lower snake or kebab case")
    return name


def _project_root(package: Path) -> Path:
    for folder in (package, *package.parents):
        if (folder / "gnode.yaml").is_file():
            return folder
    raise ValueError(f"{package} is not inside a gnode project")


def _paint(
    group: Group,
    *,
    title: str,
    prompt: str,
    size: str,
    pictures: list[Any],
) -> StepRef:
    """One cut-out painting: an edit of its first picture when it has any, else from text."""

    with_: dict[str, Any] = {"prompt": prompt, "size": size, "background": "transparent"}
    if pictures:
        with_["image"] = pictures[0]
        with_["references"] = pictures[1:]
    return group.step(
        "generate",
        title=title,
        uses="gnode/image.edit@1" if pictures else "gnode/image.generate@1",
        with_=with_,
        requires=["transparent_background"],
        view=True,
    )


class _Build:
    """One package's steps, and every file the runtime package publishes, by runtime path."""

    def __init__(
        self, resolved: ResolvedGamePackage, root: Path, project: Path, *, reviews: bool
    ) -> None:
        self.package = resolved
        self.root = root
        self.project = project
        self.reviews = reviews
        self.published: dict[str, Any] = {}

    def path(self, source: str) -> str:
        """A package file as a project path, read by content."""

        return "./" + (self.root / source).relative_to(self.project).as_posix()

    def publish(self, runtime_path: str, value: Any) -> None:
        if runtime_path in self.published:
            raise ValueError(f"two steps publish {runtime_path}")
        self.published[runtime_path] = value

    def _review(
        self,
        group: Group,
        *,
        title: str,
        schema_uses: str,
        prompt: str,
        system: str,
        pictures: list[Any],
    ) -> None:
        answer = group.step("review_schema", title="The review's shape", uses=schema_uses)
        group.step(
            "review",
            title=title,
            uses="gnode/structured.generate@1",
            with_={
                "prompt": prompt,
                "system": system,
                "schema": answer.outputs.schema,
                "context": pictures,
                "max_tokens": REVIEW_MAX_TOKENS,
            },
        )

    # ------------------------------------------------------------------ maps

    def maps(self, wf: Workflow) -> None:
        group = wf.group("maps", title="Maps")
        for game_map in self.package.maps:
            self._map(group.group(_name(game_map.map_id), title=game_map.display_name), game_map)

    def _map(self, group: Group, game_map: PreparedGameMap) -> None:
        sources = {entry.reference_id: entry.source for entry in game_map.references}
        terrain = self._terrain(group, game_map)
        self.publish(terrain_artifact_path(game_map.map_id), terrain)
        layers = self._layers(group, game_map, sources)
        ground, composed, evidence, atlas = self._ground(group, game_map, terrain, sources)
        presentations: dict[str, Any] = {}
        for asset in ("portal", "climbable"):
            image = self._presentation(group, game_map, asset, sources)
            if image is not None:
                presentations[asset] = image
        board = group.step(
            "composite",
            title="Lay out the whole map",
            uses=f"{MAPS}#composite",
            with_={
                "layers": {key: step.outputs.image for key, step in layers.items()},
                "placements": {key: step.outputs.validation for key, step in layers.items()},
                "ground": ground,
                "terrain": terrain,
                "map": game_map.model_dump(mode="json"),
                "ground_composed": composed,
            },
            view=True,
        )
        if not self.reviews:
            return
        painter_order = sorted(
            game_map.layers, key=lambda item: (item.plane == "foreground", item.order)
        )
        self._review(
            group,
            title=f"Review {game_map.display_name}",
            schema_uses=f"{MAPS}#map_review_schema",
            prompt=map_review_prompt(game_map, list(presentations)),
            system=MAP_REVIEW_SYSTEM,
            pictures=[
                board.outputs.image,
                evidence,
                *([] if atlas is None else [atlas]),
                *presentations.values(),
                *(self.path(entry.source) for entry in game_map.references),
                *(
                    picture
                    for layer in painter_order
                    for picture in (
                        layers[layer.layer_id].outputs.image,
                        layers[layer.layer_id].outputs.preview,
                    )
                ),
            ],
        )

    def _terrain(self, group: Group, game_map: PreparedGameMap) -> Any:
        """A composition the map's validator accepts, compiled into its geometry."""

        part = group.group("terrain", title="Compose the terrain")
        profile = terrain_profile(game_map)
        facts = {"map": game_map.model_dump(mode="json")}
        schema = part.step(
            "schema",
            title="The grammar this map allows",
            uses=f"{MAPS}#terrain_schema",
            with_=facts,
        )
        intent = map_prompt(self.package, game_map.terrain.brief)
        design = part.step(
            "design",
            title="Compose the level",
            uses="gnode/structured.generate@1",
            with_={
                "prompt": f"{intent}{_TERRAIN_FEEDBACK}\n\nCompose the map.",
                "system": build_chunk_prompt(profile, profile.geometry.columns),
                "schema": schema.outputs.schema,
            },
        )
        part.step(
            "check",
            title="Hold it to the map's rules",
            uses=f"{MAPS}#check_terrain",
            judges="design",
            with_={"design": design.outputs.json, **facts},
            on_reject={
                "regenerate": {"max": TERRAIN_COMPOSITIONS, "feedback": True, "then": "fail"}
            },
        )
        compiled = part.step(
            "compile",
            title="Compile the geometry",
            uses=f"{MAPS}#terrain",
            with_={"design": design.outputs.json, **facts},
            view=True,
        )
        return compiled.outputs.terrain

    def _layers(
        self, group: Group, game_map: PreparedGameMap, sources: dict[str, str]
    ) -> dict[str, StepRef]:
        part = group.group("layers", title="Scrolling layers")
        published: dict[str, StepRef] = {}
        for layer in game_map.layers:
            construction = layer.loop_construction or game_map.continuity.loop_construction
            steps = add_layer_steps(
                part.group(_name(layer.layer_id), title=f"Layer {layer.layer_id}"),
                nodes=LAYERS,
                references=[self.path(sources[ref_id]) for ref_id in layer.reference_ids],
                prompt=layer_prompt(self.package, layer),
                size="1536x1024",
                layer=layer.model_dump(mode="json"),
                construction=construction,
                fallback=game_map.continuity.loop_fallback,
                label=f"{game_map.map_id}/{layer.layer_id}",
                loop_prompt=loop_prompt(self.package, layer, construction),
                gate=LayerGate(),
                place_opaque=True,
            )
            publish = steps["publish"]
            folder = f"maps/{game_map.map_id}/layers/{layer.layer_id}"
            self.publish(f"{folder}.png", publish.outputs.image)
            self.publish(f"{folder}.validation.json", publish.outputs.validation)
            published[layer.layer_id] = publish
        return published

    def _ground(
        self, group: Group, game_map: PreparedGameMap, terrain: Any, sources: dict[str, str]
    ) -> tuple[Any, bool, Any, Any]:
        """The ground as the board draws it, whether that is composed, its evidence, its atlas."""

        part = group.group("ground", title="Ground")
        ground = game_map.ground
        materials = [self.path(sources[ref_id]) for ref_id in ground.reference_ids]
        folder = f"maps/{game_map.map_id}"
        if isinstance(ground, PaintedTerrainGround):
            style = self.package.game.style
            identity = painted_terrain_material_identity(
                prompt=ground.prompt,
                visual_direction_sha256=hashlib.sha256(
                    json.dumps(
                        {"label": style.label, "keywords": list(style.keywords)}, sort_keys=True
                    ).encode("utf-8")
                ).hexdigest(),
                reference_sha256=[
                    self.package.file(sources[ref_id]).sha256 for ref_id in ground.reference_ids
                ],
            )
            painted = add_painted_terrain_steps(
                part,
                nodes=GROUND,
                map_id=game_map.map_id,
                columns=game_map.terrain.columns,
                rows=game_map.terrain.rows,
                terrain=terrain,
                materials=materials,
                material_identity=identity,
                material_direction=material_direction(self.package, game_map),
            )
            for segment_id, step in painted["segments"].items():
                self.publish(f"{folder}/ground/{segment_id}.png", step.outputs.image)
                self.publish(
                    f"{folder}/ground/{segment_id}.validation.json", step.outputs.validation
                )
            compose = painted["compose"]
            self.publish(f"{folder}/ground.validation.json", compose.outputs.validation)
            return compose.outputs.evidence, True, compose.outputs.evidence, None
        atlas = add_atlas_steps(
            part,
            nodes=GROUND,
            prompt=terrain_atlas_generation_prompt(material_direction(self.package, game_map)),
            materials=materials,
        )["publish"].outputs.image
        evidence = part.step(
            "evidence",
            title="Draw it through the occupancy",
            uses=f"{GROUND}#ground_evidence",
            with_={"atlas": atlas, "terrain": terrain},
            view=True,
        )
        self.publish(f"{folder}/ground.png", atlas)
        return atlas, False, evidence.outputs.image, atlas

    def _presentation(
        self, group: Group, game_map: PreparedGameMap, asset: str, sources: dict[str, str]
    ) -> Any | None:
        """A climbable atlas or a portal pair, held to its sheet gate and repacked."""

        roles: list[str] = []
        if asset == "climbable":
            climbable = game_map.climbable
            if climbable is None:
                return None
            roles = [climbable.role_of(entry.variant_id) for entry in climbable.variants]
            plan = plan_climbable_atlas(len(climbable.variants))
            size, width, height = plan.size, plan.width_px, plan.height_px
            prompt = climbable_prompt(self.package, game_map, roles)
            reference_ids = climbable.reference_ids
        else:
            portal = game_map.portal
            if portal is None:
                return None
            size, width, height = "1536x1024", 1536, 1024
            prompt = portal_prompt(self.package, game_map)
            reference_ids = portal.reference_ids
        part = group.group(asset, title=f"The {asset} sheet")
        painting = _paint(
            part,
            title=f"Paint the {asset} sheet",
            prompt=prompt,
            size=size,
            pictures=[self.path(sources[ref_id]) for ref_id in reference_ids],
        )
        facts = {"asset": asset, "roles": roles}
        part.step(
            "admit",
            title="Hold the sheet to its gate",
            uses=f"{MAPS}#admit_presentation",
            judges="generate",
            with_={"image": painting.outputs.image, **facts, "width": width, "height": height},
            on_reject=_REDRAW,
        )
        published = part.step(
            "publish",
            title="One subject per cell",
            uses=f"{MAPS}#publish_presentation",
            with_={"raw": painting.outputs.image, **facts},
            view=True,
        )
        folder = f"maps/{game_map.map_id}"
        self.publish(f"{folder}/{asset}.png", published.outputs.image)
        if asset == "climbable":
            self.publish(f"{folder}/climbable.validation.json", published.outputs.validation)
        return published.outputs.image

    # --------------------------------------------------------------- actors

    def actors(self, wf: Workflow) -> None:
        package = self.package
        group = wf.group("actors", title="Actors")
        for player in package.player.players:
            self._actor(group, "player", player, package.player.references)
        for mob in package.mobs.mobs:
            self._actor(group, "mob", mob, package.mobs.references)
        for npc in package.npcs.npcs:
            self._actor(group, "npc", npc, package.npcs.references)

    def _facing(self, kind: MotionActorKind, state: str) -> Any:
        return motion_source_facing(
            kind,
            state,
            npc_world_orientation=self.package.npcs.world_orientation if kind == "npc" else None,
        )

    def _strip(
        self, group: Group, kind: MotionActorKind, entry: ActorContent, state: str, concept: Any
    ) -> StepRef:
        """One state's strip, painted from the concept, admitted and repacked."""

        facing = self._facing(kind, state)
        geometry = motion_atlas_geometry(kind, state)
        anchor = next(motion.anchor for motion in entry.motions if motion.state == state)
        strip = _paint(
            group,
            title=f"Draw the {state} strip",
            prompt=motion_prompt(self.package, kind, entry, state, facing),
            size=geometry.provider_size,
            pictures=[concept],
        )
        grid = {
            "columns": geometry.columns,
            "rows": geometry.rows,
            "required_cells": geometry.required_cells,
            "width": geometry.width,
            "height": geometry.height,
        }
        group.step(
            "admit",
            title="Every cell drawn",
            uses=f"{CONTENT}#admit_frames",
            judges="generate",
            with_={"image": strip.outputs.image, **grid},
            on_reject=_REDRAW,
        )
        return group.step(
            "publish",
            title="Repack into canonical cells",
            uses=f"{CONTENT}#publish_strip",
            with_={
                "raw": strip.outputs.image,
                **grid,
                "entity_kind": kind,
                "entity_id": entity_id(entry),
                "state": state,
                "anchor": anchor,
                "source_facing": facing,
            },
            view=True,
        )

    def _actor(
        self,
        parent: Group,
        kind: MotionActorKind,
        entry: ActorContent,
        references: list[ContentReference],
    ) -> None:
        actor_id = entity_id(entry)
        group = parent.group(_name(f"{kind}_{actor_id}"), title=f"The {kind} {entry.display_name}")
        folder = f"content/{kind}s/{actor_id}"
        sources = {reference.reference_id: reference.source for reference in references}
        concept_group = group.group("concept", title="Identity concept")
        concept = _paint(
            concept_group,
            title="Draw the identity concept",
            prompt=concept_prompt(self.package, kind, entry),
            size="1024x1536",
            pictures=[self.path(sources[ref_id]) for ref_id in entry.reference_ids],
        )
        concept_group.step(
            "admit",
            title="Admit the cut-out",
            uses=f"{CONTENT}#admit_cutout",
            judges="generate",
            with_={"image": concept.outputs.image, "width": 1024, "height": 1536},
            on_reject=_REDRAW,
        )
        sheet: dict[str, Any] = {"concept": concept.outputs.image}
        if kind != "npc":
            self.publish(f"{folder}/concept.png", concept.outputs.image)
            strips: dict[str, Any] = {}
            for motion in entry.motions:
                state = motion.state
                published = self._strip(
                    group.group(_name(state), title=f"The {state} strip"),
                    kind,
                    entry,
                    state,
                    concept.outputs.image,
                )
                strips[state] = published.outputs.image
                sheet[state] = published.outputs.image
                self.publish(f"{folder}/states/{state}.png", published.outputs.image)
            if isinstance(entry, PlayerContent):
                self._rebase(group, entry, strips, folder)
        else:
            world = self._strip(
                group.group("world", title="World sprite"),
                kind,
                entry,
                "idle",
                concept.outputs.image,
            )
            sheet["world"] = world.outputs.image
            self.publish(f"{folder}/world.png", world.outputs.image)
        if isinstance(entry, PlayerContent | NpcContent):
            expressions = (
                entry.dialogue_art.expressions
                if isinstance(entry, PlayerContent)
                else entry.dialogue_expressions
            )
            dialogue = self._dialogue(group, kind, actor_id, expressions, concept.outputs.image)
            sheet["dialogue"] = dialogue.outputs.image
            self.publish(f"{folder}/dialogue.png", dialogue.outputs.image)
        board = group.step(
            "contact_sheet",
            title="Lay out the review board",
            uses=f"{CONTENT}#contact_sheet",
            with_={"pictures": sheet, "labels": list(sheet), "title": f"{kind}: {actor_id}"},
            view=True,
        )
        if self.reviews:
            selected = set(entry.reference_ids)
            self._review(
                group,
                title=f"Review {entry.display_name}",
                schema_uses=f"{CONTENT}#review_schema",
                prompt=actor_review_prompt(
                    kind,
                    entry,
                    source_facings={
                        motion.state: self._facing(kind, motion.state) for motion in entry.motions
                    },
                ),
                system=REVIEW_SYSTEM,
                pictures=[
                    board.outputs.sheet,
                    *(self.path(ref.source) for ref in references if ref.reference_id in selected),
                ],
            )

    def _dialogue(
        self,
        group: Group,
        kind: MotionActorKind,
        actor_id: str,
        expressions: list[str],
        concept: Any,
    ) -> StepRef:
        part = group.group("dialogue", title="Dialogue portraits")
        columns, rows = dialogue_atlas_grid(len(expressions))
        painting = _paint(
            part,
            title="Draw the portraits",
            prompt=dialogue_prompt(self.package, kind, actor_id, expressions),
            size="1536x1024",
            pictures=[concept],
        )
        part.step(
            "admit",
            title="Every expression drawn",
            uses=f"{CONTENT}#admit_frames",
            judges="generate",
            with_={
                "image": painting.outputs.image,
                "columns": columns,
                "rows": rows,
                "required_cells": len(expressions),
                "width": 1536,
                "height": 1024,
            },
            on_reject=_REDRAW,
        )
        return part.step(
            "publish",
            title="Repack into canonical cells",
            uses=f"{CONTENT}#publish_dialogue",
            with_={
                "raw": painting.outputs.image,
                "entity_kind": kind,
                "entity_id": actor_id,
                "expressions": list(expressions),
            },
            view=True,
        )

    def _rebase(
        self, group: Group, player: PlayerContent, strips: dict[str, Any], folder: str
    ) -> None:
        states = [motion.state for motion in player.motions]
        rebase = add_rebase_steps(
            group.group("rebase", title="Rebase every state to idle"),
            nodes=REBASE,
            display_name=player.display_name,
            states=states,
            baseline_state=BASELINE_STATE,
            geometry={
                state: (
                    motion_atlas_geometry("player", state).columns,
                    motion_atlas_geometry("player", state).rows,
                )
                for state in states
            },
            atlases=strips,
        )
        self.publish(f"{folder}/motion-rebase.json", rebase["record"].outputs.record)
        self.publish(f"{folder}/motion-rebase-first-pass.json", rebase["first_pass"].outputs.record)
        self.publish(f"{folder}/motion-rebase-plate.png", rebase["plate"].outputs.plate)
        self.publish(
            f"{folder}/motion-rebase-verification-plate.png", rebase["verify_plate"].outputs.plate
        )

    # -------------------------------------------------------------- catalog

    def catalog(self, wf: Workflow) -> None:
        package = self.package
        families: list[tuple[CatalogFamily, list[tuple[str, Any]], list[ContentReference]]] = [
            ("prop", [(e.prop_id, e) for e in package.props.props], package.props.references),
            ("item", [(e.item_id, e) for e in package.items.items], package.items.references),
        ]
        if package.projectiles is not None:
            families.append(
                (
                    "projectile",
                    [(e.projectile_id, e) for e in package.projectiles.projectiles],
                    package.projectiles.references,
                )
            )
        for family, entries, references in families:
            self._family(
                wf.group(f"{family}s", title=f"{family.capitalize()}s"), family, entries, references
            )

    def _family(
        self,
        group: Group,
        family: CatalogFamily,
        entries: list[tuple[str, Any]],
        references: list[ContentReference],
    ) -> None:
        sources = {reference.reference_id: reference.source for reference in references}
        pictures: dict[str, Any] = {}
        for entity, entry in entries:
            part = group.group(_name(entity), title=f"The {entity} {family}")
            painting = _paint(
                part,
                title=f"Draw the {family}",
                prompt=catalog_prompt(self.package, family, entity, entry),
                size="1024x1024",
                pictures=[self.path(sources[ref_id]) for ref_id in entry.reference_ids],
            )
            projectile = isinstance(entry, ProjectileContent)
            part.step(
                "admit",
                title="Admit the cut-out",
                uses=f"{CONTENT}#admit_projectile" if projectile else f"{CONTENT}#admit_cutout",
                judges="generate",
                with_={
                    "image": painting.outputs.image,
                    **({} if projectile else {"width": 1024, "height": 1024}),
                },
                on_reject=_REDRAW,
            )
            pictures[entity] = painting.outputs.image
            self.publish(f"content/{family}s/{entity}.png", painting.outputs.image)
        board = group.step(
            "contact_sheet",
            title="Lay out the catalog board",
            uses=f"{CONTENT}#contact_sheet",
            with_={"pictures": pictures, "labels": list(pictures), "title": f"{family} catalog"},
            view=True,
        )
        if self.reviews:
            self._review(
                group,
                title=f"Review the {family} catalog",
                schema_uses=f"{CONTENT}#review_schema",
                prompt=catalog_review_prompt(family, entries),
                system=REVIEW_SYSTEM,
                pictures=[board.outputs.sheet, *(self.path(ref.source) for ref in references)],
            )

    # ------------------------------------------------------------ interface

    def interface(self, wf: Workflow) -> None:
        package = self.package
        group = wf.group("interface", title="Interface")

        def style(task: str) -> str:
            return visual_prompt(package, task)

        panel = add_inventory_steps(
            group.group("inventory_panel", title="Inventory panel"),
            nodes=INTERFACE,
            ui=package.ui,
            style_prompt=style,
            reference_path=self.path,
            review=self.reviews,
        )
        self.publish("ui/inventory_panel.png", panel["publish"].outputs.image)
        for role in document_roles(package.ui):
            sheet = add_ui_sheet_steps(
                group.group(_name(role.role), title=f"The {role.role} sheet"),
                nodes=INTERFACE,
                ui=package.ui,
                role=role,
                style_prompt=style,
                reference_path=self.path,
                review=self.reviews,
            )
            self.publish(f"ui/{role.role}.png", sheet["publish"].outputs.image)
            self.publish(f"ui/{role.role}.validation.json", sheet["publish"].outputs.validation)

    # ----------------------------------------------------------- soundtrack

    def soundtrack(self, wf: Workflow) -> None:
        package = self.package
        group = wf.group("soundtrack", title="Soundtrack")
        for track in package.soundtrack.tracks:
            steps = add_track_steps(
                group.group(_name(track.track_id), title=f"Track {track.track_id}"),
                nodes=SOUNDTRACK,
                track_id=track.track_id,
                prompt=music_track_prompt(
                    medium="a 2D game",
                    game_id=package.game.game_id,
                    track_id=track.track_id,
                    creative_brief=track.creative_brief,
                    generation=track.generation,
                ),
                target_duration_seconds=track.generation.target_duration_seconds,
                instrumental=track.generation.instrumental,
                seamless_loop=track.generation.seamless_loop,
            )
            self.publish(f"soundtrack/{track.track_id}.mp3", steps["generate"].outputs.audio)

    # -------------------------------------------------------------- package

    def package_files(self) -> dict[str, str]:
        return {entry.path: self.path(entry.path) for entry in self.package.files}

    def bindings(self, wf: Workflow) -> None:
        wf.step(
            "bindings",
            title="Resolve every gameplay binding",
            uses=f"{PACKAGE}#bindings",
            with_={"package": self.package_files()},
        )

    def runtime(self, wf: Workflow) -> StepRef:
        return wf.step(
            "package",
            title="Lay out the runtime package",
            uses=f"{PACKAGE}#assemble_package",
            with_={
                "package": self.package_files(),
                "published": dict(sorted(self.published.items())),
            },
            view=True,
        )

    def collect(self, wf: Workflow) -> StepRef:
        return wf.step(
            "files",
            title="Gather what this part published",
            uses="gnode/package@1",
            with_={"files": dict(sorted(self.published.items()))},
        )


def build(package: str, part: str = "all", reviews: str = "yes") -> Workflow:
    """The package's assets, judged; the whole build is laid out as the runtime package."""

    if part not in PARTS:
        raise ValueError(f"part is one of {', '.join(PARTS)}, not {part!r}")
    if reviews not in {"yes", "no"}:
        raise ValueError(f"reviews is yes or no, not {reviews!r}")
    root = Path(package).resolve()
    resolved = resolve_game_package(root)
    game = resolved.game
    built = _Build(resolved, root, _project_root(root), reviews=reviews == "yes")
    wf = Workflow(
        "bellweather",
        title=game.display_name if part == "all" else f"{game.display_name}: {part}",
        description="Every asset Bellweather's package declares, laid out for the Godot host.",
        budget={"max_usd": BUDGET_USD},
    )
    if part in {"all", "world"}:
        built.maps(wf)
    if part in {"all", "content"}:
        built.actors(wf)
        built.catalog(wf)
        built.interface(wf)
        built.bindings(wf)
    if part in {"all", "soundtrack"}:
        built.soundtrack(wf)
    if part == "all":
        wf.outputs(package=built.runtime(wf).outputs.files)
    else:
        wf.outputs(files=built.collect(wf).outputs.files)
    return wf


__all__ = ["BUDGET_USD", "PARTS", "TAKES", "TERRAIN_COMPOSITIONS", "build"]
