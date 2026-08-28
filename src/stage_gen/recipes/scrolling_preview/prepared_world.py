"""Execute the map-only closure of an exact-current prepared game package."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, cast

from PIL import Image, ImageChops, ImageOps, ImageStat

from stage_gen.components import (
    ImageGenerationRequest,
    ImageGenerationService,
    StructuredGenerationRequest,
    StructuredGenerationService,
)
from stage_gen.components._types import BinaryArtifact
from stage_gen.components.game_map import PreparedGameMap, PreparedMapLayer
from stage_gen.components.game_map.prepared import (
    PreparedMapTerrain,
    canonical_prepared_map_terrain_json,
    load_prepared_map_terrain_bytes,
    validate_generated_terrain,
)
from stage_gen.components.image_generation import ImageReference
from stage_gen.components.image_repeat import (
    ImageRepeatValidationPolicy,
    build_three_repeat_preview,
    validate_image_repeat,
)
from stage_gen.components.platformer_map_design import DesignBrief, design_chunks
from stage_gen.components.structured_generation import StructuredOutputSchema, StructuredReference
from stage_gen.contracts import InputProvenance, ProvenanceInput, SoftwareIdentity
from stage_gen.media import (
    AlphaComponentRepackContract,
    BridgeConditioning,
    BridgeRegistrationError,
    assemble_generated_bridge,
    build_bridge_conditioning,
    content_bottom_offset_fraction,
    mirror_repeat,
    repack_alpha_components,
    seal_offset_fraction,
    trim_layer_to_alpha_box,
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
from stage_gen.recipes.scrolling_preview.climbable_atlas import (
    MAX_HEIGHT_PARITY,
    ROLE_ASPECT_ENVELOPE,
    ClimbableRole,
    plan_climbable_atlas,
    role_aspect_admits,
)
from stage_gen.recipes.scrolling_preview.layer_contract import (
    LAYER_PLACEMENT_CANONICALIZER,
    LOOP_BRIDGE_ANCHOR_BAND_PX,
    LOOP_BRIDGE_CONTEXT_SPAN_PX,
    LOOP_BRIDGE_SPAN_PX,
)
from stage_gen.recipes.scrolling_preview.terrain_atlas import (
    MATERIAL_ASSEMBLER_ID,
    assemble_terrain_atlas,
    compose_canonical_terrain,
    require_terrain_atlas_source,
    terrain_atlas_generation_prompt,
)
from stage_gen.recipes.scrolling_preview.terrain_design import (
    compile_terrain,
    terrain_artifact_path,
    terrain_profile,
)
from stage_gen.reliability import (
    atomic_write_bytes,
    atomic_write_json,
    write_artifact_with_provenance_async,
)

WORLD_HANDLER_VERSION = "prepared-world-v3"
#: Ceiling on the common period a map composite may need. Mixed layer periods multiply out through
#: their least common multiple, so this fails a pathological authored combination loudly instead of
#: allocating an unbounded review canvas.
#: The review board is rendered at the runtime's viewport height and tile size so a reviewer is
#: judging the same composition the player sees, not a differently-scaled approximation.
_COMPOSITE_VIEWPORT_HEIGHT_PX = 720
_COMPOSITE_TILE_PX = 64
_LAYER_NODE = re.compile(
    r"^map-(?P<map_id>.+)-layer-(?P<layer_id>[a-z0-9_]+)-(?P<action>generate|loop|validate)$"
)
_GROUND_NODE = re.compile(r"^map-(?P<map_id>.+)-ground-(?P<action>generate|validate)$")
_TERRAIN_NODE = re.compile(r"^map-(?P<map_id>.+)-terrain-generate$")
_PRESENTATION_NODE = re.compile(
    r"^map-(?P<map_id>.+)-(?P<asset>climbable|portal)-(?P<action>generate|validate)$"
)
_MAP_NODE = re.compile(r"^map-(?P<map_id>.+)-(?P<action>composite|review)$")


class PreparedWorldNodeHandler:
    """Dispatch map nodes while retaining provider operations in shared components."""

    def __init__(
        self,
        graph: ExecutionGraph,
        package: ResolvedGamePackage,
        *,
        run_dir: Path,
        cache_dir: Path,
        image_service: ImageGenerationService,
        structured_service: StructuredGenerationService[object],
        terrain_template_path: Path,
        terrain_topology_reference_path: Path,
    ) -> None:
        self._graph = graph
        self._package = package
        self._run_dir = run_dir
        self._cache_dir = cache_dir
        self._images = image_service
        self._structured = structured_service
        self._terrain_template_path = terrain_template_path
        self._terrain_topology_reference_path = terrain_topology_reference_path

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

    def _terrain(self, game_map: PreparedGameMap) -> PreparedMapTerrain:
        """Read this map's generated geometry, checked against what the map asked for.

        Geometry is an artifact, so it is read from the run the way a generated image is, and
        cross-checked here rather than trusted: a terrain file for the wrong map, or one that
        moved the walk-surface datum the painted scenery is anchored to, must not reach a
        composite or a manifest.
        """

        path = self._run_dir / terrain_artifact_path(game_map.map_id)
        terrain = load_prepared_map_terrain_bytes(path.read_bytes())
        validate_generated_terrain(game_map, terrain)
        return terrain

    async def _execute(self, node: ExecutionNode) -> NodeExecutionResult:
        if node.node_id == "package-resolve":
            path = self._run_dir / node.outputs[0]
            atomic_write_json(path, self._package.identity())
            return self._result(node, (path,), provider_operations=0)
        layer_match = _LAYER_NODE.fullmatch(node.node_id)
        if layer_match:
            game_map = self._map(layer_match["map_id"])
            layer = next(
                item for item in game_map.layers if item.layer_id == layer_match["layer_id"]
            )
            if layer_match["action"] == "generate":
                return await self._generate_layer(node, game_map, layer)
            if layer_match["action"] == "loop":
                return await self._construct_layer_loop(node, game_map, layer)
            return await self._validate_layer(node, layer)
        terrain_match = _TERRAIN_NODE.fullmatch(node.node_id)
        if terrain_match:
            return await self._generate_terrain(node, self._map(terrain_match["map_id"]))
        ground_match = _GROUND_NODE.fullmatch(node.node_id)
        if ground_match:
            game_map = self._map(ground_match["map_id"])
            if ground_match["action"] == "generate":
                return await self._generate_ground(node, game_map)
            return await self._validate_ground(node, game_map)
        presentation_match = _PRESENTATION_NODE.fullmatch(node.node_id)
        if presentation_match:
            game_map = self._map(presentation_match["map_id"])
            asset = cast(Literal["climbable", "portal"], presentation_match["asset"])
            if presentation_match["action"] == "generate":
                return await self._generate_map_presentation(node, game_map, asset)
            return await self._validate_map_presentation(node, game_map, asset)
        map_match = _MAP_NODE.fullmatch(node.node_id)
        if map_match:
            game_map = self._map(map_match["map_id"])
            if map_match["action"] == "composite":
                return await self._composite(node, game_map)
            return await self._review(node, game_map)
        raise ValueError(f"prepared world handler cannot execute node: {node.node_id}")

    async def _generate_terrain(
        self, node: ExecutionNode, game_map: PreparedGameMap
    ) -> NodeExecutionResult:
        """Compose this map's terrain from its authored brief.

        The map asks for a shape the way it asks for artwork, and the answer is an artifact. The
        designer's own retry loop is semantic regeneration -- it hands the validator's complaints
        back to the model in the model's own vocabulary -- and sits outside the provider retry
        owner, which stays inside the structured-generation service.
        """

        output = self._run_dir / node.outputs[0]
        output.parent.mkdir(parents=True, exist_ok=True)
        profile = terrain_profile(game_map)
        brief = DesignBrief(intent=self._map_prompt(game_map, game_map.terrain.brief))
        attempts = await design_chunks(
            self._structured,
            profile,
            brief,
            artifact_dir=output.parent / "terrain-design",
        )
        final = attempts[-1]
        if final.problems or final.designed is None:
            listed = "; ".join(final.problems[:6])
            raise ValueError(
                f"terrain design for {game_map.map_id} never satisfied the map's own rules after "
                f"{len(attempts)} attempt(s): {listed}"
            )
        terrain = compile_terrain(final.designed, game_map)
        validate_generated_terrain(game_map, terrain)
        atomic_write_json(output, json.loads(canonical_prepared_map_terrain_json(terrain)))
        return self._result(node, (output,), provider_operations=len(attempts))

    async def _generate_layer(
        self, node: ExecutionNode, game_map: PreparedGameMap, layer: PreparedMapLayer
    ) -> NodeExecutionResult:
        output = self._run_dir / node.outputs[0]
        prompt = self._map_prompt(game_map, layer.prompt) + (
            "\nOutput one horizontally seamless repeat unit. The left and right edges must join "
            "without a visible seam. "
        )
        transparent = layer.alpha_mode == "transparent"
        prompt += (
            "Isolate only this layer on a fully transparent background with true alpha."
            if transparent
            else "Output a completely opaque sky plate with no transparency."
        )
        references = self._image_references(game_map, layer.reference_ids)
        result = await self._images.generate(
            ImageGenerationRequest(
                prompt=prompt,
                artifact_path=output,
                input_references=references,
                quality="high",
                background="transparent" if transparent else "opaque",
                output_format="png",
                size="1536x1024",
                timeout_seconds=600,
                metadata={
                    "checkpoint": "world",
                    "map_id": game_map.map_id,
                    "layer_id": layer.layer_id,
                },
                validate=lambda artifact: _validate_provider_image(
                    artifact.data, width=1536, height=1024, transparent=transparent
                ),
            )
        )
        return self._result(
            node,
            (output, Path(result.provenance_path)),
            attempts=result.attempts,
            provider_operations=result.attempts,
        )

    async def _construct_layer_loop(
        self, node: ExecutionNode, game_map: PreparedGameMap, layer: PreparedMapLayer
    ) -> NodeExecutionResult:
        """Admit the generated layer as a loop, or construct one by the map's declared method."""

        generated = self._graph.node(node.depends_on[0])
        raw_data = (self._run_dir / generated.outputs[0]).read_bytes()
        alpha_policy, coverage = _layer_repeat_policies(layer)
        output, record_path = (self._run_dir / ref for ref in node.outputs)

        def admit(data: bytes) -> object:
            return validate_image_repeat(
                data,
                axis="x",
                alpha_policy=alpha_policy,
                coverage_policy=coverage,
                validation_policy=ImageRepeatValidationPolicy(),
            )

        # Admission first. A layer the model already returned as a clean repeat unit is published
        # untouched, which is both free and strictly better than constructing over it.
        admission = admit(raw_data)
        provider_operations = 0
        if admission.verdict == "pass":  # type: ignore[attr-defined]
            looped = raw_data
            record: dict[str, object] = {
                "schema_version": 1,
                "kind": "direct-loop-admission-v1",
                "construction": "none",
                "provider_operations": 0,
            }
        elif game_map.continuity.loop_construction == "mirror_repeat":
            looped, record = mirror_repeat(raw_data)
            record["construction"] = "mirror_repeat"
        else:
            conditioning = build_bridge_conditioning(
                raw_data,
                context_span=LOOP_BRIDGE_CONTEXT_SPAN_PX,
                bridge_span=LOOP_BRIDGE_SPAN_PX,
            )
            bridge_path = self._run_dir / f"{node.outputs[0].removesuffix('.loop.png')}.bridge.png"
            transparent = layer.alpha_mode == "transparent"
            generation = await self._images.generate(
                ImageGenerationRequest(
                    prompt=self._bridge_prompt(layer, conditioning),
                    artifact_path=bridge_path,
                    input_references=(
                        ImageReference(
                            _data_url(conditioning.conditioning_png, "image/png"),
                            "loop-bridge-conditioning",
                        ),
                    ),
                    mask_reference=ImageReference(
                        _data_url(conditioning.mask_png, "image/png"), "loop-bridge-mask"
                    ),
                    quality="high",
                    background="transparent" if transparent else "opaque",
                    output_format="png",
                    size=f"{conditioning.width}x{conditioning.height}",
                    timeout_seconds=600,
                    metadata={
                        "checkpoint": "world",
                        "map_id": game_map.map_id,
                        "layer_id": layer.layer_id,
                        "operation": "loop_bridge",
                    },
                )
            )
            provider_operations = generation.attempts
            try:
                looped, record = assemble_generated_bridge(
                    raw_data,
                    bridge_path.read_bytes(),
                    conditioning=conditioning,
                    anchor_band=LOOP_BRIDGE_ANCHOR_BAND_PX,
                )
                record["construction"] = "generated_bridge"
            except BridgeRegistrationError as error:
                # The return is a different composition, not a displaced copy, so no translation
                # lands it. Mirroring is the construction that cannot fail, so the map still gets
                # a usable loop unit and the rejection is recorded rather than shipped as art.
                looped, record = mirror_repeat(raw_data)
                record["construction"] = "mirror_repeat"
                record["bridge_rejected"] = str(error)
            record["provider_operations"] = provider_operations
        report = admit(looped)
        if report.verdict != "pass":  # type: ignore[attr-defined]
            raise ValueError(
                f"constructed loop for {game_map.map_id}/{layer.layer_id} failed x-repeat admission"
            )
        record["repeat"] = report.model_dump(mode="json")  # type: ignore[attr-defined]
        sidecar = await _write_local_image(
            output,
            looped,
            model=record["kind"],  # type: ignore[arg-type]
            prompt="Admit or construct the layer's horizontal loop unit.",
            source_ref=generated.outputs[0],
            source_data=raw_data,
            validation=record,
        )
        atomic_write_json(record_path, record)
        return self._result(
            node, (output, sidecar, record_path), provider_operations=provider_operations
        )

    async def _validate_layer(
        self, node: ExecutionNode, layer: PreparedMapLayer
    ) -> NodeExecutionResult:
        looped = self._graph.node(node.depends_on[0])
        raw_path = self._run_dir / looped.outputs[0]
        raw_data = raw_path.read_bytes()
        construction = json.loads((self._run_dir / looped.outputs[1]).read_bytes())
        alpha_policy, coverage = _layer_repeat_policies(layer)
        canonical = raw_data
        report = validate_image_repeat(
            canonical,
            axis="x",
            alpha_policy=alpha_policy,
            coverage_policy=coverage,
            validation_policy=ImageRepeatValidationPolicy(),
        )
        if report.verdict != "pass":
            raise ValueError("constructed map layer failed deterministic x-repeat validation")
        trimmed, trim = trim_layer_to_alpha_box(canonical)
        trim_report = validate_image_repeat(
            trimmed,
            axis="x",
            alpha_policy=alpha_policy,
            coverage_policy=coverage,
            validation_policy=ImageRepeatValidationPolicy(),
        )
        if trim_report.verdict != "pass":
            # The bytes that ship must be the bytes that passed. Trimming empty rows can change
            # the edge statistics, so the artifact is re-admitted after the trim rather than
            # inheriting a verdict earned by a raster we no longer publish.
            raise ValueError("trimmed map layer failed deterministic x-repeat validation")
        placement = _resolve_layer_placement(layer, trim)
        output, validation_path, preview_path = (self._run_dir / ref for ref in node.outputs)
        sidecar = await _write_local_image(
            output,
            trimmed,
            model=LAYER_PLACEMENT_CANONICALIZER,
            prompt=(
                "Trim the constructed map loop unit to its alpha box vertically while preserving "
                "the repeat period."
            ),
            source_ref=looped.outputs[0],
            source_data=raw_data,
            validation={
                "construction": construction,
                "repeat": trim_report.model_dump(mode="json"),
                "trim": trim,
                "placement": placement,
            },
        )
        atomic_write_json(
            validation_path,
            {
                "repeat": trim_report.model_dump(mode="json"),
                "trim": trim,
                "placement": placement,
            },
        )
        atomic_write_bytes(preview_path, _bounded_repeat_preview(trimmed))
        return self._result(
            node, (output, sidecar, validation_path, preview_path), provider_operations=0
        )

    async def _generate_ground(
        self, node: ExecutionNode, game_map: PreparedGameMap
    ) -> NodeExecutionResult:
        output = self._run_dir / node.outputs[0]
        style = self._package.game.style
        material_direction = (
            f"{game_map.ground.prompt.strip()} Target style: {style.label}; "
            f"{', '.join(style.keywords)}."
        )
        prompt = terrain_atlas_generation_prompt(material_direction)
        template = self._terrain_template_path.read_bytes()
        topology_reference = self._terrain_topology_reference_path.read_bytes()
        references = (
            ImageReference(
                url=_data_url(template, "image/png"),
                provenance_ref=(
                    "resource://image_gen_templates/terrain_atlas_12x4_template.png"
                    f"#sha256={hashlib.sha256(template).hexdigest()}"
                ),
            ),
            ImageReference(
                url=_data_url(topology_reference, "image/png"),
                provenance_ref=(
                    "resource://image_gen_templates/"
                    "terrain_atlas_godot_topology_reference.png"
                    f"#sha256={hashlib.sha256(topology_reference).hexdigest()}"
                ),
            ),
            *self._image_references(game_map, game_map.ground.reference_ids),
        )
        result = await self._images.generate(
            ImageGenerationRequest(
                prompt=prompt,
                artifact_path=output,
                input_references=references,
                quality="high",
                background="opaque",
                output_format="png",
                size="auto",
                timeout_seconds=600,
                metadata={
                    "checkpoint": "world",
                    "map_id": game_map.map_id,
                    "ground_mode": game_map.ground.mode,
                },
                validate=lambda artifact: require_terrain_atlas_source(
                    artifact.data,
                    template=template,
                ),
            )
        )
        return self._result(
            node,
            (output, Path(result.provenance_path)),
            attempts=result.attempts,
            provider_operations=result.attempts,
        )

    async def _validate_ground(
        self, node: ExecutionNode, game_map: PreparedGameMap
    ) -> NodeExecutionResult:
        generated = self._graph.node(node.depends_on[0])
        raw_path = self._run_dir / generated.outputs[0]
        raw = raw_path.read_bytes()
        canonical, validation = assemble_terrain_atlas(
            raw,
            template=self._terrain_template_path.read_bytes(),
        )
        if validation["classification"] != "direct_pass":
            raise ValueError("dynamic terrain atlas validation requires direct_pass media")
        output, validation_path, evidence_path = (self._run_dir / ref for ref in node.outputs)
        sidecar = await _write_local_image(
            output,
            canonical,
            model=MATERIAL_ASSEMBLER_ID,
            prompt=(
                "Slice the model-painted 12x4 guide lattice, extract deterministic chroma alpha, "
                "apply the authoritative 47-mask lookup, harmonize only legal connector edges, "
                "and assemble the canonical atlas deterministically."
            ),
            source_ref=generated.outputs[0],
            source_data=raw,
            validation=validation,
        )
        atomic_write_json(validation_path, validation)
        occupancy = self._terrain(game_map).occupancy
        evidence, _ = compose_canonical_terrain(canonical, occupancy)
        evidence_sidecar = await _write_local_image(
            evidence_path,
            evidence,
            model="terrain-atlas-authored-occupancy-preview-v1",
            prompt="Compose the canonical terrain atlas through the map-authored binary occupancy.",
            source_ref=output.relative_to(self._run_dir).as_posix(),
            source_data=canonical,
            validation={
                "occupancy_rows": len(occupancy),
                "occupancy_columns": len(occupancy[0]),
                "map_id": game_map.map_id,
            },
        )
        return self._result(
            node,
            (output, sidecar, validation_path, evidence_path, evidence_sidecar),
            provider_operations=0,
        )

    async def _generate_map_presentation(
        self,
        node: ExecutionNode,
        game_map: PreparedGameMap,
        asset: Literal["climbable", "portal"],
    ) -> NodeExecutionResult:
        output = self._run_dir / node.outputs[0]
        roles: Sequence[ClimbableRole] | None = None
        mode: str
        if asset == "climbable":
            climbable = game_map.climbable
            if climbable is None:
                raise ValueError(f"map {game_map.map_id} does not declare climbable")
            variants = climbable.variants
            roles = [climbable.role_of(entry.variant_id) for entry in variants]
            plan = plan_climbable_atlas(len(variants))
            expected_size = (plan.width_px, plan.height_px)
            size = plan.size
            mode = climbable.mode
            reference_ids = climbable.reference_ids
            roster = "\n".join(
                f"  {index + 1}. {role} — {entry.prompt.strip()}"
                for index, (entry, role) in enumerate(zip(variants, roles, strict=True))
            )
            prompt = self._map_prompt(
                game_map,
                "Create one atlas sheet of this map's climbing routes. Every route is maintained "
                "by the same hands, so they share one palette, one line weight, and one world "
                f"scale.\n\nDraw exactly {len(variants)} climbable objects, left to right in a "
                f"single row, in this order:\n{roster}",
            ) + (
                f"\nLayout contract, follow exactly:\nExactly {len(variants)} objects. Not one "
                "more, not one fewer. No duplicates, no coils, no spares, no extra strands, no "
                "stacked copies.\nSpace them evenly across the canvas in one row, each wholly "
                "inside its own vertical column, with a wide fully transparent vertical gap "
                "between neighbours that no object crosses or touches.\nEvery object spans the "
                "same vertical height at the same world scale: all tops level with each other, "
                "all bottoms level with each other, each one tall and narrow.\nEach object is "
                "one continuous connected piece from its top end to its bottom end, with no "
                "break, no gap, and no loose end drifting sideways. Keep each near-vertical.\n"
                "Leave a clear transparent margin at the left, right, top, and bottom.\nUse a "
                "fully transparent exterior with no floor, scenery, shadow, labels, caption, "
                "number, border, frame, panel divider, character, or creature."
            )
        else:
            portal = game_map.portal
            if portal is None:
                raise ValueError(f"map {game_map.map_id} does not declare portal")
            expected_size = (1536, 1024)
            size = "1536x1024"
            mode = portal.mode
            reference_ids = portal.reference_ids
            prompt = self._map_prompt(game_map, portal.prompt) + (
                "\nCreate exactly two complete isolated portal structures in one horizontal "
                "row: entry on the left and exit on the right. Keep each portal wholly inside "
                "its own half with a wide transparent separator. Both bases must be level and "
                "the two structures must be the same world scale. Use a fully transparent "
                "exterior with no floor, scenery, shadow, labels, border, character, or extra "
                "portal."
            )
        result = await self._images.generate(
            ImageGenerationRequest(
                prompt=prompt,
                artifact_path=output,
                input_references=self._image_references(game_map, reference_ids),
                quality="high",
                background="transparent",
                output_format="png",
                size=size,
                timeout_seconds=900,
                metadata={
                    "checkpoint": "world",
                    "map_id": game_map.map_id,
                    "map_asset": asset,
                    "mode": mode,
                },
                validate=lambda artifact: _validate_map_presentation_source(
                    artifact.data, asset=asset, expected_size=expected_size, roles=roles
                ),
            )
        )
        return self._result(
            node,
            (output, Path(result.provenance_path)),
            attempts=result.attempts,
            provider_operations=result.attempts,
        )

    async def _validate_map_presentation(
        self,
        node: ExecutionNode,
        game_map: PreparedGameMap,
        asset: Literal["climbable", "portal"],
    ) -> NodeExecutionResult:
        generated = self._graph.node(node.depends_on[0])
        raw_path = self._run_dir / generated.outputs[0]
        raw = raw_path.read_bytes()
        roles: Sequence[ClimbableRole] | None = None
        if asset == "climbable":
            climbable = game_map.climbable
            if climbable is None:
                raise ValueError(f"map {game_map.map_id} does not declare climbable")
            roles = [climbable.role_of(entry.variant_id) for entry in climbable.variants]
        canonical, validation = _canonicalize_map_presentation(raw, asset=asset, roles=roles)
        output, validation_path = (self._run_dir / ref for ref in node.outputs)
        sidecar = await _write_local_image(
            output,
            canonical,
            model=f"prepared-map-{asset}-alpha-component-repack-v1",
            prompt=f"Isolate and repack the map-local {asset} presentation.",
            source_ref=generated.outputs[0],
            source_data=raw,
            validation=validation,
        )
        atomic_write_json(validation_path, validation)
        return self._result(
            node,
            (output, sidecar, validation_path),
            provider_operations=0,
        )

    async def _composite(
        self, node: ExecutionNode, game_map: PreparedGameMap
    ) -> NodeExecutionResult:
        backgrounds = sorted(
            (layer for layer in game_map.layers if layer.plane == "background"),
            key=lambda item: item.order,
        )
        foregrounds = sorted(
            (layer for layer in game_map.layers if layer.plane == "foreground"),
            key=lambda item: item.order,
        )
        ordered = [*backgrounds, *foregrounds]

        def layer_path(layer: PreparedMapLayer) -> Path:
            return self._run_dir / f"maps/{game_map.map_id}/layers/{layer.layer_id}.png"

        # Loop construction leaves layers on different periods: an admitted layer keeps its
        # generated width, a mirrored one doubles it, a bridged one grows by the bridge span. The
        # composite has to be one whole number of periods for every layer at once, or it stops
        # being the thing the runtime shows. Compositing straight over a wider layer silently crops
        # it, so tile each layer up to the common period instead.
        periods: list[int] = []
        heights: list[int] = []
        for layer in ordered:
            with Image.open(layer_path(layer)) as opened:
                periods.append(opened.width)
                heights.append(opened.height)
        if not periods:
            raise ValueError("map composite has no declared layers")
        # The board is review evidence for one stretch of the map, not a runtime loop unit, so it
        # spans the widest layer period rather than the least common multiple of all of them. The
        # authored terrain in the middle is not periodic at any width, so an LCM canvas would only
        # stretch the ground further while still not repeating.
        common = max(periods)
        # Layers are published trimmed to their alpha box, so pasting them at the canvas top would
        # show a stack of floating bands rather than the composed map. The board applies the same
        # resolved placement the runtime does, which is the whole point of measuring it once.
        placements = {
            layer.layer_id: json.loads(
                (
                    self._run_dir
                    / f"maps/{game_map.map_id}/layers/{layer.layer_id}.validation.json"
                ).read_bytes()
            )["placement"]
            for layer in ordered
        }
        canvas_height = _COMPOSITE_VIEWPORT_HEIGHT_PX
        terrain = self._terrain(game_map)
        rows = len(terrain.occupancy)
        walk_surface_y = canvas_height - ((rows - terrain.walk_surface_row) * _COMPOSITE_TILE_PX)
        composite_width = round(common * canvas_height / max(heights))

        def place(layer: PreparedMapLayer, image: Image.Image) -> None:
            placement = placements[layer.layer_id]
            scale = canvas_height / int(placement["source_height"])
            rendered_height = max(1, round(int(placement["trimmed_height"]) * scale))
            rendered = image.resize(
                (max(1, round(image.width * scale)), rendered_height), Image.Resampling.LANCZOS
            )
            top = _composite_layer_top(
                anchor=str(placement["vertical_anchor"]),
                offset=float(placement["vertical_offset"]),
                rendered_height=rendered_height,
                canvas_height=canvas_height,
                walk_surface_y=walk_surface_y,
            )
            for left in range(0, composite_width, rendered.width):
                canvas.alpha_composite(rendered, (left, round(top)))

        canvas = Image.new("RGBA", (composite_width, canvas_height), (0, 0, 0, 0))
        for layer in backgrounds:
            with Image.open(layer_path(layer)) as opened:
                place(layer, opened.convert("RGBA"))
        ground_path = self._run_dir / f"maps/{game_map.map_id}/ground.png"
        canvas.alpha_composite(_ground_preview(ground_path, canvas.size, terrain.occupancy))
        for layer in foregrounds:
            with Image.open(layer_path(layer)) as opened:
                place(layer, opened.convert("RGBA"))
        stream = io.BytesIO()
        canvas.save(stream, format="PNG", optimize=False)
        data = stream.getvalue()
        # Loop admission now happens per layer against the real validator, and each layer's verdict
        # is recorded in its own loop and validation records. Re-asserting it over a composite that
        # also contains non-periodic authored terrain would be checking a different, ill-defined
        # property, so the composite carries the per-layer verdicts as evidence instead.
        layer_periods = {
            layer.layer_id: period for layer, period in zip(ordered, periods, strict=True)
        }
        output = self._run_dir / node.outputs[0]
        inputs = [
            (
                f"maps/{game_map.map_id}/layers/{layer.layer_id}.png",
                (
                    self._run_dir / f"maps/{game_map.map_id}/layers/{layer.layer_id}.png"
                ).read_bytes(),
            )
            for layer in ordered
        ]
        inputs.append((f"maps/{game_map.map_id}/ground.png", ground_path.read_bytes()))
        sidecar = await _write_local_image_multi(
            output,
            data,
            model="prepared-map-placed-compositor-v6",
            prompt="Composite authored map layers at their resolved placement, plane, and order.",
            inputs=inputs,
            validation={
                "layer_count": len(ordered),
                "ground_projected": True,
                "layer_periods": layer_periods,
                "composite_period": common,
                "width": canvas.width,
                "height": canvas.height,
            },
        )
        return self._result(node, (output, sidecar), provider_operations=0)

    async def _review(self, node: ExecutionNode, game_map: PreparedGameMap) -> NodeExecutionResult:
        output = self._run_dir / node.outputs[0]
        composite_path = self._run_dir / f"maps/{game_map.map_id}/composite.png"
        ground_path = self._run_dir / f"maps/{game_map.map_id}/ground.png"
        ground_evidence_path = self._run_dir / f"maps/{game_map.map_id}/ground.evidence.png"
        references = [
            StructuredReference(
                url=_data_url(composite_path.read_bytes(), "image/png"),
                provenance_ref=f"run://{composite_path.relative_to(self._run_dir).as_posix()}",
            ),
            StructuredReference(
                url=_data_url(ground_evidence_path.read_bytes(), "image/png"),
                provenance_ref=(
                    f"run://{ground_evidence_path.relative_to(self._run_dir).as_posix()}"
                ),
            ),
            StructuredReference(
                url=_data_url(ground_path.read_bytes(), "image/png"),
                provenance_ref=f"run://{ground_path.relative_to(self._run_dir).as_posix()}",
            ),
        ]
        declared_presentations: list[str] = []
        for asset in ("portal", "climbable"):
            direction = game_map.portal if asset == "portal" else game_map.climbable
            if direction is None:
                continue
            path = self._run_dir / f"maps/{game_map.map_id}/{asset}.png"
            references.append(
                StructuredReference(
                    url=_data_url(path.read_bytes(), "image/png"),
                    provenance_ref=f"run://{path.relative_to(self._run_dir).as_posix()}",
                )
            )
            declared_presentations.append(asset)
        for ref in game_map.references:
            package_file = self._package.file(ref.source)
            references.append(
                StructuredReference(
                    url=_data_url(package_file.data, _media_type(ref.source)),
                    provenance_ref=f"package://{self._package.game.game_id}/{ref.source}#sha256={package_file.sha256}",
                )
            )
        for layer in sorted(
            game_map.layers, key=lambda item: (item.plane == "foreground", item.order)
        ):
            layer_path = self._run_dir / f"maps/{game_map.map_id}/layers/{layer.layer_id}.png"
            repeat_path = (
                self._run_dir / f"maps/{game_map.map_id}/layers/{layer.layer_id}.repeat.png"
            )
            references.extend(
                (
                    StructuredReference(
                        url=_data_url(layer_path.read_bytes(), "image/png"),
                        provenance_ref=(
                            f"run://{layer_path.relative_to(self._run_dir).as_posix()}"
                        ),
                    ),
                    StructuredReference(
                        url=_data_url(repeat_path.read_bytes(), "image/png"),
                        provenance_ref=(
                            f"run://{repeat_path.relative_to(self._run_dir).as_posix()}"
                        ),
                    ),
                )
            )
        schema = StructuredOutputSchema(name="prepared_map_review", json_schema=_review_schema())
        result = await self._structured.generate(
            StructuredGenerationRequest(
                prompt=(
                    f"Review the generated map artifacts for {game_map.display_name}. "
                    "Image 1 is the layer composite, image 2 is the deterministic authored-"
                    "occupancy terrain composition, and image 3 is the canonical 47-mask "
                    f"ground atlas. The next images are the declared map-local presentation "
                    f"assets in this exact order: {declared_presentations}. The next image is "
                    "the authored reference. Remaining images alternate "
                    "between one isolated canonical layer and its checkerboard three-repeat "
                    "evidence, in declared painter order. Transparent empty edge space is an "
                    "intentional clean wrap boundary, not missing art. Judge reference fidelity, "
                    "layer separation, style coherence, side-view playfield readability, "
                    "horizontal looping continuity from the repeat evidence, ground topology "
                    "and material compatibility, and the functional readability, isolation, "
                    "scale coherence, and map-style fidelity of every declared portal or "
                    "climbable. "
                    "A looping strip has no privileged horizontal origin: a pure "
                    "cyclic x-translation of landmarks is compositionally equivalent and must "
                    "not reduce reference fidelity. Report concrete evidence; uncertainty must "
                    "not be called accept."
                ),
                system=(
                    "You are a strict game-art technical director. Return only the "
                    "requested structured review."
                ),
                artifact_path=output,
                schema=schema,
                parse=_parse_review,
                references=tuple(references),
                max_tokens=1800,
                timeout_seconds=600,
                metadata={"checkpoint": "world", "map_id": game_map.map_id},
            )
        )
        return self._result(
            node,
            (output, Path(result.provenance_path)),
            attempts=result.attempts,
            provider_operations=result.attempts,
        )

    def _map(self, map_id: str) -> PreparedGameMap:
        return next(item for item in self._package.maps if item.map_id == map_id)

    def _map_prompt(self, game_map: PreparedGameMap, specific: str) -> str:
        universe = self._package.file(self._package.game.universe.source).data.decode("utf-8")
        style = self._package.game.style
        return (
            f"Bellweather universe context:\n{universe}\n\nVisual style: {style.label}. "
            f"Use: {', '.join(style.keywords)}. Avoid: {', '.join(style.avoid)}.\n\n"
            f"Map contract: fixed 2D side view, scrolling x-axis, seamless horizontal continuity.\n"
            f"Map asset task:\n{specific}"
        )

    def _bridge_prompt(self, layer: PreparedMapLayer, conditioning: BridgeConditioning) -> str:
        """Brief the provider for a join, not for a layer.

        The layer's own brief is a *generation* brief: it asks for landmarks, a windmill, a
        centred rhythm. Sending it here asks for a new composition and gets one, which is what
        puts an invented object across the cut line. Only the material description survives, and
        it is explicitly demoted below the join constraints.
        """

        style = self._package.game.style
        material = " ".join(layer.prompt.split())
        alpha = (
            "This is a cut-out layer. Every region that is transparent in the supplied image must "
            "stay fully transparent in yours: above the content, below it, and around it. Paint "
            "only the same band of content the left and right sides occupy, at the same top and "
            "bottom extent. Add no ground, no water, no horizon fill, no backdrop, no matte, and "
            "no vignette. Use true alpha, not a colour approximating emptiness."
            if layer.alpha_mode == "transparent"
            else "Keep the plate completely opaque."
        )
        return (
            "Image continuation task. The supplied image is one horizontal strip of side-view "
            "game art with an empty gap in the middle.\n\n"
            f"The left {conditioning.context_span} pixels and the right "
            f"{conditioning.context_span} pixels are FINISHED ARTWORK. Reproduce them exactly as "
            "given: pixel for pixel, same position, same scale, same vertical alignment. Do not "
            "move, shift, rescale, recompose, restyle, or redraw them. Do not add, remove, or "
            "relocate any object in them.\n\n"
            f"Only the middle {conditioning.bridge_span} pixels are empty. Paint that span so the "
            "artwork at the left edge of the gap continues into the artwork at the right edge as "
            "one unbroken band. Match the existing line weight, palette, lighting, ground line, "
            "and horizon exactly.\n\n"
            "Everything you paint must sit entirely inside the middle span. Do not place any "
            "object across the gap's boundary. Do not introduce a landmark, a centrepiece, a "
            "frame, a midpoint feature, or text.\n\n"
            f"Visual style: {style.label}. Avoid: {', '.join(style.avoid)}.\n"
            f"Material reference, describing what this layer is made of and not how to compose "
            f"it: {material}\n"
            "Ignore anything in that reference about landmarks, rhythm, centring, or "
            f"composition.\n\n{alpha}"
        )

    def _image_references(
        self, game_map: PreparedGameMap, reference_ids: list[str]
    ) -> tuple[ImageReference, ...]:
        by_id = {item.reference_id: item for item in game_map.references}
        values = []
        for reference_id in reference_ids:
            ref = by_id[reference_id]
            entry = self._package.file(ref.source)
            values.append(
                ImageReference(
                    url=_data_url(entry.data, _media_type(ref.source)),
                    provenance_ref=f"package://{self._package.game.game_id}/{ref.source}#sha256={entry.sha256}",
                )
            )
        return tuple(values)

    def _result(
        self,
        node: ExecutionNode,
        paths: tuple[Path, ...],
        *,
        attempts: int = 1,
        provider_operations: int,
    ) -> NodeExecutionResult:
        artifacts = tuple(_node_artifact(self._run_dir, path) for path in paths)
        return NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=attempts,
            provider_operations=provider_operations,
            artifacts=artifacts,
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
        root = self._cache_dir / "prepared-world-v1" / node.cache_key[:2] / node.cache_key
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
        for index, value in enumerate(outputs):
            if not isinstance(value, dict) or not isinstance(value.get("artifact_ref"), str):
                return None
            try:
                data = (artifacts_dir / f"{index}.bin").read_bytes()
            except OSError:
                return None
            if _sha(data) != value.get("sha256") or len(data) != value.get("bytes"):
                return None
            target = self._run_dir / value["artifact_ref"]
            atomic_write_bytes(target, data)
            restored.append(NodeArtifact.model_validate(value))
        return NodeExecutionResult(
            cache=CacheDisposition.HIT,
            attempts=1,
            provider_operations=0,
            artifacts=tuple(restored),
            known_cost_usd=0.0,
        )

    def _write_cache(
        self, node: ExecutionNode, context: NodeExecutionContext, result: NodeExecutionResult
    ) -> None:
        record_path, artifacts_dir = self._cache_paths(node)
        for index, artifact in enumerate(result.artifacts):
            atomic_write_bytes(
                artifacts_dir / f"{index}.bin", (self._run_dir / artifact.artifact_ref).read_bytes()
            )
        atomic_write_json(
            record_path,
            {
                "schema_version": 1,
                "kind": "prepared-world-node-cache-v1",
                "cache_key": node.cache_key,
                "node_id": node.node_id,
                "lineage": self._lineage(node, context),
                "artifacts": [item.model_dump(mode="json") for item in result.artifacts],
            },
        )


def world_target_node_ids(package: ResolvedGamePackage) -> tuple[str, ...]:
    return tuple(f"map-{game_map.map_id}-review" for game_map in package.maps)


def _layer_repeat_policies(
    layer: PreparedMapLayer,
) -> tuple[Literal["preserve", "require_opaque"], Literal["sparse_allowed", "continuous"]]:
    """Return the alpha and coverage admission policies implied by a layer's alpha mode."""

    if layer.alpha_mode == "transparent":
        return "preserve", "sparse_allowed"
    return "require_opaque", "continuous"


def _composite_layer_top(
    *,
    anchor: str,
    offset: float,
    rendered_height: int,
    canvas_height: int,
    walk_surface_y: int,
) -> float:
    """Mirror the consumer's layer placement so the review board matches the runtime exactly."""

    if anchor == "canvas_cover":
        return 0.0
    if anchor == "screen_top":
        return offset * rendered_height
    if anchor == "screen_center":
        return canvas_height / 2 - rendered_height / 2 + offset * rendered_height
    datum = canvas_height if anchor == "screen_bottom" else walk_surface_y
    return datum - (1 - offset) * rendered_height


def _resolve_layer_placement(layer: PreparedMapLayer, trim: dict[str, object]) -> dict[str, object]:
    """Resolve one layer's vertical placement from its declared anchor and measured raster.

    The author declares intent from a closed vocabulary; the fraction is measured here, because an
    authored fraction would be a prediction about pixels that did not exist when it was written. An
    explicit override is honoured, but a bottom-registered override that cannot reach the
    full-coverage line is rejected against the exact measured minimum rather than silently leaving
    a gap the runtime would fill with whatever sits behind the layer.
    """

    minimum: float | None = None
    if layer.vertical_anchor == "screen_bottom":
        # Sealing the frame edge is the one case that needs every column covered: a gap between
        # content shows whatever sits behind the layer, which at the screen edge is the sky plate.
        minimum = seal_offset_fraction(trim)
        if minimum is None:
            raise ValueError(
                f"map layer {layer.layer_id} anchors to screen_bottom but no row is spanned by "
                "every column, so it can never seal"
            )
    elif layer.vertical_anchor == "walk_surface":
        # Meeting the ground is a different question. A midground layer is legitimately sparse —
        # a village has sky between its buildings — so it registers on the row its content rests
        # on rather than on a full-coverage row it may not have.
        minimum = content_bottom_offset_fraction(trim)
    resolved = minimum if minimum is not None else 0.0
    source = "measured"
    if layer.vertical_offset is not None:
        if minimum is not None and layer.vertical_offset < minimum:
            raise ValueError(
                f"map layer {layer.layer_id} declares vertical_offset "
                f"{layer.vertical_offset} but sealing requires at least {minimum}"
            )
        resolved = layer.vertical_offset
        source = "authored"
    return {
        "schema_version": 1,
        "kind": LAYER_PLACEMENT_CANONICALIZER,
        "vertical_anchor": layer.vertical_anchor,
        "vertical_offset": resolved,
        "vertical_offset_source": source,
        "minimum_seal_offset": minimum,
        "source_height": trim["source_height"],
        "trimmed_height": trim["trimmed_height"],
        "trimmed_top": trim["trimmed_top"],
        "trimmed_bottom": trim["trimmed_bottom"],
        "bounds": trim["bounds"],
    }


def _canonicalize_x_wrap(
    data: bytes,
    *,
    alpha_policy: Literal["preserve", "require_opaque"],
    coverage_policy: Literal["sparse_allowed", "continuous"],
) -> tuple[bytes, dict[str, object]]:
    with Image.open(io.BytesIO(data)) as opened:
        source = opened.convert("RGBA")
    if alpha_policy == "require_opaque":
        offset = source.width // 2
        return _png_bytes(ImageChops.offset(source, offset, 0)), {
            "algorithm": "circular-offset-v1",
            "offset_x": offset,
            "source_width": source.width,
        }

    scored: list[tuple[float, int, float, float]] = []
    for x in range(16, source.width - 16):
        left = source.crop((x - 1, 0, x, source.height))
        right = source.crop((x, 0, x + 1, source.height))
        channel_difference = ImageStat.Stat(ImageChops.difference(left, right)).mean
        alpha_fraction = (
            ImageStat.Stat(left.getchannel("A")).mean[0]
            + ImageStat.Stat(right.getchannel("A")).mean[0]
        ) / 510
        average_difference = sum(channel_difference) / len(channel_difference)
        score = alpha_fraction * 2 + average_difference / 255
        scored.append((score, x, alpha_fraction, average_difference))
    candidates: list[tuple[float, int, float, float]] = []
    for candidate in sorted(scored):
        if all(abs(candidate[1] - selected[1]) > 32 for selected in candidates):
            candidates.append(candidate)
        if len(candidates) == 12:
            break
    policy = ImageRepeatValidationPolicy()
    for score, cut_x, alpha_fraction, average_difference in candidates:
        offset = source.width - cut_x
        candidate_data = _png_bytes(ImageChops.offset(source, offset, 0))
        report = validate_image_repeat(
            candidate_data,
            axis="x",
            alpha_policy=alpha_policy,
            coverage_policy=coverage_policy,
            validation_policy=policy,
        )
        if report.verdict == "pass":
            return candidate_data, {
                "algorithm": "minimum-alpha-circular-offset-v1",
                "cut_x": cut_x,
                "offset_x": offset,
                "score": round(score, 6),
                "alpha_fraction": round(alpha_fraction, 6),
                "average_channel_difference": round(average_difference, 6),
                "candidate_count": len(candidates),
                "source_width": source.width,
            }

    half = source.resize((source.width // 2, source.height), Image.Resampling.LANCZOS)
    image = Image.new("RGBA", source.size, (0, 0, 0, 0))
    image.alpha_composite(half, (0, 0))
    image.alpha_composite(ImageOps.mirror(half), (half.width, 0))
    fallback = _png_bytes(image)
    report = validate_image_repeat(
        fallback,
        axis="x",
        alpha_policy=alpha_policy,
        coverage_policy=coverage_policy,
        validation_policy=policy,
    )
    if report.verdict != "pass":
        raise ValueError("mirror-fit fallback failed deterministic x-repeat validation")
    return fallback, {
        "algorithm": "mirror-fit-fallback-v1",
        "source_width": source.width,
        "output_width": image.width,
        "candidate_count": len(candidates),
    }


def _png_bytes(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def _bounded_repeat_preview(data: bytes) -> bytes:
    preview_data = build_three_repeat_preview(data, axis="x")
    with Image.open(io.BytesIO(preview_data)) as opened:
        preview = opened.convert("RGB")
    if preview.width > 4_608:
        target_height = round(preview.height * 4_608 / preview.width)
        preview = preview.resize((4_608, target_height), Image.Resampling.LANCZOS)
    stream = io.BytesIO()
    preview.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def _ground_preview(
    path: Path, size: tuple[int, int], occupancy: tuple[str, ...] | list[str]
) -> Image.Image:
    atlas = path.read_bytes()
    composed, _ = compose_canonical_terrain(atlas, occupancy)
    with Image.open(io.BytesIO(composed)) as opened:
        ground = opened.convert("RGBA")
    preview = Image.new("RGBA", size, (0, 0, 0, 0))
    target_height = max(1, round(ground.height * size[0] / ground.width))
    if target_height > size[1] // 2:
        target_height = size[1] // 2
    projected = ground.resize((size[0], target_height), Image.Resampling.LANCZOS)
    preview.alpha_composite(projected, (0, size[1] - target_height))
    return preview


def _map_presentation_contract(
    asset: Literal["climbable", "portal"],
    *,
    subjects: int,
) -> AlphaComponentRepackContract:
    # The selector keeps the N largest components. A rope carries a small fraction of a ladder's
    # area, so the candidacy floor is set from the roster rather than a constant: too high and a
    # legitimate thin strand is never a candidate.
    return AlphaComponentRepackContract(
        rows=1,
        columns=subjects,
        required_cells=subjects,
        gutter=16,
        minimum_component_fraction=min(0.01, 0.15 / subjects),
        anchor="bottom",
    )


def _canonicalize_map_presentation(
    data: bytes,
    *,
    asset: Literal["climbable", "portal"],
    roles: Sequence[ClimbableRole] | None = None,
) -> tuple[bytes, dict[str, object]]:
    """Repack the sheet into one canonical cell per declared subject.

    ``roles`` is the authored atlas order for a climbable sheet. Cell index is roster index: that
    binding is positional and unverified within a role, exactly as the dialogue expression atlas
    binds its expressions. What is verified is that each declared subject survives with a
    silhouette its own role admits, and that the sheet shares one world scale.
    """

    subjects = 2 if asset == "portal" else len(roles or ())
    if asset == "climbable" and subjects < 1:
        raise ValueError("map climbable repack requires the declared atlas order")
    canonical, report = repack_alpha_components(
        data, _map_presentation_contract(asset, subjects=subjects)
    )
    placements = report.get("placements")
    if not isinstance(placements, list) or len(placements) != subjects:
        raise ValueError(f"map {asset} repack did not preserve the required subjects")
    # A dropped component means a declared subject may have been replaced by contamination that
    # merely had more area. That is a rejection, not a warning.
    warnings = report.get("warnings")
    if isinstance(warnings, list) and "unselected_alpha_components_were_dropped" in warnings:
        raise ValueError(
            f"map {asset} repack dropped an alpha component; the sheet carries more subjects "
            "than the map declares"
        )
    dimensions: list[dict[str, int]] = []
    for placement in placements:
        if not isinstance(placement, dict):
            raise ValueError(f"map {asset} repack placement is invalid")
        target = placement.get("target_bbox")
        if (
            not isinstance(target, list)
            or len(target) != 4
            or not all(isinstance(value, int) for value in target)
        ):
            raise ValueError(f"map {asset} repack target geometry is invalid")
        width = target[2] - target[0]
        height = target[3] - target[1]
        if width <= 0 or height <= 0:
            raise ValueError(f"map {asset} repack subject is empty")
        dimensions.append({"width": width, "height": height})
    if asset == "climbable":
        assert roles is not None
        for index, (role, size) in enumerate(zip(roles, dimensions, strict=True)):
            if not role_aspect_admits(role, size["width"], size["height"]):
                low, high = ROLE_ASPECT_ENVELOPE[role]
                raise ValueError(
                    f"map climbable column {index} does not hold a {role} silhouette: "
                    f"height/width {size['height'] / size['width']:.1f} outside [{low}, {high}]"
                )
        parity = max(item["height"] for item in dimensions) / min(
            item["height"] for item in dimensions
        )
        if parity > MAX_HEIGHT_PARITY:
            raise ValueError(
                f"map climbable variants must share one world scale: height parity {parity:.2f} "
                f"exceeds {MAX_HEIGHT_PARITY}"
            )
    if asset == "portal":
        height_ratio = max(item["height"] for item in dimensions) / min(
            item["height"] for item in dimensions
        )
        if height_ratio > 1.35:
            raise ValueError("map portal pair must retain compatible world scale")
    identity: dict[str, object] = {
        "asset_kind": asset,
        "subject_dimensions": dimensions,
        "index_order": "left_to_right",
    }
    if asset == "climbable":
        identity["atlas_roles"] = list(roles or ())
    return canonical, {**report, **identity}


def _validate_map_presentation_source(
    data: bytes,
    *,
    asset: Literal["climbable", "portal"],
    expected_size: tuple[int, int],
    roles: Sequence[ClimbableRole] | None = None,
) -> dict[str, object]:
    facts = _validate_provider_image(
        data,
        width=expected_size[0],
        height=expected_size[1],
        transparent=True,
    )
    with Image.open(io.BytesIO(data)) as opened:
        alpha = opened.convert("RGBA").getchannel("A")
    border = [
        *alpha.crop((0, 0, alpha.width, 1)).get_flattened_data(),
        *alpha.crop((0, alpha.height - 1, alpha.width, alpha.height)).get_flattened_data(),
        *alpha.crop((0, 0, 1, alpha.height)).get_flattened_data(),
        *alpha.crop((alpha.width - 1, 0, alpha.width, alpha.height)).get_flattened_data(),
    ]
    if max(border) > 16 or sum(border) / len(border) > 0.5:
        raise ValueError(f"map {asset} must retain a transparent isolated canvas border")
    _, report = _canonicalize_map_presentation(data, asset=asset, roles=roles)
    return {
        **facts,
        "principal_component_count": report["principal_candidate_count"],
        "required_subject_count": 2 if asset == "portal" else len(roles or ()),
        "subject_dimensions": report["subject_dimensions"],
        "index_order": report["index_order"],
    }


async def _write_local_image(
    path: Path,
    data: bytes,
    *,
    model: str,
    prompt: str,
    source_ref: str,
    source_data: bytes,
    validation: Mapping[str, object],
) -> Path:
    return await _write_local_image_multi(
        path,
        data,
        model=model,
        prompt=prompt,
        inputs=[(source_ref, source_data)],
        validation=validation,
    )


async def _write_local_image_multi(
    path: Path,
    data: bytes,
    *,
    model: str,
    prompt: str,
    inputs: list[tuple[str, bytes]],
    validation: Mapping[str, object],
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
            params={"version": WORLD_HANDLER_VERSION},
            validation=dict(validation),
            component=SoftwareIdentity(
                name="@stage-gen/scrolling-preview", version=WORLD_HANDLER_VERSION
            ),
            tool=SoftwareIdentity(name="stage-gen", version="0.0.0"),
            attempts=1,
        ),
    )


def _validate_provider_image(
    data: bytes, *, width: int, height: int, transparent: bool
) -> dict[str, object]:
    with Image.open(io.BytesIO(data)) as opened:
        image = opened.convert("RGBA")
    if image.size != (width, height):
        raise ValueError(f"provider image must be exactly {width}x{height}")
    extrema = cast(tuple[int, int], image.getchannel("A").getextrema())
    if transparent and not (extrema[0] == 0 and extrema[1] > 0):
        raise ValueError("transparent map output must contain both transparent and visible pixels")
    if not transparent and extrema != (255, 255):
        raise ValueError("opaque map output must be fully opaque")
    return {"width": width, "height": height, "alpha_min": extrema[0], "alpha_max": extrema[1]}


def _review_schema() -> dict[str, object]:
    checks = {
        key: {"type": "boolean"}
        for key in (
            "reference_fidelity",
            "layer_separation",
            "style_coherence",
            "playfield_readability",
            "looping_continuity",
            "ground_compatibility",
            "traversal_presentation_compatibility",
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
    if not isinstance(value, dict) or value.get("verdict") not in {"accept", "reject", "uncertain"}:
        raise ValueError("map review has an invalid verdict")
    return value


def _node_artifact(run_dir: Path, path: Path) -> NodeArtifact:
    data = path.read_bytes()
    return NodeArtifact(
        artifact_ref=path.relative_to(run_dir).as_posix(), sha256=_sha(data), bytes=len(data)
    )


def _data_url(data: bytes, media_type: str) -> str:
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"


def _media_type(path: str) -> str:
    return (
        "image/jpeg"
        if Path(path).suffix.lower() in {".jpg", ".jpeg"}
        else "image/webp"
        if Path(path).suffix.lower() == ".webp"
        else "image/png"
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


__all__ = ["PreparedWorldNodeHandler", "WORLD_HANDLER_VERSION", "world_target_node_ids"]
