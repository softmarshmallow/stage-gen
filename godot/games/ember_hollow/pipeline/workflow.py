"""Ember Hollow's asset build: every picture, sound and record the survival host reads.

    gnode plan pipeline/workflow.py:build --arg package=inputs --arg scope=minimal
    gnode run  pipeline/workflow.py:build --arg package=inputs --live --max-usd 40 \\
        --deliver package=../../../out/ember-hollow/{key}

The game's own reader resolves the package, unchanged, and refuses an incomplete world
while planning. A scope is one rung of a ladder (minimal, props, actors, full) that selects
which assets are built and changes nothing about the ones it keeps, so a narrow build's
answers are the wider build's too. Every painting is held to its family's pixel gate by a
judge and drawn again when it fails; auditioned takes are adopted through the same gates.
Reviews are evidence, never gates. The last step lays the published files out at the
paths the manifest names and writes ``manifest.json``.

A package must sit inside this project (the folder holding ``gnode.yaml``): its authored
references and takes are project files, read by content.
"""

from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from demo_game_tools.kits.screen_art.layouts import CUTOUT_ALPHA_POLICY
from demo_game_tools.kits.ui_art.nodes import document_roles
from demo_game_tools.steps.rebase import add_rebase_steps
from demo_game_tools.steps.ui_atlas import add_ui_sheet_steps
from ember_hollow_pipeline import gates, templates
from ember_hollow_pipeline import manifest as refs
from ember_hollow_pipeline import survival_prompts as prompts
from ember_hollow_pipeline.anchor import AnchorSubject
from ember_hollow_pipeline.build import (
    GROUND_CANVAS,
    MOTION_COLUMNS,
    SPRITE_CANVAS,
    STRIKE_CELL_KINDS,
    STRIP_CANVAS,
)
from ember_hollow_pipeline.models import Package, strip_key
from ember_hollow_pipeline.preparation_media import plate_gate_kwargs
from ember_hollow_pipeline.reviews import REVIEW_FAMILIES, REVIEW_MAX_TOKENS
from ember_hollow_pipeline.scopes import SCOPES
from ember_hollow_pipeline.shell.nodes import (
    clip_content_task,
    clip_resolution,
    document_clip_roles,
    document_plate_roles,
    plate_content_task,
    shell_artifact_refs,
    shell_clip_artifact_refs,
    shell_typeface_ref,
)
from ember_hollow_pipeline.survival_request import load_package
from gnode import Group, StepRef, Workflow

#: The game's node modules, as project paths.
PICTURES = "./pipeline/nodes/pictures.py"
AUDIO = "./pipeline/nodes/audio.py"
PROPS = "./pipeline/nodes/props.py"
ACTORS = "./pipeline/nodes/actors.py"
REVIEWS = "./pipeline/nodes/reviews.py"
SHELL = "./pipeline/nodes/shell.py"
WORLD = "./pipeline/nodes/world.py"
INTERFACE = "./pipeline/nodes/interface.py"

#: Draws a judged painting, track or answer gets before the run stops on it.
TAKES = 6
#: The most one full build may cost, every redraw included.
BUDGET_USD = 220.0
#: The props a minimal build draws: one tall, one squat, one soft, and the vegetation
#: set, because a wood of one repeated conifer is the demo's most visible flaw.
MINIMAL_PROPS = ("pine", "moss_boulder", "thorn_bush", "birch", "dead_snag")
#: The rung each family joins at.
_RANK = {name: index for index, name in enumerate(SCOPES)}
_REVIEW_FROM = {"props": 1, "ground": 1, "actors": 2, "fx": 3, "seasons": 1}
REVIEW_SYSTEM = (
    "You are a strict independent 2D game-art technical director. Return only the requested "
    "structured review."
)
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_REDRAW = {"regenerate": {"max": TAKES, "then": "fail"}}


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


def _head(kind: str, **fields: object) -> dict[str, object]:
    return {"schema_version": 1, "kind": kind, **fields}


def _canvas(size: tuple[int, int]) -> dict[str, int]:
    return {"width": size[0], "height": size[1]}


class _Build:
    """One package inside the project: its files as project paths, and what it publishes."""

    def __init__(self, package: Package, root: Path, scope: str) -> None:
        self.package = package
        self.root = root
        self.project = _project_root(root)
        self.rank = _RANK[scope]
        self.scope = scope
        self.published: dict[str, Any] = {}
        #: Each family's subjects for its review, labelled in the order the sheet lays them.
        self.reviewed: dict[str, list[tuple[str, Any]]] = {family: [] for family in REVIEW_FAMILIES}
        self.templates: dict[tuple[int, int, int], StepRef] = {}
        self.style = [self.path(package.style_reference)] if package.style_reference else []

    def path(self, source: str) -> str:
        """A package file as a project path, read by content."""

        return "./" + (self.root / source).relative_to(self.project).as_posix()

    def present(self, source: str) -> bool:
        return (self.root / source).is_file()

    def publish(self, ref: str, value: Any) -> None:
        if ref in self.published:
            raise ValueError(f"two steps publish {ref}")
        self.published[ref] = value

    def review(self, family: str, label: str, picture: Any) -> None:
        self.reviewed[family].append((label, picture))

    # ----------------------------------------------------------------- shared shapes

    def template(self, wf: Workflow, columns: int, rows: int, cell_px: int) -> StepRef:
        key = (columns, rows, cell_px)
        if key not in self.templates:
            group = self.templates_group(wf)
            self.templates[key] = group.step(
                f"lattice_{columns}x{rows}_{cell_px}",
                title=f"Draw the {columns}x{rows} lattice",
                uses=f"{PICTURES}#lattice_template",
                with_={
                    "columns": columns,
                    "rows": rows,
                    "cell_px": cell_px,
                    "transparent": templates.LATTICE_TRANSPARENT,
                },
            )
        return self.templates[key]

    def templates_group(self, wf: Workflow) -> Group:
        if not hasattr(self, "_templates_group"):
            self._templates_group = wf.group("templates", title="Paintover lattices")
        return self._templates_group

    def paint(
        self,
        group: Group,
        *,
        title: str,
        prompt: str,
        size: tuple[int, int],
        transparent: bool,
        pictures: list[Any],
        gate: str,
        args: dict[str, Any],
        reference: Any = None,
    ) -> StepRef:
        """One image drawn from its pictures, judged by its gate, drawn again when refused."""

        with_: dict[str, Any] = {
            "prompt": prompt,
            "size": f"{size[0]}x{size[1]}",
            "background": "transparent" if transparent else "opaque",
        }
        if pictures:
            with_ |= {"image": pictures[0], "references": pictures[1:]}
        painting = group.step(
            "generate",
            title=title,
            uses="gnode/image.edit@1" if pictures else "gnode/image.generate@1",
            with_=with_,
            requires=["transparent_background"] if transparent else [],
            view=True,
        )
        judged: dict[str, Any] = {"image": painting.outputs.image, "gate": gate, "args": args}
        if reference is not None:
            judged["reference"] = reference
        group.step(
            "admit",
            title="Hold it to its gate",
            uses=f"{PICTURES}#admit_picture",
            judges="generate",
            with_=judged,
            on_reject=_REDRAW,
        )
        return painting

    def adopt(
        self, group: Group, *, take: str, gate: str, args: dict[str, Any], reference: Any = None
    ) -> StepRef:
        """An auditioned take through the gate a draw meets; absent, the run refuses it."""

        with_: dict[str, Any] = {
            "gate": gate,
            "args": args,
            "path": take,
            "sha256": self.package.digests[take],
        }
        if self.present(take):
            with_["take"] = self.path(take)
        if reference is not None:
            with_["reference"] = reference
        return group.step(
            "adopt",
            title="Adopt the auditioned take",
            uses=f"{PICTURES}#adopt_picture",
            with_=with_,
        )

    def finish(
        self,
        group: Group,
        source: Any,
        *,
        finish: str,
        gate: str,
        args: dict[str, Any],
        head: dict[str, object],
        reference: Any = None,
        title: str = "Finish and record it",
    ) -> StepRef:
        with_: dict[str, Any] = {
            "source": source,
            "finish": finish,
            "gate": gate,
            "args": args,
            "head": head,
        }
        if reference is not None:
            with_["reference"] = reference
        return group.step(
            "publish", title=title, uses=f"{PICTURES}#finish_picture", with_=with_, view=True
        )

    def plate(
        self,
        group: Group,
        *,
        title: str,
        prompt: str,
        args: dict[str, Any],
        gate: str,
        head: dict[str, object],
        image_ref: str,
        record_ref: str,
        take: str | None = None,
        pictures: list[Any] | None = None,
        label: str,
        family: str = "ground",
    ) -> StepRef:
        """A ground-style plate, drawn or adopted, mirrored on both axes and published."""

        if take is not None:
            source = self.adopt(group, take=take, gate=gate, args=args).outputs.image
        else:
            source = self.paint(
                group,
                title=title,
                prompt=prompt,
                size=GROUND_CANVAS,
                transparent=False,
                pictures=self.style if pictures is None else pictures,
                gate=gate,
                args=args,
            ).outputs.image
        published = self.finish(group, source, finish="plate", gate=gate, args=args, head=head)
        self.publish(image_ref, published.outputs.image)
        self.publish(record_ref, published.outputs.validation)
        self.review(family, label, published.outputs.image)
        return published

    # ----------------------------------------------------------------- families

    def props(self, wf: Workflow) -> None:
        package = self.package
        group = wf.group("props", title="Props")
        summers: dict[tuple[str, str], Any] = {}
        for prop in package.props:
            minimal = prop.prop_id in MINIMAL_PROPS
            if self.rank < 1 and not minimal:
                continue
            prop_group = group.group(_name(prop.prop_id), title=prop.prop_id)
            if prop.sheet is not None:
                baseline = self.prop_sheet(prop_group, prop, summers)
            else:
                baseline = self.prop_states(prop_group, prop, summers)
            sprite, validation = baseline
            subject = AnchorSubject(
                prop_id=prop.prop_id,
                family=prop.family,
                baseline_state=prop.baseline_state,
                height_meters=package.meters(prop.height_units),
                player_height_meters=package.player_height_meters,
                pitch_degrees=float(package.camera.get("pitch_degrees", 55.0)),
            )
            anchor = prop_group.step(
                "anchor",
                title=f"Place {prop.prop_id}'s ground anchor",
                uses=f"{PROPS}#place_anchor",
                with_={"sprite": sprite, "validation": validation, "subject": asdict(subject)},
                view=True,
            )
            self.publish(refs.anchor_ref(prop.prop_id), anchor.outputs.anchor)
        self.seasons(wf, summers)

    def _states(self, prop: Any) -> list[str]:
        """The states a scope draws: every one from props up; the minimal scope draws what
        a played demo needs (the baseline, what each interaction passes through and leaves,
        and the looks the layout may place)."""

        if self.rank >= 1:
            return list(prop.states)
        states = [prop.baseline_state]
        wanted: list[str] = []
        for interaction in prop.interactions:
            wanted.extend([*interaction.progress, interaction.next_state])
        if prop.variants is not None:
            wanted.extend(prop.variants.states)
        for candidate in wanted:
            if candidate in prop.states and candidate not in states:
                states.append(candidate)
        return states

    def prop_states(
        self, group: Group, prop: Any, summers: dict[tuple[str, str], Any]
    ) -> tuple[Any, Any]:
        args = {**_canvas(SPRITE_CANVAS), "max_components": prop.max_components}
        baseline: tuple[Any, Any] | None = None
        for state in self._states(prop):
            state_group = group.group(_name(state), title=f"{prop.prop_id} {state}")
            painting = self.paint(
                state_group,
                title=f"Draw {prop.prop_id} {state}",
                prompt=prompts.prop_prompt(self.package, prop, state),
                size=SPRITE_CANVAS,
                transparent=True,
                pictures=self.style,
                gate="prop",
                args=args,
            )
            published = self.finish(
                state_group,
                painting.outputs.image,
                finish="sprite",
                gate="prop",
                args=args,
                head=_head(
                    "oblique-survival-prop-validation-v1",
                    prop_id=prop.prop_id,
                    state=state,
                    max_components=prop.max_components,
                    drawn={"kind": "sprite"},
                ),
            )
            self.publish(refs.prop_ref(prop.prop_id, state), published.outputs.image)
            self.publish(
                f"production/validation/props/{prop.prop_id}-{state}.json",
                published.outputs.validation,
            )
            summers[(prop.prop_id, state)] = published.outputs.image
            self.review("props", f"{prop.prop_id} {state}", published.outputs.image)
            if state == prop.baseline_state:
                baseline = (published.outputs.image, published.outputs.validation)
        if baseline is None:
            raise ValueError(f"{prop.prop_id} draws no baseline state")
        return baseline

    def prop_sheet(
        self, group: Group, prop: Any, summers: dict[tuple[str, str], Any]
    ) -> tuple[Any, Any]:
        """Every look on one canvas in every scope; each look cut at the emptiest seams."""

        sheet = prop.sheet
        args = {
            "columns": sheet.columns,
            "rows": sheet.rows,
            "cell_px": templates.SHEET_CELL_PX,
            "states": list(prop.states),
            "max_components": prop.max_components,
        }
        painting = self.paint(
            group,
            title=f"Draw every look of {prop.prop_id}",
            prompt=prompts.prop_sheet_prompt(self.package, prop),
            size=(sheet.columns * templates.SHEET_CELL_PX, sheet.rows * templates.SHEET_CELL_PX),
            transparent=True,
            pictures=self.style,
            gate="prop_sheet",
            args=args,
        )
        laid = group.step(
            "sheet",
            title="Lay the looks back on the grid",
            uses=f"{PICTURES}#lay_sheet",
            with_={"sheet": painting.outputs.image, "args": args, "prop_id": prop.prop_id},
        )
        self.publish(
            f"production/validation/props/{prop.prop_id}-sheet.json", laid.outputs.validation
        )
        baseline: tuple[Any, Any] | None = None
        head = _head(
            "oblique-survival-prop-validation-v1",
            prop_id=prop.prop_id,
            max_components=prop.max_components,
        )
        for state in prop.states:
            cut = group.step(
                f"look_{_name(state)}",
                title=f"Cut {prop.prop_id} {state}",
                uses=f"{PICTURES}#cut_look",
                with_={"sheet": painting.outputs.image, "args": args, "state": state, "head": head},
                view=True,
            )
            self.publish(refs.prop_ref(prop.prop_id, state), cut.outputs.image)
            self.publish(
                f"production/validation/props/{prop.prop_id}-{state}.json", cut.outputs.validation
            )
            summers[(prop.prop_id, state)] = cut.outputs.image
            self.review("props", f"{prop.prop_id} {state}", cut.outputs.image)
            if state == prop.baseline_state:
                baseline = (cut.outputs.image, cut.outputs.validation)
        if baseline is None:
            raise ValueError(f"{prop.prop_id}'s sheet has no baseline look")
        return baseline

    def seasons(self, wf: Workflow, summers: dict[tuple[str, str], Any]) -> None:
        """Each season look a paintover of its summer sprite, from the props scope up."""

        package = self.package
        if self.rank < 1 or package.seasons is None:
            return
        group = wf.group("seasons", title="Season looks")
        for season_look in package.seasons.looks:
            look_group = group.group(_name(season_look.look_id), title=season_look.look_id)
            for prop in package.props:
                for state in prop.states:
                    summer = summers.get((prop.prop_id, state))
                    if summer is None:
                        continue
                    args = {**_canvas(SPRITE_CANVAS), "max_components": prop.max_components}
                    state_group = look_group.group(
                        _name(f"{prop.prop_id}_{state}"), title=f"{prop.prop_id} {state}"
                    )
                    painting = self.paint(
                        state_group,
                        title=f"Repaint {prop.prop_id} {state} in its {season_look.look_id} look",
                        prompt=prompts.season_look_prompt(package, prop, state, season_look),
                        size=SPRITE_CANVAS,
                        transparent=True,
                        pictures=[summer, *self.style],
                        gate="look",
                        args=args,
                        reference=summer,
                    )
                    published = self.finish(
                        state_group,
                        painting.outputs.image,
                        finish="look",
                        gate="look",
                        args=args,
                        reference=summer,
                        head=_head(
                            "oblique-survival-season-look-validation-v1",
                            prop_id=prop.prop_id,
                            state=state,
                            look=season_look.look_id,
                            max_components=prop.max_components,
                        ),
                    )
                    self.publish(
                        refs.prop_look_ref(prop.prop_id, state, season_look.look_id),
                        published.outputs.image,
                    )
                    self.publish(
                        f"production/validation/props/{prop.prop_id}-{state}"
                        f".{season_look.look_id}.json",
                        published.outputs.validation,
                    )
                    self.review("seasons", f"{prop.prop_id} {state}", summer)
                    self.review(
                        "seasons",
                        f"{prop.prop_id} {state} {season_look.look_id}",
                        published.outputs.image,
                    )

    def items(self, wf: Workflow) -> None:
        package = self.package
        group = wf.group("items", title="Pickups")
        wanted: set[str] | None = None
        if self.rank < 1:
            # A minimal build draws what its props yield and what lies on the ground.
            wanted = set()
            if package.forage is not None:
                wanted.update(cell.item_id for cell in package.forage.cells)
            for prop in package.props:
                if prop.prop_id in MINIMAL_PROPS:
                    for interaction in prop.interactions:
                        wanted.update(produced.item_id for produced in interaction.yields)
        args = _canvas(SPRITE_CANVAS)
        for item in package.items:
            if wanted is not None and item.item_id not in wanted:
                continue
            item_group = group.group(_name(item.item_id), title=item.item_id)
            painting = self.paint(
                item_group,
                title=f"Draw the {item.item_id} pickup",
                prompt=prompts.item_prompt(package, item.item_id, item.prompt),
                size=SPRITE_CANVAS,
                transparent=True,
                pictures=self.style,
                gate="canvas",
                args=args,
            )
            published = self.finish(
                item_group,
                painting.outputs.image,
                finish="sprite",
                gate="canvas",
                args=args,
                head=_head("oblique-survival-item-validation-v1", item_id=item.item_id),
            )
            self.publish(refs.item_ref(item.item_id), published.outputs.image)
            self.publish(
                f"production/validation/items/{item.item_id}.json", published.outputs.validation
            )
        self.icons(wf, group)

    def pieces(
        self,
        wf: Workflow,
        group: Group,
        *,
        sheet: Any,
        cell_px: int,
        contacts: list[str] | None,
        coverage: tuple[float, float],
        prompt: str,
        head: dict[str, object],
        title: str,
    ) -> StepRef:
        """A lattice of pieces painted into its template, or adopted; cut at the guides."""

        template = self.template(wf, sheet.columns, sheet.rows, cell_px).outputs.image
        args = {
            "columns": sheet.columns,
            "rows": sheet.rows,
            "cell_px": cell_px,
            "contacts": contacts,
            "native_alpha": templates.LATTICE_TRANSPARENT,
            "coverage": list(coverage),
            "halo": False,
        }
        if sheet.take is not None:
            source = self.adopt(
                group, take=sheet.take, gate="pieces", args=args, reference=template
            ).outputs.image
        else:
            source = self.paint(
                group,
                title=title,
                prompt=prompt,
                size=(sheet.columns * cell_px, sheet.rows * cell_px),
                transparent=templates.LATTICE_TRANSPARENT,
                pictures=[template],
                gate="pieces",
                args=args,
                reference=template,
            ).outputs.image
        return self.finish(
            group,
            source,
            finish="pieces",
            gate="pieces",
            args=args,
            head=head,
            reference=template,
            title="Cut the cells at the guides",
        )

    def icons(self, wf: Workflow, group: Group) -> None:
        package = self.package
        icons = package.icons
        published = self.pieces(
            wf,
            group.group("icons", title="Inventory icons"),
            sheet=icons,
            cell_px=icons.cell_px,
            contacts=None,
            coverage=gates.ICON_CELL_COVERAGE,
            prompt=prompts.icon_sheet_prompt(package, icons, package.items),
            head={
                "kind": "oblique-survival-icons-validation-v1",
                "names": [item.item_id for item in package.items]
                + [glyph.glyph for glyph in icons.glyphs],
            },
            title=f"Paint {icons.cell_count} inventory icons into the lattice",
        )
        self.publish(refs.icons_ref(), published.outputs.image)
        self.publish("production/validation/items/icons.json", published.outputs.validation)
        self.review("props", "inventory icons", published.outputs.image)

    def ground(self, wf: Workflow) -> None:
        package = self.package
        group = wf.group("ground", title="Ground")
        for biome in package.biomes:
            args = {
                **_canvas(GROUND_CANVAS),
                "texel_meters": biome.texel_meters,
                **{
                    key: list(value) if isinstance(value, tuple) else value
                    for key, value in plate_gate_kwargs(biome).items()
                },
            }
            self.plate(
                group.group(_name(biome.biome_id), title=biome.biome_id),
                title=f"Draw the {biome.biome_id} ground plate",
                prompt=prompts.ground_prompt(package, biome),
                args=args,
                gate="ground",
                head=_head("oblique-survival-ground-validation-v1", biome_id=biome.biome_id),
                image_ref=refs.ground_ref(biome.biome_id),
                record_ref=f"production/validation/ground/{biome.biome_id}.json",
                take=biome.take,
                label=biome.biome_id,
            )
        if package.macro is not None:
            self.plate(
                group.group("macro", title="Macro colour field"),
                title="Draw the macro colour field",
                prompt=prompts.macro_prompt(package.macro),
                args=_canvas(GROUND_CANVAS),
                gate="macro",
                head=_head("oblique-survival-macro-validation-v1"),
                image_ref=refs.macro_ref(),
                record_ref="production/validation/ground/macro.json",
                pictures=[],
                label="macro colour field",
            )
        if package.road is not None:
            road = package.road
            self.plate(
                group.group("road", title=f"The {road.road_id} track"),
                title=f"Draw the {road.road_id} track plate",
                prompt=prompts.road_prompt(package, road),
                args={**_canvas(GROUND_CANVAS), "texel_meters": road.texel_meters},
                gate="ground",
                head=_head("oblique-survival-road-validation-v1", road_id=road.road_id),
                image_ref=refs.road_ref(road.road_id),
                record_ref=f"production/validation/ground/road-{road.road_id}.json",
                label=f"{road.road_id} track",
            )
        if package.water is not None:
            water = package.water
            self.plate(
                group.group("water", title="Water"),
                title="Draw the water plate beyond the coast",
                prompt=prompts.water_prompt(package, water),
                args={
                    **_canvas(GROUND_CANVAS),
                    "texel_meters": water.texel_meters,
                    "luma_range": list(gates.WATER_LUMA_RANGE),
                },
                gate="ground",
                head=_head("oblique-survival-water-validation-v1"),
                image_ref=refs.water_ref(),
                record_ref="production/validation/ground/water.json",
                label="water",
            )
        if package.forage is not None:
            forage = package.forage
            published = self.pieces(
                wf,
                group.group("forage", title="Forage"),
                sheet=forage,
                cell_px=templates.LATTICE_CELL_PX,
                contacts=[cell.contact for cell in forage.cells],
                coverage=gates.PIECE_CELL_COVERAGE,
                prompt=prompts.forage_prompt(package, forage),
                head={
                    "kind": "oblique-survival-forage-validation-v1",
                    "cell_meters": forage.cell_meters,
                    "items": [cell.item_id for cell in forage.cells],
                },
                title=f"Paint {forage.cell_count} forage pickups into the lattice",
            )
            self.publish(refs.forage_ref(), published.outputs.image)
            self.publish("production/validation/ground/forage.json", published.outputs.validation)
            self.review("ground", "forage sheet", published.outputs.image)
        decal_args: dict[str, Any] = dict(_canvas(SPRITE_CANVAS))
        for decal in package.decals:
            decal_group = group.group(_name(f"decal_{decal.decal_id}"), title=decal.decal_id)
            painting = self.paint(
                decal_group,
                title=f"Draw the {decal.decal_id} ground decal",
                prompt=prompts.decal_prompt(package, decal),
                size=SPRITE_CANVAS,
                transparent=True,
                pictures=self.style,
                gate="decal",
                args=decal_args,
            )
            published = self.finish(
                decal_group,
                painting.outputs.image,
                finish="decal",
                gate="decal",
                args=decal_args,
                head=_head("oblique-survival-decal-validation-v1", decal_id=decal.decal_id),
            )
            self.publish(refs.decal_ref(decal.decal_id), published.outputs.image)
            self.publish(
                f"production/validation/ground/decal-{decal.decal_id}.json",
                published.outputs.validation,
            )
            self.review("ground", decal.decal_id, published.outputs.image)

    def actors(self, wf: Workflow) -> None:
        package = self.package
        if self.rank < 2:
            return
        group = wf.group("actors", title="Actors")
        for actor in package.actors:
            actor_group = group.group(_name(actor.actor_id), title=actor.display_name)
            appearance = (
                [self.path(actor.appearance_reference)] if actor.appearance_reference else []
            )
            concept = self.paint(
                actor_group.group("concept", title="Appearance sheet"),
                title=f"Draw {actor.display_name}'s appearance sheet",
                prompt=prompts.actor_concept_prompt(package, actor),
                size=SPRITE_CANVAS,
                transparent=True,
                pictures=[*appearance, *self.style],
                gate="canvas",
                args=_canvas(SPRITE_CANVAS),
            )
            self.publish(refs.concept_ref(actor.actor_id), concept.outputs.image)
            strips: dict[str, Any] = {}
            fronts: dict[str, Any] = {}
            # The front strip first, off the concept alone; the other facings off the front
            # as well, so they match it pose for pose.
            ordered = sorted(actor.strips, key=lambda entry: (entry[0], entry[1] != "front"))
            for state_name, facing in ordered:
                motion = actor.state(state_name)
                key = strip_key(motion.state, facing)
                label = motion.state if facing is None else f"{motion.state} {facing}"
                args = {**_canvas(STRIP_CANVAS), "columns": MOTION_COLUMNS, "state": motion.state}
                strip_group = actor_group.group(
                    _name(f"strip_{key.replace('.', '_')}"), title=label
                )
                pictures = [concept.outputs.image]
                if facing not in (None, "front"):
                    pictures.append(fronts[motion.state])
                painting = self.paint(
                    strip_group,
                    title=f"Draw {actor.actor_id}'s {label} strip",
                    prompt=prompts.actor_motion_prompt(package, actor, motion.state, facing=facing),
                    size=STRIP_CANVAS,
                    transparent=True,
                    pictures=pictures,
                    gate="motion",
                    args=args,
                )
                published = self.finish(
                    strip_group,
                    painting.outputs.image,
                    finish="motion",
                    gate="motion",
                    args=args,
                    head=_head(
                        "oblique-survival-motion-validation-v1",
                        actor_id=actor.actor_id,
                        facing_set=actor.facings.set,
                        source_facing=facing if facing is not None else package.facing_authored,
                        runtime_horizontal_mirroring=facing is None,
                    ),
                    title="Repack it onto canonical cells",
                )
                self.publish(
                    refs.state_ref(actor.actor_id, motion.state, facing), published.outputs.image
                )
                self.publish(
                    f"production/validation/actors/{actor.actor_id}-{key}.json",
                    published.outputs.validation,
                )
                if facing == "front":
                    fronts[motion.state] = published.outputs.image
                strips[key] = published.outputs.image
                # Every facing on the sheet, labelled as the reviewer is told.
                self.review("actors", f"{actor.actor_id} {label}", published.outputs.image)
            if len(strips) > 1:
                rebase = add_rebase_steps(
                    actor_group.group("rebase", title="Rebase every strip to one scale"),
                    nodes=ACTORS,
                    display_name=actor.display_name,
                    # Sorted, as the reading has always listed them.
                    states=sorted(strips),
                    baseline_state=actor.baseline_key,
                    geometry={key: (MOTION_COLUMNS, 1) for key in strips},
                    atlases=strips,
                )
                record = actor_group.step(
                    "rebase_record",
                    title="Publish the rebase record",
                    uses=f"{ACTORS}#publish_rebase",
                    with_={
                        "record": rebase["record"].outputs.record,
                        "actor_id": actor.actor_id,
                        "baseline_state": actor.baseline_key,
                    },
                )
                self.publish(refs.rebase_ref(actor.actor_id), record.outputs.rebase)

    def fx(self, wf: Workflow) -> None:
        package = self.package
        if self.rank < 3:
            return
        group = wf.group("fx", title="Effects")
        fire = package.fire
        cell = templates.LATTICE_CELL_PX
        template = self.template(wf, fire.columns, fire.rows, cell).outputs.image
        fire_args = {
            "columns": fire.columns,
            "rows": fire.rows,
            "cell_px": cell,
            "native_alpha": templates.LATTICE_TRANSPARENT,
        }
        fire_group = group.group("fire", title="Fire")
        painting = self.paint(
            fire_group,
            title=f"Paint a {fire.frames}-frame flame cycle into the lattice",
            prompt=prompts.fire_strip_prompt(package, fire.columns, fire.rows),
            size=(fire.columns * cell, fire.rows * cell),
            transparent=templates.LATTICE_TRANSPARENT,
            pictures=[template],
            gate="fire",
            args=fire_args,
            reference=template,
        )
        published = self.finish(
            fire_group,
            painting.outputs.image,
            finish="fire",
            gate="fire",
            args=fire_args,
            head={},
            reference=template,
            title="Cut the cells and measure the cycle",
        )
        self.publish(refs.fire_ref(), published.outputs.image)
        self.publish("production/validation/fx-fire.json", published.outputs.validation)
        self.review("fx", "fire strip", published.outputs.image)
        dust_group = group.group("dust", title="Dust")
        painting = self.paint(
            dust_group,
            title="Draw the four impact puffs on one sheet",
            prompt=prompts.dust_prompt(package),
            size=SPRITE_CANVAS,
            transparent=True,
            pictures=self.style,
            gate="dust",
            args={},
        )
        published = self.finish(
            dust_group,
            painting.outputs.image,
            finish="dust",
            gate="dust",
            args={"canvas": list(SPRITE_CANVAS), "kinds": list(package.dust.kinds)},
            head=_head("oblique-survival-fx-dust-validation-v1"),
        )
        self.publish(refs.dust_ref(), published.outputs.image)
        self.publish("production/validation/fx-dust.json", published.outputs.validation)
        self.review("fx", "dust sheet", published.outputs.image)

    def audio(
        self,
        group: Group,
        *,
        gate: str,
        args: dict[str, Any],
        take: str | None,
        generate: dict[str, Any],
        head: dict[str, object],
        audio_ref: str,
        record_ref: str,
    ) -> None:
        """A track or clip composed and judged, or adopted by ear; published unchanged."""

        if take is not None:
            with_: dict[str, Any] = {
                "gate": gate,
                "args": args,
                "path": take,
                "sha256": self.package.digests[take],
            }
            if self.present(take):
                with_["take"] = self.path(take)
            source = group.step(
                "adopt", title="Adopt the auditioned take", uses=f"{AUDIO}#adopt_audio", with_=with_
            ).outputs.audio
        else:
            drawn = group.step("generate", title="Compose it", view=True, **generate)
            group.step(
                "admit",
                title="Long and loud enough",
                uses=f"{AUDIO}#admit_audio",
                judges="generate",
                with_={"audio": drawn.outputs.audio, "gate": gate, "args": args},
                on_reject=_REDRAW,
            )
            source = drawn.outputs.audio
        published = group.step(
            "publish",
            title="Record its length and peak",
            uses=f"{AUDIO}#publish_audio",
            with_={"source": source, "gate": gate, "args": args, "head": head},
        )
        self.publish(audio_ref, published.outputs.audio)
        self.publish(record_ref, published.outputs.validation)

    def music(self, wf: Workflow) -> None:
        package = self.package
        if self.rank < 3 or not package.music:
            return
        group = wf.group("music", title="Music")
        for track in package.music:
            self.audio(
                group.group(_name(track.track_id), title=f"The {track.cue} loop"),
                gate="music",
                args={},
                take=track.take,
                generate={
                    "uses": "gnode/music.generate@1",
                    "with_": {"prompt": prompts.music_prompt(track)},
                },
                head=_head(
                    "oblique-survival-music-validation-v1",
                    track_id=track.track_id,
                    cue=track.cue,
                    loop=True,
                    target_duration_seconds=track.target_duration_seconds,
                ),
                audio_ref=refs.music_ref(track.track_id),
                record_ref=f"production/validation/music-{track.track_id}.json",
            )

    def sounds(self, wf: Workflow) -> None:
        package = self.package
        if self.rank < 3 or not package.sounds:
            return
        group = wf.group("sounds", title="Sound effects")
        for clip in package.sounds:
            self.audio(
                group.group(_name(clip.cue), title=clip.cue),
                gate="sound",
                args={"duration_seconds": clip.duration_seconds},
                take=clip.take,
                generate={
                    "uses": "gnode/sound.generate@1",
                    "with_": {
                        "prompt": clip.prompt,
                        "duration": clip.duration_seconds,
                        "loop": clip.loop,
                    },
                },
                head=_head("oblique-survival-sound-validation-v1", cue=clip.cue, loop=clip.loop),
                audio_ref=refs.sound_ref(clip.cue),
                record_ref=f"production/validation/sound-{clip.cue}.json",
            )

    def weather(self, wf: Workflow) -> None:
        package = self.package
        if self.rank < 3:
            return
        group = wf.group("weather", title="Weather")
        for condition in package.weather:
            cid = condition.condition_id
            condition_group = group.group(_name(cid), title=cid)
            # Each quadrant sheet: its layer, its review label, its brief, its cells, its
            # coverage band and any extra gate arguments.
            sheets: list[
                tuple[str, str, str, list[str], tuple[float, float], dict[str, float]]
            ] = []
            if condition.drops is not None:
                sheets.append(
                    (
                        "drops",
                        "drops sheet",
                        prompts.drops_sheet_prompt(package, condition.drops),
                        list(condition.drops.kinds),
                        gates.DROPS_CELL_COVERAGE,
                        {},
                    )
                )
            if condition.cover is not None:
                cover = condition.cover
                self.plate(
                    condition_group.group("cover", title="Cover plate"),
                    title=f"Draw the {cid} cover plate",
                    prompt=prompts.cover_prompt(package, cover),
                    args={
                        **_canvas(GROUND_CANVAS),
                        "texel_meters": cover.texel_meters,
                        "luma_range": list(gates.COVER_LUMA_RANGE),
                    },
                    gate="ground",
                    head=_head("oblique-survival-weather-cover-validation-v1", condition_id=cid),
                    image_ref=refs.weather_ref(cid, "cover"),
                    record_ref=f"production/validation/weather-{cid}-cover.json",
                    label=f"{cid} cover plate",
                )
            if condition.ice is not None:
                ice = condition.ice
                self.plate(
                    condition_group.group("ice", title="Ice plate"),
                    title=f"Draw the {cid} ice plate",
                    prompt=prompts.ice_prompt(package, ice),
                    args={
                        **_canvas(GROUND_CANVAS),
                        "texel_meters": ice.texel_meters,
                        "luma_range": list(gates.COVER_LUMA_RANGE),
                    },
                    gate="ground",
                    head=_head("oblique-survival-weather-ice-validation-v1", condition_id=cid),
                    image_ref=refs.weather_ref(cid, "ice"),
                    record_ref=f"production/validation/weather-{cid}-ice.json",
                    take=ice.take,
                    label=f"{cid} ice plate",
                )
            if condition.ground is not None:
                sheets.append(
                    (
                        "ground",
                        "splash sheet",
                        prompts.splash_sheet_prompt(package, condition.ground),
                        list(condition.ground.kinds),
                        gates.SPLASH_CELL_COVERAGE,
                        {},
                    )
                )
            if condition.strike is not None:
                sheets.append(
                    (
                        "strike",
                        "bolt sheet",
                        prompts.strike_sheet_prompt(package, condition.strike),
                        list(STRIKE_CELL_KINDS),
                        gates.STRIKE_CELL_COVERAGE,
                        {
                            "tallness_min": gates.STRIKE_TALLNESS_MIN,
                            "span_min": gates.STRIKE_SPAN_MIN,
                        },
                    )
                )
            for layer, label, prompt, kinds, coverage, extra in sheets:
                args = {
                    **_canvas(SPRITE_CANVAS),
                    "kinds": kinds,
                    "coverage_range": list(coverage),
                    **extra,
                }
                layer_group = condition_group.group(layer, title=f"The {layer} sheet")
                painting = self.paint(
                    layer_group,
                    title=f"Draw the {cid} {layer} sheet",
                    prompt=prompt,
                    size=SPRITE_CANVAS,
                    transparent=True,
                    # The drops carry only the ink line: a reference picture of a clearing
                    # would put a clearing on the sheet.
                    pictures=[] if layer == "drops" else self.style,
                    gate="quadrant",
                    args=args,
                )
                published = self.finish(
                    layer_group,
                    painting.outputs.image,
                    finish="quadrant",
                    gate="quadrant",
                    args=args,
                    head=_head(f"oblique-survival-weather-{layer}-validation-v1", condition_id=cid),
                )
                self.publish(refs.weather_ref(cid, layer), published.outputs.image)
                self.publish(
                    f"production/validation/weather-{cid}-{layer}.json",
                    published.outputs.validation,
                )
                self.review("fx", f"{cid} {label}", published.outputs.image)
            for name, cue in condition.sound_cues:
                self.audio(
                    condition_group.group(_name(f"sound_{name}"), title=f"The {name} clip"),
                    gate="sound",
                    args={"duration_seconds": cue.duration_seconds},
                    take=None,
                    generate={
                        "uses": "gnode/sound.generate@1",
                        "with_": {
                            "prompt": cue.prompt,
                            "duration": cue.duration_seconds,
                            "loop": cue.loop,
                        },
                    },
                    head=_head(
                        "oblique-survival-weather-sound-validation-v1",
                        condition_id=cid,
                        cue=name,
                        loop=cue.loop,
                    ),
                    audio_ref=refs.weather_ref(cid, f"sound-{name}", "mp3"),
                    record_ref=f"production/validation/weather-{cid}-sound-{name}.json",
                )

    def reviews(self, wf: Workflow) -> None:
        package = self.package
        group = wf.group("reviews", title="Reviews")
        for family in REVIEW_FAMILIES:
            subjects = self.reviewed[family]
            if self.rank < _REVIEW_FROM[family] or not subjects:
                continue
            review_group = group.group(f"{family}_set", title=f"The {family} review")
            labels = [label for label, _picture in subjects]
            sheet = review_group.step(
                "sheet",
                title=f"Lay out every {family} asset on one labelled sheet",
                uses=f"{REVIEWS}#review_sheet",
                with_={"pictures": [picture for _label, picture in subjects], "labels": labels},
            )
            schema = review_group.step(
                "schema", title="The review's shape", uses=f"{REVIEWS}#review_schema"
            )
            answer = review_group.step(
                "judge",
                title=f"Judge the {family} set",
                uses="gnode/structured.generate@1",
                with_={
                    "prompt": prompts.family_review_prompt(family, labels, package.ground_contact),
                    "system": REVIEW_SYSTEM,
                    "schema": schema.outputs.schema,
                    "context": [sheet.outputs.sheet],
                    "max_tokens": REVIEW_MAX_TOKENS,
                },
                view=True,
            )
            review_group.step(
                "admit",
                title="Consistent with itself",
                uses=f"{REVIEWS}#admit_review",
                judges="judge",
                with_={"review": answer.outputs.json},
                on_reject=_REDRAW,
            )
            record = review_group.step(
                "record",
                title="Record the review",
                uses=f"{REVIEWS}#review_record",
                with_={"review": answer.outputs.json},
            )
            self.publish(refs.review_ref(family), record.outputs.review)

    def interface(self, wf: Workflow) -> None:
        """The HUD's frames, from the props scope up, in the package's own style."""

        package = self.package
        if package.ui is None or self.rank < _RANK["props"]:
            return
        group = wf.group("interface", title="Interface")
        for role in document_roles(package.ui):
            steps = add_ui_sheet_steps(
                group.group(_name(role.role), title=f"The {role.role} sheet"),
                nodes=INTERFACE,
                ui=package.ui,
                role=role,
                style_prompt=lambda task: prompts.ui_atlas_prompt(package, task),
                reference_path=self.path,
            )
            self.publish(f"ui/{role.role}.png", steps["publish"].outputs.image)
            self.publish(f"ui/{role.role}.validation.json", steps["publish"].outputs.validation)

    def shell(self, wf: Workflow) -> None:
        """The opening, the title and the loading screen, from the props scope up."""

        package = self.package
        shell = package.shell
        if shell is None or self.rank < _RANK["props"]:
            return
        group = wf.group("shell", title="Opening, title and loading")
        sources = {entry.reference_id: entry.source for entry in shell.references}
        published_plates: dict[str, Any] = {}
        for role in document_plate_roles(shell):
            _raw, image_ref, validation_ref, evidence_ref, verdict_ref = shell_artifact_refs(role)
            role_group = group.group(_name(role.role), title=f"The {role.role} plate")
            plate = {
                "layout": role.layout.layout,
                "alpha_policy": role.alpha_policy,
                "measured_regions": list(role.measured_regions),
            }
            references = [self.path(sources[ref]) for ref in role.plate.reference_ids]
            transparent = role.alpha_policy == CUTOUT_ALPHA_POLICY
            with_: dict[str, Any] = {
                "prompt": prompts.shell_plate_prompt(package, plate_content_task(role)),
                "size": f"{role.layout.canvas[0]}x{role.layout.canvas[1]}",
                "background": "transparent" if transparent else "opaque",
            }
            if references:
                with_ |= {"image": references[0], "references": references[1:]}
            painting = role_group.step(
                "generate",
                title=f"Draw the {role.screen} screen's {role.role} plate",
                uses="gnode/image.edit@1" if references else "gnode/image.generate@1",
                with_=with_,
                requires=["transparent_background"] if transparent else [],
                view=True,
            )
            role_group.step(
                "admit",
                title="Hold it to its layout",
                uses=f"{SHELL}#admit_shell_plate",
                judges="generate",
                with_={"image": painting.outputs.image, **plate},
                on_reject=_REDRAW,
            )
            published = role_group.step(
                "publish",
                title="Clamp it and outline its regions",
                uses=f"{SHELL}#publish_shell_plate",
                with_={
                    "raw": painting.outputs.image,
                    "role": role.role,
                    "screen": role.screen,
                    **plate,
                },
                view=True,
            )
            published_plates[role.role] = published.outputs.image
            self.publish(image_ref, published.outputs.image)
            self.publish(validation_ref, published.outputs.validation)
            self.publish(evidence_ref, published.outputs.evidence)
            verdict = self.shell_review(
                role_group,
                record=published.outputs.validation,
                pictures=[published.outputs.evidence, *references],
                role=role.role,
                screen=role.screen,
                brief=role.plate.prompt,
                seconds=0.0,
                clip=False,
            )
            self.publish(verdict_ref, verdict)
        for clip_role in document_clip_roles(shell):
            _raw, validation_ref, clip_ref, contact_ref, published_ref = shell_clip_artifact_refs(
                clip_role
            )
            role_group = group.group(_name(clip_role.role), title=f"The {clip_role.shot_id} shot")
            clip = {"layout": clip_role.layout.layout, "seconds": clip_role.seconds}
            references = [self.path(sources[ref]) for ref in clip_role.clip.reference_ids]
            take = clip_role.clip.take
            if take is not None:
                adopt: dict[str, Any] = {**clip, "path": take.path, "sha256": take.sha256}
                if self.present(take.path):
                    adopt["take"] = self.path(take.path)
                source = role_group.step(
                    "adopt",
                    title="Adopt the auditioned shot",
                    uses=f"{SHELL}#adopt_clip",
                    with_=adopt,
                ).outputs.clip
            else:
                if not references:
                    raise ValueError(f"the {clip_role.shot_id} shot is filmed from no reference")
                filmed = role_group.step(
                    "generate",
                    title=f"Film the opening's {clip_role.shot_id} shot",
                    uses="gnode/video.generate@1",
                    with_={
                        "prompt": prompts.shell_plate_prompt(package, clip_content_task(clip_role)),
                        "first_frame": references[0],
                        "duration": clip_role.seconds,
                        "resolution": clip_resolution(clip_role.layout),
                        "aspect_ratio": "16:9",
                    },
                    view=True,
                )
                role_group.step(
                    "admit",
                    title="As long and as large as asked, and moving",
                    uses=f"{SHELL}#admit_clip",
                    judges="generate",
                    with_={"clip": filmed.outputs.video, **clip},
                    on_reject=_REDRAW,
                )
                source = filmed.outputs.video
            record = role_group.step(
                "record",
                title="Record the admission",
                uses=f"{SHELL}#clip_record",
                with_={
                    "clip": source,
                    "role": clip_role.role,
                    "shot_id": clip_role.shot_id,
                    **clip,
                },
            )
            published = role_group.step(
                "publish",
                title="Publish it in the codec the host plays",
                uses=f"{SHELL}#publish_clip",
                with_={"clip": source, "role": clip_role.role, **clip},
                view=True,
            )
            self.publish(validation_ref, record.outputs.validation)
            self.publish(clip_ref, published.outputs.clip)
            self.publish(contact_ref, published.outputs.contact)
            self.publish(published_ref, published.outputs.published)
            verdict = self.shell_review(
                role_group,
                record=record.outputs.validation,
                pictures=[published.outputs.contact, *references],
                role=clip_role.role,
                screen="opening",
                brief=clip_role.clip.prompt,
                seconds=clip_role.seconds,
                clip=True,
            )
            self.publish(f"shell/{clip_role.role}.clip.review.json", verdict)
            if clip_role.ends_the_opening:
                ending = group.step(
                    "opening_ending",
                    title="Measure the last frame against the title",
                    uses=f"{SHELL}#measure_ending",
                    with_={
                        "clip": published.outputs.clip,
                        "backdrop": published_plates["title_backdrop_far"],
                    },
                )
                self.publish("shell/opening.ending.json", ending.outputs.ending)
        if shell.typeface is not None:
            face = group.step(
                "typeface",
                title=f"Publish the {shell.typeface.family} face",
                uses=f"{SHELL}#publish_typeface",
                with_={
                    "face": self.path(shell.typeface.source),
                    "sha256": shell.typeface.source_sha256,
                },
            )
            self.publish(shell_typeface_ref(shell), face.outputs.typeface)

    def shell_review(
        self,
        group: Group,
        *,
        record: Any,
        pictures: list[Any],
        role: str,
        screen: str,
        brief: str,
        seconds: float,
        clip: bool,
    ) -> Any:
        schema = group.step(
            "review_schema",
            title="The review's shape",
            uses=f"{SHELL}#shell_review_schema",
            with_={"clip": clip},
        )
        asked = group.step(
            "review_brief",
            title="What the reviewer is asked",
            uses=f"{SHELL}#shell_review_brief",
            with_={
                "record": record,
                "role": role,
                "screen": screen,
                "brief": brief,
                "seconds": seconds,
                "clip": clip,
            },
        )
        answer = group.step(
            "review",
            title=f"Review the {role} {'shot' if clip else 'plate'}",
            uses="gnode/structured.generate@1",
            with_={
                "prompt": str(asked.outputs.brief.prompt),
                "system": REVIEW_SYSTEM,
                "schema": schema.outputs.schema,
                "context": pictures,
                "max_tokens": 1800,
            },
            view=True,
        )
        group.step(
            "review_admit",
            title="In the shape asked for",
            uses=f"{SHELL}#admit_shell_review",
            judges="review",
            with_={"review": answer.outputs.json},
            on_reject=_REDRAW,
        )
        return group.step(
            "review_record",
            title="Record the review",
            uses=f"{SHELL}#shell_review_record",
            with_={"review": answer.outputs.json},
        ).outputs.verdict

    def world(self, wf: Workflow) -> None:
        layout = wf.step(
            "world",
            title="Lay the world from its seed",
            uses=f"{WORLD}#world_layout",
            with_={"package": self.package_files()},
            view=True,
        )
        self.publish(refs.layout_ref(), layout.outputs.layout)
        self.publish(refs.splat_ref(), layout.outputs.splat)
        self.publish(refs.biome_splat_ref(), layout.outputs.biome_splat)

    def package_files(self) -> dict[str, str]:
        """Every authored file but the takes: what the reader reads the package from."""

        takes = set(take_paths(self.package))
        return {
            source: self.path(source)
            for source in sorted(self.package.digests)
            if source not in takes and self.present(source)
        }


def take_paths(package: Package) -> list[str]:
    """Every auditioned take the package declares: bound by digest, kept out of git."""

    found = [biome.take for biome in package.biomes if biome.take is not None]
    if package.forage is not None and package.forage.take is not None:
        found.append(package.forage.take)
    if package.icons.take is not None:
        found.append(package.icons.take)
    found.extend(track.take for track in package.music if track.take is not None)
    found.extend(clip.take for clip in package.sounds if clip.take is not None)
    found.extend(
        condition.ice.take
        for condition in package.weather
        if condition.ice is not None and condition.ice.take is not None
    )
    if package.shell is not None:
        found.extend(
            role.clip.take.path
            for role in document_clip_roles(package.shell)
            if role.clip.take is not None
        )
    return found


def build(package: str, scope: str = "full") -> Workflow:
    """Every asset the package declares at one rung of the scope ladder, judged and laid out."""

    if scope not in SCOPES:
        raise ValueError(f"unknown scope {scope!r}; the ladder is {', '.join(SCOPES)}")
    root = Path(package).resolve()
    resolved = load_package(root)
    built = _Build(resolved, root, scope)
    wf = Workflow(
        "ember-hollow",
        title=f"{resolved.title}: {scope}",
        description="Every asset Ember Hollow's package declares, laid out for the Godot host.",
        budget={"max_usd": BUDGET_USD},
    )
    built.props(wf)
    built.items(wf)
    built.ground(wf)
    built.actors(wf)
    built.fx(wf)
    built.music(wf)
    built.weather(wf)
    built.sounds(wf)
    built.reviews(wf)
    built.interface(wf)
    built.shell(wf)
    built.world(wf)
    package_step = wf.step(
        "package",
        title="Lay out the runtime folder",
        uses=f"{WORLD}#package_manifest",
        with_={
            "package": built.package_files(),
            "published": dict(sorted(built.published.items())),
            "scope": scope,
        },
        view=True,
    )
    wf.outputs(package=package_step.outputs.files)
    return wf


__all__ = ["BUDGET_USD", "MINIMAL_PROPS", "TAKES", "build", "take_paths"]
