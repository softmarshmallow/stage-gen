"""Sideview-runner execution documents and the exact DAG one package's runner member implies.

Fourth recipe, same engine. The package node is a barrier into every provider
node - `cache_depends_on=()` - so an unrelated authored edit re-keys only the
nodes whose own instructions changed, and the container's visual direction is
the first input digest of every generative root, so one style edit re-bills
the whole generative graph on purpose.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import Field

from gnode import (
    SHA256_PATTERN,
    AuthoredInput,
    Binding,
    BindingTable,
    Graph,
    GraphBuilder,
    ModelRef,
    NodeCard,
    Port,
    PortRef,
    seal_graph,
)
from gnode.providers.openai import supports_openai_native_alpha_model
from stage_gen.components.game_soundtrack.prompt import music_track_prompt
from stage_gen.components.runner_content import (
    RUNNER_MOTION_ORDER,
    declared_motion_states,
)
from stage_gen.components.runner_track import (
    STRUCTURAL_GROUND_CANONICALIZER_ID,
    STRUCTURAL_GROUND_GUIDE_ID,
    STRUCTURAL_GROUND_SEAM_BRIDGE_CANONICALIZER_ID,
    RunnerSegmentChunk,
    RunnerStructuralGround,
    structural_ground_material_identity,
    structural_ground_occupancy_sha256,
)
from stage_gen.components.sideview_actor.motion_rebase import (
    motion_rebase_prompt,
    motion_rebase_verification_prompt,
)
from stage_gen.components.sound_effect import GeneratedClipRealization
from stage_gen.recipes.sideview_runner.runner_prompts import (
    avatar_concept_prompt,
    avatar_motion_prompt,
    catalog_asset_prompt,
    ground_prompt,
    layer_loop_prompt,
    layer_prompt,
    soundtrack_direction,
    structural_ground_prompt,
    visual_direction_digest,
)
from stage_gen.recipes.sideview_runner.runner_types import (
    ATTEMPT_LEDGER_KIND,
    AVATAR_CONCEPT_GENERATE,
    AVATAR_CONCEPT_KIND,
    AVATAR_MOTION_GENERATE,
    AVATAR_MOTION_VALIDATE,
    CATALOG_ASSET_GENERATE,
    CATALOG_ASSET_KIND,
    CATALOG_ASSET_VALIDATE,
    CATALOG_RAW_KIND,
    CATALOG_VALIDATION_KIND,
    GROUND_ATLAS_KIND,
    GROUND_RAW_KIND,
    GROUND_VALIDATION_KIND,
    LAYER_GENERATE,
    LAYER_LOOP_CONSTRUCT,
    LAYER_LOOP_EDIT_KIND,
    LAYER_LOOP_KIND,
    LAYER_LOOP_PAINT,
    LAYER_LOOP_REPORT_KIND,
    LAYER_RAW_KIND,
    LAYER_VALIDATE,
    LAYER_VALIDATION_KIND,
    MANIFEST_ASSEMBLE,
    MANIFEST_KIND,
    MOTION_ATLAS_KIND,
    MOTION_RAW_KIND,
    MOTION_REBASE_JUDGE,
    MOTION_REBASE_VERIFY,
    MOTION_VALIDATION_KIND,
    PACKAGE_KIND,
    PACKAGE_RESOLVE,
    REBASE_PLATE_KIND,
    REBASE_READING_KIND,
    REBASE_VERIFICATION_KIND,
    REFERENCE_KIND,
    SOUND_EFFECT_CLIP_KIND,
    SOUND_EFFECT_FEATURES,
    SOUND_EFFECT_GENERATE,
    SOUND_EFFECT_VALIDATE,
    SOUND_EFFECT_VALIDATION_KIND,
    SOUNDTRACK_GENERATE,
    SOUNDTRACK_TRACK_KIND,
    SOUNDTRACK_VALIDATE,
    SOUNDTRACK_VALIDATION_KIND,
    STRUCTURAL_GROUND_GUIDE_KIND,
    STRUCTURAL_GROUND_GUIDE_VALIDATION_KIND,
    STRUCTURAL_GROUND_KIND,
    STRUCTURAL_GROUND_RAW_KIND,
    STRUCTURAL_GROUND_SEAM_BRIDGE_KIND,
    STRUCTURAL_GROUND_SEAM_BRIDGE_VALIDATION_KIND,
    STRUCTURAL_GROUND_VALIDATION_KIND,
    TRACK_GROUND_GENERATE,
    TRACK_GROUND_VALIDATE,
    TRACK_STRUCTURAL_GROUND_GENERATE,
    TRACK_STRUCTURAL_GROUND_GUIDE,
    TRACK_STRUCTURAL_GROUND_SEAM_BRIDGE,
    TRACK_STRUCTURAL_GROUND_VALIDATE,
)
from stage_gen.resources import (
    terrain_atlas_lookup_path,
    terrain_atlas_template_path,
    terrain_atlas_topology_reference_path,
)

if TYPE_CHECKING:
    from stage_gen.config import StageGenConfig
    from stage_gen.media import LoopConstruction
    from stage_gen.recipes.sideview_runner.runner_request import ResolvedRunnerPackage

RUNNER_GRAPH_SCHEMA_VERSION = 1
RUNNER_TRACE_SCHEMA_VERSION = 1
RUNNER_CACHE_NAMESPACE = "sideview-runner-nodes-v1"
RUNNER_CACHE_RECORD_KIND = "sideview-runner-node-cache-v1"
#: The generate node's identity contract: bump when what a clip request means changes.
SOUND_EFFECT_CONTRACT_VERSION = "runner-sound-effect-v1"

#: The one canonical motion-state order: deterministic node ids and plate bands.
#: Re-exported from the contract component so the vocabulary that validates,
#: the tuple that fans out nodes, and the runtime's copy cannot drift apart.
RUNNER_MOTION_STATES: tuple[str, ...] = RUNNER_MOTION_ORDER


class RunnerOperationKind(StrEnum):
    """The capabilities a runner node is allowed to use."""

    LOCAL = "local"
    IMAGE_GENERATION = "image_generation"
    STRUCTURED_GENERATION = "structured_generation"
    MUSIC_GENERATION = "music_generation"
    SOUND_EFFECT_GENERATION = "sound_effect_generation"


class SideviewRunnerGraph(Graph):
    """One runner plan of record, bound to the package closure that produced it."""

    TRACE_SCHEMA_VERSION: ClassVar[int] = RUNNER_TRACE_SCHEMA_VERSION
    TRACE_EVENT_KIND: ClassVar[str] = "sideview-runner-execution-event-v1"
    RUN_SUMMARY_KIND: ClassVar[str] = "sideview-runner-execution-summary-v1"
    PROJECTION_KIND: ClassVar[str] = "sideview-runner-execution-projection-v1"
    VIEW_KIND: ClassVar[str] = "sideview-runner-execution-view-v1"
    VIEW_SCHEMA_VERSION: ClassVar[int] = 3

    schema_version: Literal[1]
    kind: Literal["sideview-runner-execution-graph-v1"]
    recipe: Literal["sideview-runner"]
    game_id: str
    track_id: str
    package_sha256: str = Field(pattern=SHA256_PATTERN)

    def identity_header(self) -> dict[str, object]:
        return {**super().identity_header(), "recipe": self.recipe}

    def annotator_key(self) -> str:
        return self.recipe

    def view_header(self) -> dict[str, object]:
        return {"recipe": self.recipe, "game_id": self.game_id, "track_id": self.track_id}

    def operation_vocabulary(self) -> tuple[str, ...]:
        return tuple(operation.value for operation in RunnerOperationKind)


def runner_graph_profile(config: StageGenConfig) -> BindingTable:
    """Declare the provider routes a runner plan may use, credentials untouched."""

    if not supports_openai_native_alpha_model(config.openai_image_model):
        raise ValueError(
            "sideview-runner requires a verified GPT Image 2 OpenAI model with "
            "native transparent-background support"
        )

    return BindingTable(
        [
            Binding(
                operation=RunnerOperationKind.IMAGE_GENERATION,
                model=ModelRef(model=config.openai_image_model, provider="openai"),
                features=frozenset(("transparent_background", "reference_images", "masked_edit")),
                resource_id="openai-image",
                estimated_duration_seconds=120.0,
                estimated_cost_low_usd=0.04,
                estimated_cost_high_usd=0.20,
                requests_per_minute=config.openai_image_ipm,
                rate_limit_owner="provider_adapter",
                verified_on="2026-08-25",
            ),
            Binding(
                operation=RunnerOperationKind.STRUCTURED_GENERATION,
                model=ModelRef(model=config.text_model, provider="openrouter"),
                features=frozenset(("structured_output", "image_input")),
                resource_id="openrouter-structured",
                estimated_duration_seconds=30.0,
                estimated_cost_low_usd=0.005,
                estimated_cost_high_usd=0.08,
                verified_on="2026-08-20",
            ),
            Binding(
                operation=RunnerOperationKind.MUSIC_GENERATION,
                model=ModelRef(model=config.music_model, provider="openrouter"),
                features=frozenset(("instrumental_loop",)),
                resource_id="openrouter-music",
                estimated_duration_seconds=300.0,
                estimated_cost_low_usd=0.05,
                estimated_cost_high_usd=0.50,
                verified_on="2026-08-20",
            ),
            # Measured in the sound-effect spike: about two seconds of wall
            # clock per call and roughly eleven credits per generated second.
            Binding(
                operation=RunnerOperationKind.SOUND_EFFECT_GENERATION,
                model=ModelRef(model=config.sound_effect_model, provider="elevenlabs"),
                features=frozenset(SOUND_EFFECT_FEATURES),
                resource_id="elevenlabs-sound-effect",
                estimated_duration_seconds=10.0,
                estimated_cost_low_usd=0.001,
                estimated_cost_high_usd=0.10,
                verified_on="2026-09-02",
            ),
        ]
    )


def _artifact(port_id: str, ref: str, kind: str) -> Port:
    return Port(port_id=port_id, artifact_ref=ref, kind=kind, sidecar_ref=f"{ref}.meta.json")


def _record(port_id: str, ref: str, kind: str) -> Port:
    return Port(port_id=port_id, artifact_ref=ref, kind=kind)


def _attempts(node_id: str) -> Port:
    return Port(
        port_id="attempts", artifact_ref=f"attempts/{node_id}.json", kind=ATTEMPT_LEDGER_KIND
    )


def _text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _object_sha256(value: object) -> str:
    return _text_digest(json.dumps(value, sort_keys=True, separators=(",", ":")))


def effective_loop_construction(resolved: ResolvedRunnerPackage, layer_id: str) -> LoopConstruction:
    track = resolved.runner.track
    for layer in track.layers:
        if layer.layer_id == layer_id:
            return layer.loop_construction or track.continuity.loop_construction
    raise KeyError(layer_id)


def build_runner_execution_graph(
    resolved: ResolvedRunnerPackage,
    *,
    profile: BindingTable,
) -> SideviewRunnerGraph:
    """Compile one package's runner member into the exact node graph it implies."""

    from stage_gen.media import LOOP_METHODS

    package = resolved.package
    runner = resolved.runner
    track = runner.track
    direction_digest = visual_direction_digest(resolved)
    builder = GraphBuilder(profile=profile, local_max_in_flight=32)

    def reference_inputs(
        reference_ids: list[str], sources: dict[str, str]
    ) -> tuple[AuthoredInput, ...]:
        return tuple(
            AuthoredInput(
                label=reference_id,
                ref=sources[reference_id],
                sha256=package.file(sources[reference_id]).sha256,
            )
            for reference_id in reference_ids
        )

    track_sources = {entry.reference_id: entry.source for entry in track.references}
    avatar_sources = {entry.reference_id: entry.source for entry in runner.avatar.references}
    prop_sources = {entry.reference_id: entry.source for entry in runner.props.references}
    item_sources = {entry.reference_id: entry.source for entry in runner.items.references}

    builder.add(
        PACKAGE_RESOLVE,
        "package-resolve",
        domain="package",
        description="Capture and admit the prepared package's runner member",
        input_digests=(package.closure_sha256,),
        ports=(_record("package", "package-identity.json", PACKAGE_KIND),),
    )
    barrier = ("package-resolve",)

    # ------------------------------------------------------------------ ground
    ground_references = reference_inputs(track.ground.reference_ids, track_sources)
    ground_validations: list[str] = []
    if isinstance(track.ground, RunnerStructuralGround):
        material_identity = structural_ground_material_identity(
            prompt=track.ground.prompt,
            visual_direction_sha256=direction_digest,
            reference_sha256=[entry.sha256 for entry in ground_references],
            projection=track.ground.projection_mode(),
        )
        with builder.within_template("structural-ground-segment-pipeline@v2"):
            structural_sources: list[tuple[RunnerSegmentChunk, str, str, str]] = []
            for chunk in track.segments.chunks:
                segment_id = chunk.segment_id
                occupancy_digest = structural_ground_occupancy_sha256(chunk.occupancy)
                prompt = structural_ground_prompt(resolved, track, chunk)
                guide_id = f"track-ground-{segment_id}-guide"
                guide = builder.add(
                    TRACK_STRUCTURAL_GROUND_GUIDE,
                    guide_id,
                    domain="world",
                    description=f"compose the {segment_id} structural-ground guide and aprons",
                    params={"segment_id": segment_id},
                    depends_on=barrier,
                    cache_depends_on=(),
                    input_digests=(
                        direction_digest,
                        material_identity,
                        occupancy_digest,
                        _text_digest(str(track.segments.walk_surface_row)),
                        _text_digest(STRUCTURAL_GROUND_GUIDE_ID),
                        *(entry.sha256 for entry in ground_references),
                    ),
                    ports=(
                        _artifact(
                            "image",
                            f"world/ground/{segment_id}.guide.png",
                            STRUCTURAL_GROUND_GUIDE_KIND,
                        ),
                        _record(
                            "validation",
                            f"world/ground/{segment_id}.guide.json",
                            STRUCTURAL_GROUND_GUIDE_VALIDATION_KIND,
                        ),
                    ),
                    card=NodeCard(authored_inputs=ground_references),
                )
                generate_id = f"track-ground-{segment_id}-generate"
                generated = builder.add(
                    TRACK_STRUCTURAL_GROUND_GENERATE,
                    generate_id,
                    domain="world",
                    description=f"paint bespoke structural ground for {segment_id}",
                    params={"segment_id": segment_id},
                    depends_on=(guide.node_id,),
                    input_digests=(
                        _text_digest(track.track_id),
                        direction_digest,
                        material_identity,
                        _text_digest(prompt),
                        *(entry.sha256 for entry in ground_references),
                    ),
                    ports=(
                        _artifact(
                            "image",
                            f"world/ground/{segment_id}.raw.png",
                            STRUCTURAL_GROUND_RAW_KIND,
                        ),
                        _attempts(generate_id),
                    ),
                    card=NodeCard(
                        prompt=prompt,
                        reference_inputs=(PortRef(node_id=guide.node_id, port_id="image"),),
                        authored_inputs=ground_references,
                    ),
                )
                structural_sources.append(
                    (chunk, occupancy_digest, guide.node_id, generated.node_id)
                )

            first_chunk, first_occupancy_digest, first_guide_id, first_generated_id = (
                structural_sources[0]
            )
            seam_bridge = builder.add(
                TRACK_STRUCTURAL_GROUND_SEAM_BRIDGE,
                "track-ground-shared-seam-bridge",
                domain="world",
                description=(
                    "canonicalize the first generated right apron as the shared seam bridge"
                ),
                params={"segment_id": first_chunk.segment_id},
                depends_on=(first_guide_id, first_generated_id),
                input_digests=(
                    material_identity,
                    first_occupancy_digest,
                    _text_digest(first_chunk.segment_id),
                    _text_digest(str(track.segments.walk_surface_row)),
                    _text_digest(STRUCTURAL_GROUND_SEAM_BRIDGE_CANONICALIZER_ID),
                    *(entry.sha256 for entry in ground_references),
                ),
                ports=(
                    _artifact(
                        "image",
                        "world/ground/shared-seam-bridge.png",
                        STRUCTURAL_GROUND_SEAM_BRIDGE_KIND,
                    ),
                    _record(
                        "validation",
                        "world/ground/shared-seam-bridge.validation.json",
                        STRUCTURAL_GROUND_SEAM_BRIDGE_VALIDATION_KIND,
                    ),
                ),
                card=NodeCard(
                    reference_inputs=(
                        PortRef(node_id=first_guide_id, port_id="image"),
                        PortRef(node_id=first_generated_id, port_id="image"),
                    ),
                    authored_inputs=ground_references,
                ),
            )

            for chunk, occupancy_digest, guide_id, generated_id in structural_sources:
                segment_id = chunk.segment_id
                validated = builder.add(
                    TRACK_STRUCTURAL_GROUND_VALIDATE,
                    f"track-ground-{segment_id}-validate",
                    domain="world",
                    description=(
                        f"mask {segment_id} and install complementary shared-bridge roles"
                    ),
                    params={"segment_id": segment_id},
                    depends_on=(guide_id, generated_id, seam_bridge.node_id),
                    input_digests=(
                        material_identity,
                        occupancy_digest,
                        _text_digest(STRUCTURAL_GROUND_CANONICALIZER_ID),
                    ),
                    ports=(
                        _artifact(
                            "image",
                            f"world/ground/{segment_id}.png",
                            STRUCTURAL_GROUND_KIND,
                        ),
                        _record(
                            "validation",
                            f"world/ground/{segment_id}.validation.json",
                            STRUCTURAL_GROUND_VALIDATION_KIND,
                        ),
                    ),
                    card=NodeCard(
                        reference_inputs=(
                            PortRef(node_id=guide_id, port_id="image"),
                            PortRef(node_id=generated_id, port_id="image"),
                            PortRef(node_id=seam_bridge.node_id, port_id="image"),
                        ),
                        authored_inputs=ground_references,
                    ),
                )
                ground_validations.append(validated.node_id)
    else:
        terrain_template_sha256 = hashlib.sha256(
            terrain_atlas_template_path().read_bytes()
        ).hexdigest()
        terrain_topology_sha256 = hashlib.sha256(
            terrain_atlas_topology_reference_path().read_bytes()
        ).hexdigest()
        ground_generate = builder.add(
            TRACK_GROUND_GENERATE,
            "track-ground-generate",
            domain="world",
            description="Paint the 47-mask ground atlas over the locked template",
            depends_on=barrier,
            cache_depends_on=(),
            input_digests=(
                _text_digest(track.track_id),
                direction_digest,
                _text_digest(ground_prompt(resolved, track)),
                terrain_template_sha256,
                terrain_topology_sha256,
                *(entry.sha256 for entry in ground_references),
            ),
            ports=(
                _artifact("image", "world/ground.raw.png", GROUND_RAW_KIND),
                _attempts("track-ground-generate"),
            ),
            card=NodeCard(
                prompt=ground_prompt(resolved, track),
                authored_inputs=ground_references,
                template_ref="terrain_atlas_12x4_template_v1",
            ),
        )
        ground_validate = builder.add(
            TRACK_GROUND_VALIDATE,
            "track-ground-validate",
            domain="world",
            description="Canonicalize the painted atlas against the locked topology",
            depends_on=(ground_generate.node_id,),
            input_digests=(
                package.closure_sha256,
                terrain_template_sha256,
                hashlib.sha256(terrain_atlas_lookup_path().read_bytes()).hexdigest(),
            ),
            ports=(
                _artifact("image", "world/ground.png", GROUND_ATLAS_KIND),
                _record("validation", "world/ground.validation.json", GROUND_VALIDATION_KIND),
            ),
            card=NodeCard(
                reference_inputs=(PortRef(node_id=ground_generate.node_id, port_id="image"),)
            ),
        )
        ground_validations.append(ground_validate.node_id)

    # ------------------------------------------------------------------ layers
    layer_validations: list[str] = []
    with builder.within_template("track-layer-pipeline@v1"):
        for layer in track.layers:
            transparent = layer.alpha_mode == "transparent"
            prompt = layer_prompt(resolved, layer.prompt, transparent=transparent)
            layer_references = reference_inputs(layer.reference_ids, track_sources)
            generate_id = f"layer-{layer.layer_id}-generate"
            generated = builder.add(
                LAYER_GENERATE,
                generate_id,
                domain="world",
                description=f"paint the {layer.layer_id} parallax layer",
                params={"layer_id": layer.layer_id},
                depends_on=barrier,
                cache_depends_on=(),
                input_digests=(
                    _text_digest(track.track_id),
                    direction_digest,
                    _text_digest(prompt),
                    *(entry.sha256 for entry in layer_references),
                ),
                ports=(
                    _artifact("image", f"world/layers/{layer.layer_id}.raw.png", LAYER_RAW_KIND),
                    _attempts(generate_id),
                ),
                card=NodeCard(prompt=prompt, authored_inputs=layer_references),
            )
            construction = layer.loop_construction or track.continuity.loop_construction
            loop_type = (
                LAYER_LOOP_PAINT
                if LOOP_METHODS[construction].is_generative
                else LAYER_LOOP_CONSTRUCT
            )
            loop_id = f"layer-{layer.layer_id}-loop"
            loop_ports = [
                _artifact("loop_image", f"world/layers/{layer.layer_id}.loop.png", LAYER_LOOP_KIND),
                _record(
                    "loop_report",
                    f"world/layers/{layer.layer_id}.loop.json",
                    LAYER_LOOP_REPORT_KIND,
                ),
            ]
            if LOOP_METHODS[construction].is_generative:
                loop_ports.append(
                    _artifact(
                        "edit_image",
                        f"world/layers/{layer.layer_id}.loop-edit.png",
                        LAYER_LOOP_EDIT_KIND,
                    )
                )
                loop_ports.append(_attempts(loop_id))
            looped = builder.add(
                loop_type,
                loop_id,
                domain="world",
                description=f"loop the {layer.layer_id} layer by {construction}",
                params={"layer_id": layer.layer_id, "construction": construction},
                depends_on=(generated.node_id,),
                input_digests=(
                    _text_digest(track.track_id),
                    _text_digest(construction),
                    *(
                        (
                            _text_digest(track.continuity.loop_fallback),
                            _text_digest(layer.prompt),
                        )
                        if LOOP_METHODS[construction].is_generative
                        else ()
                    ),
                ),
                ports=tuple(loop_ports),
                card=(
                    NodeCard(prompt=layer_loop_prompt(layer.prompt))
                    if LOOP_METHODS[construction].is_generative
                    else None
                ),
            )
            validated = builder.add(
                LAYER_VALIDATE,
                f"layer-{layer.layer_id}-validate",
                domain="world",
                description=f"admit and place the {layer.layer_id} layer",
                params={"layer_id": layer.layer_id},
                depends_on=(looped.node_id,),
                input_digests=(package.closure_sha256,),
                ports=(
                    _artifact("image", f"world/layers/{layer.layer_id}.png", LAYER_LOOP_KIND),
                    _record(
                        "validation",
                        f"world/layers/{layer.layer_id}.validation.json",
                        LAYER_VALIDATION_KIND,
                    ),
                ),
            )
            layer_validations.append(validated.node_id)

    # ------------------------------------------------------------------ avatar
    avatar = runner.avatar.avatar
    avatar_references = reference_inputs(avatar.reference_ids, avatar_sources)
    concept = builder.add(
        AVATAR_CONCEPT_GENERATE,
        "avatar-concept-generate",
        domain="avatar",
        description=f"draw the {avatar.avatar_id} identity concept",
        depends_on=barrier,
        cache_depends_on=(),
        input_digests=(
            _text_digest(avatar.avatar_id),
            direction_digest,
            _text_digest(avatar_concept_prompt(resolved, avatar)),
            *(entry.sha256 for entry in avatar_references),
        ),
        ports=(
            _artifact("image", "avatar/concept.png", AVATAR_CONCEPT_KIND),
            _attempts("avatar-concept-generate"),
        ),
        card=NodeCard(
            prompt=avatar_concept_prompt(resolved, avatar), authored_inputs=avatar_references
        ),
    )
    motion_validations: list[str] = []
    motions_by_state = {entry.state: entry for entry in avatar.motions}
    with builder.within_template("avatar-motion-pipeline@v1"):
        # Fan out over what the avatar actually declares, in the canonical
        # order: the required set is a function of the member (a track with no
        # overhead hazards buys no slide strip), and admission already proved
        # the declaration matches the track's demands.
        for state in declared_motion_states(avatar):
            prompt = avatar_motion_prompt(resolved, avatar, state)
            generate_id = f"avatar-{state}-generate"
            generated = builder.add(
                AVATAR_MOTION_GENERATE,
                generate_id,
                domain="avatar",
                description=f"draw the {avatar.avatar_id} {state} motion strip",
                params={"state": state},
                depends_on=(concept.node_id,),
                input_digests=(
                    _text_digest(avatar.avatar_id),
                    direction_digest,
                    _text_digest(prompt),
                ),
                ports=(
                    _artifact("image", f"avatar/{state}.raw.png", MOTION_RAW_KIND),
                    _attempts(generate_id),
                ),
                card=NodeCard(
                    prompt=prompt,
                    reference_inputs=(PortRef(node_id=concept.node_id, port_id="image"),),
                ),
            )
            validated = builder.add(
                AVATAR_MOTION_VALIDATE,
                f"avatar-{state}-validate",
                domain="avatar",
                description=f"repack the {state} strip into canonical cells",
                params={"state": state},
                depends_on=(generated.node_id,),
                # Identity is what the repack actually reads - the strip via
                # lineage plus the authored anchor - not the whole closure:
                # this node feeds the paid rebase judges, and an unrelated
                # authored edit must not re-bill them through it.
                input_digests=(_text_digest(motions_by_state[state].anchor),),
                ports=(
                    _artifact("image", f"avatar/{state}.png", MOTION_ATLAS_KIND),
                    _record(
                        "validation", f"avatar/{state}.validation.json", MOTION_VALIDATION_KIND
                    ),
                ),
            )
            motion_validations.append(validated.node_id)

    rebase_judge = builder.add(
        MOTION_REBASE_JUDGE,
        "avatar-rebase-judge",
        domain="avatar",
        description="judge every motion atlas against the run baseline on one plate",
        depends_on=tuple(motion_validations),
        # The judge reads the motion atlases (carried by lineage) and names the
        # avatar in its prompt; keying it on the closure re-billed both
        # structured operations for every unrelated authored edit.
        input_digests=(
            _text_digest(avatar.avatar_id),
            _text_digest(avatar.display_name),
        ),
        ports=(
            _artifact("plate", "avatar/rebase-plate.png", REBASE_PLATE_KIND),
            _artifact("reading", "avatar/rebase-reading.json", REBASE_READING_KIND),
            _attempts("avatar-rebase-judge"),
        ),
        card=NodeCard(
            prompt=motion_rebase_prompt(avatar.display_name, list(declared_motion_states(avatar)))
        ),
    )
    rebase_verify = builder.add(
        MOTION_REBASE_VERIFY,
        "avatar-rebase-verify",
        domain="avatar",
        description="judge the residual on a plate composed with the first reading applied",
        depends_on=(rebase_judge.node_id,),
        input_digests=(
            _text_digest(avatar.avatar_id),
            _text_digest(avatar.display_name),
        ),
        ports=(
            _artifact("plate", "avatar/rebase-verify-plate.png", REBASE_PLATE_KIND),
            _artifact("verification", "avatar/rebase-verification.json", REBASE_VERIFICATION_KIND),
            _attempts("avatar-rebase-verify"),
        ),
        card=NodeCard(
            prompt=motion_rebase_verification_prompt(
                avatar.display_name, list(declared_motion_states(avatar))
            )
        ),
    )

    # ----------------------------------------------------------------- catalog
    catalog_validations: list[str] = []
    catalog_families = (
        (
            "prop",
            [(entry.prop_id, entry.prompt, entry.reference_ids) for entry in runner.props.props],
            prop_sources,
        ),
        (
            "item",
            [(entry.item_id, entry.prompt, entry.reference_ids) for entry in runner.items.items],
            item_sources,
        ),
    )
    with builder.within_template("catalog-asset-pipeline@v1"):
        for family, entries, sources in catalog_families:
            for entity_id, entity_prompt, reference_ids in entries:
                prompt = catalog_asset_prompt(resolved, family=family, prompt_text=entity_prompt)
                entity_references = reference_inputs(reference_ids, sources)
                generate_id = f"{family}-{entity_id}-generate"
                generated = builder.add(
                    CATALOG_ASSET_GENERATE,
                    generate_id,
                    domain="catalog",
                    description=f"draw the {entity_id} {family}",
                    params={"family": family, "entity_id": entity_id},
                    depends_on=barrier,
                    cache_depends_on=(),
                    input_digests=(
                        direction_digest,
                        _text_digest(prompt),
                        *(entry.sha256 for entry in entity_references),
                    ),
                    ports=(
                        _artifact(
                            "image", f"catalog/{family}s/{entity_id}.raw.png", CATALOG_RAW_KIND
                        ),
                        _attempts(generate_id),
                    ),
                    card=NodeCard(prompt=prompt, authored_inputs=entity_references),
                )
                validated = builder.add(
                    CATALOG_ASSET_VALIDATE,
                    f"{family}-{entity_id}-validate",
                    domain="catalog",
                    description=f"admit isolated alpha for the {entity_id} {family}",
                    params={"family": family, "entity_id": entity_id},
                    depends_on=(generated.node_id,),
                    input_digests=(package.closure_sha256,),
                    ports=(
                        _artifact(
                            "image", f"catalog/{family}s/{entity_id}.png", CATALOG_ASSET_KIND
                        ),
                        _record(
                            "validation",
                            f"catalog/{family}s/{entity_id}.validation.json",
                            CATALOG_VALIDATION_KIND,
                        ),
                    ),
                )
                catalog_validations.append(validated.node_id)

    # -------------------------------------------------------------- soundtrack
    soundtrack_validations: list[str] = []
    if runner.soundtrack is not None:
        with builder.within_template("soundtrack-pipeline@v1"):
            for track_id in runner.soundtrack.track_ids:
                audio_track = runner.soundtrack.track(track_id)
                provider_prompt = music_track_prompt(
                    medium="a 2D game",
                    game_id=package.game.game_id,
                    track_id=audio_track.track_id,
                    creative_brief=audio_track.creative_brief,
                    generation=audio_track.generation,
                    direction=soundtrack_direction(),
                )
                generate_id = f"soundtrack-{track_id}-generate"
                generated = builder.add(
                    SOUNDTRACK_GENERATE,
                    generate_id,
                    domain="soundtrack",
                    description=f"generate the {track_id} track",
                    params={"track_id": track_id},
                    depends_on=barrier,
                    cache_depends_on=(),
                    input_digests=(_text_digest(provider_prompt),),
                    ports=(
                        _artifact("audio", f"soundtrack/{track_id}.mp3", SOUNDTRACK_TRACK_KIND),
                        _attempts(generate_id),
                    ),
                    card=NodeCard(prompt=provider_prompt),
                )
                validated = builder.add(
                    SOUNDTRACK_VALIDATE,
                    f"soundtrack-{track_id}-validate",
                    domain="soundtrack",
                    description=f"admit the {track_id} container and duration",
                    params={"track_id": track_id},
                    depends_on=(generated.node_id,),
                    input_digests=(package.closure_sha256,),
                    ports=(
                        _record(
                            "validation",
                            f"soundtrack/{track_id}.validation.json",
                            SOUNDTRACK_VALIDATION_KIND,
                        ),
                    ),
                )
                soundtrack_validations.append(validated.node_id)

    # ------------------------------------------------------------ sound effects
    # The prompt is the authored text, verbatim: the recipe compiles nothing
    # onto it, and playback gain stays out of the identity so a rebalance
    # after listening is never a redraw.
    sound_effect_validations: list[str] = []
    generated_effects = runner.audio.generated_effects()
    if generated_effects:
        with builder.within_template("sound-effect-pipeline@v1"):
            for effect in generated_effects:
                realization = effect.realization
                assert isinstance(realization, GeneratedClipRealization)
                generate_id = f"sound-effect-{effect.effect_id}-generate"
                generated = builder.add(
                    SOUND_EFFECT_GENERATE,
                    generate_id,
                    domain="audio",
                    description=f"generate the {effect.effect_id} clip",
                    params={"effect_id": effect.effect_id},
                    depends_on=barrier,
                    cache_depends_on=(),
                    input_digests=(
                        _object_sha256(
                            {
                                "contract": SOUND_EFFECT_CONTRACT_VERSION,
                                **realization.generation_identity(),
                            }
                        ),
                    ),
                    ports=(
                        _artifact("audio", f"audio/{effect.effect_id}.mp3", SOUND_EFFECT_CLIP_KIND),
                        _attempts(generate_id),
                    ),
                    card=NodeCard(prompt=realization.prompt),
                )
                validated = builder.add(
                    SOUND_EFFECT_VALIDATE,
                    f"sound-effect-{effect.effect_id}-validate",
                    domain="audio",
                    description=f"admit the {effect.effect_id} container, duration, and level",
                    params={"effect_id": effect.effect_id},
                    depends_on=(generated.node_id,),
                    input_digests=(package.closure_sha256,),
                    ports=(
                        _record(
                            "validation",
                            f"audio/{effect.effect_id}.validation.json",
                            SOUND_EFFECT_VALIDATION_KIND,
                        ),
                    ),
                )
                sound_effect_validations.append(validated.node_id)

    # ---------------------------------------------------------------- manifest
    # Reference IDs are catalog-local. Two legal IDs in different members may
    # bind the same source path, which is one published artifact rather than
    # two ports pointing at the same ref. Key ports on the path digest so the
    # identity stays stable when another source sorts before it.
    republished_sources = sorted(
        {
            *track_sources.values(),
            *avatar_sources.values(),
            *prop_sources.values(),
            *item_sources.values(),
        }
    )
    builder.add(
        MANIFEST_ASSEMBLE,
        "manifest-assemble",
        domain="package",
        description="Assemble the playable runner runtime manifest",
        depends_on=(
            *ground_validations,
            *layer_validations,
            *motion_validations,
            rebase_verify.node_id,
            *catalog_validations,
            *soundtrack_validations,
            *sound_effect_validations,
        ),
        input_digests=(package.closure_sha256,),
        ports=(
            *(
                _artifact(
                    f"reference_{hashlib.sha256(source.encode('utf-8')).hexdigest()[:32]}",
                    source,
                    REFERENCE_KIND,
                )
                for source in republished_sources
            ),
            _record("manifest", "manifest.json", MANIFEST_KIND),
        ),
    )

    return seal_graph(
        SideviewRunnerGraph,
        resources=builder.resources(),
        nodes=builder.nodes,
        terminal_node_id="manifest-assemble",
        schema_version=RUNNER_GRAPH_SCHEMA_VERSION,
        kind="sideview-runner-execution-graph-v1",
        recipe="sideview-runner",
        game_id=package.game.game_id,
        track_id=track.track_id,
        package_sha256=package.package_sha256,
    )


__all__ = [
    "RUNNER_CACHE_NAMESPACE",
    "RUNNER_CACHE_RECORD_KIND",
    "RUNNER_GRAPH_SCHEMA_VERSION",
    "RUNNER_MOTION_STATES",
    "RUNNER_TRACE_SCHEMA_VERSION",
    "RunnerOperationKind",
    "SideviewRunnerGraph",
    "build_runner_execution_graph",
    "effective_loop_construction",
    "runner_graph_profile",
]
