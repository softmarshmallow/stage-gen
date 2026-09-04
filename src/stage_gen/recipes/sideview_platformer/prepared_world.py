"""Execute the map-only closure of an exact-current prepared game package."""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from PIL import Image, ImageChops, ImageOps, ImageStat

from gnode import (
    BinaryArtifact,
    ImageGenerationRequest,
    ImageGenerationService,
    ImageReference,
    InputProvenance,
    Node,
    NodeExecutionResult,
    NodeType,
    ProvenanceInput,
    SoftwareIdentity,
    StructuredGenerationRequest,
    StructuredGenerationService,
    StructuredOutputSchema,
    StructuredReference,
    atomic_write_bytes,
    atomic_write_json,
    dependency_port,
    write_artifact_with_provenance_async,
)
from stage_gen.components.image_repeat import (
    ImageRepeatValidationPolicy,
    build_three_repeat_preview,
    validate_image_repeat,
)
from stage_gen.components.painted_terrain import (
    PAINTED_TERRAIN_CANONICALIZE,
    PAINTED_TERRAIN_CANONICALIZER_ID,
    PAINTED_TERRAIN_COMPOSE,
    PAINTED_TERRAIN_GENERATE,
    PAINTED_TERRAIN_GROUND_VALIDATION_KIND,
    PAINTED_TERRAIN_GUIDE,
    PAINTED_TERRAIN_GUIDE_HEIGHT,
    PAINTED_TERRAIN_GUIDE_ID,
    PAINTED_TERRAIN_GUIDE_KIND,
    PAINTED_TERRAIN_GUIDE_WIDTH,
    PAINTED_TERRAIN_RAW_KIND,
    PaintedTerrainGround,
    PaintedTerrainSegment,
    build_painted_terrain_guide,
    canonicalize_painted_terrain_segment,
    painted_silhouette_tolerance,
    painted_terrain_generation_prompt,
    painted_terrain_join_discontinuity,
    painted_terrain_material_identity,
    painted_terrain_segments,
    stitch_painted_terrain,
    validate_painted_terrain_source,
)
from stage_gen.components.platformer_map import PreparedGameMap, PreparedMapLayer
from stage_gen.components.platformer_map.prepared import (
    PreparedMapTerrain,
    canonical_prepared_map_terrain_json,
    load_prepared_map_terrain_bytes,
    validate_generated_terrain,
)
from stage_gen.components.sideview_layers.contract import (
    LAYER_PLACEMENT_CANONICALIZER,
    resolve_layer_placement,
)
from stage_gen.components.sideview_layers.pipeline import (
    layer_repeat_policies,
    loop_layer,
    validate_provider_image,
)
from stage_gen.components.sideview_map_design import DesignBrief, design_chunks
from stage_gen.components.sideview_terrain.atlas import (
    MATERIAL_ASSEMBLER_ID,
    assemble_terrain_atlas,
    compose_canonical_terrain,
    require_terrain_atlas_source,
    terrain_atlas_generation_prompt,
)
from stage_gen.media import (
    LOOP_METHODS,
    AlphaComponentRepackContract,
    LoopConstruction,
    SeamConditioning,
    data_url,
    repack_alpha_components,
    trim_layer_to_alpha_box,
)
from stage_gen.media.codec import decode_rgba, encode_png
from stage_gen.orchestration.game_package import ResolvedGamePackage
from stage_gen.recipes.node_handler import NodeMethod, RecipeNodeHandler
from stage_gen.recipes.sideview_platformer.climbable_atlas import (
    MAX_HEIGHT_PARITY,
    ROLE_ASPECT_ENVELOPE,
    ClimbableRole,
    plan_climbable_atlas,
    role_aspect_admits,
)
from stage_gen.recipes.sideview_platformer.execution_graph import ExecutionGraph, OperationKind
from stage_gen.recipes.sideview_platformer.package_graph import (
    CACHE_RECORD_KIND,
    WORLD_CACHE_NAMESPACE,
)
from stage_gen.recipes.sideview_platformer.package_types import (
    MAP_CLIMBABLE_GENERATE,
    MAP_CLIMBABLE_VALIDATE,
    MAP_COMPOSITE,
    MAP_GROUND_GENERATE,
    MAP_GROUND_VALIDATE,
    MAP_LAYER_GENERATE,
    MAP_LAYER_LOOP_CONSTRUCT,
    MAP_LAYER_LOOP_PAINT,
    MAP_LAYER_VALIDATE,
    MAP_PORTAL_GENERATE,
    MAP_PORTAL_VALIDATE,
    MAP_REVIEW,
    MAP_TERRAIN_DESIGN,
    PACKAGE_RESOLVE,
)
from stage_gen.recipes.sideview_platformer.terrain_design import (
    compile_terrain,
    terrain_artifact_path,
    terrain_profile,
)

WORLD_HANDLER_VERSION = "prepared-world-v3"
#: Ceiling on the common period a map composite may need. Mixed layer periods multiply out through
#: their least common multiple, so this fails a pathological authored combination loudly instead of
#: allocating an unbounded review canvas.
#: The review board is rendered at the runtime's viewport height and tile size so a reviewer is
#: judging the same composition the player sees, not a differently-scaled approximation.
_COMPOSITE_VIEWPORT_HEIGHT_PX = 720
_COMPOSITE_TILE_PX = 64


class PreparedWorldNodeHandler(RecipeNodeHandler):
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
        self._package = package
        self._images = image_service
        self._structured = structured_service
        self._terrain_template_path = terrain_template_path
        self._terrain_topology_reference_path = terrain_topology_reference_path
        super().__init__(
            graph,
            run_dir=run_dir,
            cache_dir=cache_dir,
            namespace=WORLD_CACHE_NAMESPACE,
            record_kind=CACHE_RECORD_KIND,
            admit=lambda node, payloads: (
                bool(payloads) and self._cached_world_artifact_valid(node, payloads[0])
            ),
        )

    def _cached_world_artifact_valid(self, node: Node, data: bytes) -> bool:
        """Re-prove a restored image against the gate its generation ran inside.

        The content checkpoint has done this since it existed; the world checkpoint,
        which spends the most on images, admitted on key, digest and lineage alone.
        A validator tightened after an image was accepted therefore kept serving the
        old bytes - the exact drift a two-thousand-line replay tool was written to
        repair. Re-running the gate here makes a tightening cost exactly the images
        that no longer pass, and nothing else.
        """

        if node.operation != OperationKind.IMAGE_GENERATION:
            return True
        try:
            game_map = self._node_map(node)
            if node.type_id == MAP_LAYER_GENERATE.type_id:
                layer = self._node_layer(node, game_map)
                validate_provider_image(
                    data,
                    width=1536,
                    height=1024,
                    transparent=layer.alpha_mode == "transparent",
                )
            elif node.type_id == MAP_LAYER_LOOP_PAINT.type_id:
                # The loop's own gate - a clean declared-axis repeat - runs in the free
                # validate node downstream over the published unit; what is restored here
                # is the provider's edit at the conditioning canvas, so the bar is that it
                # decodes at all.
                decode_rgba(data, label="loop edit")
            elif node.type_id == MAP_GROUND_GENERATE.type_id:
                require_terrain_atlas_source(
                    data, template=self._terrain_template_path.read_bytes()
                )
            elif node.type_id == PAINTED_TERRAIN_GENERATE.type_id:
                segment = self._painted_segment(node, game_map)
                identity, references = self._painted_material(game_map)
                occupancy = self._terrain(game_map).occupancy
                guide, _report = build_painted_terrain_guide(
                    occupancy, segment, material_identity=identity, material_references=references
                )
                validate_painted_terrain_source(
                    data,
                    occupancy=occupancy,
                    segment=segment,
                    guide=guide,
                    material_identity=identity,
                    material_references=references,
                )
            elif node.type_id == MAP_CLIMBABLE_GENERATE.type_id:
                climbable = game_map.climbable
                if climbable is None:
                    return False
                plan = plan_climbable_atlas(len(climbable.variants))
                _validate_map_presentation_source(
                    data,
                    asset="climbable",
                    expected_size=(plan.width_px, plan.height_px),
                    roles=[climbable.role_of(entry.variant_id) for entry in climbable.variants],
                )
            elif node.type_id == MAP_PORTAL_GENERATE.type_id:
                _validate_map_presentation_source(data, asset="portal", expected_size=(1536, 1024))
            else:
                return False
        except (OSError, ValueError):
            return False
        return True

    # ---------------------------------------------------------------- dispatch

    def _handlers(self) -> tuple[tuple[NodeType, NodeMethod], ...]:
        """Registered types replace the five node-id regexes this handler once walked.

        The manifest type is deliberately absent: this checkpoint stops at the map
        reviews, and the registry's own "unregistered type" refusal is what says so.
        """

        return (
            (PACKAGE_RESOLVE, self._resolve_package),
            (MAP_LAYER_GENERATE, self._generate_layer),
            (MAP_LAYER_LOOP_PAINT, self._paint_layer_loop),
            (MAP_LAYER_LOOP_CONSTRUCT, self._construct_layer_loop),
            (MAP_LAYER_VALIDATE, self._validate_layer),
            (MAP_TERRAIN_DESIGN, self._generate_terrain),
            (MAP_GROUND_GENERATE, self._generate_ground),
            (MAP_GROUND_VALIDATE, self._validate_ground),
            (PAINTED_TERRAIN_GUIDE, self._guide_painted_terrain),
            (PAINTED_TERRAIN_GENERATE, self._generate_painted_terrain),
            (PAINTED_TERRAIN_CANONICALIZE, self._canonicalize_painted_terrain),
            (PAINTED_TERRAIN_COMPOSE, self._compose_painted_terrain),
            (MAP_CLIMBABLE_GENERATE, self._generate_climbable),
            (MAP_CLIMBABLE_VALIDATE, self._validate_climbable),
            (MAP_PORTAL_GENERATE, self._generate_portal),
            (MAP_PORTAL_VALIDATE, self._validate_portal),
            (MAP_COMPOSITE, self._composite),
            (MAP_REVIEW, self._review),
        )

    # ------------------------------------------------------------- instance ids

    def _node_map(self, node: Node) -> PreparedGameMap:
        """The authored map this node instance is bound to."""

        map_id = node.params.get("map_id")
        if map_id is None:
            raise ValueError(f"node {node.node_id} declares no map_id")
        return self._map(map_id)

    def _node_layer(self, node: Node, game_map: PreparedGameMap) -> PreparedMapLayer:
        """The authored layer this node instance is bound to."""

        layer_id = node.params.get("layer_id")
        if layer_id is None:
            raise ValueError(f"node {node.node_id} declares no layer_id")
        for layer in game_map.layers:
            if layer.layer_id == layer_id:
                return layer
        raise ValueError(f"map {game_map.map_id} declares no layer {layer_id}")

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

    # ------------------------------------------------------------------ nodes

    async def _resolve_package(self, node: Node) -> NodeExecutionResult:
        atomic_write_json(
            self._run_dir / node.port("identity").artifact_ref, self._package.identity()
        )
        return self._result(node, provider_operations=0)

    async def _generate_terrain(self, node: Node) -> NodeExecutionResult:
        """Compose this map's terrain from its authored brief.

        The map asks for a shape the way it asks for artwork, and the answer is an artifact. The
        designer's own retry loop is semantic regeneration -- it hands the validator's complaints
        back to the model in the model's own vocabulary -- and sits outside the provider retry
        owner, which stays inside the structured-generation service.
        """

        game_map = self._node_map(node)
        output = self._run_dir / node.port("terrain").artifact_ref
        output.parent.mkdir(parents=True, exist_ok=True)
        profile = terrain_profile(game_map)
        brief = DesignBrief(intent=self._map_prompt(game_map, game_map.terrain.brief))
        attempts = await design_chunks(
            self._structured,
            profile,
            brief,
            artifact_dir=output.parent / "terrain-design",
            # Policy as data: the semantic-regeneration budget comes from the
            # node type's declaration, not a constant buried in a call site.
            max_attempts=MAP_TERRAIN_DESIGN.policy.semantic_attempts,
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
        return self._result(node, provider_operations=len(attempts))

    async def _generate_layer(self, node: Node) -> NodeExecutionResult:
        game_map = self._node_map(node)
        layer = self._node_layer(node, game_map)
        output = self._run_dir / node.port("image").artifact_ref
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
                validate=lambda artifact: validate_provider_image(
                    artifact.data, width=1536, height=1024, transparent=transparent
                ),
            )
        )
        return self._result(
            node,
            attempts=result.attempts,
            provider_operations=result.attempts,
        )

    async def _paint_layer_loop(self, node: Node) -> NodeExecutionResult:
        """The generative route: admission first, then a provider edit when it fails."""

        return await self._layer_loop(node)

    async def _construct_layer_loop(self, node: Node) -> NodeExecutionResult:
        """The local route: admission first, then a deterministic construction."""

        return await self._layer_loop(node)

    async def _layer_loop(self, node: Node) -> NodeExecutionResult:
        """Admit the generated layer as a loop, or construct one by the declared construction.

        The layer's own selection wins over the map's. A map's layers do not share a difficulty:
        one whose ends already agree loops under any construction, while one whose ends disagree
        in the source art fails under all of them, and a single map-wide choice cannot say so.

        Which of the two loop types the plan carries follows from that same selection, so both
        routes read one implementation: the branch below is the declaration the builder read.
        """

        game_map = self._node_map(node)
        layer = self._node_layer(node, game_map)
        _producer, source_port = dependency_port(self._graph, node, kind="map-layer-raw-v1")
        raw_data = (self._run_dir / source_port.artifact_ref).read_bytes()
        construction = layer.loop_construction or game_map.continuity.loop_construction
        generative = LOOP_METHODS[construction].is_generative
        edit_ref = node.port("edit_image").artifact_ref if generative else None

        async def paint(conditioning: SeamConditioning) -> tuple[bytes, int]:
            assert edit_ref is not None
            edit_path = self._run_dir / edit_ref
            transparent = layer.alpha_mode == "transparent"
            generation = await self._images.generate(
                ImageGenerationRequest(
                    prompt=self._loop_prompt(layer, conditioning, construction),
                    artifact_path=edit_path,
                    input_references=(
                        ImageReference(
                            data_url(conditioning.conditioning_png, "image/png"),
                            "loop-conditioning",
                        ),
                    ),
                    mask_reference=ImageReference(
                        data_url(conditioning.mask_png, "image/png"), "loop-mask"
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
                        "operation": f"loop_{construction}",
                    },
                )
            )
            return edit_path.read_bytes(), generation.attempts

        outcome = await loop_layer(
            raw_data,
            construction=construction,
            fallback=game_map.continuity.loop_fallback,
            alpha_mode=layer.alpha_mode,
            label=f"{game_map.map_id}/{layer.layer_id}",
            paint=paint if generative else None,
        )
        if outcome.edit_bypassed and edit_ref is not None and outcome.edit_data is not None:
            await _write_local_image(
                self._run_dir / edit_ref,
                outcome.edit_data,
                model="prepared-map-loop-edit-bypass-v1",
                prompt="Record a provider-free bypass for an already seamless layer.",
                source_ref=source_port.artifact_ref,
                source_data=raw_data,
                validation={"construction": "none", "provider_skipped": True},
            )
        inputs = [(source_port.artifact_ref, raw_data)]
        if outcome.edit_is_the_selected_construction and edit_ref is not None:
            assert outcome.edit_data is not None
            inputs.append((edit_ref, outcome.edit_data))
        await _write_local_image_multi(
            self._run_dir / node.port("loop_image").artifact_ref,
            outcome.looped,
            model=outcome.record["kind"],  # type: ignore[arg-type]
            prompt="Admit or construct the layer's horizontal loop unit.",
            inputs=inputs,
            validation=outcome.record,
        )
        atomic_write_json(self._run_dir / node.port("loop_report").artifact_ref, outcome.record)
        return self._result(node, provider_operations=outcome.provider_operations)

    async def _validate_layer(self, node: Node) -> NodeExecutionResult:
        layer = self._node_layer(node, self._node_map(node))
        _producer, loop_port = dependency_port(self._graph, node, kind="map-layer-loop-image-v1")
        _report_producer, report_port = dependency_port(
            self._graph, node, kind="layer-loop-report-v1"
        )
        raw_path = self._run_dir / loop_port.artifact_ref
        raw_data = raw_path.read_bytes()
        construction = json.loads((self._run_dir / report_port.artifact_ref).read_bytes())
        alpha_policy, coverage = layer_repeat_policies(layer.alpha_mode)
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
        output = self._run_dir / node.port("image").artifact_ref
        validation_path = self._run_dir / node.port("validation").artifact_ref
        preview_path = self._run_dir / node.port("repeat_preview").artifact_ref
        await _write_local_image(
            output,
            trimmed,
            model=LAYER_PLACEMENT_CANONICALIZER,
            prompt=(
                "Trim the constructed map loop unit to its alpha box vertically while preserving "
                "the repeat period."
            ),
            source_ref=loop_port.artifact_ref,
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
        return self._result(node, provider_operations=0)

    async def _generate_ground(self, node: Node) -> NodeExecutionResult:
        game_map = self._node_map(node)
        output = self._run_dir / node.port("image").artifact_ref
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
                url=data_url(template, "image/png"),
                provenance_ref=(
                    "resource://image_gen_templates/terrain_atlas_12x4_template.png"
                    f"#sha256={hashlib.sha256(template).hexdigest()}"
                ),
            ),
            ImageReference(
                url=data_url(topology_reference, "image/png"),
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
            attempts=result.attempts,
            provider_operations=result.attempts,
        )

    # -------------------------------------------------------- painted terrain

    def _painted_ground(self, game_map: PreparedGameMap) -> PaintedTerrainGround:
        ground = game_map.ground
        if not isinstance(ground, PaintedTerrainGround):
            raise ValueError(f"map {game_map.map_id} does not declare painted terrain")
        return ground

    def _painted_material(self, game_map: PreparedGameMap) -> tuple[str, list[bytes]]:
        """The identity every painted node agrees on, and the bytes it is derived from.

        Derived here rather than passed down the graph so the guide, the source validator
        and the canonicalizer cannot disagree about what material they are talking about:
        the canonicalizer re-derives the guide and refuses a mismatch, which only works if
        all three arrive at the same digest from the same inputs.
        """

        ground = self._painted_ground(game_map)
        by_id = {item.reference_id: item for item in game_map.references}
        entries = [self._package.file(by_id[rid].source) for rid in ground.reference_ids]
        style = self._package.game.style
        identity = painted_terrain_material_identity(
            prompt=ground.prompt,
            visual_direction_sha256=hashlib.sha256(
                json.dumps(
                    {"label": style.label, "keywords": list(style.keywords)},
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest(),
            reference_sha256=[entry.sha256 for entry in entries],
        )
        return identity, [entry.data for entry in entries]

    def _painted_segment(self, node: Node, game_map: PreparedGameMap) -> PaintedTerrainSegment:
        segment_id = node.params.get("segment_id")
        if segment_id is None:
            raise ValueError(f"node {node.node_id} declares no segment_id")
        for segment in painted_terrain_segments(game_map.terrain.columns, game_map.terrain.rows):
            if segment.segment_id == segment_id:
                return segment
        raise ValueError(f"map {game_map.map_id} has no painted segment {segment_id}")

    async def _guide_painted_terrain(self, node: Node) -> NodeExecutionResult:
        game_map = self._node_map(node)
        segment = self._painted_segment(node, game_map)
        identity, references = self._painted_material(game_map)
        occupancy = self._terrain(game_map).occupancy
        guide, report = build_painted_terrain_guide(
            occupancy,
            segment,
            material_identity=identity,
            material_references=references,
        )
        await _write_local_image_multi(
            self._run_dir / node.port("guide").artifact_ref,
            guide,
            model=PAINTED_TERRAIN_GUIDE_ID,
            prompt=(
                "Draw the authored occupancy of one map segment as flat registration blocks, "
                "with a band on every side that faces air and the bottom row running off the "
                "canvas."
            ),
            inputs=[
                (
                    terrain_artifact_path(game_map.map_id),
                    "\n".join(occupancy).encode("utf-8"),
                )
            ],
            validation=report,
        )
        atomic_write_json(self._run_dir / node.port("guide_report").artifact_ref, report)
        return self._result(node, provider_operations=0)

    async def _generate_painted_terrain(self, node: Node) -> NodeExecutionResult:
        game_map = self._node_map(node)
        segment = self._painted_segment(node, game_map)
        identity, references = self._painted_material(game_map)
        occupancy = self._terrain(game_map).occupancy
        _producer, guide_port = dependency_port(self._graph, node, kind=PAINTED_TERRAIN_GUIDE_KIND)
        guide = (self._run_dir / guide_port.artifact_ref).read_bytes()
        style = self._package.game.style
        material_direction = (
            f"{self._painted_ground(game_map).prompt.strip()} Target style: {style.label}; "
            f"{', '.join(style.keywords)}."
        )
        result = await self._images.generate(
            ImageGenerationRequest(
                prompt=painted_terrain_generation_prompt(
                    material_direction,
                    segment=segment,
                    columns=segment.columns,
                    rows=len(occupancy),
                ),
                artifact_path=self._run_dir / node.port("image").artifact_ref,
                input_references=(
                    ImageReference(
                        url=data_url(guide, "image/png"),
                        provenance_ref=(
                            f"run://{guide_port.artifact_ref}"
                            f"#sha256={hashlib.sha256(guide).hexdigest()}"
                        ),
                    ),
                    *self._image_references(game_map, self._painted_ground(game_map).reference_ids),
                ),
                quality="high",
                background="transparent",
                output_format="png",
                size=f"{PAINTED_TERRAIN_GUIDE_WIDTH}x{PAINTED_TERRAIN_GUIDE_HEIGHT}",
                timeout_seconds=600,
                metadata={
                    "checkpoint": "world",
                    "map_id": game_map.map_id,
                    "segment_id": segment.segment_id,
                    "ground_mode": game_map.ground.mode,
                    "native_alpha": True,
                },
                # Admission runs inside the provider's own retry budget, so a painting that
                # closed a hop gap or hung a support re-rolls rather than failing the run
                # after the spend.
                validate=lambda artifact: validate_painted_terrain_source(
                    artifact.data,
                    occupancy=occupancy,
                    segment=segment,
                    guide=guide,
                    material_identity=identity,
                    material_references=references,
                ),
            )
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _canonicalize_painted_terrain(self, node: Node) -> NodeExecutionResult:
        game_map = self._node_map(node)
        segment = self._painted_segment(node, game_map)
        identity, references = self._painted_material(game_map)
        occupancy = self._terrain(game_map).occupancy
        _guide_producer, guide_port = dependency_port(
            self._graph, node, kind=PAINTED_TERRAIN_GUIDE_KIND
        )
        _source_producer, source_port = dependency_port(
            self._graph, node, kind=PAINTED_TERRAIN_RAW_KIND
        )
        guide = (self._run_dir / guide_port.artifact_ref).read_bytes()
        source = (self._run_dir / source_port.artifact_ref).read_bytes()
        canonical, report = canonicalize_painted_terrain_segment(
            source,
            occupancy=occupancy,
            segment=segment,
            guide=guide,
            material_identity=identity,
            material_references=references,
        )
        await _write_local_image_multi(
            self._run_dir / node.port("image").artifact_ref,
            canonical,
            model=PAINTED_TERRAIN_CANONICALIZER_ID,
            prompt=(
                "Crop the segment's own columns from the conditioning canvas, clip the "
                "painting to the published silhouette band, and lay deterministic material "
                "under whatever the model did not paint."
            ),
            inputs=[
                (guide_port.artifact_ref, guide),
                (source_port.artifact_ref, source),
            ],
            validation=report,
        )
        atomic_write_json(self._run_dir / node.port("validation").artifact_ref, report)
        return self._result(node, provider_operations=0)

    async def _compose_painted_terrain(self, node: Node) -> NodeExecutionResult:
        game_map = self._node_map(node)
        identity, _references = self._painted_material(game_map)
        occupancy = self._terrain(game_map).occupancy
        segments = painted_terrain_segments(game_map.terrain.columns, game_map.terrain.rows)
        published: list[tuple[PaintedTerrainSegment, bytes]] = []
        inputs: list[tuple[str, bytes]] = []
        boundaries: list[int] = []
        for segment in segments:
            ref = f"maps/{game_map.map_id}/ground/{segment.segment_id}.png"
            data = (self._run_dir / ref).read_bytes()
            published.append((segment, data))
            inputs.append((ref, data))
            if segment.start_column:
                boundaries.append(segment.start_column)
        plate = stitch_painted_terrain(published, occupancy=occupancy)
        joins = painted_terrain_join_discontinuity(_decode_png(plate), boundaries=boundaries)
        validation: dict[str, object] = {
            "schema_version": 1,
            "kind": PAINTED_TERRAIN_GROUND_VALIDATION_KIND,
            "mode": game_map.ground.mode,
            "map_id": game_map.map_id,
            "material_identity": identity,
            "geometry_authority": "authored_occupancy",
            "silhouette_tolerance": painted_silhouette_tolerance().model_dump(mode="json"),
            "segments": [
                {
                    "segment_id": segment.segment_id,
                    "start_column": segment.start_column,
                    "columns": segment.columns,
                }
                for segment in segments
            ],
            # A cut is invisible when the step across it is unremarkable among the steps
            # inside the paintings. Recorded rather than gated: the deterministic jittered
            # cut that would fix a visible one costs no provider call, so this is the
            # measurement that decides whether to turn it on.
            "joins": joins,
        }
        await _write_local_image_multi(
            self._run_dir / node.port("evidence").artifact_ref,
            plate,
            model="painted-terrain-plate-v1",
            prompt="Stitch every published painted segment into one plate of the whole map.",
            inputs=inputs,
            validation=validation,
        )
        atomic_write_json(self._run_dir / node.port("validation").artifact_ref, validation)
        return self._result(node, provider_operations=0)

    async def _validate_ground(self, node: Node) -> NodeExecutionResult:
        game_map = self._node_map(node)
        _producer, source_port = dependency_port(self._graph, node, kind="ground-atlas-raw-v1")
        raw_path = self._run_dir / source_port.artifact_ref
        raw = raw_path.read_bytes()
        canonical, validation = assemble_terrain_atlas(
            raw,
            template=self._terrain_template_path.read_bytes(),
        )
        if validation["classification"] != "direct_pass":
            raise ValueError("dynamic terrain atlas validation requires direct_pass media")
        output = self._run_dir / node.port("image").artifact_ref
        validation_path = self._run_dir / node.port("validation").artifact_ref
        evidence_path = self._run_dir / node.port("evidence").artifact_ref
        await _write_local_image(
            output,
            canonical,
            model=MATERIAL_ASSEMBLER_ID,
            prompt=(
                "Slice the model-painted 12x4 guide lattice, extract deterministic chroma alpha, "
                "apply the authoritative 47-mask lookup, harmonize only legal connector edges, "
                "and assemble the canonical atlas deterministically."
            ),
            source_ref=source_port.artifact_ref,
            source_data=raw,
            validation=validation,
        )
        atomic_write_json(validation_path, validation)
        occupancy = self._terrain(game_map).occupancy
        evidence, _ = compose_canonical_terrain(canonical, occupancy)
        await _write_local_image(
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
        return self._result(node, provider_operations=0)

    async def _generate_climbable(self, node: Node) -> NodeExecutionResult:
        return await self._generate_map_presentation(node, "climbable")

    async def _generate_portal(self, node: Node) -> NodeExecutionResult:
        return await self._generate_map_presentation(node, "portal")

    async def _validate_climbable(self, node: Node) -> NodeExecutionResult:
        return await self._validate_map_presentation(node, "climbable")

    async def _validate_portal(self, node: Node) -> NodeExecutionResult:
        return await self._validate_map_presentation(node, "portal")

    async def _generate_map_presentation(
        self,
        node: Node,
        asset: Literal["climbable", "portal"],
    ) -> NodeExecutionResult:
        game_map = self._node_map(node)
        output = self._run_dir / node.port("image").artifact_ref
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
            attempts=result.attempts,
            provider_operations=result.attempts,
        )

    async def _validate_map_presentation(
        self,
        node: Node,
        asset: Literal["climbable", "portal"],
    ) -> NodeExecutionResult:
        game_map = self._node_map(node)
        source_port = self._graph.node(node.depends_on[0]).port("image")
        raw_path = self._run_dir / source_port.artifact_ref
        raw = raw_path.read_bytes()
        roles: Sequence[ClimbableRole] | None = None
        if asset == "climbable":
            climbable = game_map.climbable
            if climbable is None:
                raise ValueError(f"map {game_map.map_id} does not declare climbable")
            roles = [climbable.role_of(entry.variant_id) for entry in climbable.variants]
        canonical, validation = _canonicalize_map_presentation(raw, asset=asset, roles=roles)
        output = self._run_dir / node.port("image").artifact_ref
        validation_path = self._run_dir / node.port("validation").artifact_ref
        await _write_local_image(
            output,
            canonical,
            model=f"prepared-map-{asset}-alpha-component-repack-v3",
            prompt=f"Isolate and repack the map-local {asset} presentation.",
            source_ref=source_port.artifact_ref,
            source_data=raw,
            validation=validation,
        )
        atomic_write_json(validation_path, validation)
        return self._result(node, provider_operations=0)

    async def _composite(self, node: Node) -> NodeExecutionResult:
        game_map = self._node_map(node)
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
        # Both modes hand the composite one plate of the terrain as it will be drawn. The
        # atlas has to be composed through the occupancy to become one; painted terrain's
        # stitched plate already is one, which is the whole point of the compose node.
        painted = isinstance(game_map.ground, PaintedTerrainGround)
        ground_path = self._run_dir / (
            f"maps/{game_map.map_id}/ground.evidence.png"
            if painted
            else f"maps/{game_map.map_id}/ground.png"
        )
        canvas.alpha_composite(
            _ground_preview(ground_path, canvas.size, terrain.occupancy, composed=painted)
        )
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
        output = self._run_dir / node.port("image").artifact_ref
        inputs = [
            (
                f"maps/{game_map.map_id}/layers/{layer.layer_id}.png",
                (
                    self._run_dir / f"maps/{game_map.map_id}/layers/{layer.layer_id}.png"
                ).read_bytes(),
            )
            for layer in ordered
        ]
        inputs.append((ground_path.relative_to(self._run_dir).as_posix(), ground_path.read_bytes()))
        await _write_local_image_multi(
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
        return self._result(node, provider_operations=0)

    async def _review(self, node: Node) -> NodeExecutionResult:
        game_map = self._node_map(node)
        output = self._run_dir / node.port("verdict").artifact_ref
        composite_path = self._run_dir / f"maps/{game_map.map_id}/composite.png"
        ground_evidence_path = self._run_dir / f"maps/{game_map.map_id}/ground.evidence.png"
        references = [
            StructuredReference(
                url=data_url(_judge_plate(composite_path.read_bytes()), "image/png"),
                provenance_ref=f"run://{composite_path.relative_to(self._run_dir).as_posix()}",
            ),
            StructuredReference(
                url=data_url(_judge_plate(ground_evidence_path.read_bytes()), "image/png"),
                provenance_ref=(
                    f"run://{ground_evidence_path.relative_to(self._run_dir).as_posix()}"
                ),
            ),
        ]
        # The atlas ships a third plate -- the repeating material sheet itself -- because the
        # judge cannot see tile joins in a composed map. Painted terrain has no such sheet:
        # every segment is bespoke, so the two plates above are the whole of it.
        if not isinstance(game_map.ground, PaintedTerrainGround):
            ground_path = self._run_dir / f"maps/{game_map.map_id}/ground.png"
            references.append(
                StructuredReference(
                    url=data_url(_judge_plate(ground_path.read_bytes()), "image/png"),
                    provenance_ref=f"run://{ground_path.relative_to(self._run_dir).as_posix()}",
                )
            )
        declared_presentations: list[str] = []
        for asset in ("portal", "climbable"):
            direction = game_map.portal if asset == "portal" else game_map.climbable
            if direction is None:
                continue
            path = self._run_dir / f"maps/{game_map.map_id}/{asset}.png"
            references.append(
                StructuredReference(
                    url=data_url(_judge_plate(path.read_bytes()), "image/png"),
                    provenance_ref=f"run://{path.relative_to(self._run_dir).as_posix()}",
                )
            )
            declared_presentations.append(asset)
        for ref in game_map.references:
            package_file = self._package.file(ref.source)
            references.append(
                StructuredReference(
                    url=data_url(_judge_plate(package_file.data), "image/png"),
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
                        url=data_url(_judge_plate(layer_path.read_bytes()), "image/png"),
                        provenance_ref=(
                            f"run://{layer_path.relative_to(self._run_dir).as_posix()}"
                        ),
                    ),
                    StructuredReference(
                        url=data_url(_judge_plate(repeat_path.read_bytes()), "image/png"),
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

    def _loop_prompt(
        self,
        layer: PreparedMapLayer,
        conditioning: SeamConditioning,
        construction: LoopConstruction,
    ) -> str:
        """Brief the provider for the construction actually selected.

        The two families ask for materially different things and must not share a brief. A bridge
        asks the provider to invent a span between two ends it cannot see across; a repaint asks
        it to carry existing content through a region it can see both sides of. Sending one brief
        for the other describes a canvas the provider is not looking at.
        """

        if construction == "generated_bridge":
            return self._bridge_prompt(layer, conditioning)
        return self._repaint_prompt(layer, conditioning, mirrored=construction == "fold_repaint")

    def _layer_style_clauses(self, layer: PreparedMapLayer) -> tuple[str, str, str]:
        """Style label, material reference, and alpha rule shared by every loop brief."""

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
            f"Visual style: {style.label}. Avoid: {', '.join(style.avoid)}.",
            "Material reference, describing what this layer is made of and not how to compose "
            f"it: {material}\nIgnore anything in that reference about landmarks, rhythm, "
            "centring, or composition.",
            alpha,
        )

    def _repaint_prompt(
        self, layer: PreparedMapLayer, conditioning: SeamConditioning, *, mirrored: bool
    ) -> str:
        """Brief the provider to carry existing content through a join it can already see.

        Nothing is appended here; the marked region replaces pixels that already exist. The
        provider is shown continuous artwork with the defect in the middle of its own canvas,
        which is why this brief can ask for flow through a region rather than a match at an edge.
        """

        style_clause, material_clause, alpha = self._layer_style_clauses(layer)
        if mirrored:
            situation = (
                "The supplied image is one horizontal strip of side-view game art. Its right half "
                "is a mirror image of its left half, so the centre of the image is a reflection "
                "axis: the artwork bounces back on itself there and reads as an obvious mirror."
                f"\n\nRepaint only the marked middle {conditioning.editable_span} pixels so the "
                "strip reads as one continuous scene travelling in a single direction through "
                "that region, with no reflection and no axis of symmetry. Break up any left-right "
                "mirrored pairing."
            )
        else:
            situation = (
                "The supplied image is one horizontal strip of side-view game art, formed by "
                "placing the end of a scene directly against its own beginning. The centre of the "
                "image is therefore a hard cut: the artwork does not line up there."
                f"\n\nRepaint only the marked middle {conditioning.editable_span} pixels so the "
                "artwork flows through the cut as one unbroken band, with no visible seam, step, "
                "or discontinuity."
            )
        return (
            f"Image repair task. {situation}\n\n"
            "Everything outside that middle region is FINISHED ARTWORK: reproduce it exactly as "
            "given, pixel for pixel, same position, same scale, same vertical alignment. Do not "
            "move, shift, rescale, recompose, or restyle it.\n\n"
            "Match the existing line weight, palette, lighting, ground line, and horizon exactly. "
            "Do not introduce a landmark, a centrepiece, a frame, or text.\n\n"
            "Paint the span at full strength edge to edge. Do not fade, feather, blur, ghost, or "
            "ramp opacity toward either boundary, and do not use a gradient, haze, glow, or "
            "vignette to blend into the neighbours. If the two sides differ, resolve it with "
            "drawn content - foliage, masonry, terrain - not with transparency or a soft wash. "
            "Empty space inside the span is allowed only where the neighbouring artwork is "
            "genuinely empty; elsewhere keep the same density of drawn detail as the sides.\n\n"
            f"{style_clause}\n{material_clause}\n\n{alpha}"
        )

    def _bridge_prompt(self, layer: PreparedMapLayer, conditioning: SeamConditioning) -> str:
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
            f"Only the middle {conditioning.editable_span} pixels are empty. Paint that span "
            "so the artwork at the left edge of the gap continues into the artwork at the "
            "right edge as "
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
                    url=data_url(entry.data, _media_type(ref.source)),
                    provenance_ref=f"package://{self._package.game.game_id}/{ref.source}#sha256={entry.sha256}",
                )
            )
        return tuple(values)


def world_review_target_node_ids(graph: ExecutionGraph) -> tuple[str, ...]:
    """Every map review, read off the plan: the `world-review` checkpoint's terminals."""

    return tuple(node.node_id for node in graph.nodes if node.type_id == MAP_REVIEW.type_id)


def world_target_node_ids(graph: ExecutionGraph) -> tuple[str, ...]:
    """The world checkpoint's terminals: everything a map review reads, and not the review.

    A semantic review is evidence for an operator, not a gate the manifest consumes,
    and it is a paid structured operation per map. The default closure therefore
    stops one edge short of it - at the composite and the presentation validations
    the review depends on - and `world-review` runs the reviews over a world the
    cache already holds. Read off the review's own edges so the closure cannot
    drift from what the review actually needs.
    """

    terminals: list[str] = []
    for node in graph.nodes:
        if node.type_id == MAP_REVIEW.type_id:
            terminals.extend(
                dependency for dependency in node.depends_on if dependency not in terminals
            )
    return tuple(terminals)


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
    """Resolve one layer's vertical placement through the resolver every recipe shares.

    The rule used to live here. It moved to the shared layer component when the runner gained
    the same measured placement, so one anchor name cannot mean two things in two genres; the
    thin wrapper keeps this recipe's call sites and error prefix unchanged.
    """

    try:
        return resolve_layer_placement(layer, trim)
    except ValueError as error:
        raise ValueError(f"map {error}") from error


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
    return encode_png(image)


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
    path: Path,
    size: tuple[int, int],
    occupancy: tuple[str, ...] | list[str],
    *,
    composed: bool = False,
) -> Image.Image:
    data = path.read_bytes()
    if not composed:
        data, _ = compose_canonical_terrain(data, occupancy)
    with Image.open(io.BytesIO(data)) as opened:
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
    facts = validate_provider_image(
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


def _decode_png(data: bytes) -> Image.Image:
    return decode_rgba(data)


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
                name="@stage-gen/sideview-platformer", version=WORLD_HANDLER_VERSION
            ),
            tool=SoftwareIdentity(name="stage-gen", version="0.0.0"),
            attempts=1,
        ),
    )


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


#: The longest side a judge reference is transported at. Judges are constrained
#: to recognition, never measurement (doctrine), so a bounded plate changes
#: nothing they are allowed to read - and an unbounded one already broke a
#: review in production when a large map's reference payload crossed the
#: provider's request ceiling.
_JUDGE_PLATE_MAX_SIDE = 1280


def _judge_plate(data: bytes) -> bytes:
    """Bound one judge reference image for transport, re-encoded as PNG."""

    with Image.open(io.BytesIO(data)) as opened:
        width, height = opened.size
        longest = max(width, height)
        if longest <= _JUDGE_PLATE_MAX_SIDE and len(data) <= 1_500_000:
            return data
        scale = min(1.0, _JUDGE_PLATE_MAX_SIDE / longest)
        resized = opened.convert("RGBA").resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            Image.Resampling.LANCZOS,
        )
    buffer = io.BytesIO()
    resized.save(buffer, format="PNG")
    return bytes(buffer.getvalue())


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


__all__ = [
    "PreparedWorldNodeHandler",
    "WORLD_HANDLER_VERSION",
    "world_review_target_node_ids",
    "world_target_node_ids",
]
