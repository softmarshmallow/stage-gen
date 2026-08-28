"""Execute the content-only closure of an exact-current prepared game package."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, cast

from PIL import Image, ImageDraw, ImageFont, ImageOps

from stage_gen.components import (
    ImageGenerationRequest,
    ImageGenerationService,
    MusicGenerationRequest,
    MusicGenerationService,
    StructuredGenerationRequest,
    StructuredGenerationService,
)
from stage_gen.components._types import BinaryArtifact
from stage_gen.components.game_content import (
    ContentReference,
    ItemContent,
    MobContent,
    MotionPresentation,
    NpcContent,
    PlayerContent,
    PropContent,
)
from stage_gen.components.game_sequence import DialogueNode
from stage_gen.components.game_ui import (
    INVENTORY_CANVAS_HEIGHT,
    INVENTORY_CANVAS_WIDTH,
    INVENTORY_PANEL_HEIGHT,
    INVENTORY_PANEL_LEFT,
    INVENTORY_PANEL_TOP,
    INVENTORY_PANEL_WIDTH,
    INVENTORY_SLOT_COLUMNS,
    INVENTORY_SLOT_GUTTER,
    INVENTORY_SLOT_LEFT,
    INVENTORY_SLOT_ROWS,
    INVENTORY_SLOT_SIZE,
    INVENTORY_SLOT_TOP,
    UiReference,
    inventory_panel_layout_contract,
)
from stage_gen.components.image_generation import ImageReference
from stage_gen.components.structured_generation import StructuredOutputSchema, StructuredReference
from stage_gen.contracts import InputProvenance, ProvenanceInput, SoftwareIdentity
from stage_gen.media import (
    AlphaComponentRepackContract,
    measure_alpha_ground_contact,
    probe_audio,
    repack_alpha_components,
)
from stage_gen.orchestration.execution_graph import (
    CacheDisposition,
    ExecutionGraph,
    ExecutionNode,
    NodeArtifact,
    NodeExecutionContext,
    NodeExecutionError,
    NodeExecutionResult,
    OperationKind,
)
from stage_gen.orchestration.game_package import ResolvedGamePackage
from stage_gen.recipes.scrolling_preview.motion_contract import (
    MOTION_ATLAS_COLUMNS,
    MOTION_ATLAS_REQUIRED_CELLS,
    MOTION_ATLAS_ROWS,
    MotionActorKind,
    dialogue_atlas_grid,
    motion_semantic_direction,
    motion_source_facing,
    runtime_mirrors_source,
)
from stage_gen.recipes.scrolling_preview.soundtrack import soundtrack_track_prompt
from stage_gen.reliability import (
    atomic_write_bytes,
    atomic_write_json,
    write_artifact_with_provenance_async,
)
from stage_gen.resources import inventory_template_path

CONTENT_HANDLER_VERSION = "prepared-content-v4"
CONTENT_CACHE_VERSION = "prepared-content-v3"
_PLAYER_NODE = re.compile(
    r"^player-(?P<entity_id>[a-z0-9_]+)-(?:(?:state-(?P<state>[a-z0-9_]+)-(?P<state_action>generate|validate))|(?P<action>concept-generate|dialogue-generate|dialogue-validate|contact-sheet|review))$"
)
_MOB_NODE = re.compile(
    r"^mob-(?P<entity_id>[a-z0-9_]+)-(?:(?:state-(?P<state>[a-z0-9_]+)-(?P<state_action>generate|validate))|(?P<action>concept-generate|contact-sheet|review))$"
)
_NPC_NODE = re.compile(
    r"^npc-(?P<entity_id>[a-z0-9_]+)-(?P<action>concept-generate|world-generate|world-validate|dialogue-generate|dialogue-validate|contact-sheet|review)$"
)
_CATALOG_NODE = re.compile(
    r"^(?P<kind>prop|item)-(?P<entity_id>[a-z0-9_]+)-(?P<action>generate|validate)$"
)
_TRACK_NODE = re.compile(r"^track-(?P<track_id>[a-z0-9_]+)-(?P<action>generate|validate)$")
_UI_INVENTORY_NODE = re.compile(r"^ui-inventory-panel-(?P<action>generate|validate|review)$")


class PreparedContentNodeHandler:
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
        self._graph = graph
        self._package = package
        self._run_dir = run_dir
        self._cache_dir = cache_dir
        self._images = image_service
        self._structured = structured_service
        self._music = music_service

    def _motion_source_facing(
        self, kind: MotionActorKind, state: str
    ) -> Literal["right", "back", "front"]:
        return motion_source_facing(
            kind,
            state,
            npc_world_orientation=(self._package.npcs.world_orientation if kind == "npc" else None),
        )

    async def __call__(
        self, node: ExecutionNode, context: NodeExecutionContext
    ) -> NodeExecutionResult:
        cached = self._read_cache(node, context)
        if cached is not None:
            return cached
        try:
            result = await self._execute(node)
        except NodeExecutionError:
            raise
        except Exception as error:
            external = node.operation is not OperationKind.LOCAL
            attempts = int(getattr(error, "attempts", 1))
            raise NodeExecutionError(
                str(error),
                attempts=attempts,
                provider_operations=attempts if external else 0,
            ) from error
        self._write_cache(node, context, result)
        return result

    async def _execute(self, node: ExecutionNode) -> NodeExecutionResult:
        if node.node_id == "package-resolve":
            path = self._run_dir / node.outputs[0]
            atomic_write_json(path, self._package.identity())
            return self._result(node, (path,), provider_operations=0)
        if node.node_id == "gameplay-bindings-validate":
            return await self._write_bindings(node)
        if node.node_id == "props-contact-sheet":
            return await self._catalog_contact_sheet(node, "prop")
        if node.node_id == "items-contact-sheet":
            return await self._catalog_contact_sheet(node, "item")
        if node.node_id == "props-review":
            return await self._catalog_review(node, "prop")
        if node.node_id == "items-review":
            return await self._catalog_review(node, "item")
        ui_match = _UI_INVENTORY_NODE.fullmatch(node.node_id)
        if ui_match:
            return await self._ui_inventory_node(node, ui_match["action"])

        match = _PLAYER_NODE.fullmatch(node.node_id)
        if match:
            return await self._player_node(node, match)
        match = _MOB_NODE.fullmatch(node.node_id)
        if match:
            return await self._mob_node(node, match)
        match = _NPC_NODE.fullmatch(node.node_id)
        if match:
            return await self._npc_node(node, match)
        match = _CATALOG_NODE.fullmatch(node.node_id)
        if match:
            return await self._catalog_node(node, match)
        match = _TRACK_NODE.fullmatch(node.node_id)
        if match:
            return await self._track_node(node, match)
        raise ValueError(f"prepared content handler cannot execute node: {node.node_id}")

    async def _ui_inventory_node(self, node: ExecutionNode, action: str) -> NodeExecutionResult:
        if action == "generate":
            return await self._generate_inventory_panel(node)
        if action == "validate":
            return await self._validate_inventory_panel(node)
        return await self._review_inventory_panel(node)

    async def _generate_inventory_panel(self, node: ExecutionNode) -> NodeExecutionResult:
        panel = self._package.ui.inventory_panel
        output = self._run_dir / node.outputs[0]
        template = inventory_template_path()
        template_data = template.read_bytes()
        prompt = self._visual_prompt(
            "Create one inventory panel for the game's screen-fixed interface.\n"
            f"Authored direction: {panel.prompt}\n"
            "Use the supplied layout template as the exact geometry authority: one 1536 by 1024 "
            "canvas, one outer panel, and eight empty slots in a strict four-column by two-row "
            "layout. Preserve the template's panel and slot positions. The template is layout "
            "guidance, not the requested visual style. Keep the canvas exterior outside the panel "
            "transparent. The entire panel body and every empty slot well must be solid, filled, "
            "and fully opaque alpha 255. Do not cut transparent or semi-transparent holes into "
            "the panel middle or any slot interior. Slots may look recessed through opaque color "
            "and shading only. Keep the canvas border and empty space beyond the decorated panel "
            "silhouette clear alpha 0. No exterior glow, drop shadow, color wash, backdrop, or "
            "scenery. Straps, leaves, corners, and ornaments may shape the panel silhouette. No "
            "items, text, numbers, labels, icons, cursor, character, logo, signature, or watermark."
        )
        references = (
            *self._image_references(self._package.ui.references, panel.reference_ids),
            ImageReference(
                url=_data_url(template_data, "image/png"),
                provenance_ref=(
                    "resource://fixtures/image_gen_templates/inventory_template.png"
                    f"#sha256={_sha(template_data)}"
                ),
            ),
        )
        result = await self._images.generate(
            ImageGenerationRequest(
                prompt=prompt,
                artifact_path=output,
                input_references=references,
                quality="high",
                background="transparent",
                output_format="png",
                size="1536x1024",
                timeout_seconds=600,
                metadata={
                    "checkpoint": "ui",
                    "role": "inventory_panel",
                    "layout": panel.layout,
                    "alpha_policy": panel.alpha_policy,
                },
                validate=lambda artifact: _validate_inventory_panel_image(artifact.data),
            )
        )
        return self._result(
            node,
            (output, Path(result.provenance_path)),
            attempts=result.attempts,
            provider_operations=result.attempts,
        )

    async def _validate_inventory_panel(self, node: ExecutionNode) -> NodeExecutionResult:
        source = self._run_dir / self._graph.node(node.depends_on[0]).outputs[0]
        data = source.read_bytes()
        canonical_data, facts = _canonicalize_inventory_panel_image(data)
        canonical, validation, evidence = (self._run_dir / value for value in node.outputs)
        provenance = await _write_local_image(
            canonical,
            canonical_data,
            prompt=(
                "Normalize only the admitted alpha boundary: clear the already-transparent "
                "exterior and clamp the already-opaque panel core and slot interiors to alpha 255."
            ),
            inputs=((source.relative_to(self._run_dir).as_posix(), data),),
            validation=facts,
            model="prepared-ui-inventory-validation-v2",
        )
        atomic_write_json(
            validation,
            {
                "schema_version": 1,
                "kind": "prepared-ui-inventory-validation-v2",
                **inventory_panel_layout_contract(),
                **facts,
            },
        )
        evidence_data = _inventory_panel_evidence(canonical_data)
        evidence_provenance = await _write_local_image(
            evidence,
            evidence_data,
            prompt="Composite the inventory panel over a checkerboard for review evidence.",
            inputs=((canonical.relative_to(self._run_dir).as_posix(), data),),
            validation={"source_validation": facts, "checkerboard_only": True},
            model="prepared-ui-inventory-evidence-v1",
        )
        return self._result(
            node,
            (canonical, provenance, validation, evidence, evidence_provenance),
            provider_operations=0,
        )

    async def _review_inventory_panel(self, node: ExecutionNode) -> NodeExecutionResult:
        panel = self._package.ui.inventory_panel
        evidence = self._run_dir / "ui/inventory_panel.evidence.png"
        references = [self._run_structured_reference(evidence)]
        references.extend(
            self._package_structured_reference(reference)
            for reference in self._package.ui.references
            if reference.reference_id in set(panel.reference_ids)
        )
        return await self._run_review(
            node,
            prompt=(
                "Review the generated inventory panel against its authored direction and the "
                "exact four-column by two-row layout. Image 1 is the generated panel composited "
                "over a checkerboard; remaining images are authored visual references. "
                "Deterministic pixel validation has already proved a transparent canvas border, "
                "a fully opaque panel core, and fully opaque interiors for all eight slots. "
                "Do not mistake the checkerboard outside the panel for artwork. Judge style "
                "coherence, eight-slot readability, consistent visual hierarchy, clean exterior "
                "silhouette, and absence of items, text, pseudo-text, labels, logos, or scenery. "
                f"Authored direction: {panel.prompt} Uncertainty must not be called accept."
            ),
            references=references,
            metadata={"checkpoint": "ui", "role": "inventory_panel"},
        )

    async def _player_node(self, node: ExecutionNode, match: re.Match[str]) -> NodeExecutionResult:
        player = self._player(match["entity_id"])
        if match["state"] is not None:
            if match["state_action"] == "generate":
                return await self._generate_motion(node, "player", player, match["state"])
            return await self._validate_motion(node, "player", player.player_id, match["state"])
        action = match["action"]
        if action == "concept-generate":
            return await self._generate_concept(
                node, "player", player, self._package.player.references
            )
        if action == "dialogue-generate":
            return await self._generate_dialogue(
                node, "player", player.player_id, player.dialogue_art.expressions
            )
        if action == "dialogue-validate":
            return await self._validate_dialogue(
                node, "player", player.player_id, player.dialogue_art.expressions
            )
        if action == "contact-sheet":
            return await self._actor_contact_sheet(node, "player", player.player_id)
        return await self._actor_review(
            node,
            kind="player",
            entity_id=player.player_id,
            display_name=player.display_name,
            references=self._content_references(
                self._package.player.references, player.reference_ids
            ),
        )

    async def _mob_node(self, node: ExecutionNode, match: re.Match[str]) -> NodeExecutionResult:
        mob = self._mob(match["entity_id"])
        if match["state"] is not None:
            if match["state_action"] == "generate":
                return await self._generate_motion(node, "mob", mob, match["state"])
            return await self._validate_motion(node, "mob", mob.mob_id, match["state"])
        action = match["action"]
        if action == "concept-generate":
            return await self._generate_concept(node, "mob", mob, self._package.mobs.references)
        if action == "contact-sheet":
            return await self._actor_contact_sheet(node, "mob", mob.mob_id)
        return await self._actor_review(
            node,
            kind="mob",
            entity_id=mob.mob_id,
            display_name=mob.display_name,
            references=self._content_references(self._package.mobs.references, mob.reference_ids),
        )

    async def _npc_node(self, node: ExecutionNode, match: re.Match[str]) -> NodeExecutionResult:
        npc = self._npc(match["entity_id"])
        action = match["action"]
        if action == "concept-generate":
            return await self._generate_concept(node, "npc", npc, self._package.npcs.references)
        if action == "world-generate":
            return await self._generate_motion(node, "npc", npc, "idle")
        if action == "world-validate":
            return await self._validate_motion(node, "npc", npc.npc_id, "idle")
        if action == "dialogue-generate":
            return await self._generate_dialogue(node, "npc", npc.npc_id, npc.dialogue_expressions)
        if action == "dialogue-validate":
            return await self._validate_dialogue(node, "npc", npc.npc_id, npc.dialogue_expressions)
        if action == "contact-sheet":
            return await self._actor_contact_sheet(node, "npc", npc.npc_id)
        return await self._actor_review(
            node,
            kind="npc",
            entity_id=npc.npc_id,
            display_name=npc.display_name,
            references=self._content_references(self._package.npcs.references, npc.reference_ids),
        )

    async def _catalog_node(self, node: ExecutionNode, match: re.Match[str]) -> NodeExecutionResult:
        kind = cast(Literal["prop", "item"], match["kind"])
        entry = self._prop(match["entity_id"]) if kind == "prop" else self._item(match["entity_id"])
        if match["action"] == "generate":
            return await self._generate_catalog_asset(node, kind, entry)
        return self._validate_catalog_asset(node, kind, match["entity_id"])

    async def _track_node(self, node: ExecutionNode, match: re.Match[str]) -> NodeExecutionResult:
        track = self._package.soundtrack.track(match["track_id"])
        if match["action"] == "generate":
            output = self._run_dir / node.outputs[0]
            result = await self._music.generate(
                MusicGenerationRequest(
                    prompt=soundtrack_track_prompt(self._package.game.game_id, track),
                    artifact_path=output,
                    output_format="mp3",
                    timeout_seconds=900,
                    metadata={
                        "checkpoint": "content",
                        "track_id": track.track_id,
                        "target_duration_seconds": track.generation.target_duration_seconds,
                        "seamless_loop": track.generation.seamless_loop,
                    },
                    validate=lambda artifact: _validate_audio_bytes(artifact.data),
                )
            )
            return self._result(
                node,
                (output, Path(result.provenance_path)),
                attempts=result.attempts,
                provider_operations=result.attempts,
            )
        generated = self._graph.node(node.depends_on[0])
        source = self._run_dir / generated.outputs[0]
        probe = await probe_audio(source, timeout_seconds=120)
        if probe.duration_seconds < 15:
            raise ValueError("generated soundtrack track is shorter than 15 seconds")
        output = self._run_dir / node.outputs[0]
        atomic_write_json(
            output,
            {
                "schema_version": 1,
                "kind": "prepared-soundtrack-validation-v1",
                "track_id": track.track_id,
                "format_name": probe.format_name,
                "duration_seconds": round(probe.duration_seconds, 3),
                "target_duration_seconds": track.generation.target_duration_seconds,
                "target_delta_seconds": round(
                    probe.duration_seconds - track.generation.target_duration_seconds, 3
                ),
                "bit_rate": probe.bit_rate,
                "instrumental_intent": track.generation.instrumental,
                "seamless_loop_intent": track.generation.seamless_loop,
                "container_valid": True,
                "listening_verdict": "not_performed",
            },
        )
        return self._result(node, (output,), provider_operations=0)

    async def _generate_concept(
        self,
        node: ExecutionNode,
        kind: MotionActorKind,
        entry: PlayerContent | MobContent | NpcContent,
        catalog_references: Sequence[ContentReference],
    ) -> NodeExecutionResult:
        entity_id = _entity_id(entry)
        output = self._run_dir / node.outputs[0]
        references = self._image_references(catalog_references, entry.reference_ids)
        prompt = self._visual_prompt(
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
        return self._result(
            node,
            (output, Path(result.provenance_path)),
            attempts=result.attempts,
            provider_operations=result.attempts,
        )

    async def _generate_motion(
        self,
        node: ExecutionNode,
        kind: Literal["player", "mob", "npc"],
        entry: PlayerContent | MobContent | NpcContent,
        state: str,
    ) -> NodeExecutionResult:
        entity_id = _entity_id(entry)
        output = self._run_dir / node.outputs[0]
        concept = self._run_dir / f"content/{_kind_directory(kind)}/{entity_id}/concept.png"
        concept_data = concept.read_bytes()
        references = (
            ImageReference(
                url=_data_url(concept_data, "image/png"),
                provenance_ref=f"run://{concept.relative_to(self._run_dir).as_posix()}#sha256={_sha(concept_data)}",
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
        prompt = self._visual_prompt(
            f"Create the canonical side-view motion atlas for {kind} {entity_id}, state {state}. "
            "Use the supplied identity concept exactly. Output a strict single-row strip of four "
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
                size="1536x1024",
                timeout_seconds=600,
                metadata={
                    "checkpoint": "content",
                    "kind": kind,
                    "entity_id": entity_id,
                    "state": state,
                    "atlas_columns": MOTION_ATLAS_COLUMNS,
                    "atlas_rows": MOTION_ATLAS_ROWS,
                    "source_facing": source_facing,
                },
                validate=lambda artifact: _validate_atlas(
                    artifact.data,
                    columns=MOTION_ATLAS_COLUMNS,
                    rows=MOTION_ATLAS_ROWS,
                    required_cells=MOTION_ATLAS_REQUIRED_CELLS,
                ),
            )
        )
        return self._result(
            node,
            (output, Path(result.provenance_path)),
            attempts=result.attempts,
            provider_operations=result.attempts,
        )

    async def _generate_dialogue(
        self,
        node: ExecutionNode,
        kind: Literal["player", "npc"],
        entity_id: str,
        expressions: Sequence[str],
    ) -> NodeExecutionResult:
        output = self._run_dir / node.outputs[0]
        concept = self._run_dir / f"content/{_kind_directory(kind)}/{entity_id}/concept.png"
        concept_data = concept.read_bytes()
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
                        url=_data_url(concept_data, "image/png"),
                        provenance_ref=f"run://{concept.relative_to(self._run_dir).as_posix()}#sha256={_sha(concept_data)}",
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
        return self._result(
            node,
            (output, Path(result.provenance_path)),
            attempts=result.attempts,
            provider_operations=result.attempts,
        )

    async def _generate_catalog_asset(
        self,
        node: ExecutionNode,
        kind: Literal["prop", "item"],
        entry: PropContent | ItemContent,
    ) -> NodeExecutionResult:
        entity_id = entry.prop_id if isinstance(entry, PropContent) else entry.item_id
        catalog = self._package.props if kind == "prop" else self._package.items
        output = self._run_dir / node.outputs[0]
        prompt = self._visual_prompt(
            f"Generate exactly one canonical {kind} asset, stable ID {entity_id}.\n"
            f"Authored direction: {entry.prompt}\n"
            "Use a fixed side-view game-asset camera. Center the complete object with comfortable "
            "transparent padding. Preserve a clear gameplay silhouette and the authored scale "
            "cues. Output true alpha with no floor, scenery, shadow plate, frame, text, label, "
            "symbol, or "
            "second object."
        )
        result = await self._images.generate(
            ImageGenerationRequest(
                prompt=prompt,
                artifact_path=output,
                input_references=self._image_references(catalog.references, entry.reference_ids),
                quality="high",
                background="transparent",
                output_format="png",
                size="1024x1024",
                timeout_seconds=600,
                metadata={"checkpoint": "content", "kind": kind, "entity_id": entity_id},
                validate=lambda artifact: _validate_transparent_image(
                    artifact.data, width=1024, height=1024
                ),
            )
        )
        return self._result(
            node,
            (output, Path(result.provenance_path)),
            attempts=result.attempts,
            provider_operations=result.attempts,
        )

    async def _validate_motion(
        self, node: ExecutionNode, kind: MotionActorKind, entity_id: str, state: str
    ) -> NodeExecutionResult:
        source = self._run_dir / self._graph.node(node.depends_on[0]).outputs[0]
        source_facing = self._motion_source_facing(kind, state)
        source_data = source.read_bytes()
        source_facts = _validate_atlas(
            source_data,
            columns=MOTION_ATLAS_COLUMNS,
            rows=MOTION_ATLAS_ROWS,
            required_cells=MOTION_ATLAS_REQUIRED_CELLS,
        )
        canonical_data, repack = repack_alpha_components(
            source_data,
            AlphaComponentRepackContract(
                rows=MOTION_ATLAS_ROWS,
                columns=MOTION_ATLAS_COLUMNS,
                required_cells=MOTION_ATLAS_REQUIRED_CELLS,
                anchor="bottom",
            ),
        )
        canonical = self._run_dir / node.outputs[0]
        source_ref = (
            f"run://{source.relative_to(self._run_dir).as_posix()}#sha256={_sha(source_data)}"
        )
        provenance = await _write_local_image(
            canonical,
            canonical_data,
            prompt=(
                f"Repack the {kind} {entity_id} {state} source atlas using native-alpha "
                "connected components."
            ),
            inputs=((source_ref, source_data),),
            validation=repack,
        )
        validation = self._run_dir / node.outputs[1]
        atomic_write_json(
            validation,
            {
                "schema_version": 1,
                "kind": "prepared-motion-atlas-validation-v3",
                "entity_kind": kind,
                "entity_id": entity_id,
                "state": state,
                "columns": MOTION_ATLAS_COLUMNS,
                "rows": MOTION_ATLAS_ROWS,
                "source_facing": source_facing,
                "frames": MOTION_ATLAS_REQUIRED_CELLS,
                "runtime_horizontal_mirroring": runtime_mirrors_source(source_facing),
                "source_validation": source_facts,
                "repack": repack,
            },
        )
        return self._result(node, (canonical, provenance, validation), provider_operations=0)

    async def _validate_dialogue(
        self,
        node: ExecutionNode,
        kind: str,
        entity_id: str,
        expressions: Sequence[str],
    ) -> NodeExecutionResult:
        source = self._run_dir / self._graph.node(node.depends_on[0]).outputs[0]
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
        canonical = self._run_dir / node.outputs[0]
        source_ref = (
            f"run://{source.relative_to(self._run_dir).as_posix()}#sha256={_sha(source_data)}"
        )
        provenance = await _write_local_image(
            canonical,
            canonical_data,
            prompt=(
                f"Repack the {kind} {entity_id} dialogue atlas using native-alpha connected "
                "components."
            ),
            inputs=((source_ref, source_data),),
            validation=repack,
        )
        validation = self._run_dir / node.outputs[1]
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
        return self._result(node, (canonical, provenance, validation), provider_operations=0)

    def _validate_catalog_asset(
        self, node: ExecutionNode, kind: str, entity_id: str
    ) -> NodeExecutionResult:
        source = self._run_dir / self._graph.node(node.depends_on[0]).outputs[0]
        source_data = source.read_bytes()
        facts = _validate_transparent_image(source_data, width=1024, height=1024)
        ground_contact = measure_alpha_ground_contact(source_data) if kind == "prop" else None
        output = self._run_dir / node.outputs[0]
        atomic_write_json(
            output,
            {
                "schema_version": 1,
                "kind": (
                    "prepared-isolated-prop-validation-v2"
                    if kind == "prop"
                    else "prepared-isolated-asset-validation-v1"
                ),
                "asset_kind": kind,
                "asset_id": entity_id,
                **facts,
                **({"ground_contact": ground_contact} if ground_contact is not None else {}),
            },
        )
        return self._result(node, (output,), provider_operations=0)

    async def _actor_contact_sheet(
        self, node: ExecutionNode, kind: Literal["player", "mob", "npc"], entity_id: str
    ) -> NodeExecutionResult:
        root = self._run_dir / f"content/{_kind_directory(kind)}/{entity_id}"
        entries: list[tuple[str, Path]] = [("concept", root / "concept.png")]
        if kind == "player":
            player = self._player(entity_id)
            entries.extend(
                (motion.state, root / f"states/{motion.state}.png") for motion in player.motions
            )
            entries.append(("dialogue", root / "dialogue.png"))
        elif kind == "mob":
            mob = self._mob(entity_id)
            entries.extend(
                (motion.state, root / f"states/{motion.state}.png") for motion in mob.motions
            )
        else:
            entries.extend((value, root / f"{value}.png") for value in ("world", "dialogue"))
        output = self._run_dir / node.outputs[0]
        data = _contact_sheet(entries, title=f"{kind}: {entity_id}")
        sidecar = await _write_local_image(
            output,
            data,
            prompt=f"Assemble the complete labeled {kind} contact sheet for {entity_id}.",
            inputs=[
                (path.relative_to(self._run_dir).as_posix(), path.read_bytes())
                for _, path in entries
            ],
            validation={"entry_count": len(entries), "entity_kind": kind, "entity_id": entity_id},
        )
        return self._result(node, (output, sidecar), provider_operations=0)

    async def _catalog_contact_sheet(
        self, node: ExecutionNode, kind: Literal["prop", "item"]
    ) -> NodeExecutionResult:
        values = self._package.props.props if kind == "prop" else self._package.items.items
        directory = "props" if kind == "prop" else "items"
        entries = []
        for entry in values:
            entity_id = entry.prop_id if isinstance(entry, PropContent) else entry.item_id
            entries.append((entity_id, self._run_dir / f"content/{directory}/{entity_id}.png"))
        output = self._run_dir / node.outputs[0]
        data = _contact_sheet(entries, title=f"{kind} catalog")
        sidecar = await _write_local_image(
            output,
            data,
            prompt=f"Assemble the complete stable-ID {kind} catalog contact sheet.",
            inputs=[
                (path.relative_to(self._run_dir).as_posix(), path.read_bytes())
                for _, path in entries
            ],
            validation={"entry_count": len(entries), "asset_kind": kind},
        )
        return self._result(node, (output, sidecar), provider_operations=0)

    async def _actor_review(
        self,
        node: ExecutionNode,
        *,
        kind: MotionActorKind,
        entity_id: str,
        display_name: str,
        references: Sequence[ContentReference],
    ) -> NodeExecutionResult:
        actor_root = self._run_dir / f"content/{_kind_directory(kind)}/{entity_id}"
        contact = actor_root / "contact-sheet.png"
        structured_refs = [self._run_structured_reference(contact)]
        states: Sequence[str]
        expressions: Sequence[str]
        motions: Sequence[MotionPresentation]
        if kind == "player":
            player = self._player(entity_id)
            authored_prompt = player.prompt
            motions = player.motions
            states = [motion.state for motion in motions]
            expressions = player.dialogue_art.expressions
        elif kind == "mob":
            mob = self._mob(entity_id)
            authored_prompt = mob.prompt
            motions = mob.motions
            states = [motion.state for motion in motions]
            expressions = []
        else:
            npc = self._npc(entity_id)
            authored_prompt = npc.prompt
            motions = npc.motions
            states = [motion.state for motion in motions]
            expressions = npc.dialogue_expressions
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
                "isolation, and declared dialogue-expression coverage where applicable. A labeled "
                "state tile may itself contain a multi-cell atlas. Report concrete visible "
                "defects. "
                "Uncertainty must not be called accept."
            ),
            references=structured_refs,
            metadata={"checkpoint": "content", "kind": kind, "entity_id": entity_id},
        )

    async def _catalog_review(
        self, node: ExecutionNode, kind: Literal["prop", "item"]
    ) -> NodeExecutionResult:
        directory = "props" if kind == "prop" else "items"
        contact = self._run_dir / f"content/{directory}/contact-sheet.png"
        catalog = self._package.props if kind == "prop" else self._package.items
        references = [self._run_structured_reference(contact)]
        entries: Sequence[PropContent | ItemContent] = (
            self._package.props.props if kind == "prop" else self._package.items.items
        )
        expected_ids = [
            entry.prop_id if isinstance(entry, PropContent) else entry.item_id for entry in entries
        ]
        authored_directions = [
            {
                "asset_id": (entry.prop_id if isinstance(entry, PropContent) else entry.item_id),
                "prompt": entry.prompt,
            }
            for entry in entries
        ]
        references.extend(self._package_structured_reference(ref) for ref in catalog.references)
        return await self._run_review(
            node,
            prompt=(
                f"Review the complete generated {kind} catalog. The exact complete stable-ID list "
                f"is {expected_ids}. Authored directions are {authored_directions}. Image 1 is a "
                "locally labeled stable-ID contact sheet; remaining images are authored "
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
            ),
            references=references,
            metadata={"checkpoint": "content", "kind": kind},
        )

    async def _run_review(
        self,
        node: ExecutionNode,
        *,
        prompt: str,
        references: Sequence[StructuredReference],
        metadata: Mapping[str, object],
    ) -> NodeExecutionResult:
        output = self._run_dir / node.outputs[0]
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
        return self._result(
            node,
            (output, Path(result.provenance_path)),
            attempts=result.attempts,
            provider_operations=result.attempts,
        )

    async def _write_bindings(self, node: ExecutionNode) -> NodeExecutionResult:
        gameplay = self._package.gameplay
        speaker_expressions = []
        player = self._package.player.players[0]
        npc_by_id = {entry.npc_id: entry for entry in self._package.npcs.npcs}
        for sequence in self._package.sequences:
            for sequence_node in sequence.nodes:
                if not isinstance(sequence_node, DialogueNode):
                    continue
                expressions = (
                    player.dialogue_art.expressions
                    if sequence_node.speaker_id == player.player_id
                    else npc_by_id[sequence_node.speaker_id].dialogue_expressions
                )
                if sequence_node.expression not in expressions:
                    raise ValueError(
                        f"sequence expression does not resolve: {sequence.sequence_id}/"
                        f"{sequence_node.node_id}/{sequence_node.expression}"
                    )
                speaker_expressions.append(
                    {
                        "sequence_id": sequence.sequence_id,
                        "node_id": sequence_node.node_id,
                        "speaker_id": sequence_node.speaker_id,
                        "expression": sequence_node.expression,
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
            "sequence_speaker_expressions": speaker_expressions,
            "effect_ids": [entry.effect_id for entry in gameplay.effects],
            "track_ids": sorted(
                {track_id for map_use in gameplay.map_uses for track_id in map_use.track_ids}
            ),
            "map_topology": [
                {
                    "map_id": game_map.map_id,
                    "occupancy_rows": len(game_map.ground.occupancy),
                    "occupancy_columns": len(game_map.ground.occupancy[0]),
                    "climbable_ids": (
                        []
                        if game_map.climbable is None
                        else [entry.climbable_id for entry in game_map.climbable.placements]
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
        binding_path, coverage_path = (self._run_dir / value for value in node.outputs)
        atomic_write_json(binding_path, bindings)
        atomic_write_json(coverage_path, coverage)
        return self._result(node, (binding_path, coverage_path), provider_operations=0)

    def _visual_prompt(self, specific: str) -> str:
        universe = self._package.file(self._package.game.universe.source).data.decode("utf-8")
        style = self._package.game.style
        return (
            f"Game universe:\n{universe}\n\nVisual style: {style.label}. "
            f"Use: {', '.join(style.keywords)}. Avoid: {', '.join(style.avoid)}.\n\n"
            f"Content task:\n{specific}"
        )

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
                    url=_data_url(package_file.data, _media_type(reference.source)),
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
            url=_data_url(path.read_bytes(), "image/png"),
            provenance_ref=f"run://{path.relative_to(self._run_dir).as_posix()}",
        )

    def _package_structured_reference(
        self, reference: ContentReference | UiReference
    ) -> StructuredReference:
        package_file = self._package.file(reference.source)
        return StructuredReference(
            url=_data_url(package_file.data, _media_type(reference.source)),
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

    def _prop(self, entity_id: str) -> PropContent:
        return next(entry for entry in self._package.props.props if entry.prop_id == entity_id)

    def _item(self, entity_id: str) -> ItemContent:
        return next(entry for entry in self._package.items.items if entry.item_id == entity_id)

    def _result(
        self,
        node: ExecutionNode,
        paths: tuple[Path, ...],
        *,
        attempts: int = 1,
        provider_operations: int,
    ) -> NodeExecutionResult:
        return NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=attempts,
            provider_operations=provider_operations,
            artifacts=tuple(_node_artifact(self._run_dir, path) for path in paths),
        )

    def _lineage(
        self, node: ExecutionNode, context: NodeExecutionContext
    ) -> list[dict[str, object]]:
        return [
            {
                "node_id": dependency,
                "cache_key": self._graph.node(dependency).cache_key,
                "artifact_sha256": [
                    artifact.sha256 for artifact in context.dependency_results[dependency].artifacts
                ],
            }
            for dependency in node.depends_on
        ]

    def _cache_paths(self, node: ExecutionNode) -> tuple[Path, Path]:
        root = self._cache_dir / CONTENT_CACHE_VERSION / node.cache_key[:2] / node.cache_key
        return root / "record.json", root / "artifacts"

    def _read_cache(
        self, node: ExecutionNode, context: NodeExecutionContext
    ) -> NodeExecutionResult | None:
        record_path, artifacts_dir = self._cache_paths(node)
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if (
            not isinstance(record, dict)
            or record.get("cache_key") != node.cache_key
            or record.get("lineage") != self._lineage(node, context)
        ):
            return None
        outputs = record.get("artifacts")
        if not isinstance(outputs, list):
            return None
        restored: list[NodeArtifact] = []
        payloads: list[bytes] = []
        for index, value in enumerate(outputs):
            if not isinstance(value, dict) or not isinstance(value.get("artifact_ref"), str):
                return None
            try:
                data = (artifacts_dir / f"{index}.bin").read_bytes()
            except OSError:
                return None
            if _sha(data) != value.get("sha256") or len(data) != value.get("bytes"):
                return None
            payloads.append(data)
            restored.append(NodeArtifact.model_validate(value))
        if not payloads or not self._cached_primary_artifact_valid(node, payloads[0]):
            return None
        for artifact, data in zip(restored, payloads, strict=True):
            atomic_write_bytes(self._run_dir / artifact.artifact_ref, data)
        return NodeExecutionResult(
            cache=CacheDisposition.HIT,
            attempts=1,
            provider_operations=0,
            artifacts=tuple(restored),
            known_cost_usd=0.0,
        )

    def _cached_primary_artifact_valid(self, node: ExecutionNode, data: bytes) -> bool:
        if node.operation is not OperationKind.IMAGE_GENERATION:
            return True
        try:
            player_match = _PLAYER_NODE.fullmatch(node.node_id)
            if player_match:
                if player_match["state_action"] == "generate":
                    _validate_atlas(
                        data,
                        columns=MOTION_ATLAS_COLUMNS,
                        rows=MOTION_ATLAS_ROWS,
                        required_cells=MOTION_ATLAS_REQUIRED_CELLS,
                    )
                elif player_match["action"] == "dialogue-generate":
                    expressions = self._player(player_match["entity_id"]).dialogue_art.expressions
                    columns, rows = dialogue_atlas_grid(len(expressions))
                    _validate_atlas(
                        data,
                        columns=columns,
                        rows=rows,
                        required_cells=len(expressions),
                    )
                else:
                    _validate_transparent_image(data, width=1024, height=1536)
                return True
            mob_match = _MOB_NODE.fullmatch(node.node_id)
            if mob_match:
                if mob_match["state_action"] == "generate":
                    _validate_atlas(
                        data,
                        columns=MOTION_ATLAS_COLUMNS,
                        rows=MOTION_ATLAS_ROWS,
                        required_cells=MOTION_ATLAS_REQUIRED_CELLS,
                    )
                else:
                    _validate_transparent_image(data, width=1024, height=1536)
                return True
            npc_match = _NPC_NODE.fullmatch(node.node_id)
            if npc_match:
                if npc_match["action"] == "world-generate":
                    _validate_atlas(
                        data,
                        columns=MOTION_ATLAS_COLUMNS,
                        rows=MOTION_ATLAS_ROWS,
                        required_cells=MOTION_ATLAS_REQUIRED_CELLS,
                    )
                elif npc_match["action"] == "dialogue-generate":
                    expressions = self._npc(npc_match["entity_id"]).dialogue_expressions
                    columns, rows = dialogue_atlas_grid(len(expressions))
                    _validate_atlas(
                        data,
                        columns=columns,
                        rows=rows,
                        required_cells=len(expressions),
                    )
                else:
                    _validate_transparent_image(data, width=1024, height=1536)
                return True
            if _CATALOG_NODE.fullmatch(node.node_id):
                _validate_transparent_image(data, width=1024, height=1024)
                return True
            if _UI_INVENTORY_NODE.fullmatch(node.node_id):
                _validate_inventory_panel_image(data)
                return True
        except (OSError, ValueError):
            return False
        return False

    def _write_cache(
        self, node: ExecutionNode, context: NodeExecutionContext, result: NodeExecutionResult
    ) -> None:
        record_path, artifacts_dir = self._cache_paths(node)
        for index, artifact in enumerate(result.artifacts):
            atomic_write_bytes(
                artifacts_dir / f"{index}.bin",
                (self._run_dir / artifact.artifact_ref).read_bytes(),
            )
        atomic_write_json(
            record_path,
            {
                "schema_version": 1,
                "kind": "prepared-content-node-cache-v1",
                "cache_key": node.cache_key,
                "node_id": node.node_id,
                "lineage": self._lineage(node, context),
                "artifacts": [entry.model_dump(mode="json") for entry in result.artifacts],
            },
        )


def content_target_node_ids(package: ResolvedGamePackage) -> tuple[str, ...]:
    player_targets = tuple(f"player-{entry.player_id}-review" for entry in package.player.players)
    mob_targets = tuple(f"mob-{entry.mob_id}-review" for entry in package.mobs.mobs)
    npc_targets = tuple(f"npc-{entry.npc_id}-review" for entry in package.npcs.npcs)
    track_targets = tuple(f"track-{entry.track_id}-validate" for entry in package.soundtrack.tracks)
    return (
        *player_targets,
        *mob_targets,
        *npc_targets,
        "props-review",
        "items-review",
        "ui-inventory-panel-review",
        *track_targets,
        "gameplay-bindings-validate",
    )


def _coverage_matrix(package: ResolvedGamePackage) -> dict[str, object]:
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
        "track_ids": list(package.soundtrack.track_ids),
        "sequence_ids": [entry.sequence_id for entry in package.sequences],
        "required_image_operations": (
            sum(2 + len(entry.motions) for entry in package.player.players)
            + sum(1 + len(entry.motions) for entry in package.mobs.mobs)
            + 3 * len(package.npcs.npcs)
            + len(package.props.props)
            + len(package.items.items)
            + 1
        ),
        "required_structured_reviews": (
            len(package.player.players) + len(package.mobs.mobs) + len(package.npcs.npcs) + 3
        ),
        "required_music_operations": len(package.soundtrack.tracks),
    }


def _entity_id(entry: PlayerContent | MobContent | NpcContent) -> str:
    if isinstance(entry, PlayerContent):
        return entry.player_id
    if isinstance(entry, MobContent):
        return entry.mob_id
    return entry.npc_id


def _kind_directory(kind: str) -> str:
    return {"player": "players", "mob": "mobs", "npc": "npcs"}[kind]


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


def _validate_atlas(
    data: bytes, *, columns: int, rows: int, required_cells: int
) -> dict[str, object]:
    facts = _validate_transparent_image(data, width=1536, height=1024)
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


def _validate_inventory_panel_image(data: bytes) -> dict[str, object]:
    with Image.open(io.BytesIO(data)) as opened:
        if "A" not in opened.getbands():
            raise ValueError("inventory panel output must carry an alpha channel")
        image = opened.convert("RGBA")
    if image.size != (INVENTORY_CANVAS_WIDTH, INVENTORY_CANVAS_HEIGHT):
        raise ValueError(
            "inventory panel output must be exactly "
            f"{INVENTORY_CANVAS_WIDTH}x{INVENTORY_CANVAS_HEIGHT}"
        )
    alpha = image.getchannel("A")
    extrema = cast(tuple[int, int], alpha.getextrema())
    opaque_admission_min = 250
    transparent_admission_max = 16
    if extrema[0] > transparent_admission_max or extrema[1] < opaque_admission_min:
        raise ValueError("inventory panel must contain transparent exterior and opaque artwork")
    border = [
        *alpha.crop((0, 0, alpha.width, 1)).get_flattened_data(),
        *alpha.crop((0, alpha.height - 1, alpha.width, alpha.height)).get_flattened_data(),
        *alpha.crop((0, 0, 1, alpha.height)).get_flattened_data(),
        *alpha.crop((alpha.width - 1, 0, alpha.width, alpha.height)).get_flattened_data(),
    ]
    if max(border) > transparent_admission_max:
        raise ValueError("inventory panel exterior must remain transparent at the canvas border")

    transparent_pixels = sum(alpha.histogram()[: transparent_admission_max + 1])
    transparent_pixel_fraction = transparent_pixels / (alpha.width * alpha.height)
    if transparent_pixel_fraction < 0.1:
        raise ValueError("inventory panel must retain meaningful transparent exterior space")

    core_inset = 32
    core = alpha.crop(
        (
            INVENTORY_PANEL_LEFT + core_inset,
            INVENTORY_PANEL_TOP + core_inset,
            INVENTORY_PANEL_LEFT + INVENTORY_PANEL_WIDTH - core_inset,
            INVENTORY_PANEL_TOP + INVENTORY_PANEL_HEIGHT - core_inset,
        )
    )
    core_min = cast(tuple[int, int], core.getextrema())[0]
    if core_min < opaque_admission_min:
        raise ValueError(
            "inventory panel middle must be fully opaque; transparent or translucent pixels found"
        )

    slot_alpha_minima: list[int] = []
    slot_inset = 24
    for row in range(INVENTORY_SLOT_ROWS):
        for column in range(INVENTORY_SLOT_COLUMNS):
            left = (
                INVENTORY_SLOT_LEFT
                + column * (INVENTORY_SLOT_SIZE + INVENTORY_SLOT_GUTTER)
                + slot_inset
            )
            top = (
                INVENTORY_SLOT_TOP
                + row * (INVENTORY_SLOT_SIZE + INVENTORY_SLOT_GUTTER)
                + slot_inset
            )
            interior = alpha.crop(
                (
                    left,
                    top,
                    left + INVENTORY_SLOT_SIZE - 2 * slot_inset,
                    top + INVENTORY_SLOT_SIZE - 2 * slot_inset,
                )
            )
            slot_alpha_minima.append(cast(tuple[int, int], interior.getextrema())[0])
    if any(value < opaque_admission_min for value in slot_alpha_minima):
        raise ValueError(
            "every inventory slot interior must be visually opaque before normalization"
        )

    return {
        "width": image.width,
        "height": image.height,
        "alpha_min": extrema[0],
        "alpha_max": extrema[1],
        "border_alpha_max": max(border),
        "transparent_pixel_fraction": round(transparent_pixel_fraction, 6),
        "panel_core_alpha_min": core_min,
        "slot_interior_alpha_minima": slot_alpha_minima,
        "opaque_admission_min": opaque_admission_min,
        "transparent_admission_max": transparent_admission_max,
        "all_slot_interiors_opaque": True,
        "pixel_rewrite_performed": False,
    }


def _canonicalize_inventory_panel_image(data: bytes) -> tuple[bytes, dict[str, object]]:
    source_facts = _validate_inventory_panel_image(data)
    with Image.open(io.BytesIO(data)) as opened:
        image = opened.convert("RGBA")
    alpha = image.getchannel("A")

    transparent_admission_max = cast(int, source_facts["transparent_admission_max"])
    alpha = alpha.point(lambda value: 0 if value <= transparent_admission_max else value)
    core_inset = 32
    alpha.paste(
        255,
        (
            INVENTORY_PANEL_LEFT + core_inset,
            INVENTORY_PANEL_TOP + core_inset,
            INVENTORY_PANEL_LEFT + INVENTORY_PANEL_WIDTH - core_inset,
            INVENTORY_PANEL_TOP + INVENTORY_PANEL_HEIGHT - core_inset,
        ),
    )
    image.putalpha(alpha)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False)
    canonical_data = output.getvalue()
    canonical_facts = _validate_inventory_panel_image(canonical_data)
    return canonical_data, {
        "source": source_facts,
        "canonical": canonical_facts,
        "pixel_rewrite_performed": True,
        "pixel_rewrite": "alpha_boundary_normalization_v1",
    }


def _inventory_panel_evidence(data: bytes) -> bytes:
    with Image.open(io.BytesIO(data)) as opened:
        panel = opened.convert("RGBA")
    canvas = _checkerboard(panel.size)
    canvas.alpha_composite(panel)
    stream = io.BytesIO()
    canvas.convert("RGB").save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def _validate_audio_bytes(data: bytes) -> dict[str, object]:
    if len(data) < 64 * 1024:
        raise ValueError("generated soundtrack payload is too small")
    return {"minimum_bytes": 64 * 1024, "bytes": len(data)}


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
                name="@stage-gen/scrolling-preview", version=CONTENT_HANDLER_VERSION
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


def _node_artifact(run_dir: Path, path: Path) -> NodeArtifact:
    data = path.read_bytes()
    return NodeArtifact(
        artifact_ref=path.relative_to(run_dir).as_posix(), sha256=_sha(data), bytes=len(data)
    )


def _data_url(data: bytes, media_type: str) -> str:
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"


def _media_type(path: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }[Path(path).suffix.lower()]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


__all__ = ["PreparedContentNodeHandler", "content_target_node_ids"]
