"""Execute the content-only closure of an exact-current prepared game package."""

from __future__ import annotations

import hashlib
import io
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, cast

from PIL import Image, ImageDraw, ImageFont, ImageOps

from gnode import (
    BinaryArtifact,
    ImageGenerationRequest,
    ImageGenerationService,
    ImageReference,
    InputProvenance,
    MusicGenerationService,
    Node,
    NodeExecutionResult,
    NodeType,
    ProvenanceInput,
    SoftwareIdentity,
    StructuredGenerationRequest,
    StructuredGenerationService,
    StructuredOutputSchema,
    StructuredReference,
    atomic_write_json,
    dependency_port,
    write_artifact_with_provenance_async,
)
from stage_gen.components.game_soundtrack.nodes import SoundtrackHandlers, SoundtrackHost
from stage_gen.components.game_ui import (
    AtlasRole,
    UiReference,
)
from stage_gen.components.game_ui.inventory_nodes import (
    InventoryPanelHandlers,
    InventoryPanelHost,
    validate_inventory_panel_image,
)
from stage_gen.components.game_ui.nodes import (
    UI_ATLAS_GENERATE,
    UI_ATLAS_REVIEW,
    UI_ATLAS_VALIDATE,
    UiAtlasHandlers,
    UiAtlasHost,
    document_roles,
    validate_ui_sheet,
)
from stage_gen.components.platformer_content import (
    ContentReference,
    ItemContent,
    MobContent,
    MotionPresentation,
    NpcContent,
    PlayerContent,
    ProjectileContent,
    PropContent,
    projectile_silhouette_art,
)
from stage_gen.components.sideview_actor.motion_geometry import (
    MOTION_ATLAS_HEIGHT,
    MOTION_ATLAS_WIDTH,
    MotionAtlasGeometry,
    dialogue_atlas_grid,
    runtime_mirrors_source,
)
from stage_gen.components.sideview_actor.motion_rebase import (
    BASELINE_STATE,
)
from stage_gen.components.sideview_actor.motion_rebase_nodes import (
    MotionRebaseHandlers,
    MotionRebaseHost,
    RebaseSubject,
)
from stage_gen.media import (
    AlphaComponentRepackContract,
    data_url,
    measure_alpha_ground_contact,
    repack_alpha_components,
)
from stage_gen.media.sprite_sheets import measure_alpha_subjects
from stage_gen.orchestration.game_package import ResolvedGamePackage
from stage_gen.recipes.node_handler import NodeMethod, RecipeNodeHandler
from stage_gen.recipes.sideview_platformer.execution_graph import ExecutionGraph, OperationKind
from stage_gen.recipes.sideview_platformer.motion_contract import (
    MotionActorKind,
    motion_atlas_geometry,
    motion_semantic_direction,
    motion_source_facing,
)
from stage_gen.recipes.sideview_platformer.package_graph import (
    CACHE_RECORD_KIND,
    CONTENT_CACHE_NAMESPACE,
    visual_prompt,
)
from stage_gen.recipes.sideview_platformer.package_types import (
    ACTOR_CONCEPT_GENERATE,
    ACTOR_CONTACT_SHEET,
    ACTOR_REVIEW,
    CATALOG_ASSET_GENERATE,
    CATALOG_ASSET_VALIDATE,
    CATALOG_CONTACT_SHEET,
    CATALOG_REVIEW,
    DIALOGUE_ATLAS_GENERATE,
    DIALOGUE_ATLAS_VALIDATE,
    GAMEPLAY_BINDINGS_VALIDATE,
    MOTION_ATLAS_GENERATE,
    MOTION_ATLAS_VALIDATE,
    MOTION_REBASE_JUDGE,
    MOTION_REBASE_VERIFY,
    PACKAGE_RESOLVE,
    SOUNDTRACK_GENERATE,
    SOUNDTRACK_VALIDATE,
    UI_INVENTORY_GENERATE,
    UI_INVENTORY_REVIEW,
    UI_INVENTORY_VALIDATE,
    WORLD_SPRITE_GENERATE,
    WORLD_SPRITE_VALIDATE,
)
from stage_gen.recipes.sideview_platformer.weapon_silhouettes import player_equipment_art
from stage_gen.resources import inventory_template_path

CONTENT_HANDLER_VERSION = "prepared-content-v4"

#: The three catalog families the packaged catalog pipeline draws. A family is a node parameter,
#: not a node identity: props, items, and projectiles run the same generate-validate-board-review
#: shape, and the projectile residue below is a branch inside it rather than a copy of it.
CatalogFamily = Literal["prop", "item", "projectile"]
CatalogEntry = PropContent | ItemContent | ProjectileContent
ActorContent = PlayerContent | MobContent | NpcContent


class PreparedContentNodeHandler(RecipeNodeHandler):
    """Dispatch content nodes while shared components retain provider/retry ownership."""

    def __init__(
        self,
        graph: ExecutionGraph,
        package: ResolvedGamePackage,
        *,
        run_dir: Path,
        cache_dir: Path,
        image_service: ImageGenerationService,
        structured_service: StructuredGenerationService[object],
        music_service: MusicGenerationService,
    ) -> None:
        self._package = package
        self._images = image_service
        self._structured = structured_service
        self._music = music_service
        ui_host = UiAtlasHost(
            ui=package.ui,
            run_dir=run_dir,
            package_id=package.game.game_id,
            file=package.file,
            component=SoftwareIdentity(
                name="@stage-gen/sideview-platformer", version=CONTENT_HANDLER_VERSION
            ),
            tool=SoftwareIdentity(name="stage-gen", version="0.0.0"),
        )
        self._atlas = UiAtlasHandlers(
            ui_host,
            graph=graph,
            image_service=image_service,
            structured_service=structured_service,
        )
        self._inventory = InventoryPanelHandlers(
            InventoryPanelHost(
                ui=ui_host,
                frame_prompt=self._visual_prompt,
                template_path=inventory_template_path(),
            ),
            graph=graph,
            image_service=image_service,
            structured_service=structured_service,
        )
        self._rebase = MotionRebaseHandlers(
            MotionRebaseHost(
                run_dir=run_dir,
                subject=self._rebase_subject,
                component=SoftwareIdentity(
                    name="@stage-gen/sideview-platformer", version=CONTENT_HANDLER_VERSION
                ),
                handler_version=CONTENT_HANDLER_VERSION,
                plate_model="prepared-content-motion-rebase-plate-v1",
                metadata={"checkpoint": "content"},
            ),
            graph=graph,
            structured_service=structured_service,
        )
        self._soundtrack = SoundtrackHandlers(
            SoundtrackHost(run_dir=run_dir, track=package.soundtrack.track),
            graph=graph,
            music_service=music_service,
        )
        super().__init__(
            graph,
            run_dir=run_dir,
            cache_dir=cache_dir,
            namespace=CONTENT_CACHE_NAMESPACE,
            record_kind=CACHE_RECORD_KIND,
            admit=lambda node, payloads: (
                bool(payloads) and self._cached_primary_artifact_valid(node, payloads[0])
            ),
        )

    def _motion_source_facing(
        self, kind: MotionActorKind, state: str
    ) -> Literal["right", "back", "front"]:
        return motion_source_facing(
            kind,
            state,
            npc_world_orientation=(self._package.npcs.world_orientation if kind == "npc" else None),
        )

    # ---------------------------------------------------------------- dispatch

    def _handlers(self) -> tuple[tuple[NodeType, NodeMethod], ...]:
        """Registered types replace the seven id regexes this handler once walked."""

        return (
            (PACKAGE_RESOLVE, self._resolve_package),
            (GAMEPLAY_BINDINGS_VALIDATE, self._write_bindings),
            (ACTOR_CONCEPT_GENERATE, self._generate_concept),
            (MOTION_ATLAS_GENERATE, self._generate_motion),
            (MOTION_ATLAS_VALIDATE, self._validate_motion),
            (DIALOGUE_ATLAS_GENERATE, self._generate_dialogue),
            (DIALOGUE_ATLAS_VALIDATE, self._validate_dialogue),
            (WORLD_SPRITE_GENERATE, self._generate_world_sprite),
            (WORLD_SPRITE_VALIDATE, self._validate_world_sprite),
            (MOTION_REBASE_JUDGE, self._rebase.judge),
            (MOTION_REBASE_VERIFY, self._rebase.verify),
            (ACTOR_CONTACT_SHEET, self._actor_contact_sheet),
            (ACTOR_REVIEW, self._actor_review),
            (CATALOG_ASSET_GENERATE, self._generate_catalog_asset),
            (CATALOG_ASSET_VALIDATE, self._validate_catalog_asset),
            (CATALOG_CONTACT_SHEET, self._catalog_contact_sheet),
            (CATALOG_REVIEW, self._catalog_review),
            (SOUNDTRACK_GENERATE, self._soundtrack.generate),
            (SOUNDTRACK_VALIDATE, self._soundtrack.validate),
            (UI_INVENTORY_GENERATE, self._inventory.generate),
            (UI_INVENTORY_VALIDATE, self._inventory.validate),
            (UI_INVENTORY_REVIEW, self._inventory.review),
            (UI_ATLAS_GENERATE, self._atlas.generate),
            (UI_ATLAS_VALIDATE, self._atlas.validate),
            (UI_ATLAS_REVIEW, self._atlas.review),
        )

    # ------------------------------------------------------------- node params

    def _actor_kind(self, node: Node) -> MotionActorKind:
        """The actor family this node instance is bound to."""

        kind = node.params.get("actor_kind")
        if kind not in {"player", "mob", "npc"}:
            raise ValueError(f"node {node.node_id} declares no known actor kind")
        return cast(MotionActorKind, kind)

    def _actor(self, node: Node) -> ActorContent:
        """The authored actor this node instance is bound to."""

        kind = self._actor_kind(node)
        entity_id = node.params["actor_id"]
        if kind == "player":
            return self._player(entity_id)
        if kind == "mob":
            return self._mob(entity_id)
        return self._npc(entity_id)

    def _actor_references(self, kind: MotionActorKind) -> Sequence[ContentReference]:
        if kind == "player":
            return self._package.player.references
        if kind == "mob":
            return self._package.mobs.references
        return self._package.npcs.references

    def _dialogue_expressions(self, node: Node) -> Sequence[str]:
        """The declared expression list for whichever actor kind carries one."""

        entry = self._actor(node)
        if isinstance(entry, PlayerContent):
            return entry.dialogue_art.expressions
        if isinstance(entry, NpcContent):
            return entry.dialogue_expressions
        raise ValueError(f"node {node.node_id} declares an actor with no dialogue expressions")

    def _family(self, node: Node) -> CatalogFamily:
        """The catalog family this node instance is bound to."""

        family = node.params.get("family")
        if family not in {"prop", "item", "projectile"}:
            raise ValueError(f"node {node.node_id} declares no known catalog family")
        return cast(CatalogFamily, family)

    def _catalog_entries(self, family: CatalogFamily) -> tuple[tuple[str, CatalogEntry], ...]:
        """Every stable ID in one family, in authored order."""

        if family == "prop":
            return tuple((entry.prop_id, entry) for entry in self._package.props.props)
        if family == "item":
            return tuple((entry.item_id, entry) for entry in self._package.items.items)
        catalog = self._package.projectiles
        if catalog is None:
            raise ValueError("this package declares no projectile catalog")
        return tuple((entry.projectile_id, entry) for entry in catalog.projectiles)

    def _catalog_entry(self, family: CatalogFamily, entity_id: str) -> CatalogEntry:
        return next(
            entry for declared, entry in self._catalog_entries(family) if declared == entity_id
        )

    def _catalog_references(self, family: CatalogFamily) -> Sequence[ContentReference]:
        if family == "prop":
            return self._package.props.references
        if family == "item":
            return self._package.items.references
        catalog = self._package.projectiles
        if catalog is None:
            raise ValueError("this package declares no projectile catalog")
        return catalog.references

    # --------------------------------------------------------------- lineage

    def _dependency_artifact(self, node: Node, *, kind: str, port_id: str | None = None) -> str:
        """Resolve one typed input to the artifact ref its producer declared."""

        _producer, port = dependency_port(self._graph, node, kind=kind, port_id=port_id)
        return port.artifact_ref

    def _published_port(self, type_id: str, params: Mapping[str, str], port_id: str) -> str:
        """One artifact a sibling node publishes, located by type rather than by path.

        Some inputs are not the node's own dependencies - the contact sheet shows a
        concept it does not depend on, and the rebase verification reads atlases only
        its first pass depended on. Those are still declared ports on declared types,
        so they are looked up as such instead of by rebuilding a path convention.
        """

        for candidate in self._graph.nodes:
            if candidate.type_id != type_id:
                continue
            if all(candidate.params.get(key) == value for key, value in params.items()):
                return candidate.port(port_id).artifact_ref
        raise ValueError(f"no {type_id} node declares {dict(params)}")

    def _published_state_atlases(self, node: Node, states: Sequence[str]) -> dict[str, str]:
        """The validated atlas ref for each of this actor's declared states."""

        actor = {"actor_kind": node.params["actor_kind"], "actor_id": node.params["actor_id"]}
        return {
            state: self._published_port(
                MOTION_ATLAS_VALIDATE.type_id, {**actor, "state": state}, "image"
            )
            for state in states
        }

    def _rebase_player(self, node: Node) -> PlayerContent:
        """Only a player is rebased; the graph says so and this refuses anything else."""

        entry = self._actor(node)
        if not isinstance(entry, PlayerContent):
            raise ValueError(f"node {node.node_id} rebases an actor that is not a player")
        return entry

    # ------------------------------------------------------------------ nodes

    async def _resolve_package(self, node: Node) -> NodeExecutionResult:
        atomic_write_json(
            self._run_dir / node.port("identity").artifact_ref, self._package.identity()
        )
        return self._result(node, provider_operations=0)

    async def _generate_concept(self, node: Node) -> NodeExecutionResult:
        kind = self._actor_kind(node)
        entry = self._actor(node)
        entity_id = _entity_id(entry)
        output = self._run_dir / node.port("image").artifact_ref
        references = self._image_references(self._actor_references(kind), entry.reference_ids)
        prompt = self._visual_prompt(
            f"{_equipment_directive(entry)}"
            f"Create the canonical identity concept for the {kind} {entity_id}.\n"
            f"Authored direction: {entry.prompt}\n"
            "Show one complete side-view game-scale figure and one front-three-quarter identity "
            "view, with identical costume, colors, proportions, and equipment. Keep the complete "
            "figures separated, fully visible, and isolated on a truly transparent background. "
            "No frame, floor, scenery, text, labels, symbols, or shadow plate. This image is the "
            "strict identity source for all later motion and dialogue atlases."
        )
        result = await self._images.generate(
            ImageGenerationRequest(
                prompt=prompt,
                artifact_path=output,
                input_references=references,
                quality="high",
                background="transparent",
                output_format="png",
                size="1024x1536",
                timeout_seconds=600,
                metadata={"checkpoint": "content", "kind": kind, "entity_id": entity_id},
                validate=lambda artifact: _validate_transparent_image(
                    artifact.data, width=1024, height=1536
                ),
            )
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _generate_motion(self, node: Node) -> NodeExecutionResult:
        return await self._generate_motion_atlas(node, node.params["state"])

    async def _generate_world_sprite(self, node: Node) -> NodeExecutionResult:
        """An NPC's single world strip is its idle motion under another name."""

        return await self._generate_motion_atlas(node, "idle")

    async def _generate_motion_atlas(self, node: Node, state: str) -> NodeExecutionResult:
        kind = self._actor_kind(node)
        entry = self._actor(node)
        entity_id = _entity_id(entry)
        output = self._run_dir / node.port("image").artifact_ref
        concept_ref = self._dependency_artifact(node, kind="actor-concept-v1")
        concept_data = (self._run_dir / concept_ref).read_bytes()
        references = (
            ImageReference(
                url=data_url(concept_data, "image/png"),
                provenance_ref=f"run://{concept_ref}#sha256={_sha(concept_data)}",
            ),
        )
        source_facing = self._motion_source_facing(kind, state)
        if source_facing == "back":
            facing_directive = "Every figure is shown from behind, facing away from the camera."
        elif source_facing == "front":
            facing_directive = (
                "Every figure directly faces the camera in a strict symmetrical front view: "
                "both eyes, shoulders, hands, and feet remain front-facing in every cell."
            )
        else:
            facing_directive = (
                "Every figure is a strict side view facing RIGHT: eyes, face, chest, and toes "
                "point toward the right edge."
            )
        motion_directive = motion_semantic_direction(kind, state)
        geometry = motion_atlas_geometry(kind, state)
        prompt = self._visual_prompt(
            f"{_equipment_directive(entry)}"
            f"Create the canonical side-view motion atlas for {kind} {entity_id}, state {state}. "
            "Use the supplied identity concept exactly. Output a strict single-row strip of "
            f"{geometry.frame_word} "
            f"sequential frames. {facing_directive} Preserve identity, apparent height, foot "
            "baseline, silhouette, "
            "costume, equipment, and camera scale in every cell. The required motion is: "
            f"{motion_directive}. Keep every figure wholly inside its cell on true alpha. "
            "Leave transparent separation between cells. No grid lines, boxes, captions, scenery, "
            "ground, cast shadows, text, or symbols."
        )
        result = await self._images.generate(
            ImageGenerationRequest(
                prompt=prompt,
                artifact_path=output,
                input_references=references,
                quality="high",
                background="transparent",
                output_format="png",
                size=geometry.provider_size,
                timeout_seconds=600,
                metadata={
                    "checkpoint": "content",
                    "kind": kind,
                    "entity_id": entity_id,
                    "state": state,
                    "atlas_columns": geometry.columns,
                    "atlas_rows": geometry.rows,
                    "source_facing": source_facing,
                },
                validate=lambda artifact: _validate_atlas(
                    artifact.data,
                    columns=geometry.columns,
                    rows=geometry.rows,
                    required_cells=geometry.required_cells,
                    width=geometry.width,
                    height=geometry.height,
                ),
            )
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _generate_dialogue(self, node: Node) -> NodeExecutionResult:
        kind = self._actor_kind(node)
        entity_id = node.params["actor_id"]
        expressions = self._dialogue_expressions(node)
        output = self._run_dir / node.port("image").artifact_ref
        concept_ref = self._dependency_artifact(node, kind="actor-concept-v1")
        concept_data = (self._run_dir / concept_ref).read_bytes()
        columns, rows = dialogue_atlas_grid(len(expressions))
        expression_text = ", ".join(
            f"cell {index + 1}: {expression}" for index, expression in enumerate(expressions)
        )
        prompt = self._visual_prompt(
            f"Create a front-three-quarter dialogue portrait atlas for {kind} {entity_id} using "
            "the "
            f"supplied identity concept exactly. Output a strict {columns}-column by {rows}-row "
            f"row-major atlas. Required cells in order: {expression_text}. Preserve head shape, "
            "hair, eyes, costume, palette, and apparent crop across every portrait; change only "
            "the "
            "authored facial expression and restrained supporting pose. Keep each bust centered in "
            "its cell on true alpha. Unused cells must remain transparent. No grid lines, boxes, "
            "labels, text, speech balloons, scenery, or symbols."
        )
        result = await self._images.generate(
            ImageGenerationRequest(
                prompt=prompt,
                artifact_path=output,
                input_references=(
                    ImageReference(
                        url=data_url(concept_data, "image/png"),
                        provenance_ref=f"run://{concept_ref}#sha256={_sha(concept_data)}",
                    ),
                ),
                quality="high",
                background="transparent",
                output_format="png",
                size="1536x1024",
                timeout_seconds=600,
                metadata={
                    "checkpoint": "content",
                    "kind": kind,
                    "entity_id": entity_id,
                    "expressions": list(expressions),
                    "atlas_columns": columns,
                    "atlas_rows": rows,
                },
                validate=lambda artifact: _validate_atlas(
                    artifact.data,
                    columns=columns,
                    rows=rows,
                    required_cells=len(expressions),
                ),
            )
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _generate_catalog_asset(self, node: Node) -> NodeExecutionResult:
        """One catalog subject, drawn by the family's own directive.

        A projectile is the residue this branch exists for: it leads with the axis its
        silhouette must read as, names that shape in the sentence that asks for it, and
        forbids the trail or spark a moving object attracts, because the consumer measures
        the painted bounding box. Props and items ask the plain isolated-asset question.
        """

        family = self._family(node)
        entity_id = node.params["entity_id"]
        entry = self._catalog_entry(family, entity_id)
        output = self._run_dir / node.port("image").artifact_ref
        projectile = isinstance(entry, ProjectileContent)
        if isinstance(entry, ProjectileContent):
            art = projectile_silhouette_art(entry.silhouette)
            prompt = self._visual_prompt(
                f"{art.axis_directive}\n"
                f"Generate exactly one canonical projectile asset, stable ID "
                f"{entity_id}: {art.shape_clause}.\n"
                f"Authored direction: {entry.prompt}\n"
                "Draw exactly ONE connected object and nothing else. No motion trail, speed line, "
                "spark, glow streak, impact burst, smoke, or detached fragment: the runtime "
                "supplies motion, and anything painted beside the object is measured as part of "
                "it. Center the complete object with comfortable transparent padding on every "
                "side. Output true alpha with no floor, scenery, shadow plate, frame, text, "
                "label, symbol, or second object."
            )
        else:
            prompt = self._visual_prompt(
                f"Generate exactly one canonical {family} asset, stable ID {entity_id}.\n"
                f"Authored direction: {entry.prompt}\n"
                "Use a fixed side-view game-asset camera. Center the complete object with "
                "comfortable transparent padding. Preserve a clear gameplay silhouette and the "
                "authored scale cues. Output true alpha with no floor, scenery, shadow plate, "
                "frame, text, label, symbol, or second object."
            )
        result = await self._images.generate(
            ImageGenerationRequest(
                prompt=prompt,
                artifact_path=output,
                input_references=self._image_references(
                    self._catalog_references(family), entry.reference_ids
                ),
                quality="high",
                background="transparent",
                output_format="png",
                size="1024x1024",
                timeout_seconds=600,
                metadata={"checkpoint": "content", "kind": family, "entity_id": entity_id},
                validate=(
                    (lambda artifact: _validate_projectile_image(artifact.data))
                    if projectile
                    else (
                        lambda artifact: _validate_transparent_image(
                            artifact.data, width=1024, height=1024
                        )
                    )
                ),
            )
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _validate_motion(self, node: Node) -> NodeExecutionResult:
        return await self._validate_motion_atlas(node, node.params["state"])

    async def _validate_world_sprite(self, node: Node) -> NodeExecutionResult:
        """The NPC world strip is admitted as the idle motion it is."""

        return await self._validate_motion_atlas(node, "idle")

    async def _validate_motion_atlas(self, node: Node, state: str) -> NodeExecutionResult:
        kind = self._actor_kind(node)
        entry = self._actor(node)
        entity_id = _entity_id(entry)
        source_ref_path = self._dependency_artifact(node, kind="motion-source-v1")
        source = self._run_dir / source_ref_path
        source_facing = self._motion_source_facing(kind, state)
        source_data = source.read_bytes()
        geometry = motion_atlas_geometry(kind, state)
        anchor = _motion_presentation(entry, state).anchor
        source_facts = _validate_atlas(
            source_data,
            columns=geometry.columns,
            rows=geometry.rows,
            required_cells=geometry.required_cells,
            width=geometry.width,
            height=geometry.height,
        )
        canonical_data, repack = repack_alpha_components(
            source_data,
            AlphaComponentRepackContract(
                rows=geometry.rows,
                columns=geometry.columns,
                required_cells=geometry.required_cells,
                anchor=anchor,
            ),
        )
        canonical = self._run_dir / node.port("image").artifact_ref
        source_ref = f"run://{source_ref_path}#sha256={_sha(source_data)}"
        await _write_local_image(
            canonical,
            canonical_data,
            prompt=(
                f"Repack the {kind} {entity_id} {state} source atlas using native-alpha "
                "connected components."
            ),
            inputs=((source_ref, source_data),),
            validation=repack,
        )
        validation = self._run_dir / node.port("validation").artifact_ref
        atomic_write_json(
            validation,
            {
                "schema_version": 1,
                "kind": "prepared-motion-atlas-validation-v3",
                "entity_kind": kind,
                "entity_id": entity_id,
                "state": state,
                "columns": geometry.columns,
                "rows": geometry.rows,
                "source_facing": source_facing,
                "frames": geometry.required_cells,
                "runtime_horizontal_mirroring": runtime_mirrors_source(source_facing),
                "source_validation": source_facts,
                "repack": repack,
            },
        )
        return self._result(node, provider_operations=0)

    async def _validate_dialogue(self, node: Node) -> NodeExecutionResult:
        kind = self._actor_kind(node)
        entity_id = node.params["actor_id"]
        expressions = self._dialogue_expressions(node)
        source_ref_path = self._dependency_artifact(node, kind="dialogue-source-v1")
        source = self._run_dir / source_ref_path
        columns, rows = dialogue_atlas_grid(len(expressions))
        source_data = source.read_bytes()
        source_facts = _validate_atlas(
            source_data, columns=columns, rows=rows, required_cells=len(expressions)
        )
        canonical_data, repack = repack_alpha_components(
            source_data,
            AlphaComponentRepackContract(
                rows=rows,
                columns=columns,
                required_cells=len(expressions),
                anchor="center",
            ),
        )
        canonical = self._run_dir / node.port("image").artifact_ref
        source_ref = f"run://{source_ref_path}#sha256={_sha(source_data)}"
        await _write_local_image(
            canonical,
            canonical_data,
            prompt=(
                f"Repack the {kind} {entity_id} dialogue atlas using native-alpha connected "
                "components."
            ),
            inputs=((source_ref, source_data),),
            validation=repack,
        )
        validation = self._run_dir / node.port("validation").artifact_ref
        atomic_write_json(
            validation,
            {
                "schema_version": 1,
                "kind": "prepared-dialogue-atlas-validation-v2",
                "entity_kind": kind,
                "entity_id": entity_id,
                "columns": columns,
                "rows": rows,
                "index_order": "row_major",
                "expressions": list(expressions),
                "source_validation": source_facts,
                "repack": repack,
            },
        )
        return self._result(node, provider_operations=0)

    async def _validate_catalog_asset(self, node: Node) -> NodeExecutionResult:
        """Admit one catalog subject, and a projectile against its stricter contract.

        The projectile record is not the isolated-asset record with a field added: it
        additionally proves a single connected subject and a canvas the subject actually
        fills, because the consumer scales and rotates the painted bounding box.
        """

        family = self._family(node)
        entity_id = node.params["entity_id"]
        entry = self._catalog_entry(family, entity_id)
        source_data = (
            self._run_dir / self._dependency_artifact(node, kind="catalog-sprite-v1")
        ).read_bytes()
        output = self._run_dir / node.port("validation").artifact_ref
        record: dict[str, object]
        if isinstance(entry, ProjectileContent):
            record = {
                "projectile_id": entity_id,
                "silhouette": entry.silhouette,
                **_validate_projectile_image(source_data),
            }
        else:
            facts = _validate_transparent_image(source_data, width=1024, height=1024)
            ground_contact = measure_alpha_ground_contact(source_data) if family == "prop" else None
            record = {
                "schema_version": 1,
                "kind": (
                    "prepared-isolated-prop-validation-v2"
                    if family == "prop"
                    else "prepared-isolated-asset-validation-v1"
                ),
                "asset_kind": family,
                "asset_id": entity_id,
                **facts,
                **({"ground_contact": ground_contact} if ground_contact is not None else {}),
            }
        atomic_write_json(output, record)
        return self._result(node, provider_operations=0)

    async def _actor_contact_sheet(self, node: Node) -> NodeExecutionResult:
        kind = self._actor_kind(node)
        entry = self._actor(node)
        entity_id = _entity_id(entry)
        actor = {"actor_kind": kind, "actor_id": entity_id}
        entries: list[tuple[str, Path]] = [
            (
                "concept",
                self._run_dir
                / self._published_port(ACTOR_CONCEPT_GENERATE.type_id, actor, "image"),
            )
        ]
        if kind in {"player", "mob"}:
            entries.extend(
                (
                    motion.state,
                    self._run_dir
                    / self._published_port(
                        MOTION_ATLAS_VALIDATE.type_id, {**actor, "state": motion.state}, "image"
                    ),
                )
                for motion in entry.motions
            )
        else:
            entries.append(
                (
                    "world",
                    self._run_dir
                    / self._published_port(WORLD_SPRITE_VALIDATE.type_id, actor, "image"),
                )
            )
        if kind in {"player", "npc"}:
            entries.append(
                (
                    "dialogue",
                    self._run_dir
                    / self._published_port(DIALOGUE_ATLAS_VALIDATE.type_id, actor, "image"),
                )
            )
        output = self._run_dir / node.port("sheet").artifact_ref
        data = _contact_sheet(entries, title=f"{kind}: {entity_id}")
        await _write_local_image(
            output,
            data,
            prompt=f"Assemble the complete labeled {kind} contact sheet for {entity_id}.",
            inputs=[
                (path.relative_to(self._run_dir).as_posix(), path.read_bytes())
                for _, path in entries
            ],
            validation={"entry_count": len(entries), "entity_kind": kind, "entity_id": entity_id},
        )
        return self._result(node, provider_operations=0)

    async def _catalog_contact_sheet(self, node: Node) -> NodeExecutionResult:
        family = self._family(node)
        entries = [
            (
                entity_id,
                self._run_dir
                / self._published_port(
                    CATALOG_ASSET_GENERATE.type_id,
                    {"family": family, "entity_id": entity_id},
                    "image",
                ),
            )
            for entity_id, _entry in self._catalog_entries(family)
        ]
        output = self._run_dir / node.port("sheet").artifact_ref
        data = _contact_sheet(entries, title=f"{family} catalog")
        await _write_local_image(
            output,
            data,
            prompt=f"Assemble the complete stable-ID {family} catalog contact sheet.",
            inputs=[
                (path.relative_to(self._run_dir).as_posix(), path.read_bytes())
                for _, path in entries
            ],
            validation={"entry_count": len(entries), "asset_kind": family},
        )
        return self._result(node, provider_operations=0)

    def _rebase_subject(self, node: Node) -> RebaseSubject:
        """The player this rebase node judges, with its atlases located by type."""

        player = self._rebase_player(node)
        states = tuple(motion.state for motion in player.motions)
        return RebaseSubject(
            label="player",
            entity_id=player.player_id,
            display_name=player.display_name,
            states=states,
            baseline_state=BASELINE_STATE,
            atlas_refs=self._published_state_atlases(node, states),
            geometry=lambda state: motion_atlas_geometry("player", state),
        )

    async def _actor_review(self, node: Node) -> NodeExecutionResult:
        kind = self._actor_kind(node)
        entry = self._actor(node)
        entity_id = _entity_id(entry)
        display_name = entry.display_name
        references = self._content_references(self._actor_references(kind), entry.reference_ids)
        contact = self._run_dir / self._dependency_artifact(node, kind="contact-sheet-v1")
        structured_refs = [self._run_structured_reference(contact)]
        states: Sequence[str]
        expressions: Sequence[str]
        motions: Sequence[MotionPresentation]
        # Only a player declares equipment. Empty for the other actor kinds rather than absent, so
        # the prompt below reads the same shape for all three.
        equipment_clause = ""
        if isinstance(entry, PlayerContent):
            authored_prompt = entry.prompt
            motions = entry.motions
            states = [motion.state for motion in motions]
            expressions = entry.dialogue_art.expressions
            equipment_clause = (
                "The character's declared equipment is "
                f"{entry.equipment}. Confirm that "
                f"{player_equipment_art(entry.equipment).review_clause}. "
            )
        elif isinstance(entry, MobContent):
            authored_prompt = entry.prompt
            motions = entry.motions
            states = [motion.state for motion in motions]
            expressions = []
        else:
            authored_prompt = entry.prompt
            motions = entry.motions
            states = [motion.state for motion in motions]
            expressions = entry.dialogue_expressions
        structured_refs.extend(self._package_structured_reference(ref) for ref in references)
        source_facings = {state: self._motion_source_facing(kind, state) for state in states}
        motion_semantics = {state: motion_semantic_direction(kind, state) for state in states}
        playback = {motion.state: motion.model_dump(mode="json") for motion in motions}
        runtime_scale_context = ""
        if kind == "player":
            runtime_scale_context = (
                "The contact sheet shows canonical source-atlas pixels, not final runtime world "
                "scale. The prepared consumer deterministically head-matches every non-crouch "
                "state to the idle character scale and registers it from the bottom/feet, so "
                "different raw atlas crop heights do not imply runtime size or baseline popping. "
                "Crouch is the intentional exception: it preserves canonical atlas scale and a "
                "bottom/feet anchor so the bent, stationary pose remains visibly lower than "
                "standing. Judge cross-state runtime scale under that declared adapter; still "
                "reject inconsistent scale or registration within one four-frame atlas. "
            )
        return await self._run_review(
            node,
            prompt=(
                f"Review the complete generated {kind} content for {display_name} ({entity_id}). "
                f"Authored identity direction: {authored_prompt} "
                f"The complete declared state list is exactly {list(states)}. "
                f"The complete declared dialogue-expression list is exactly {list(expressions)}. "
                f"The exact required visual meaning for each motion is {motion_semantics}. "
                f"The exact authored runtime playback projection is {playback}. For hold playback, "
                "judge motion semantics only on the selected canonical frame; unused generated "
                "candidate cells still require stable identity, facing, scale, registration, and "
                "alpha, but their gestures are not runtime motion coverage and must not cause a "
                "rejection. "
                "Every motion atlas is one row of four frames. The exact required source facing "
                f"for each state is {source_facings}. Ordinary right-facing side-view sources are "
                "mirrored deterministically by the runtime for left-facing play; rear-facing and "
                "front-facing sources are not mirrored. For hold playback, generation still "
                "provides the complete four-cell atlas while runtime presentation selects only "
                "the declared canonical frame. Image 1 is the locally labeled "
                "contact sheet; remaining images are authored identity/style references. The "
                "contact sheet was locally alpha-composited from decoded RGBA sources onto "
                f"checkerboards. {runtime_scale_context}"
                "Deterministic decoding already proved true alpha (minimum alpha 0, visible alpha "
                "greater than 0), zero-alpha canvas borders, and nonempty occupancy in every "
                "required atlas cell. Hidden RGB stored behind fully transparent pixels is not "
                "visible game content. Judge alpha isolation from the checkerboard composition "
                "and these deterministic facts; do not reject it because checkerboard is shown. "
                "Do not require states or expressions outside the exact declared lists. Judge "
                "identity fidelity against both the authored text and applicable image references, "
                "style continuity, complete state coverage, "
                "the declared source-facing consistency for motion, stable scale and registration, "
                "native-alpha "
                f"isolation, and declared dialogue-expression coverage where applicable. "
                f"{equipment_clause}A labeled "
                "state tile may itself contain a multi-cell atlas. Report concrete visible "
                "defects. "
                "Uncertainty must not be called accept."
            ),
            references=structured_refs,
            metadata={"checkpoint": "content", "kind": kind, "entity_id": entity_id},
        )

    async def _catalog_review(self, node: Node) -> NodeExecutionResult:
        """Judge one catalog family's board, and a projectile's axis where that applies.

        The projectile residue again: every authored direction carries the axis its
        silhouette must read as, and the judge is told why that matters - the consumer
        scales, mirrors and rotates the subject along it.
        """

        family = self._family(node)
        contact = self._run_dir / self._dependency_artifact(node, kind="contact-sheet-v1")
        references = [self._run_structured_reference(contact)]
        entries = self._catalog_entries(family)
        expected_ids = [entity_id for entity_id, _entry in entries]
        references.extend(
            self._package_structured_reference(ref) for ref in self._catalog_references(family)
        )
        if family == "projectile":
            authored_directions: list[dict[str, object]] = [
                {
                    "asset_id": entity_id,
                    "prompt": entry.prompt,
                    "must_read_as": projectile_silhouette_art(entry.silhouette).review_clause,
                }
                for entity_id, entry in entries
                if isinstance(entry, ProjectileContent)
            ]
            prompt = (
                "Review the complete generated projectile catalog. The exact complete stable-ID "
                f"list is {expected_ids}. Authored directions are {authored_directions}, each "
                "carrying the drawn axis its silhouette requires. Image 1 is a locally labeled "
                "stable-ID contact sheet; remaining images are authored style references. The "
                "contact sheet was locally alpha-composited from decoded RGBA sources onto "
                "checkerboards. Deterministic decoding proved true alpha, zero-alpha canvas "
                "borders, visible subject pixels, and exactly one connected subject per source. "
                "Judge alpha isolation from the checkerboard composition and these deterministic "
                "facts, and do not claim the expected manifest is missing. Judge, for every "
                "entry: authored identity fidelity, style coherence, and above all whether the "
                "drawn subject matches its stated axis, because the consumer scales, mirrors and "
                "rotates these along that axis and a reversed or tilted subject flies backwards. "
                "Report concrete visible defects. Uncertainty must not be called accept."
            )
        else:
            authored_directions = [
                {"asset_id": entity_id, "prompt": entry.prompt} for entity_id, entry in entries
            ]
            prompt = (
                f"Review the complete generated {family} catalog. The exact complete stable-ID "
                f"list is {expected_ids}. Authored directions are {authored_directions}. Image 1 "
                "is a locally labeled stable-ID contact sheet; remaining images are authored "
                "style/scene references. The contact sheet was locally alpha-composited from "
                "decoded RGBA sources onto checkerboards. Deterministic decoding proved true "
                "alpha, zero-alpha canvas borders, and visible subject pixels for every source. "
                "Hidden RGB behind fully transparent pixels is not visible game content. Judge "
                "alpha isolation from the checkerboard composition and these deterministic facts, "
                "and do not claim the expected manifest is missing. Judge authored identity "
                "fidelity, style coherence, unique readable silhouettes, "
                "side-view gameplay framing, native-alpha isolation, scale consistency within the "
                "catalog, and complete catalog coverage. Report concrete visible defects. "
                "Uncertainty must not be called accept."
            )
        return await self._run_review(
            node,
            prompt=prompt,
            references=references,
            metadata={"checkpoint": "content", "kind": family},
        )

    async def _run_review(
        self,
        node: Node,
        *,
        prompt: str,
        references: Sequence[StructuredReference],
        metadata: Mapping[str, object],
    ) -> NodeExecutionResult:
        output = self._run_dir / node.port("verdict").artifact_ref
        result = await self._structured.generate(
            StructuredGenerationRequest(
                prompt=prompt,
                system=(
                    "You are a strict independent 2D game-art technical director. Return only the "
                    "requested structured review."
                ),
                artifact_path=output,
                schema=StructuredOutputSchema(
                    name="prepared_content_review", json_schema=_review_schema()
                ),
                parse=_parse_review,
                references=tuple(references),
                max_tokens=1800,
                timeout_seconds=600,
                metadata=metadata,
            )
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _write_bindings(self, node: Node) -> NodeExecutionResult:
        gameplay = self._package.gameplay
        speaker_expressions = []
        player = self._package.player.players[0]
        npc_by_id = {entry.npc_id: entry for entry in self._package.npcs.npcs}
        for scenario in self._package.scenarios:
            scenario_id = scenario.declarations.scenario_id
            for member in scenario.declarations.cast:
                expressions = (
                    player.dialogue_art.expressions
                    if member.actor_id == player.player_id
                    else npc_by_id[member.actor_id].dialogue_expressions
                )
                for expression in member.expressions:
                    if expression not in expressions:
                        raise ValueError(
                            f"scenario expression does not resolve: {scenario_id}/"
                            f"{member.actor_id}/{expression}"
                        )
                    speaker_expressions.append(
                        {
                            "scenario_id": scenario_id,
                            "speaker_id": member.actor_id,
                            "expression": expression,
                        }
                    )
        bindings = {
            "schema_version": 1,
            "kind": "prepared-gameplay-bindings-v1",
            "game_id": self._package.game.game_id,
            "package_sha256": self._package.package_sha256,
            "player_id": gameplay.player.player_id,
            "starting_item_ids": gameplay.player.starting_item_ids,
            "currency_item_id": gameplay.inventory.currency_item_id,
            "mob_spawn_ids": sorted(
                {
                    entry.mob_id
                    for map_entry in gameplay.mob_population.maps
                    for zone in map_entry.zones
                    for entry in zone.spawn_table
                }
            ),
            "boss_mob_ids": [entry.mob_id for entry in gameplay.boss_encounters],
            "loot": [entry.model_dump(mode="json") for entry in gameplay.loot_rules],
            "npc_placements": [entry.model_dump(mode="json") for entry in gameplay.npc_placements],
            "prop_placements": [
                entry.model_dump(mode="json") for entry in gameplay.prop_placements
            ],
            "interactions": [entry.model_dump(mode="json") for entry in gameplay.interactions],
            "scenario_speaker_expressions": speaker_expressions,
            "effect_ids": [entry.effect_id for entry in gameplay.effects],
            "track_ids": sorted(
                {track_id for map_use in gameplay.map_uses for track_id in map_use.track_ids}
            ),
            "map_topology": [
                {
                    "map_id": game_map.map_id,
                    # The authored request, not generated geometry: content direction needs the
                    # shape of the world, and taking it from the map keeps this stage
                    # independent of terrain generation.
                    "occupancy_rows": game_map.terrain.rows,
                    "occupancy_columns": game_map.terrain.columns,
                    "climbable_ids": (
                        []
                        if game_map.climbable is None
                        else [entry.variant_id for entry in game_map.climbable.variants]
                    ),
                    "climbable_variants": (
                        []
                        if game_map.climbable is None
                        else [entry.variant_id for entry in game_map.climbable.variants]
                    ),
                    "portal_anchors": (
                        []
                        if game_map.portal is None
                        else [entry.anchor for entry in game_map.portal.endpoints]
                    ),
                }
                for game_map in self._package.maps
            ],
            "all_references_resolved": True,
        }
        coverage = _coverage_matrix(self._package)
        atomic_write_json(self._run_dir / node.port("bindings").artifact_ref, bindings)
        atomic_write_json(self._run_dir / node.port("coverage").artifact_ref, coverage)
        return self._result(node, provider_operations=0)

    def _visual_prompt(self, specific: str) -> str:
        return visual_prompt(self._package, specific)

    def _image_references(
        self,
        catalog: Sequence[ContentReference | UiReference],
        reference_ids: Sequence[str],
    ) -> tuple[ImageReference, ...]:
        by_id = {entry.reference_id: entry for entry in catalog}
        values = []
        for reference_id in reference_ids:
            reference = by_id[reference_id]
            package_file = self._package.file(reference.source)
            values.append(
                ImageReference(
                    url=data_url(package_file.data, _media_type(reference.source)),
                    provenance_ref=(
                        f"package://{self._package.game.game_id}/{reference.source}"
                        f"#sha256={package_file.sha256}"
                    ),
                )
            )
        return tuple(values)

    def _content_references(
        self, catalog: Sequence[ContentReference], reference_ids: Sequence[str]
    ) -> tuple[ContentReference, ...]:
        selected = set(reference_ids)
        return tuple(entry for entry in catalog if entry.reference_id in selected)

    def _run_structured_reference(self, path: Path) -> StructuredReference:
        return StructuredReference(
            url=data_url(path.read_bytes(), "image/png"),
            provenance_ref=f"run://{path.relative_to(self._run_dir).as_posix()}",
        )

    def _package_structured_reference(
        self, reference: ContentReference | UiReference
    ) -> StructuredReference:
        package_file = self._package.file(reference.source)
        return StructuredReference(
            url=data_url(package_file.data, _media_type(reference.source)),
            provenance_ref=(
                f"package://{self._package.game.game_id}/{reference.source}"
                f"#sha256={package_file.sha256}"
            ),
        )

    def _player(self, entity_id: str) -> PlayerContent:
        return next(entry for entry in self._package.player.players if entry.player_id == entity_id)

    def _mob(self, entity_id: str) -> MobContent:
        return next(entry for entry in self._package.mobs.mobs if entry.mob_id == entity_id)

    def _npc(self, entity_id: str) -> NpcContent:
        return next(entry for entry in self._package.npcs.npcs if entry.npc_id == entity_id)

    def _cached_primary_artifact_valid(self, node: Node, data: bytes) -> bool:
        """Re-prove a restored image against the contract the node was asked for.

        Keyed on the node's declared type and parameters rather than on its id, which
        is what makes the geometry question answerable: a climb atlas is two cells on a
        2464x3328 canvas, and validating every cached strip against the 4x1 default
        rejected those forever, so a climb state could never be served from cache.
        """

        if node.operation != OperationKind.IMAGE_GENERATION:
            return True
        try:
            if node.type_id == MOTION_ATLAS_GENERATE.type_id:
                self._validate_cached_atlas(
                    data, motion_atlas_geometry(self._actor_kind(node), node.params["state"])
                )
            elif node.type_id == WORLD_SPRITE_GENERATE.type_id:
                self._validate_cached_atlas(data, motion_atlas_geometry("npc", "idle"))
            elif node.type_id == DIALOGUE_ATLAS_GENERATE.type_id:
                expressions = self._dialogue_expressions(node)
                columns, rows = dialogue_atlas_grid(len(expressions))
                _validate_atlas(data, columns=columns, rows=rows, required_cells=len(expressions))
            elif node.type_id == ACTOR_CONCEPT_GENERATE.type_id:
                _validate_transparent_image(data, width=1024, height=1536)
            elif node.type_id == CATALOG_ASSET_GENERATE.type_id:
                if self._family(node) == "projectile":
                    _validate_projectile_image(data)
                else:
                    _validate_transparent_image(data, width=1024, height=1024)
            elif node.type_id == UI_INVENTORY_GENERATE.type_id:
                validate_inventory_panel_image(data)
            elif node.type_id == UI_ATLAS_GENERATE.type_id:
                validate_ui_sheet(data, str(node.params["role"]))
            else:
                return False
        except (OSError, ValueError):
            return False
        return True

    @staticmethod
    def _validate_cached_atlas(data: bytes, geometry: MotionAtlasGeometry) -> None:
        _validate_atlas(
            data,
            columns=geometry.columns,
            rows=geometry.rows,
            required_cells=geometry.required_cells,
            width=geometry.width,
            height=geometry.height,
        )


#: The declared terminals of the content checkpoint. Naming types rather than rebuilding
#: node ids keeps two properties the id strings had to promise by hand: the motion-rebase
#: verification is a terminal in its own right, so naming it pulls the whole rebase chain
#: into the closure instead of leaving the record the manifest binds unproduced; and the
#: projectile review is here exactly when the package declared a projectile catalog,
#: because that is exactly when the graph carries the node.
CONTENT_TARGET_TYPE_IDS: frozenset[str] = frozenset(
    node_type.type_id
    for node_type in (
        ACTOR_REVIEW,
        MOTION_REBASE_VERIFY,
        CATALOG_REVIEW,
        SOUNDTRACK_VALIDATE,
        UI_INVENTORY_REVIEW,
        UI_ATLAS_REVIEW,
        GAMEPLAY_BINDINGS_VALIDATE,
    )
)


#: The reviews among the content terminals: evidence for an operator, run by the
#: `content-review` checkpoint, and not part of the default paid closure.
CONTENT_REVIEW_TYPE_IDS: frozenset[str] = frozenset(
    node_type.type_id
    for node_type in (ACTOR_REVIEW, CATALOG_REVIEW, UI_INVENTORY_REVIEW, UI_ATLAS_REVIEW)
)


def content_review_target_node_ids(graph: ExecutionGraph) -> tuple[str, ...]:
    """Every content review this plan carries, in graph order."""

    return tuple(node.node_id for node in graph.nodes if node.type_id in CONTENT_REVIEW_TYPE_IDS)


def content_target_node_ids(graph: ExecutionGraph) -> tuple[str, ...]:
    """Every content terminal this plan carries, with each review replaced by what it reads.

    See `world_target_node_ids`: a review is a paid structured operation whose verdict
    nothing downstream consumes, so the default closure stops at the review's own
    dependencies and `content-review` runs the reviews over a content the cache holds.
    """

    terminals: list[str] = []
    for node in graph.nodes:
        if node.type_id not in CONTENT_TARGET_TYPE_IDS:
            continue
        chosen = node.depends_on if node.type_id in CONTENT_REVIEW_TYPE_IDS else (node.node_id,)
        terminals.extend(node_id for node_id in chosen if node_id not in terminals)
    return tuple(terminals)


def soundtrack_target_node_ids(graph: ExecutionGraph) -> tuple[str, ...]:
    """The soundtrack's own terminals, and nothing else this plan carries.

    A track's cache identity is its own authored entry and the content contract, and it
    declares no cache dependency on the package root, so a rewritten creative brief re-bills
    exactly one track. The whole content checkpoint cannot honour that: it drags in every
    actor, catalog and interface terminal, and any of those whose contract has moved since
    the last accepted run regenerates as well -- replacing reviewed art to change a piece of
    music. Scoping the targets is what keeps the cost of an edit proportional to the edit.
    """

    return tuple(
        node.node_id for node in graph.nodes if node.type_id == SOUNDTRACK_VALIDATE.type_id
    )


def _coverage_matrix(package: ResolvedGamePackage) -> dict[str, object]:
    projectile_ids = (
        []
        if package.projectiles is None
        else [entry.projectile_id for entry in package.projectiles.projectiles]
    )
    return {
        "schema_version": 1,
        "kind": "prepared-content-coverage-matrix-v1",
        "game_id": package.game.game_id,
        "package_sha256": package.package_sha256,
        "players": [
            {
                "player_id": entry.player_id,
                "motions": [motion.model_dump(mode="json") for motion in entry.motions],
                "source_facings": {
                    motion.state: motion_source_facing("player", motion.state)
                    for motion in entry.motions
                },
                "dialogue_expressions": entry.dialogue_art.expressions,
            }
            for entry in package.player.players
        ],
        "mobs": [
            {
                "mob_id": entry.mob_id,
                "motions": [motion.model_dump(mode="json") for motion in entry.motions],
                "source_facings": {
                    motion.state: motion_source_facing("mob", motion.state)
                    for motion in entry.motions
                },
            }
            for entry in package.mobs.mobs
        ],
        "npcs": [
            {
                "npc_id": entry.npc_id,
                "motions": [motion.model_dump(mode="json") for motion in entry.motions],
                "source_facings": {
                    motion.state: motion_source_facing(
                        "npc",
                        motion.state,
                        npc_world_orientation=package.npcs.world_orientation,
                    )
                    for motion in entry.motions
                },
                "dialogue_expressions": entry.dialogue_expressions,
            }
            for entry in package.npcs.npcs
        ],
        "prop_ids": [entry.prop_id for entry in package.props.props],
        "item_ids": [entry.item_id for entry in package.items.items],
        "projectile_ids": projectile_ids,
        "track_ids": list(package.soundtrack.track_ids),
        "scenario_ids": [entry.declarations.scenario_id for entry in package.scenarios],
        # Content families only: map layers and their loop passes are the map recipe's fan-out and
        # are counted by the execution graph, not here. Every family the *content* recipe draws
        # contributes, and a family that contributes nothing to these two totals is a family whose
        # coverage nothing is checking - which is exactly how the projectile catalog was missed.
        "required_image_operations": (
            sum(2 + len(entry.motions) for entry in package.player.players)
            + sum(1 + len(entry.motions) for entry in package.mobs.mobs)
            + 3 * len(package.npcs.npcs)
            + len(package.props.props)
            + len(package.items.items)
            + len(projectile_ids)
            + 1
            + len(document_roles(package.ui))
        ),
        # One board-and-review pass per catalog family (props, items, inventory panel), one per
        # nine-slice atlas role, plus one per actor, plus one for the projectile catalog when the
        # package declares it.
        "required_structured_reviews": (
            len(package.player.players)
            + len(package.mobs.mobs)
            + len(package.npcs.npcs)
            + 3
            + len(document_roles(package.ui))
            + (1 if package.projectiles is not None else 0)
        ),
        "required_music_operations": len(package.soundtrack.tracks),
    }


def _equipment_directive(entry: PlayerContent | MobContent | NpcContent) -> str:
    """The leading equipment clause for a player, and nothing for any other actor.

    Only the player declares equipment: a mob or an NPC is drawn entirely from its authored prose,
    and neither has a `weapon_class` for a declaration to be checked against.
    """

    if not isinstance(entry, PlayerContent):
        return ""
    return f"{player_equipment_art(entry.equipment).carry_directive}\n"


def _entity_id(entry: PlayerContent | MobContent | NpcContent) -> str:
    if isinstance(entry, PlayerContent):
        return entry.player_id
    if isinstance(entry, MobContent):
        return entry.mob_id
    return entry.npc_id


def _motion_presentation(
    entry: PlayerContent | MobContent | NpcContent, state: str
) -> MotionPresentation:
    """Return the authored presentation for one of an entry's motion states."""

    for motion in entry.motions:
        if motion.state == state:
            return motion
    raise ValueError(f"{_entity_id(entry)} declares no motion state {state}")


def _validate_transparent_image(data: bytes, *, width: int, height: int) -> dict[str, object]:
    with Image.open(io.BytesIO(data)) as opened:
        image = opened.convert("RGBA")
    if image.size != (width, height):
        raise ValueError(f"provider image must be exactly {width}x{height}")
    alpha = image.getchannel("A")
    extrema = cast(tuple[int, int], alpha.getextrema())
    if extrema[0] != 0 or extrema[1] == 0:
        raise ValueError("content output must contain transparent and visible pixels")
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError("content output contains no visible subject")
    visible_fraction = sum(alpha.histogram()[1:]) / (width * height)
    if visible_fraction < 0.01:
        raise ValueError("content output subject is too small")
    border_values = [
        *alpha.crop((0, 0, width, 1)).get_flattened_data(),
        *alpha.crop((0, height - 1, width, height)).get_flattened_data(),
        *alpha.crop((0, 0, 1, height)).get_flattened_data(),
        *alpha.crop((width - 1, 0, width, height)).get_flattened_data(),
    ]
    border_alpha_max = max(border_values)
    border_alpha_mean = sum(border_values) / len(border_values)
    if border_alpha_max > 16 or border_alpha_mean > 0.5:
        raise ValueError("content output has visible alpha contamination at the canvas border")
    return {
        "width": width,
        "height": height,
        "alpha_min": extrema[0],
        "alpha_max": extrema[1],
        "visible_fraction": round(visible_fraction, 6),
        "visible_bbox": list(bbox),
        "border_alpha_max": border_alpha_max,
        "border_alpha_mean": round(border_alpha_mean, 6),
    }


#: How much of its own canvas a projectile's subject may fill.
#:
#: Tighter than the generic content floor for a reason the runtime supplies: the object is drawn on
#: a 1024px canvas and then redrawn a few dozen pixels wide, so a subject that spent most of its
#: canvas on padding arrives with almost no pixels left. Not an upper bound, because a subject that
#: fills its canvas is exactly what the trimmed loader wants.
_PROJECTILE_MINIMUM_VISIBLE_FRACTION = 0.02


def _validate_projectile_image(data: bytes) -> dict[str, object]:
    """Every isolation check an item gets, plus the one a moving object needs.

    A projectile is the only generated subject the consumer scales along a measured axis and may
    rotate. Both of those read the painted bounding box, so a detached spark, speed line or trail
    is not a cosmetic flaw here: it moves the box, and the object then draws at the wrong size
    around a pivot that is not inside it. Nothing else in the pipeline asks this question, and the
    generic isolation check passes an image holding an object and a streak.
    """

    report = _validate_transparent_image(data, width=1024, height=1024)
    subjects = measure_alpha_subjects(data)
    count = int(cast(int, subjects["subject_count"]))
    if count != 1:
        raise ValueError(f"projectile output must be exactly one connected subject, found {count}")
    visible_fraction = float(cast(float, report["visible_fraction"]))
    if visible_fraction < _PROJECTILE_MINIMUM_VISIBLE_FRACTION:
        raise ValueError(
            "projectile subject fills too little of its canvas to survive being drawn small"
        )
    return {
        **report,
        "subject_count": count,
        "subject_bbox": subjects["largest_bbox"],
        "subject_width": subjects["largest_width"],
        "subject_height": subjects["largest_height"],
    }


def _validate_atlas(
    data: bytes,
    *,
    columns: int,
    rows: int,
    required_cells: int,
    width: int = MOTION_ATLAS_WIDTH,
    height: int = MOTION_ATLAS_HEIGHT,
) -> dict[str, object]:
    facts = _validate_transparent_image(data, width=width, height=height)
    with Image.open(io.BytesIO(data)) as opened:
        alpha = opened.convert("RGBA").getchannel("A")
    cell_width = alpha.width / columns
    cell_height = alpha.height / rows
    coverage: list[float] = []
    for index in range(required_cells):
        row, column = divmod(index, columns)
        left = round(column * cell_width)
        top = round(row * cell_height)
        right = round((column + 1) * cell_width)
        bottom = round((row + 1) * cell_height)
        cell = alpha.crop((left, top, right, bottom))
        visible = sum(cell.histogram()[1:]) / (cell.width * cell.height)
        coverage.append(visible)
    if any(value < 0.005 for value in coverage):
        raise ValueError("content atlas is missing a required visible cell")
    return {
        **facts,
        "required_cells": required_cells,
        "cell_visible_fractions": [round(value, 6) for value in coverage],
        "all_required_cells_visible": True,
    }


_ATLAS_GEOMETRY_COMMON = (
    "Use the supplied layout template as the exact geometry authority. It is layout guidance, "
    "not the requested visual style: do not draw its magenta, yellow, or cyan. Magenta marks "
    "where the opaque body goes, the yellow outline is the body's outer edge, and the cyan lines "
    "divide each body into nine regions. Keep the canvas exterior transparent alpha 0 with no "
    "glow, drop shadow, colour wash, backdrop, or scenery; every body must be fully opaque. "
    "No text, numbers, labels, icons, items, characters, logo, signature, or watermark."
)

_ATLAS_NINE_SLICE_RULE = (
    "Nine-slice rule: the four corner regions may carry ornament. The four edge regions must "
    "each be one straight, uniform band that repeats identically along its whole length, with "
    "no motif, emblem, medallion, knot, notch, or break anywhere in the band. The centre region "
    "must be one flat, even, unornamented surface that text can sit on, with no vignette, "
    "gradient, hotspot, texture cluster, or pattern. Nothing crosses from a corner into an edge "
    "band except the continuous border itself."
)

_ATLAS_STATE_LOOKS = {
    "hover": "Hover is slightly brighter with a gentle highlight.",
    "pressed": "Pressed is darker with an inset, pushed-in look.",
    "disabled": "Disabled is desaturated and dimmer.",
}


def _atlas_prompt(role: AtlasRole, direction: str) -> str:
    """The content task for one atlas role, read off its geometry rather than its name."""

    width, height = role.canvas
    if len(role.cells) == 1:
        body = (
            "Create one nine-slice panel frame for the game's screen-fixed interface.\n"
            f"Authored direction: {direction}\n"
            f"One {width} by {height} canvas holding one rectangular panel body at the "
            "template's magenta rectangle. "
        )
    else:
        looks = " ".join(
            _ATLAS_STATE_LOOKS[state] for state in role.states if state in _ATLAS_STATE_LOOKS
        )
        body = (
            f"Create one {role.role.replace('_', ' ')} state sheet for the game's screen-fixed "
            "interface.\n"
            f"Authored direction: {direction}\n"
            f"One {width} by {height} canvas holding {len(role.cells)} identical rectangular "
            "bodies stacked top to bottom at the template's magenta rectangles, in this order: "
            f"{', '.join(role.states)}. All share exactly the same outer silhouette, size, "
            "corner shape, border and ornament; only lighting, value, and hue change between "
            f"states. {looks} Each body is itself a nine-slice. "
        )
    return f"{body}{_ATLAS_NINE_SLICE_RULE} {_ATLAS_GEOMETRY_COMMON}"


def _contact_sheet(entries: Sequence[tuple[str, Path]], *, title: str) -> bytes:
    columns = 3
    tile_width, tile_height = 512, 384
    title_height = 56
    rows = math.ceil(len(entries) / columns)
    canvas = Image.new(
        "RGB", (columns * tile_width, title_height + rows * tile_height), (28, 31, 39)
    )
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    draw.text((18, 18), title, fill=(245, 242, 232), font=font)
    for index, (label, path) in enumerate(entries):
        row, column = divmod(index, columns)
        left = column * tile_width
        top = title_height + row * tile_height
        draw.rectangle(
            (left + 8, top + 8, left + tile_width - 8, top + tile_height - 8),
            fill=(48, 52, 62),
            outline=(104, 111, 126),
        )
        with Image.open(path) as opened:
            image = opened.convert("RGBA")
        preview = ImageOps.contain(image, (tile_width - 32, tile_height - 56))
        checker = _checkerboard(preview.size)
        checker.alpha_composite(preview)
        x = left + (tile_width - checker.width) // 2
        y = top + 32 + (tile_height - 48 - checker.height) // 2
        canvas.paste(checker.convert("RGB"), (x, y))
        draw.text((left + 16, top + 14), label, fill=(255, 222, 141), font=font)
    stream = io.BytesIO()
    canvas.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def _checkerboard(size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGBA", size, (220, 220, 220, 255))
    draw = ImageDraw.Draw(image)
    block = 20
    for y in range(0, size[1], block):
        for x in range(0, size[0], block):
            if (x // block + y // block) % 2:
                draw.rectangle((x, y, x + block - 1, y + block - 1), fill=(174, 174, 174, 255))
    return image


async def _write_local_image(
    path: Path,
    data: bytes,
    *,
    prompt: str,
    inputs: Sequence[tuple[str, bytes]],
    validation: Mapping[str, object],
    model: str = "prepared-content-contact-sheet-v1",
) -> Path:
    return await write_artifact_with_provenance_async(
        path,
        BinaryArtifact(data=data, media_type="image/png"),
        ProvenanceInput(
            provider="local",
            model=model,
            prompt=prompt,
            refs=[ref for ref, _ in inputs],
            inputs=[
                InputProvenance(
                    ref=ref,
                    sha256=_sha(payload),
                    source="content",
                    bytes=len(payload),
                    media_type="image/png",
                )
                for ref, payload in inputs
            ],
            params={"version": CONTENT_HANDLER_VERSION},
            validation=dict(validation),
            component=SoftwareIdentity(
                name="@stage-gen/sideview-platformer", version=CONTENT_HANDLER_VERSION
            ),
            tool=SoftwareIdentity(name="stage-gen", version="0.0.0"),
            attempts=1,
        ),
    )


def _review_schema() -> dict[str, object]:
    checks = {
        key: {"type": "boolean"}
        for key in (
            "identity_fidelity",
            "style_coherence",
            "state_coverage",
            "facing_coverage",
            "registration_consistency",
            "alpha_isolation",
            "expression_coverage",
            "catalog_coverage",
        )
    }
    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["accept", "reject", "uncertain"]},
            "confidence": {"type": "number"},
            "checks": {"type": "object", "properties": checks},
            "issues": {"type": "array", "items": {"type": "string"}},
            "evidence": {"type": "string"},
        },
    }


def _parse_review(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("verdict") not in {
        "accept",
        "reject",
        "uncertain",
    }:
        raise ValueError("content review has an invalid verdict")
    return value


def _media_type(path: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }[Path(path).suffix.lower()]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


__all__ = [
    "PreparedContentNodeHandler",
    "content_review_target_node_ids",
    "content_target_node_ids",
]
