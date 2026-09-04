"""Sideview-runner execution documents and the exact DAG one package's runner member implies.

Fourth recipe, same engine. The package node is a barrier into every provider
node - `cache_depends_on=()` - so an unrelated authored edit re-keys only the
nodes whose own instructions changed, and the container's visual direction is
the first input digest of every generative root, so one style edit re-bills
the whole generative graph on purpose.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from gnode import (
    SHA256_PATTERN,
    AuthoredInput,
    Binding,
    BindingTable,
    GraphBuilder,
    ModelRef,
    Node,
    NodeCard,
    PortRef,
)
from gnode.providers.openai import supports_openai_native_alpha_model
from stage_gen.components.game_fx import CutInPortraitSubject
from stage_gen.components.game_fx.nodes import (
    TOOL_LOOP_FEATURES,
    add_cut_in_nodes,
    add_sprite_nodes,
)
from stage_gen.components.game_soundtrack.nodes import (
    SoundtrackNodeTypes,
    add_soundtrack_nodes,
)
from stage_gen.components.game_soundtrack.prompt import music_track_prompt
from stage_gen.components.game_voices import GameVoice
from stage_gen.components.runner_content import (
    RUNNER_MOTION_ORDER,
    declared_boss_motion_states,
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
    MOTION_REBASE_SCHEMA_NAME,
)
from stage_gen.components.sideview_actor.motion_rebase_nodes import (
    MotionRebaseNodeTypes,
    RebaseLayout,
    add_motion_rebase_nodes,
)
from stage_gen.components.sideview_layers.nodes import (
    LayerLayout,
    LayerNodeTypes,
    add_layer_nodes,
)
from stage_gen.components.sound_effect import GeneratedClipRealization, PinnedTake
from stage_gen.components.speech import SpokenLineRealization
from stage_gen.recipes.graph_document import RecipeGraph
from stage_gen.recipes.ports import (
    artifact_port,
    attempts_port,
    object_digest,
    record_port,
    text_digest,
)
from stage_gen.recipes.sideview_runner.runner_prompts import (
    avatar_concept_prompt,
    avatar_motion_prompt,
    boss_concept_prompt,
    boss_motion_prompt,
    catalog_asset_prompt,
    fx_plate_prompt,
    ground_prompt,
    layer_loop_prompt,
    layer_prompt,
    soundtrack_direction,
    structural_ground_prompt,
    visual_direction_digest,
)
from stage_gen.recipes.sideview_runner.runner_types import (
    ATTEMPT_LEDGER_KIND,
    AUDIO_REPUBLISH,
    AVATAR_CONCEPT_GENERATE,
    AVATAR_CONCEPT_KIND,
    AVATAR_MOTION_GENERATE,
    AVATAR_MOTION_VALIDATE,
    BOSS_CONCEPT_GENERATE,
    BOSS_CONCEPT_KIND,
    BOSS_MOTION_GENERATE,
    BOSS_MOTION_VALIDATE,
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
    LAYER_LOOP_PAINT,
    LAYER_VALIDATE,
    MANIFEST_ASSEMBLE,
    MANIFEST_KIND,
    MOTION_ATLAS_KIND,
    MOTION_RAW_KIND,
    MOTION_REBASE_JUDGE,
    MOTION_REBASE_VERIFY,
    MOTION_VALIDATION_KIND,
    PACKAGE_KIND,
    PACKAGE_RESOLVE,
    REFERENCE_KIND,
    SOUND_EFFECT_CLIP_KIND,
    SOUND_EFFECT_FEATURES,
    SOUND_EFFECT_GENERATE,
    SOUND_EFFECT_VALIDATE,
    SOUND_EFFECT_VALIDATION_KIND,
    SOUNDTRACK_GENERATE,
    SOUNDTRACK_VALIDATE,
    SPEECH_CLIP_KIND,
    SPEECH_FEATURES,
    SPEECH_GENERATE,
    SPEECH_VALIDATE,
    SPEECH_VALIDATION_KIND,
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
    from stage_gen.orchestration.game_package import ResolvedRunnerMember
    from stage_gen.recipes.sideview_runner.runner_request import ResolvedRunnerPackage

RUNNER_GRAPH_SCHEMA_VERSION = 1
RUNNER_TRACE_SCHEMA_VERSION = 1
RUNNER_CACHE_NAMESPACE = "sideview-runner-nodes-v1"
RUNNER_CACHE_RECORD_KIND = "sideview-runner-node-cache-v1"
#: The generate node's identity contract: bump when what a clip request means changes.
SOUND_EFFECT_CONTRACT_VERSION = "runner-sound-effect-v1"
#: The spoken line's identity contract: bump when what a read request means changes.
SPEECH_CONTRACT_VERSION = "runner-speech-line-v1"
#: The pinned take's identity contract: the committed bytes and sidecar, republished.
PINNED_TAKE_CONTRACT_VERSION = "runner-pinned-take-v1"

#: The one canonical motion-state order: deterministic node ids and plate bands.
#: Re-exported from the contract component so the vocabulary that validates,
#: the tuple that fans out nodes, and the runtime's copy cannot drift apart.
RUNNER_MOTION_STATES: tuple[str, ...] = RUNNER_MOTION_ORDER


class RunnerOperationKind(StrEnum):
    """The capabilities a runner node is allowed to use."""

    LOCAL = "local"
    IMAGE_GENERATION = "image_generation"
    STRUCTURED_GENERATION = "structured_generation"
    TOOL_LOOP = "tool_loop"
    MUSIC_GENERATION = "music_generation"
    SOUND_EFFECT_GENERATION = "sound_effect_generation"
    SPEECH_GENERATION = "speech_generation"


class SideviewRunnerGraph(RecipeGraph):
    """One runner plan of record, bound to the package closure that produced it."""

    OPERATIONS = RunnerOperationKind
    VIEW_FIELDS = ("game_id", "track_id")

    schema_version: Literal[1]
    kind: Literal["sideview-runner-execution-graph-v1"]
    recipe: Literal["sideview-runner"]
    game_id: str
    track_id: str
    package_sha256: str = Field(pattern=SHA256_PATTERN)


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
            # One episode is bounded at six looks; the ceiling is a six-step
            # transcript of images on a frontier vision model.
            Binding(
                operation=RunnerOperationKind.TOOL_LOOP,
                model=ModelRef(model=config.text_model, provider="openrouter"),
                features=frozenset(TOOL_LOOP_FEATURES),
                resource_id="openrouter-tool-loop",
                estimated_duration_seconds=120.0,
                estimated_cost_low_usd=0.02,
                estimated_cost_high_usd=0.60,
                verified_on="2026-09-03",
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
            # Measured in the speech spike: a bark is a few dozen characters,
            # the route bills per character, and a call returns in seconds.
            Binding(
                operation=RunnerOperationKind.SPEECH_GENERATION,
                model=ModelRef(model=config.speech_model, provider="elevenlabs"),
                features=frozenset(SPEECH_FEATURES),
                resource_id="elevenlabs-speech",
                estimated_duration_seconds=10.0,
                estimated_cost_low_usd=0.001,
                estimated_cost_high_usd=0.05,
                verified_on="2026-09-03",
            ),
        ]
    )


def effective_loop_construction(resolved: ResolvedRunnerPackage, layer_id: str) -> LoopConstruction:
    track = resolved.runner.track
    for layer in track.layers:
        if layer.layer_id == layer_id:
            return layer.loop_construction or track.continuity.loop_construction
    raise KeyError(layer_id)


def _add_pinned_take(
    builder: GraphBuilder,
    effect_id: str,
    pinned: PinnedTake,
    *,
    kind: str,
    barrier: tuple[str, ...],
) -> Node:
    """One local node that republishes a reviewed audition as the effect's artifact.

    Its identity is the committed bytes and the sidecar that produced them, so
    re-pinning a different take re-keys it and nothing else. The package is a
    barrier here as it is for a bought draw: the take's own digests are its
    lineage, and an unrelated authored edit must not republish it.
    """

    return builder.add(
        AUDIO_REPUBLISH,
        f"audio-{effect_id}-republish",
        domain="audio",
        description=f"republish the reviewed {effect_id} take",
        params={"effect_id": effect_id},
        depends_on=barrier,
        cache_depends_on=(),
        input_digests=(
            object_digest(
                {
                    "contract": PINNED_TAKE_CONTRACT_VERSION,
                    "source_sha256": pinned.source_sha256,
                    "provenance_sha256": pinned.provenance_sha256,
                }
            ),
        ),
        ports=(artifact_port("audio", f"audio/{effect_id}.mp3", kind),),
    )


def resolved_voice(runner: ResolvedRunnerMember, voice_id: str) -> GameVoice:
    """The catalog voice a spoken line names.

    The package resolver has already refused a name the catalog lacks, so this
    is the graph builder refusing to plan around a voice it cannot see rather
    than a second validation.
    """

    if runner.voices is None:
        raise ValueError(f"spoken line names voice {voice_id!r} but the package binds no catalog")
    voice = runner.voices.voice(voice_id)
    if voice is None:
        raise ValueError(f"spoken line names voice {voice_id!r}, which the catalog does not cast")
    return voice


def runner_subject_reference(
    runner: ResolvedRunnerMember,
) -> Callable[[CutInPortraitSubject], PortRef]:
    """Resolve a cut-in portrait's declared subject to the node that draws it.

    The runner draws exactly one family of actor a moment can announce, so an id
    that is not a declared boss is refused rather than quietly resolved to
    something else. Member validation has already refused an id that is not the
    encounter's own boss; this is the graph builder refusing to reach for an
    artifact no node in it produces.
    """

    def resolve(subject: CutInPortraitSubject) -> PortRef:
        declared = set() if runner.bosses is None else {e.boss_id for e in runner.bosses.bosses}
        if subject.actor_id not in declared:
            raise ValueError(
                f"cut-in portrait subject {subject.actor_id!r} is not a boss this package draws"
            )
        return PortRef(node_id=f"boss-{subject.actor_id}-concept-generate", port_id="image")

    return resolve


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
        ports=(record_port("package", "package-identity.json", PACKAGE_KIND),),
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
                        text_digest(str(track.segments.walk_surface_row)),
                        text_digest(STRUCTURAL_GROUND_GUIDE_ID),
                        *(entry.sha256 for entry in ground_references),
                    ),
                    ports=(
                        artifact_port(
                            "image",
                            f"world/ground/{segment_id}.guide.png",
                            STRUCTURAL_GROUND_GUIDE_KIND,
                        ),
                        record_port(
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
                        text_digest(track.track_id),
                        direction_digest,
                        material_identity,
                        text_digest(prompt),
                        *(entry.sha256 for entry in ground_references),
                    ),
                    ports=(
                        artifact_port(
                            "image",
                            f"world/ground/{segment_id}.raw.png",
                            STRUCTURAL_GROUND_RAW_KIND,
                        ),
                        attempts_port(generate_id, ATTEMPT_LEDGER_KIND),
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
                    text_digest(first_chunk.segment_id),
                    text_digest(str(track.segments.walk_surface_row)),
                    text_digest(STRUCTURAL_GROUND_SEAM_BRIDGE_CANONICALIZER_ID),
                    *(entry.sha256 for entry in ground_references),
                ),
                ports=(
                    artifact_port(
                        "image",
                        "world/ground/shared-seam-bridge.png",
                        STRUCTURAL_GROUND_SEAM_BRIDGE_KIND,
                    ),
                    record_port(
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
                        text_digest(STRUCTURAL_GROUND_CANONICALIZER_ID),
                    ),
                    ports=(
                        artifact_port(
                            "image",
                            f"world/ground/{segment_id}.png",
                            STRUCTURAL_GROUND_KIND,
                        ),
                        record_port(
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
                text_digest(track.track_id),
                direction_digest,
                text_digest(ground_prompt(resolved, track)),
                terrain_template_sha256,
                terrain_topology_sha256,
                *(entry.sha256 for entry in ground_references),
            ),
            ports=(
                artifact_port("image", "world/ground.raw.png", GROUND_RAW_KIND),
                attempts_port("track-ground-generate", ATTEMPT_LEDGER_KIND),
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
                artifact_port("image", "world/ground.png", GROUND_ATLAS_KIND),
                record_port("validation", "world/ground.validation.json", GROUND_VALIDATION_KIND),
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
            construction = layer.loop_construction or track.continuity.loop_construction
            generative = LOOP_METHODS[construction].is_generative
            layer_validations.append(
                add_layer_nodes(
                    builder,
                    types=LayerNodeTypes(
                        generate=LAYER_GENERATE,
                        loop_paint=LAYER_LOOP_PAINT,
                        loop_construct=LAYER_LOOP_CONSTRUCT,
                        validate=LAYER_VALIDATE,
                    ),
                    layer=layer,
                    construction=construction,
                    node_ids=(
                        f"layer-{layer.layer_id}-generate",
                        f"layer-{layer.layer_id}-loop",
                        f"layer-{layer.layer_id}-validate",
                    ),
                    domain="world",
                    depends_on=barrier,
                    generate_digests=(
                        text_digest(track.track_id),
                        direction_digest,
                        text_digest(prompt),
                        *(entry.sha256 for entry in layer_references),
                    ),
                    loop_digests=(
                        text_digest(track.track_id),
                        text_digest(construction),
                        *(
                            (
                                text_digest(track.continuity.loop_fallback),
                                text_digest(layer.prompt),
                            )
                            if generative
                            else ()
                        ),
                    ),
                    layout=LayerLayout(
                        raw=f"world/layers/{layer.layer_id}.raw.png",
                        loop=f"world/layers/{layer.layer_id}.loop.png",
                        loop_report=f"world/layers/{layer.layer_id}.loop.json",
                        loop_edit=f"world/layers/{layer.layer_id}.loop-edit.png",
                        image=f"world/layers/{layer.layer_id}.png",
                        validation=f"world/layers/{layer.layer_id}.validation.json",
                    ),
                    params={"layer_id": layer.layer_id},
                    generate_prompt=prompt,
                    authored_inputs=layer_references,
                    loop_prompt=layer_loop_prompt(layer.prompt) if generative else None,
                    attempts_port=lambda node_id: attempts_port(node_id, ATTEMPT_LEDGER_KIND),
                )
            )

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
            text_digest(avatar.avatar_id),
            direction_digest,
            text_digest(avatar_concept_prompt(resolved, avatar)),
            *(entry.sha256 for entry in avatar_references),
        ),
        ports=(
            artifact_port("image", "avatar/concept.png", AVATAR_CONCEPT_KIND),
            attempts_port("avatar-concept-generate", ATTEMPT_LEDGER_KIND),
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
                    text_digest(avatar.avatar_id),
                    direction_digest,
                    text_digest(prompt),
                ),
                ports=(
                    artifact_port("image", f"avatar/{state}.raw.png", MOTION_RAW_KIND),
                    attempts_port(generate_id, ATTEMPT_LEDGER_KIND),
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
                input_digests=(text_digest(motions_by_state[state].anchor),),
                ports=(
                    artifact_port("image", f"avatar/{state}.png", MOTION_ATLAS_KIND),
                    record_port(
                        "validation", f"avatar/{state}.validation.json", MOTION_VALIDATION_KIND
                    ),
                ),
            )
            motion_validations.append(validated.node_id)

    # The judge reads the motion atlases (carried by lineage) and names the avatar in its
    # prompt; keying it on the closure re-billed both structured operations for every
    # unrelated authored edit.
    _avatar_rebase_judge, avatar_rebase_verify = add_motion_rebase_nodes(
        builder,
        types=MotionRebaseNodeTypes(judge=MOTION_REBASE_JUDGE, verify=MOTION_REBASE_VERIFY),
        judge_id="avatar-rebase-judge",
        verify_id="avatar-rebase-verify",
        domain="avatar",
        display_name=avatar.display_name,
        states=declared_motion_states(avatar),
        depends_on=motion_validations,
        input_digests=(
            text_digest(avatar.avatar_id),
            text_digest(avatar.display_name),
            text_digest(MOTION_REBASE_SCHEMA_NAME),
        ),
        layout=RebaseLayout(
            plate="avatar/rebase-plate.png",
            reading="avatar/rebase-reading.json",
            verification_plate="avatar/rebase-verify-plate.png",
            verification="avatar/rebase-verification.json",
        ),
        attempts_port=lambda node_id: attempts_port(node_id, ATTEMPT_LEDGER_KIND),
    )

    # -------------------------------------------------------------------- boss
    # The same pipeline the avatar rides, with its own vocabulary and its own
    # baseline: an encounter's boss is drawn once as a concept and then as one
    # strip per state, and rebased against its hover the way the avatar is
    # rebased against its run.
    boss_terminals: list[str] = []
    if runner.bosses is not None:
        boss_sources = {entry.reference_id: entry.source for entry in runner.bosses.references}
        for boss in runner.bosses.bosses:
            boss_references = reference_inputs(boss.reference_ids, boss_sources)
            boss_concept_text = boss_concept_prompt(resolved, boss)
            boss_concept = builder.add(
                BOSS_CONCEPT_GENERATE,
                f"boss-{boss.boss_id}-concept-generate",
                domain="boss",
                description=f"draw the {boss.boss_id} identity concept",
                params={"actor": "boss", "boss_id": boss.boss_id},
                depends_on=barrier,
                cache_depends_on=(),
                input_digests=(
                    text_digest(boss.boss_id),
                    direction_digest,
                    text_digest(boss_concept_text),
                    *(entry.sha256 for entry in boss_references),
                ),
                ports=(
                    artifact_port("image", f"boss/{boss.boss_id}/concept.png", BOSS_CONCEPT_KIND),
                    attempts_port(f"boss-{boss.boss_id}-concept-generate", ATTEMPT_LEDGER_KIND),
                ),
                card=NodeCard(prompt=boss_concept_text, authored_inputs=boss_references),
            )
            boss_motion_validations: list[str] = []
            boss_motions = {entry.state: entry for entry in boss.motions}
            with builder.within_template("boss-motion-pipeline@v1"):
                for state in declared_boss_motion_states(boss):
                    prompt = boss_motion_prompt(resolved, boss, state)
                    generate_id = f"boss-{boss.boss_id}-{state}-generate"
                    generated = builder.add(
                        BOSS_MOTION_GENERATE,
                        generate_id,
                        domain="boss",
                        description=f"draw the {boss.boss_id} {state} motion strip",
                        params={"actor": "boss", "boss_id": boss.boss_id, "state": state},
                        depends_on=(boss_concept.node_id,),
                        input_digests=(
                            text_digest(boss.boss_id),
                            direction_digest,
                            text_digest(prompt),
                        ),
                        ports=(
                            artifact_port(
                                "image",
                                f"boss/{boss.boss_id}/{state}.raw.png",
                                MOTION_RAW_KIND,
                            ),
                            attempts_port(generate_id, ATTEMPT_LEDGER_KIND),
                        ),
                        card=NodeCard(
                            prompt=prompt,
                            reference_inputs=(
                                PortRef(node_id=boss_concept.node_id, port_id="image"),
                            ),
                        ),
                    )
                    validated = builder.add(
                        BOSS_MOTION_VALIDATE,
                        f"boss-{boss.boss_id}-{state}-validate",
                        domain="boss",
                        description=f"repack the {boss.boss_id} {state} strip into cells",
                        params={"actor": "boss", "boss_id": boss.boss_id, "state": state},
                        depends_on=(generated.node_id,),
                        input_digests=(text_digest(boss_motions[state].anchor),),
                        ports=(
                            artifact_port(
                                "image",
                                f"boss/{boss.boss_id}/{state}.png",
                                MOTION_ATLAS_KIND,
                            ),
                            record_port(
                                "validation",
                                f"boss/{boss.boss_id}/{state}.validation.json",
                                MOTION_VALIDATION_KIND,
                            ),
                        ),
                    )
                    boss_motion_validations.append(validated.node_id)
            _boss_judge, boss_verify = add_motion_rebase_nodes(
                builder,
                types=MotionRebaseNodeTypes(judge=MOTION_REBASE_JUDGE, verify=MOTION_REBASE_VERIFY),
                judge_id=f"boss-{boss.boss_id}-rebase-judge",
                verify_id=f"boss-{boss.boss_id}-rebase-verify",
                domain="boss",
                display_name=boss.display_name,
                states=declared_boss_motion_states(boss),
                depends_on=boss_motion_validations,
                input_digests=(
                    text_digest(boss.boss_id),
                    text_digest(boss.display_name),
                    text_digest(MOTION_REBASE_SCHEMA_NAME),
                ),
                layout=RebaseLayout(
                    plate=f"boss/{boss.boss_id}/rebase-plate.png",
                    reading=f"boss/{boss.boss_id}/rebase-reading.json",
                    verification_plate=f"boss/{boss.boss_id}/rebase-verify-plate.png",
                    verification=f"boss/{boss.boss_id}/rebase-verification.json",
                ),
                params={"actor": "boss", "boss_id": boss.boss_id},
                attempts_port=lambda node_id: attempts_port(node_id, ATTEMPT_LEDGER_KIND),
            )
            boss_terminals.append(boss_verify)

    # ----------------------------------------------------------------- catalog
    catalog_validations: list[str] = []
    catalog_families: list[
        tuple[str, list[tuple[str, str, list[str], str | None]], dict[str, str]]
    ] = [
        (
            "prop",
            [
                (entry.prop_id, entry.prompt, entry.reference_ids, None)
                for entry in runner.props.props
            ],
            prop_sources,
        ),
        (
            "item",
            [
                (entry.item_id, entry.prompt, entry.reference_ids, None)
                for entry in runner.items.items
            ],
            item_sources,
        ),
    ]
    if runner.projectiles is not None:
        # The third family rides the same generate-and-admit pipeline, and
        # differs only in carrying its silhouette into the prompt: a thrown
        # object is the one catalog subject the runtime moves, so the axis it
        # was drawn along is part of the direction rather than a detail.
        projectile_sources = {
            entry.reference_id: entry.source for entry in runner.projectiles.references
        }
        catalog_families.append(
            (
                "projectile",
                [
                    (entry.projectile_id, entry.prompt, entry.reference_ids, entry.silhouette)
                    for entry in runner.projectiles.projectiles
                ],
                projectile_sources,
            )
        )
    with builder.within_template("catalog-asset-pipeline@v1"):
        for family, entries, sources in catalog_families:
            for entity_id, entity_prompt, reference_ids, silhouette in entries:
                prompt = catalog_asset_prompt(
                    resolved,
                    family=family,
                    prompt_text=entity_prompt,
                    silhouette=silhouette,
                )
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
                        text_digest(prompt),
                        *(entry.sha256 for entry in entity_references),
                    ),
                    ports=(
                        artifact_port(
                            "image", f"catalog/{family}s/{entity_id}.raw.png", CATALOG_RAW_KIND
                        ),
                        attempts_port(generate_id, ATTEMPT_LEDGER_KIND),
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
                        artifact_port(
                            "image", f"catalog/{family}s/{entity_id}.png", CATALOG_ASSET_KIND
                        ),
                        record_port(
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
            soundtrack_validations = add_soundtrack_nodes(
                builder,
                types=SoundtrackNodeTypes(
                    generate=SOUNDTRACK_GENERATE, validate=SOUNDTRACK_VALIDATE
                ),
                tracks=[
                    runner.soundtrack.track(track_id) for track_id in runner.soundtrack.track_ids
                ],
                depends_on=barrier,
                node_id=lambda track, stage: f"soundtrack-{track.track_id}-{stage}",
                prompt=lambda track: music_track_prompt(
                    medium="a 2D game",
                    game_id=package.game.game_id,
                    track_id=track.track_id,
                    creative_brief=track.creative_brief,
                    generation=track.generation,
                    direction=soundtrack_direction(),
                ),
                # Keyed on the complete compiled prompt, as it always was.
                generate_digests=lambda _track, provider_prompt: (text_digest(provider_prompt),),
                attempts_port=lambda node_id: attempts_port(node_id, ATTEMPT_LEDGER_KIND),
            )

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
                if realization.pinned is not None:
                    generated = _add_pinned_take(
                        builder,
                        effect.effect_id,
                        realization.pinned,
                        kind=SOUND_EFFECT_CLIP_KIND,
                        barrier=barrier,
                    )
                else:
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
                            object_digest(
                                {
                                    "contract": SOUND_EFFECT_CONTRACT_VERSION,
                                    **realization.generation_identity(),
                                }
                            ),
                        ),
                        ports=(
                            artifact_port(
                                "audio", f"audio/{effect.effect_id}.mp3", SOUND_EFFECT_CLIP_KIND
                            ),
                            attempts_port(generate_id, ATTEMPT_LEDGER_KIND),
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
                        record_port(
                            "validation",
                            f"audio/{effect.effect_id}.validation.json",
                            SOUND_EFFECT_VALIDATION_KIND,
                        ),
                    ),
                )
                sound_effect_validations.append(validated.node_id)

    # ---------------------------------------------------------- spoken lines
    # The text is authored, verbatim, annotations included. The identity takes
    # the *resolved* voice: the same catalog name recast to another provider
    # voice is a different asset. Gain, pitch and the frame budget stay out of
    # it, so a rebalance after listening is never a redraw.
    speech_validations: list[str] = []
    spoken_lines = runner.audio.spoken_lines()
    if spoken_lines:
        # A package whose every line is pinned never touches the route, so
        # the route is only required when a line is actually bought.
        speech_route = (
            profile.require(RunnerOperationKind.SPEECH_GENERATION)
            if runner.audio.bought_spoken_lines()
            else None
        )
        with builder.within_template("speech-pipeline@v1"):
            for effect in spoken_lines:
                realization = effect.realization
                assert isinstance(realization, SpokenLineRealization)
                if realization.pinned is not None:
                    generated = _add_pinned_take(
                        builder,
                        effect.effect_id,
                        realization.pinned,
                        kind=SPEECH_CLIP_KIND,
                        barrier=barrier,
                    )
                else:
                    assert speech_route is not None
                    voice = resolved_voice(runner, realization.voice_id)
                    if voice.provider.name != speech_route.model.provider:
                        raise ValueError(
                            f"voice {voice.voice_id} is cast on {voice.provider.name!r} but the "
                            f"speech route is {speech_route.model}"
                        )
                    generate_id = f"speech-{effect.effect_id}-generate"
                    generated = builder.add(
                        SPEECH_GENERATE,
                        generate_id,
                        domain="audio",
                        description=f"speak the {effect.effect_id} line",
                        params={"effect_id": effect.effect_id},
                        depends_on=barrier,
                        cache_depends_on=(),
                        input_digests=(
                            object_digest(
                                {
                                    "contract": SPEECH_CONTRACT_VERSION,
                                    **realization.generation_identity(
                                        provider=voice.provider.name,
                                        voice=voice.provider.voice,
                                        language_code=voice.language_code,
                                    ),
                                }
                            ),
                        ),
                        ports=(
                            artifact_port(
                                "audio", f"audio/{effect.effect_id}.mp3", SPEECH_CLIP_KIND
                            ),
                            attempts_port(generate_id, ATTEMPT_LEDGER_KIND),
                        ),
                        card=NodeCard(prompt=realization.text),
                    )
                validated = builder.add(
                    SPEECH_VALIDATE,
                    f"speech-{effect.effect_id}-validate",
                    domain="audio",
                    description=f"admit the {effect.effect_id} container, length, and level",
                    params={"effect_id": effect.effect_id},
                    depends_on=(generated.node_id,),
                    input_digests=(package.closure_sha256,),
                    ports=(
                        record_port(
                            "validation",
                            f"audio/{effect.effect_id}.validation.json",
                            SPEECH_VALIDATION_KIND,
                        ),
                    ),
                )
                speech_validations.append(validated.node_id)

    # -------------------------------------------------------------------- fx
    # The screen-FX plates are the shared family's nodes, hosted here: the
    # runner supplies its art direction and its ledger port and nothing else.
    fx_terminals: list[str] = []
    fx_sources: dict[str, str] = {}
    if runner.fx is not None:
        fx_sources = {entry.reference_id: entry.source for entry in runner.fx.references}

        fx_terminals = add_cut_in_nodes(
            builder,
            root="package-resolve",
            fx=runner.fx,
            style_prompt=lambda task: fx_plate_prompt(resolved, task),
            direction_digests=(direction_digest,),
            attempts_port=lambda node_id: attempts_port(node_id, ATTEMPT_LEDGER_KIND),
            subject_reference=runner_subject_reference(runner),
        )
        # World-space sprites are the same family's nodes and the same art direction;
        # they answer to the runtime rather than to a moment, so they bind no moment.
        fx_terminals.extend(
            add_sprite_nodes(
                builder,
                root="package-resolve",
                fx=runner.fx,
                style_prompt=lambda task: fx_plate_prompt(resolved, task),
                direction_digests=(direction_digest,),
                attempts_port=lambda node_id: attempts_port(node_id, ATTEMPT_LEDGER_KIND),
            )
        )

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
            *fx_sources.values(),
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
            avatar_rebase_verify,
            *boss_terminals,
            *catalog_validations,
            *soundtrack_validations,
            *sound_effect_validations,
            *speech_validations,
            *fx_terminals,
        ),
        input_digests=(package.closure_sha256,),
        ports=(
            *(
                artifact_port(
                    f"reference_{hashlib.sha256(source.encode('utf-8')).hexdigest()[:32]}",
                    source,
                    REFERENCE_KIND,
                )
                for source in republished_sources
            ),
            record_port("manifest", "manifest.json", MANIFEST_KIND),
        ),
    )

    return SideviewRunnerGraph.seal(
        resources=builder.resources(),
        nodes=builder.nodes,
        terminal_node_id="manifest-assemble",
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
