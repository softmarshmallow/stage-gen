"""Execute one sideview-runner node: world, avatar, catalog, and the manifest.

Every provider operation stays inside a component service, which owns the whole
retry-validate-persist contract. Generation-side machinery is the shared
side-view components - the 47-mask terrain atlas, the loop pipeline, the
alpha-component repacker, the motion-rebase judges - composed here into this
recipe's node wiring.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
from typing import TYPE_CHECKING, Any, cast

from PIL import Image

from gnode import (
    BinaryArtifact,
    CacheDisposition,
    ImageGenerationRequest,
    ImageReference,
    InputProvenance,
    MusicGenerationRequest,
    NodeArtifact,
    NodeExecutionError,
    NodeExecutionResult,
    NodeTypeRegistry,
    ProvenanceInput,
    SoftwareIdentity,
    StructuredGenerationRequest,
    StructuredOutputSchema,
    StructuredReference,
    atomic_write_json,
    dependency_port,
    write_artifact_with_provenance_async,
)
from stage_gen.canonical import content_sha256
from stage_gen.components.game_soundtrack.prompt import music_track_prompt
from stage_gen.components.image_repeat import ImageRepeatValidationPolicy, validate_image_repeat
from stage_gen.components.sideview_actor.asset_unit import (
    calibrate_subject,
    measure_subject_extent,
    resolve_declared_magnitude,
    resolve_player_magnitude,
)
from stage_gen.components.sideview_actor.motion_geometry import DEFAULT_MOTION_ATLAS_GEOMETRY
from stage_gen.components.sideview_actor.motion_rebase import (
    MOTION_REBASE_SCHEMA_NAME,
    MotionRebaseError,
    MotionRebaseReading,
    admit_first_pass_record,
    build_motion_rebase_plate,
    build_motion_rebase_verification_plate,
    evaluate_motion_rebase,
    evaluate_motion_rebase_correction,
    motion_rebase_json_schema,
    motion_rebase_prompt,
    motion_rebase_verification_prompt,
    parse_motion_rebase,
)
from stage_gen.components.sideview_layers.pipeline import (
    assemble_loop,
    construct_deterministic,
    layer_repeat_policies,
    loop_conditioning,
    validate_provider_image,
)
from stage_gen.components.sideview_terrain import (
    assemble_terrain_atlas,
    require_terrain_atlas_source,
)
from stage_gen.media import RegistrationError, probe_audio, validate_music_payload
from stage_gen.media.layer_rasters import trim_layer_to_alpha_box
from stage_gen.media.sprite_sheets import (
    AlphaComponentRepackContract,
    repack_alpha_components,
    split_atlas_columns,
)
from stage_gen.recipes.node_cache import NodeArtifactCache
from stage_gen.recipes.sideview_runner.runner_graph import (
    RUNNER_CACHE_NAMESPACE,
    RUNNER_CACHE_RECORD_KIND,
    RUNNER_MOTION_STATES,
    RunnerOperationKind,
    SideviewRunnerGraph,
)
from stage_gen.recipes.sideview_runner.runner_types import (
    AVATAR_CONCEPT_GENERATE,
    AVATAR_MOTION_GENERATE,
    AVATAR_MOTION_VALIDATE,
    CATALOG_ASSET_GENERATE,
    CATALOG_ASSET_VALIDATE,
    CATALOG_RAW_KIND,
    GROUND_RAW_KIND,
    LAYER_GENERATE,
    LAYER_LOOP_CONSTRUCT,
    LAYER_LOOP_KIND,
    LAYER_LOOP_PAINT,
    LAYER_RAW_KIND,
    LAYER_VALIDATE,
    MANIFEST_ASSEMBLE,
    MANIFEST_KIND,
    MOTION_RAW_KIND,
    MOTION_REBASE_JUDGE,
    MOTION_REBASE_VERIFY,
    PACKAGE_RESOLVE,
    REBASE_READING_KIND,
    SOUNDTRACK_GENERATE,
    SOUNDTRACK_TRACK_KIND,
    SOUNDTRACK_VALIDATE,
    TRACK_GROUND_GENERATE,
    TRACK_GROUND_VALIDATE,
)
from stage_gen.resources import (
    terrain_atlas_template_path,
    terrain_atlas_topology_reference_path,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence
    from pathlib import Path

    from gnode import (
        ImageGenerationService,
        MusicGenerationService,
        Node,
        NodeExecutionContext,
        NodeHandler,
        StructuredGenerationService,
    )
    from stage_gen.components.platformer_map import PreparedMapLayer
    from stage_gen.components.runner_track import RunnerTrack
    from stage_gen.media import LoopConstruction
    from stage_gen.recipes.sideview_runner.runner_request import ResolvedRunnerPackage

RUNNER_HANDLER_VERSION = "1"
RUNNER_BASELINE_STATE = "run"
#: The one place the unit meets pixels in this recipe, matching the platformer's
#: projection so a shared avatar reads at the same magnitude in both genres.
RUNTIME_TILE_PX = 64

_COMPONENT = SoftwareIdentity(name="@stage-gen/sideview-runner", version=RUNNER_HANDLER_VERSION)


def _data_url(data: bytes, media_type: str) -> str:
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"


async def _write_local_image(
    path: Path,
    data: bytes,
    *,
    prompt: str,
    inputs: Sequence[tuple[str, bytes]],
    validation: Mapping[str, object],
    model: str = "sideview-runner-local-v1",
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
                    sha256=content_sha256(payload),
                    source="content",
                    bytes=len(payload),
                    media_type="image/png",
                )
                for ref, payload in inputs
            ],
            params={"version": RUNNER_HANDLER_VERSION},
            validation=dict(validation),
            component=_COMPONENT,
            tool=SoftwareIdentity(name="stage-gen", version="0.0.0"),
            attempts=1,
        ),
    )


def _validate_transparent_sprite(data: bytes) -> dict[str, object]:
    with Image.open(io.BytesIO(data)) as opened:
        image = opened.convert("RGBA")
    extrema = cast("tuple[int, int]", image.getchannel("A").getextrema())
    if not (extrema[0] == 0 and extrema[1] > 0):
        raise ValueError("sprite output must contain both transparent and visible pixels")
    return {
        "width": image.width,
        "height": image.height,
        "alpha_min": extrema[0],
        "alpha_max": extrema[1],
    }


def _validate_motion_source(data: bytes) -> dict[str, object]:
    geometry = DEFAULT_MOTION_ATLAS_GEOMETRY
    facts = _validate_transparent_sprite(data)
    if (facts["width"], facts["height"]) != (geometry.width, geometry.height):
        raise ValueError(f"motion atlas must be exactly {geometry.provider_size}")
    with Image.open(io.BytesIO(data)) as opened:
        alpha = opened.convert("RGBA").getchannel("A")
    cell_width = alpha.width / geometry.columns
    coverage: list[float] = []
    for index in range(geometry.required_cells):
        left = round(index * cell_width)
        right = round((index + 1) * cell_width)
        cell = alpha.crop((left, 0, right, alpha.height))
        visible = sum(cell.histogram()[1:]) / (cell.width * cell.height)
        coverage.append(visible)
    if any(value < 0.005 for value in coverage):
        raise ValueError("motion atlas is missing a required visible cell")
    return {**facts, "cell_visible_fractions": [round(value, 6) for value in coverage]}


class SideviewRunnerNodeHandler:
    """Dispatch runner nodes while provider operations stay component-owned."""

    def __init__(
        self,
        graph: SideviewRunnerGraph,
        resolved: ResolvedRunnerPackage,
        *,
        run_dir: Path,
        cache_dir: Path,
        image_service: ImageGenerationService,
        structured_service: StructuredGenerationService[Any],
        music_service: MusicGenerationService | None = None,
        capability_timeout_s: float | None = None,
    ) -> None:
        self._graph = graph
        self._resolved = resolved
        self._package = resolved.package
        self._runner = resolved.runner
        self._run_dir = run_dir
        self._images = image_service
        self._structured = structured_service
        self._music = music_service
        self._timeout = capability_timeout_s
        self._cache = NodeArtifactCache(
            graph,
            run_dir=run_dir,
            cache_dir=cache_dir,
            namespace=RUNNER_CACHE_NAMESPACE,
            record_kind=RUNNER_CACHE_RECORD_KIND,
        )
        self._registry = self._build_registry()

    async def __call__(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        cached = self._cache.read(node, context)
        if cached is not None:
            return cached
        try:
            result = await self._registry(node, context)
        except NodeExecutionError:
            raise
        except Exception as error:
            external = node.operation != RunnerOperationKind.LOCAL
            attempts = int(getattr(error, "attempts", 1))
            raise NodeExecutionError(
                str(error),
                attempts=attempts,
                provider_operations=attempts if external else 0,
            ) from error
        self._cache.write(node, context, result)
        return result

    # ---------------------------------------------------------------- dispatch

    def _build_registry(self) -> NodeTypeRegistry:
        registry = NodeTypeRegistry()
        registry.register(PACKAGE_RESOLVE, self._bind(self._write_package))
        registry.register(TRACK_GROUND_GENERATE, self._bind(self._generate_ground))
        registry.register(TRACK_GROUND_VALIDATE, self._bind(self._validate_ground))
        registry.register(LAYER_GENERATE, self._bind(self._generate_layer))
        registry.register(LAYER_LOOP_CONSTRUCT, self._bind(self._layer_loop))
        registry.register(LAYER_LOOP_PAINT, self._bind(self._layer_loop))
        registry.register(LAYER_VALIDATE, self._bind(self._validate_layer))
        registry.register(AVATAR_CONCEPT_GENERATE, self._bind(self._generate_concept))
        registry.register(AVATAR_MOTION_GENERATE, self._bind(self._generate_motion))
        registry.register(AVATAR_MOTION_VALIDATE, self._bind(self._validate_motion))
        registry.register(MOTION_REBASE_JUDGE, self._bind(self._rebase_judge))
        registry.register(MOTION_REBASE_VERIFY, self._bind(self._rebase_verify))
        registry.register(CATALOG_ASSET_GENERATE, self._bind(self._generate_catalog))
        registry.register(CATALOG_ASSET_VALIDATE, self._bind(self._validate_catalog))
        registry.register(SOUNDTRACK_GENERATE, self._bind(self._generate_track))
        registry.register(SOUNDTRACK_VALIDATE, self._bind(self._validate_track))
        registry.register(MANIFEST_ASSEMBLE, self._bind(self._assemble_manifest))
        return registry

    def _bind(self, method: Callable[[Node], Awaitable[NodeExecutionResult]]) -> NodeHandler:
        async def handler(node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
            return await method(node)

        return handler

    def _result(
        self, node: Node, *, attempts: int = 1, provider_operations: int = 0
    ) -> NodeExecutionResult:
        refs: list[str] = []
        for port in node.ports:
            refs.append(port.artifact_ref)
            if port.sidecar_ref is not None:
                refs.append(port.sidecar_ref)
        artifacts = tuple(
            NodeArtifact(
                artifact_ref=ref,
                sha256=content_sha256((self._run_dir / ref).read_bytes()),
                bytes=(self._run_dir / ref).stat().st_size,
            )
            for ref in refs
            if (self._run_dir / ref).is_file()
        )
        return NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=attempts,
            provider_operations=provider_operations,
            artifacts=artifacts,
        )

    # ------------------------------------------------------------------ shared

    def _card_prompt(self, node: Node) -> str:
        card = node.card
        if card is None or card.prompt is None:
            raise ValueError(f"node {node.node_id} carries no card prompt")
        return card.prompt

    def _authored_references(self, node: Node) -> tuple[ImageReference, ...]:
        card = node.card
        if card is None:
            return ()
        references = []
        for authored in card.authored_inputs:
            data = self._package.file(authored.ref).data
            references.append(ImageReference(_data_url(data, "image/png"), authored.label))
        return tuple(references)

    def _dependency_artifact(self, node: Node, *, kind: str, port_id: str | None = None) -> str:
        _producer, port = dependency_port(self._graph, node, kind=kind, port_id=port_id)
        return port.artifact_ref

    def _track(self) -> RunnerTrack:
        return self._runner.track

    def _layer(self, node: Node) -> PreparedMapLayer:
        layer_id = node.params["layer_id"]
        for layer in self._track().layers:
            if layer.layer_id == layer_id:
                return layer
        raise KeyError(layer_id)

    # ------------------------------------------------------------------- nodes

    async def _write_package(self, node: Node) -> NodeExecutionResult:
        atomic_write_json(
            self._run_dir / node.port("package").artifact_ref, self._resolved.identity()
        )
        return self._result(node)

    async def _generate_ground(self, node: Node) -> NodeExecutionResult:
        output = self._run_dir / node.port("image").artifact_ref
        # The model paints over the locked 12x4 lattice template; without it in
        # the references there is no lattice to preserve and the paintover can
        # never slice.
        template = terrain_atlas_template_path().read_bytes()
        topology_reference = terrain_atlas_topology_reference_path().read_bytes()
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
            *self._authored_references(node),
        )
        result = await self._images.generate(
            ImageGenerationRequest(
                prompt=self._card_prompt(node),
                artifact_path=output,
                input_references=references,
                quality="high",
                background="opaque",
                output_format="png",
                size="auto",
                timeout_seconds=600,
                metadata={"track_id": self._track().track_id, "operation": "ground_atlas"},
                validate=lambda artifact: require_terrain_atlas_source(
                    artifact.data, template=template
                ),
            )
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _validate_ground(self, node: Node) -> NodeExecutionResult:
        source_ref = self._dependency_artifact(node, kind=GROUND_RAW_KIND)
        raw = (self._run_dir / source_ref).read_bytes()
        canonical, validation = assemble_terrain_atlas(raw)
        if validation["classification"] != "direct_pass":
            raise ValueError("dynamic terrain atlas validation requires direct_pass media")
        await _write_local_image(
            self._run_dir / node.port("image").artifact_ref,
            canonical,
            prompt=(
                "Slice the model-painted 12x4 guide lattice, extract deterministic chroma alpha, "
                "apply the authoritative 47-mask lookup, harmonize only legal connector edges, "
                "and assemble the canonical atlas deterministically."
            ),
            inputs=[(source_ref, raw)],
            validation=validation,
        )
        atomic_write_json(self._run_dir / node.port("validation").artifact_ref, validation)
        return self._result(node)

    async def _generate_layer(self, node: Node) -> NodeExecutionResult:
        layer = self._layer(node)
        transparent = layer.alpha_mode == "transparent"
        output = self._run_dir / node.port("image").artifact_ref
        result = await self._images.generate(
            ImageGenerationRequest(
                prompt=self._card_prompt(node),
                artifact_path=output,
                input_references=self._authored_references(node),
                quality="high",
                background="transparent" if transparent else "opaque",
                output_format="png",
                size="1536x1024",
                timeout_seconds=600,
                metadata={"track_id": self._track().track_id, "layer_id": layer.layer_id},
                validate=lambda artifact: validate_provider_image(
                    artifact.data, width=1536, height=1024, transparent=transparent
                ),
            )
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _layer_loop(self, node: Node) -> NodeExecutionResult:
        layer = self._layer(node)
        construction = cast("LoopConstruction", node.params["construction"])
        source_ref = self._dependency_artifact(node, kind=LAYER_RAW_KIND)
        raw_data = (self._run_dir / source_ref).read_bytes()
        alpha_policy, coverage = layer_repeat_policies(layer.alpha_mode)

        def admit(data: bytes) -> Any:
            return validate_image_repeat(
                data,
                axis="x",
                alpha_policy=alpha_policy,
                coverage_policy=coverage,
                validation_policy=ImageRepeatValidationPolicy(),
            )

        from stage_gen.media import LOOP_METHODS

        admission = admit(raw_data)
        provider_operations = 0
        fallback = self._track().continuity.loop_fallback
        if admission.verdict == "pass":
            looped = raw_data
            record: dict[str, object] = {
                "schema_version": 1,
                "kind": "direct-loop-admission-v1",
                "construction": "none",
                "skipped_construction": construction,
                "provider_operations": 0,
            }
        elif not LOOP_METHODS[construction].is_generative:
            looped, record = construct_deterministic(construction, raw_data)
            record["construction"] = construction
        else:
            conditioning = loop_conditioning(construction, raw_data)
            edit_path = self._run_dir / node.port("edit_image").artifact_ref
            transparent = layer.alpha_mode == "transparent"
            generation = await self._images.generate(
                ImageGenerationRequest(
                    prompt=(
                        f"{layer.prompt}\nContinue this artwork seamlessly across the masked "
                        "span so the far left and far right edges of the original image join "
                        "perfectly. Match the existing palette, lighting, and level of detail "
                        "exactly. Paint only inside the masked span."
                    ),
                    artifact_path=edit_path,
                    input_references=(
                        ImageReference(
                            _data_url(conditioning.conditioning_png, "image/png"),
                            "loop-conditioning",
                        ),
                    ),
                    mask_reference=ImageReference(
                        _data_url(conditioning.mask_png, "image/png"), "loop-mask"
                    ),
                    quality="high",
                    background="transparent" if transparent else "opaque",
                    output_format="png",
                    size=f"{conditioning.width}x{conditioning.height}",
                    timeout_seconds=600,
                    metadata={
                        "track_id": self._track().track_id,
                        "layer_id": layer.layer_id,
                        "operation": f"loop_{construction}",
                    },
                )
            )
            provider_operations = generation.attempts
            try:
                looped, record = assemble_loop(
                    construction, raw_data, edit_path.read_bytes(), conditioning=conditioning
                )
                record["construction"] = construction
            except RegistrationError as error:
                looped, record = construct_deterministic(fallback, raw_data)
                record["construction"] = fallback
                record["rejected_construction"] = construction
                record["rejection"] = str(error)
            record["provider_operations"] = provider_operations
        report = admit(looped)
        if report.verdict != "pass" and LOOP_METHODS[construction].is_generative:
            rejected_report = report.model_dump(mode="json")
            looped, record = construct_deterministic(fallback, raw_data)
            record["construction"] = fallback
            record["rejected_construction"] = construction
            record["rejection"] = "constructed loop failed x-repeat admission"
            record["rejected_repeat"] = rejected_report
            record["provider_operations"] = provider_operations
            report = admit(looped)
        if report.verdict != "pass":
            raise ValueError(
                f"constructed loop for {self._track().track_id}/{layer.layer_id} failed "
                "x-repeat admission"
            )
        record["repeat"] = report.model_dump(mode="json")
        await _write_local_image(
            self._run_dir / node.port("loop_image").artifact_ref,
            looped,
            prompt=f"Loop the {layer.layer_id} layer by {record['construction']}.",
            inputs=[(source_ref, raw_data)],
            validation={"construction": record["construction"]},
        )
        atomic_write_json(self._run_dir / node.port("loop_report").artifact_ref, record)
        return self._result(
            node, attempts=max(1, provider_operations), provider_operations=provider_operations
        )

    async def _validate_layer(self, node: Node) -> NodeExecutionResult:
        layer = self._layer(node)
        source_ref = self._dependency_artifact(node, kind=LAYER_LOOP_KIND)
        looped = (self._run_dir / source_ref).read_bytes()
        if layer.alpha_mode == "transparent":
            published, trim = trim_layer_to_alpha_box(looped)
        else:
            published, trim = looped, {"trimmed": False}
        with Image.open(io.BytesIO(published)) as opened:
            width, height = opened.size
        validation = {
            "schema_version": 1,
            "kind": "sideview-runner-layer-validation-v1",
            "layer_id": layer.layer_id,
            "alpha_mode": layer.alpha_mode,
            "vertical_anchor": layer.vertical_anchor,
            "width": width,
            "height": height,
            "trim": trim,
        }
        await _write_local_image(
            self._run_dir / node.port("image").artifact_ref,
            published,
            prompt=f"Publish the admitted {layer.layer_id} loop unit.",
            inputs=[(source_ref, looped)],
            validation=validation,
        )
        atomic_write_json(self._run_dir / node.port("validation").artifact_ref, validation)
        return self._result(node)

    async def _generate_concept(self, node: Node) -> NodeExecutionResult:
        output = self._run_dir / node.port("image").artifact_ref
        result = await self._images.generate(
            ImageGenerationRequest(
                prompt=self._card_prompt(node),
                artifact_path=output,
                input_references=self._authored_references(node),
                quality="high",
                background="transparent",
                output_format="png",
                size="1024x1536",
                timeout_seconds=600,
                metadata={"avatar_id": self._runner.avatar.avatar.avatar_id},
                validate=lambda artifact: _validate_transparent_sprite(artifact.data),
            )
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _generate_motion(self, node: Node) -> NodeExecutionResult:
        geometry = DEFAULT_MOTION_ATLAS_GEOMETRY
        concept_ref = self._dependency_artifact(node, kind="avatar-concept-v1")
        concept_data = (self._run_dir / concept_ref).read_bytes()
        output = self._run_dir / node.port("image").artifact_ref
        result = await self._images.generate(
            ImageGenerationRequest(
                prompt=self._card_prompt(node),
                artifact_path=output,
                input_references=(
                    ImageReference(_data_url(concept_data, "image/png"), "identity-concept"),
                ),
                quality="high",
                background="transparent",
                output_format="png",
                size=geometry.provider_size,
                timeout_seconds=600,
                metadata={
                    "avatar_id": self._runner.avatar.avatar.avatar_id,
                    "state": str(node.params["state"]),
                },
                validate=lambda artifact: _validate_motion_source(artifact.data),
            )
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _validate_motion(self, node: Node) -> NodeExecutionResult:
        state = str(node.params["state"])
        geometry = DEFAULT_MOTION_ATLAS_GEOMETRY
        source_ref = self._dependency_artifact(node, kind=MOTION_RAW_KIND)
        source_data = (self._run_dir / source_ref).read_bytes()
        source_facts = _validate_motion_source(source_data)
        motion = next(entry for entry in self._runner.avatar.avatar.motions if entry.state == state)
        canonical_data, repack = repack_alpha_components(
            source_data,
            AlphaComponentRepackContract(
                rows=geometry.rows,
                columns=geometry.columns,
                required_cells=geometry.required_cells,
                anchor=motion.anchor,
            ),
        )
        validation = {
            "schema_version": 1,
            "kind": "sideview-runner-motion-validation-v1",
            "state": state,
            "columns": geometry.columns,
            "rows": geometry.rows,
            "frames": geometry.required_cells,
            "runtime_horizontal_mirroring": True,
            "source_validation": source_facts,
            "repack": repack,
        }
        await _write_local_image(
            self._run_dir / node.port("image").artifact_ref,
            canonical_data,
            prompt=f"Repack the avatar {state} source atlas using native-alpha components.",
            inputs=[(source_ref, source_data)],
            validation=repack,
        )
        atomic_write_json(self._run_dir / node.port("validation").artifact_ref, validation)
        return self._result(node)

    def _state_frames(self, node: Node) -> dict[str, tuple[bytes, ...]]:
        frames_by_state: dict[str, tuple[bytes, ...]] = {}
        geometry = DEFAULT_MOTION_ATLAS_GEOMETRY
        for state in RUNNER_MOTION_STATES:
            atlas_ref = f"avatar/{state}.png"
            frames_by_state[state] = split_atlas_columns(
                (self._run_dir / atlas_ref).read_bytes(), geometry.columns, geometry.rows
            )
        return frames_by_state

    async def _rebase_judge(self, node: Node) -> NodeExecutionResult:
        avatar = self._runner.avatar.avatar
        states = list(RUNNER_MOTION_STATES)
        frames_by_state = self._state_frames(node)
        plate = build_motion_rebase_plate(frames_by_state, baseline_state=RUNNER_BASELINE_STATE)
        plate_output = self._run_dir / node.port("plate").artifact_ref
        await _write_local_image(
            plate_output,
            plate.png,
            prompt=(
                f"Compose the complete motion-rebase judging plate for {avatar.avatar_id}: "
                "every frame of every state at one uniform source scale."
            ),
            inputs=[
                (f"avatar/{state}.png", (self._run_dir / f"avatar/{state}.png").read_bytes())
                for state in states
            ],
            validation={"baseline_state": RUNNER_BASELINE_STATE, "frame_count": len(plate.frames)},
            model="sideview-runner-rebase-plate-v1",
        )

        def admit(reading: object) -> dict[str, object]:
            if not isinstance(reading, MotionRebaseReading):
                raise MotionRebaseError("judge returned a reading the parser did not admit")
            return evaluate_motion_rebase(
                reading,
                published_states=states,
                plate=plate,
                baseline_state=RUNNER_BASELINE_STATE,
            )

        result = await self._structured.generate(
            StructuredGenerationRequest(
                prompt=motion_rebase_prompt(avatar.display_name, states),
                system=(
                    "You are a sprite-sheet scale judge. Return only the strict structured object."
                ),
                artifact_path=self._run_dir / node.port("reading").artifact_ref,
                schema=StructuredOutputSchema(
                    name=MOTION_REBASE_SCHEMA_NAME,
                    description="Per-state draw-scale multipliers against an actor's baseline",
                    json_schema=motion_rebase_json_schema(),
                    strict=True,
                ),
                parse=parse_motion_rebase,
                references=(self._structured_reference(plate_output),),
                artifact_value=admit,
                validate=admit,
                timeout_seconds=600,
                metadata={
                    "kind": "avatar-motion-rebase",
                    "entity_id": avatar.avatar_id,
                    "states": states,
                    "plate_sha256": plate.sha256,
                },
            )
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _rebase_verify(self, node: Node) -> NodeExecutionResult:
        avatar = self._runner.avatar.avatar
        states = list(RUNNER_MOTION_STATES)
        frames_by_state = self._state_frames(node)
        plate = build_motion_rebase_plate(frames_by_state, baseline_state=RUNNER_BASELINE_STATE)
        first_pass = admit_first_pass_record(
            json.loads(
                (
                    self._run_dir
                    / self._dependency_artifact(node, kind=REBASE_READING_KIND, port_id="reading")
                ).read_bytes()
            ),
            published_states=states,
            plate=plate,
            baseline_state=RUNNER_BASELINE_STATE,
        )
        verification_plate = build_motion_rebase_verification_plate(
            frames_by_state, first_pass, baseline_state=RUNNER_BASELINE_STATE
        )
        plate_output = self._run_dir / node.port("plate").artifact_ref
        await _write_local_image(
            plate_output,
            verification_plate.png,
            prompt=(
                f"Compose the motion-rebase verification plate for {avatar.avatar_id}: every "
                "frame with its first-pass multiplier applied."
            ),
            inputs=[
                (f"avatar/{state}.png", (self._run_dir / f"avatar/{state}.png").read_bytes())
                for state in states
            ],
            validation={"baseline_state": RUNNER_BASELINE_STATE},
            model="sideview-runner-rebase-plate-v1",
        )

        def admit(reading: object) -> dict[str, object]:
            if not isinstance(reading, MotionRebaseReading):
                raise MotionRebaseError("judge returned a reading the parser did not admit")
            return evaluate_motion_rebase_correction(
                reading,
                first_pass=first_pass,
                published_states=states,
                plate=plate,
                verification_plate=verification_plate,
                baseline_state=RUNNER_BASELINE_STATE,
            )

        result = await self._structured.generate(
            StructuredGenerationRequest(
                prompt=motion_rebase_verification_prompt(avatar.display_name, states),
                system=(
                    "You are a sprite-sheet scale judge. Return only the strict structured object."
                ),
                artifact_path=self._run_dir / node.port("verification").artifact_ref,
                schema=StructuredOutputSchema(
                    name=MOTION_REBASE_SCHEMA_NAME,
                    description="Residual per-state multipliers on the rebased plate",
                    json_schema=motion_rebase_json_schema(),
                    strict=True,
                ),
                parse=parse_motion_rebase,
                references=(self._structured_reference(plate_output),),
                artifact_value=admit,
                validate=admit,
                timeout_seconds=600,
                metadata={
                    "kind": "avatar-motion-rebase-verify",
                    "entity_id": avatar.avatar_id,
                    "states": states,
                    "plate_sha256": verification_plate.sha256,
                },
            )
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    def _structured_reference(self, path: Path) -> StructuredReference:
        return StructuredReference(
            url=_data_url(path.read_bytes(), "image/png"),
            provenance_ref=f"run://{path.relative_to(self._run_dir).as_posix()}",
        )

    async def _generate_catalog(self, node: Node) -> NodeExecutionResult:
        output = self._run_dir / node.port("image").artifact_ref
        result = await self._images.generate(
            ImageGenerationRequest(
                prompt=self._card_prompt(node),
                artifact_path=output,
                input_references=self._authored_references(node),
                quality="high",
                background="transparent",
                output_format="png",
                size="1024x1024",
                timeout_seconds=600,
                metadata={
                    "family": str(node.params["family"]),
                    "entity_id": str(node.params["entity_id"]),
                },
                validate=lambda artifact: _validate_transparent_sprite(artifact.data),
            )
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _validate_catalog(self, node: Node) -> NodeExecutionResult:
        source_ref = self._dependency_artifact(node, kind=CATALOG_RAW_KIND)
        source_data = (self._run_dir / source_ref).read_bytes()
        facts = _validate_transparent_sprite(source_data)
        published, trim = trim_layer_to_alpha_box(source_data)
        validation = {
            "schema_version": 1,
            "kind": "sideview-runner-catalog-validation-v1",
            "family": node.params["family"],
            "entity_id": node.params["entity_id"],
            "source_validation": facts,
            "trim": trim,
        }
        await _write_local_image(
            self._run_dir / node.port("image").artifact_ref,
            published,
            prompt=f"Publish the trimmed {node.params['entity_id']} catalog asset.",
            inputs=[(source_ref, source_data)],
            validation=validation,
        )
        atomic_write_json(self._run_dir / node.port("validation").artifact_ref, validation)
        return self._result(node)

    async def _generate_track(self, node: Node) -> NodeExecutionResult:
        if self._music is None:
            raise ValueError("runner soundtrack execution requires a music service")
        soundtrack = self._runner.soundtrack
        if soundtrack is None:
            raise ValueError("runner package declares no soundtrack member")
        track = soundtrack.track(str(node.params["track_id"]))
        result = await self._music.generate(
            MusicGenerationRequest(
                prompt=music_track_prompt(
                    medium="a 2D game",
                    game_id=self._package.game.game_id,
                    track_id=track.track_id,
                    creative_brief=track.creative_brief,
                    generation=track.generation,
                ),
                artifact_path=self._run_dir / node.port("audio").artifact_ref,
                output_format="mp3",
                timeout_seconds=900,
                metadata={
                    "track_id": track.track_id,
                    "target_duration_seconds": track.generation.target_duration_seconds,
                    "seamless_loop": track.generation.seamless_loop,
                },
                validate=lambda artifact: validate_music_payload(artifact.data),
            )
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _validate_track(self, node: Node) -> NodeExecutionResult:
        soundtrack = self._runner.soundtrack
        if soundtrack is None:
            raise ValueError("runner package declares no soundtrack member")
        track = soundtrack.track(str(node.params["track_id"]))
        source = self._run_dir / self._dependency_artifact(node, kind=SOUNDTRACK_TRACK_KIND)
        probe = await probe_audio(source, timeout_seconds=120)
        if probe.duration_seconds < 15:
            raise ValueError("generated soundtrack track is shorter than 15 seconds")
        atomic_write_json(
            self._run_dir / node.port("validation").artifact_ref,
            {
                "schema_version": 1,
                "kind": "sideview-runner-soundtrack-validation-v1",
                "track_id": track.track_id,
                "format_name": probe.format_name,
                "duration_seconds": round(probe.duration_seconds, 3),
                "container_valid": True,
                "listening_verdict": "not_performed",
            },
        )
        return self._result(node)

    # ---------------------------------------------------------------- manifest

    async def _assemble_manifest(self, node: Node) -> NodeExecutionResult:
        runner = self._runner
        track = runner.track
        scale = self._package.game.scale

        # Republish every authored reference the manifest names.
        for port in node.ports:
            if port.kind != "runner-reference-v1":
                continue
            data = self._package.file(port.artifact_ref).data
            await _write_local_image(
                self._run_dir / port.artifact_ref,
                data,
                prompt="Republish the authored reference into the run.",
                inputs=[(f"package://{port.artifact_ref}", data)],
                validation={"republished": True},
            )

        def read_json(ref: str) -> dict[str, object]:
            return cast("dict[str, object]", json.loads((self._run_dir / ref).read_bytes()))

        rebase = read_json("avatar/rebase-verification.json")
        multipliers = cast("dict[str, float]", rebase.get("multipliers_by_state", {}))

        def calibration(
            data: bytes, *, height_units_declared: float | None, subject: str, player: bool
        ) -> dict[str, object]:
            magnitude = (
                resolve_player_magnitude(None)
                if player
                else resolve_declared_magnitude(scale, height_units_declared, subject=subject)
            )
            extent = measure_subject_extent(data, subject=subject)
            return calibrate_subject(
                magnitude=magnitude,
                subject_extent_px=extent,
                measured_sha256=content_sha256(data),
                scale=scale,
                tile_px=RUNTIME_TILE_PX,
                subject=subject,
            ).as_record()

        avatar = runner.avatar.avatar
        run_atlas = (self._run_dir / "avatar/run.png").read_bytes()
        motions = []
        for motion_entry in avatar.motions:
            motions.append(
                {
                    "state": motion_entry.state,
                    "playback_mode": motion_entry.playback_mode,
                    "canonical_frame_indices": motion_entry.canonical_frame_indices,
                    "frames_per_second": motion_entry.frames_per_second,
                    "anchor": motion_entry.anchor,
                    "atlas": f"avatar/{motion_entry.state}.png",
                    "columns": DEFAULT_MOTION_ATLAS_GEOMETRY.columns,
                    "rebase_multiplier": multipliers.get(motion_entry.state, 1.0),
                }
            )

        props = []
        for prop_entry in runner.props.props:
            prop_data = (self._run_dir / f"catalog/props/{prop_entry.prop_id}.png").read_bytes()
            props.append(
                {
                    "prop_id": prop_entry.prop_id,
                    "display_name": prop_entry.display_name,
                    "image": f"catalog/props/{prop_entry.prop_id}.png",
                    "calibration": calibration(
                        prop_data,
                        height_units_declared=prop_entry.height_units,
                        subject=f"prop {prop_entry.prop_id}",
                        player=False,
                    ),
                }
            )
        items = []
        for item_entry in runner.items.items:
            item_data = (self._run_dir / f"catalog/items/{item_entry.item_id}.png").read_bytes()
            items.append(
                {
                    "item_id": item_entry.item_id,
                    "display_name": item_entry.display_name,
                    "image": f"catalog/items/{item_entry.item_id}.png",
                    "calibration": calibration(
                        item_data,
                        height_units_declared=item_entry.height_units,
                        subject=f"item {item_entry.item_id}",
                        player=False,
                    ),
                }
            )

        layers = []
        for layer in track.layers:
            validation = read_json(f"world/layers/{layer.layer_id}.validation.json")
            layers.append(
                {
                    "layer_id": layer.layer_id,
                    "plane": layer.plane,
                    "order": layer.order,
                    "parallax": layer.parallax,
                    "alpha_mode": layer.alpha_mode,
                    "vertical_anchor": layer.vertical_anchor,
                    "vertical_offset": layer.vertical_offset,
                    "image": f"world/layers/{layer.layer_id}.png",
                    "width": validation["width"],
                    "height": validation["height"],
                    "presentation": layer.presentation.model_dump(mode="json"),
                }
            )

        manifest = {
            "schema_version": 1,
            "kind": MANIFEST_KIND,
            "game_id": self._package.game.game_id,
            "display_name": self._package.game.display_name,
            "track_id": track.track_id,
            "track_display_name": track.display_name,
            "package_sha256": self._package.package_sha256,
            "presentation": runner.member.presentation.model_dump(mode="json"),
            "camera": {"mode": track.camera.mode},
            "scale": {
                "player_height_tiles": scale.player_height_tiles,
                "tile_px": RUNTIME_TILE_PX,
            },
            "gameplay": {
                "speed_profile": runner.gameplay.run.speed_profile,
                "jump_profile": runner.gameplay.run.jump_profile,
                "collision_policy": runner.gameplay.run.collision_policy,
                "ramp_profile": runner.gameplay.ramp.profile,
                "max_clear_gap_columns": runner.gameplay.jump_profile().max_clear_gap_columns,
                "max_rise_tiles": runner.gameplay.jump_profile().max_rise_tiles,
            },
            "ground": {
                "atlas": "world/ground.png",
                "mode": track.ground.mode,
                "vertical_fit": track.ground.vertical_fit,
            },
            "layers": layers,
            "segments": {
                "rows": track.segments.rows,
                "walk_surface_row": track.segments.walk_surface_row,
                "chunks": [
                    {
                        "segment_id": chunk.segment_id,
                        "difficulty": chunk.difficulty,
                        "occupancy": chunk.occupancy,
                        "hazards": [
                            {"prop_id": hazard.prop_id, "column": hazard.column}
                            for hazard in chunk.hazards
                        ],
                        "pickups": [
                            {
                                "item_id": pickup.item_id,
                                "column": pickup.column,
                                "row": pickup.row,
                            }
                            for pickup in chunk.pickups
                        ],
                    }
                    for chunk in track.segments.chunks
                ],
            },
            "avatar": {
                "avatar_id": avatar.avatar_id,
                "display_name": avatar.display_name,
                "concept": "avatar/concept.png",
                "calibration": calibration(
                    run_atlas, height_units_declared=None, subject="avatar", player=True
                ),
                "motions": motions,
            },
            "props": props,
            "items": items,
            "soundtrack": (
                None
                if runner.soundtrack is None
                else {
                    "selection": runner.soundtrack.playback.selection,
                    "tracks": [
                        {"track_id": track_id, "audio": f"soundtrack/{track_id}.mp3"}
                        for track_id in runner.soundtrack.track_ids
                    ],
                }
            ),
        }
        atomic_write_json(self._run_dir / node.port("manifest").artifact_ref, manifest)
        return self._result(node)


__all__ = ["RUNNER_BASELINE_STATE", "RUNTIME_TILE_PX", "SideviewRunnerNodeHandler"]
