"""Execute one sideview-runner node: world, avatar, catalog, and the manifest.

Every provider operation stays inside a component service, which owns the whole
retry-validate-persist contract. Generation-side machinery is the shared
side-view components - the 47-mask terrain atlas, the loop pipeline, the
alpha-component repacker, the motion-rebase judges - composed here into this
recipe's node wiring.
"""

from __future__ import annotations

import inspect
import io
import json
import math
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

from PIL import Image

from gnode import (
    ArtifactProvenance,
    BinaryArtifact,
    CacheDisposition,
    CancellationError,
    ImageGenerationRequest,
    ImageReference,
    InputProvenance,
    NodeArtifact,
    NodeExecutionError,
    NodeExecutionResult,
    NodeType,
    ProvenanceInput,
    SoftwareIdentity,
    SoundEffectGenerationRequest,
    SpeechGenerationRequest,
    StructuredOutputSchema,
    StructuredReference,
    ToolLoopReference,
    ToolLoopService,
    assert_audio_signature,
    assert_image_signature,
    atomic_write_bytes,
    atomic_write_json,
    dependency_port,
    hash_input_reference,
    sanitize_reference,
    write_artifact_with_provenance_async,
)
from stage_gen.canonical import content_sha256
from stage_gen.components.actor_content import MotionPresentation
from stage_gen.components.game_fx.cut_in import (
    admit_cut_in_placement,
    draw_procedural_frame,
    validate_frame_plate,
    validate_portrait_plate,
)
from stage_gen.components.game_fx.nodes import (
    FX_CUT_IN_DRAW,
    FX_CUT_IN_GENERATE,
    FX_CUT_IN_PLACE,
    FX_CUT_IN_PLACEMENT_KIND,
    FX_CUT_IN_PLATE_KIND,
    FX_CUT_IN_RAW_KIND,
    FX_CUT_IN_REVIEW,
    FX_CUT_IN_VALIDATE,
    FX_CUT_IN_VALIDATION_KIND,
    FX_SPRITE_DUST_GENERATE,
    FX_SPRITE_DUST_RAW_KIND,
    FX_SPRITE_DUST_VALIDATE,
    FxCutInHost,
    cut_in_generate_request,
    cut_in_place_request,
    cut_in_review_request,
    derive_cut_in_validation,
    derive_sprite_dust_validation,
    fx_manifest_block,
    parse_cut_in_review,
    sprite_dust_generate_request,
    write_cut_in_draw,
    write_cut_in_validation,
    write_sprite_dust_validation,
)
from stage_gen.components.game_fx.sprite import validate_dust_atlas
from stage_gen.components.game_soundtrack import SoundtrackTrack
from stage_gen.components.game_soundtrack.nodes import SoundtrackHandlers, SoundtrackHost
from stage_gen.components.game_soundtrack.prompt import music_track_prompt
from stage_gen.components.image_repeat import ImageRepeatValidationPolicy, validate_image_repeat
from stage_gen.components.runner_audio import RunnerAudioContract
from stage_gen.components.runner_content import (
    RUNNER_BOSS_BASELINE_STATE,
    declared_boss_motion_states,
    declared_motion_states,
)
from stage_gen.components.runner_gameplay import (
    COLLISION_BOXES,
    DUCK_PROFILES,
    JUMP_PROFILES,
    SPEED_PROFILES,
    VITALS_PROFILES,
    RunnerGameplayContract,
)
from stage_gen.components.runner_track import (
    STRUCTURAL_GROUND_CANONICALIZER_ID,
    STRUCTURAL_GROUND_CELL_PX,
    STRUCTURAL_GROUND_GUIDE_HEIGHT,
    STRUCTURAL_GROUND_GUIDE_WIDTH,
    STRUCTURAL_GROUND_SEAM_BRIDGE_CANONICALIZER_ID,
    RunnerStructuralGround,
    build_structural_ground_guide,
    canonicalize_structural_ground,
    canonicalize_structural_ground_seam_bridge,
    structural_ground_material_identity,
    validate_structural_ground_canonical,
    validate_structural_ground_seam_bridge,
    validate_structural_ground_source,
)
from stage_gen.components.sideview_actor.asset_unit import (
    SubjectExtentAxis,
    calibrate_subject,
    measure_subject_extent,
    resolve_declared_magnitude,
    resolve_player_magnitude,
)
from stage_gen.components.sideview_actor.motion_geometry import DEFAULT_MOTION_ATLAS_GEOMETRY
from stage_gen.components.sideview_actor.motion_rebase import (
    MOTION_REBASE_SCHEMA_NAME,
    admit_first_pass_record,
    build_motion_rebase_plate,
    build_motion_rebase_verification_plate,
    motion_rebase_json_schema,
    motion_rebase_prompt,
    motion_rebase_verification_prompt,
)
from stage_gen.components.sideview_actor.motion_rebase_nodes import (
    MotionRebaseHandlers,
    MotionRebaseHost,
    RebaseSubject,
)
from stage_gen.components.sideview_layers.contract import resolve_layer_placement
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
from stage_gen.components.sound_effect import (
    DURATION_TOLERANCE_SECONDS,
    GeneratedClipRealization,
    PinnedTake,
    admit_sound_effect_bytes,
    admit_sound_effect_bytes_sync,
)
from stage_gen.components.speech import (
    SpokenLineRealization,
    admit_speech_bytes,
    admit_speech_bytes_sync,
)
from stage_gen.identity import (
    IMAGE_GENERATION_COMPONENT,
    MUSIC_GENERATION_COMPONENT,
    SOUND_EFFECT_GENERATION_COMPONENT,
    SPEECH_GENERATION_COMPONENT,
    STAGE_GEN_TOOL,
    STRUCTURED_GENERATION_COMPONENT,
    TOOL_LOOP_COMPONENT,
)
from stage_gen.media import RegistrationError, data_url, probe_audio, validate_music_payload
from stage_gen.media.layer_rasters import trim_layer_to_alpha_box
from stage_gen.media.sprite_sheets import (
    AlphaComponentRepackContract,
    repack_alpha_components,
    split_atlas_columns,
)
from stage_gen.recipes.manifest_blocks import present_blocks
from stage_gen.recipes.node_handler import NodeMethod, RecipeNodeHandler
from stage_gen.recipes.sideview_runner.runner_graph import (
    RUNNER_CACHE_NAMESPACE,
    RUNNER_CACHE_RECORD_KIND,
    RunnerOperationKind,
    SideviewRunnerGraph,
)
from stage_gen.recipes.sideview_runner.runner_prompts import (
    layer_loop_prompt,
    soundtrack_direction,
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
    MANIFEST_SCHEMA_VERSION,
    MOTION_RAW_KIND,
    MOTION_REBASE_JUDGE,
    MOTION_REBASE_VERIFY,
    PACKAGE_RESOLVE,
    REBASE_READING_KIND,
    RUNNER_MANIFEST_BLOCK_VERSIONS,
    SOUND_EFFECT_CLIP_KIND,
    SOUND_EFFECT_GENERATE,
    SOUND_EFFECT_VALIDATE,
    SOUNDTRACK_GENERATE,
    SOUNDTRACK_VALIDATE,
    SPEECH_CLIP_KIND,
    SPEECH_GENERATE,
    SPEECH_VALIDATE,
    STRUCTURAL_GROUND_GUIDE_KIND,
    STRUCTURAL_GROUND_RAW_KIND,
    STRUCTURAL_GROUND_SEAM_BRIDGE_KIND,
    TRACK_GROUND_GENERATE,
    TRACK_GROUND_VALIDATE,
    TRACK_STRUCTURAL_GROUND_GENERATE,
    TRACK_STRUCTURAL_GROUND_GUIDE,
    TRACK_STRUCTURAL_GROUND_SEAM_BRIDGE,
    TRACK_STRUCTURAL_GROUND_VALIDATE,
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
        SoundEffectGenerationService,
        SpeechGenerationService,
        StructuredGenerationService,
    )
    from stage_gen.components.game_voices import GameVoice
    from stage_gen.components.platformer_map import PreparedMapLayer
    from stage_gen.components.runner_track import RunnerSegmentChunk, RunnerTrack
    from stage_gen.media import LoopConstruction
    from stage_gen.recipes.sideview_runner.runner_request import ResolvedRunnerPackage

RUNNER_HANDLER_VERSION = "1"
RUNNER_BASELINE_STATE = "run"


@dataclass(frozen=True, slots=True)
class _ActorSubject:
    """Which drawn actor a node is about.

    The runner draws two kinds of actor through one pipeline: the avatar it
    always has, and the boss an encounter brings. They differ in their
    vocabulary, their baseline and where their art lands, and in nothing else -
    the concept, the strips, the repack and the two rebase judgements are the
    same operation on both. Resolving the subject from the node's own params is
    what keeps that one pipeline rather than two copies drifting apart.
    """

    label: str
    entity_id: str
    display_name: str
    motions: tuple[MotionPresentation, ...]
    states: tuple[str, ...]
    baseline_state: str
    #: Where this actor's artifacts live, relative to the run directory.
    artifact_dir: str
    concept_kind: str

    def motion(self, state: str) -> MotionPresentation:
        return next(entry for entry in self.motions if entry.state == state)


#: The one place the unit meets pixels in this recipe, matching the platformer's
#: projection so a shared avatar reads at the same magnitude in both genres.
RUNTIME_TILE_PX = 64
RUNNER_CATALOG_SPARSE_TAIL_TRIM_VERSION = "runner-catalog-sparse-tail-trim-v1"
RUNNER_MOTION_SOURCE_VISIBLE_ALPHA_MIN = 128
RUNNER_SPRITE_VISIBLE_ALPHA_MIN = 16
RUNNER_CUTOUT_MIN_TRANSPARENT_FRACTION = 0.10
RUNNER_CUTOUT_MIN_VISIBLE_FRACTION = 0.005
RUNNER_CUTOUT_MIN_TRANSPARENT_EDGE_FRACTION = 0.10
RUNNER_LAYER_MIN_TRANSPARENT_FRACTION = 0.05
RUNNER_LAYER_MIN_VISIBLE_FRACTION = 0.005
RUNNER_LAYER_MIN_TRANSPARENT_EDGE_FRACTION = 0.05

_COMPONENT = SoftwareIdentity(name="@stage-gen/sideview-runner", version=RUNNER_HANDLER_VERSION)


def _json_normalize_provider_identity(value: dict[str, object]) -> dict[str, object]:
    """Return the exact JSON value a persisted provenance sidecar can represent."""

    try:
        normalized = json.loads(
            json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("runner provider identity is not standards-compliant JSON") from error
    if not isinstance(normalized, dict):
        raise ValueError("runner provider identity must normalize to an object")
    return cast("dict[str, object]", normalized)


def _image_media_type(data: bytes) -> str:
    with Image.open(io.BytesIO(data)) as opened:
        image_format = opened.format
    media_type = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}.get(
        image_format or ""
    )
    if media_type is None:
        raise ValueError(f"runner image input has unsupported format {image_format!r}")
    return media_type


def _input_media_type(ref: str, data: bytes) -> str:
    clean_ref = ref.split("#", 1)[0]
    if clean_ref.endswith(".json"):
        return "application/json"
    return _image_media_type(data)


async def _write_local_image(
    path: Path,
    data: bytes,
    *,
    prompt: str,
    inputs: Sequence[tuple[str, bytes]],
    validation: Mapping[str, object],
    model: str = "sideview-runner-local-v1",
) -> Path:
    media_type = _image_media_type(data)
    return await write_artifact_with_provenance_async(
        path,
        BinaryArtifact(data=data, media_type=media_type),
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
                    media_type=_input_media_type(ref, payload),
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
    if not (extrema[0] == 0 and extrema[1] >= RUNNER_SPRITE_VISIBLE_ALPHA_MIN):
        raise ValueError(
            "sprite output must contain transparent pixels and meaningful visible alpha"
        )
    alpha = image.getchannel("A")
    alpha_bytes = alpha.tobytes()
    pixel_count = image.width * image.height
    transparent_fraction = alpha_bytes.count(0) / pixel_count
    visible_fraction = sum(alpha.histogram()[RUNNER_SPRITE_VISIBLE_ALPHA_MIN:]) / pixel_count
    edge_bytes = b"".join(
        (
            alpha.crop((0, 0, image.width, 1)).tobytes(),
            alpha.crop((0, image.height - 1, image.width, image.height)).tobytes(),
            alpha.crop((0, 1, 1, image.height - 1)).tobytes(),
            alpha.crop((image.width - 1, 1, image.width, image.height - 1)).tobytes(),
        )
    )
    transparent_edge_fraction = edge_bytes.count(0) / len(edge_bytes)
    if transparent_fraction < RUNNER_CUTOUT_MIN_TRANSPARENT_FRACTION:
        raise ValueError("sprite output lacks meaningful transparent negative space")
    if visible_fraction < RUNNER_CUTOUT_MIN_VISIBLE_FRACTION:
        raise ValueError("sprite output lacks meaningful visible alpha coverage")
    if transparent_edge_fraction < RUNNER_CUTOUT_MIN_TRANSPARENT_EDGE_FRACTION:
        raise ValueError("sprite output lacks meaningful transparent edge separation")
    return {
        "width": image.width,
        "height": image.height,
        "alpha_min": extrema[0],
        "alpha_max": extrema[1],
        "visible_alpha_min": RUNNER_SPRITE_VISIBLE_ALPHA_MIN,
        "transparent_fraction": round(transparent_fraction, 9),
        "visible_fraction": round(visible_fraction, 9),
        "transparent_edge_fraction": round(transparent_edge_fraction, 9),
    }


def _publish_runner_layer(
    layer: PreparedMapLayer, looped: bytes
) -> tuple[bytes, dict[str, object]]:
    """Trim a looped layer and resolve its placement, once, for the node and its cache mirror.

    Module-level and pure so the live validate node and the byte-exact cache admission cannot
    drift: they must produce identical records or every cached run becomes a permanent miss. A
    transparent layer's offset is resolved from the raster it actually received, through the
    resolver the platformer shares; the opaque cover is placed by its anchor alone.
    """

    if layer.alpha_mode == "transparent":
        published, trim = trim_layer_to_alpha_box(looped)
        placement: dict[str, object] | None = resolve_layer_placement(layer, trim)
    else:
        published, trim, placement = looped, {"trimmed": False}, None
    with Image.open(io.BytesIO(published)) as opened:
        width, height = opened.size
    validation: dict[str, object] = {
        "schema_version": 2,
        "kind": "sideview-runner-layer-validation-v2",
        "layer_id": layer.layer_id,
        "alpha_mode": layer.alpha_mode,
        "vertical_anchor": layer.vertical_anchor,
        "width": width,
        "height": height,
        "trim": trim,
        "placement": placement,
    }
    return published, validation


def _published_layer_offset(validation: dict[str, object]) -> float | None:
    """The producer-resolved offset, or None for the opaque cover that has no placement."""

    placement = validation.get("placement")
    if not isinstance(placement, dict):
        return None
    return cast("float", placement["vertical_offset"])


def _published_layer_offset_source(validation: dict[str, object]) -> str | None:
    placement = validation.get("placement")
    if not isinstance(placement, dict):
        return None
    return cast("str", placement["vertical_offset_source"])


def _validate_layer_candidate(data: bytes, *, transparent: bool) -> dict[str, object]:
    return validate_provider_image(
        data,
        width=1536,
        height=1024,
        transparent=transparent,
        minimum_transparent_fraction=(
            RUNNER_LAYER_MIN_TRANSPARENT_FRACTION if transparent else 0.0
        ),
        minimum_visible_fraction=(RUNNER_LAYER_MIN_VISIBLE_FRACTION if transparent else 0.0),
        minimum_transparent_edge_fraction=(
            RUNNER_LAYER_MIN_TRANSPARENT_EDGE_FRACTION if transparent else 0.0
        ),
    )


def canonicalize_runner_catalog_sprite(
    data: bytes, *, family: str
) -> tuple[bytes, dict[str, object], dict[str, object]]:
    """Trim transparent framing and a proven short sparse tail from runner props.

    A generated prop may carry a decorative leaf or glow a few rows below the broad hardware or
    foot that gameplay must register. We trim only a narrow, low-area terminal tail: the median
    meaningful-alpha column bottom must sit 2-8% above the alpha box, its row must span at least a
    quarter of the painted width, and pixels below it must be at most 1% of painted pixels. Long
    cables, roots, legs, and other meaningful narrow silhouettes therefore remain untouched.
    """

    published, vertical_trim = trim_layer_to_alpha_box(data)
    tail_report: dict[str, object] = {
        "schema_version": 1,
        "kind": RUNNER_CATALOG_SPARSE_TAIL_TRIM_VERSION,
        "painted_alpha_threshold": 64,
        "minimum_tail_height_fraction": 0.02,
        "maximum_tail_height_fraction": 0.08,
        "minimum_contact_row_coverage": 0.25,
        "maximum_tail_painted_fraction": 0.01,
        "applied": False,
        "reason": "family_is_not_prop" if family != "prop" else "tail_not_proven_sparse",
    }
    if family != "prop":
        return published, vertical_trim, tail_report

    bounds = cast("dict[str, object]", vertical_trim["bounds"])
    median_raw = bounds.get("column_bottom_median")
    if not isinstance(median_raw, int) or isinstance(median_raw, bool):
        tail_report["reason"] = "missing_column_bottom_median"
        return published, vertical_trim, tail_report
    trimmed_top = cast("int", vertical_trim["trimmed_top"])
    trimmed_height = cast("int", vertical_trim["trimmed_height"])
    contact_row = median_raw - trimmed_top
    if not 0 <= contact_row < trimmed_height:
        raise ValueError("runner catalog median contact row lies outside the alpha trim")

    with Image.open(io.BytesIO(published)) as opened:
        image = opened.convert("RGBA")
    alpha = image.getchannel("A")
    painted = alpha.point(lambda value: 255 if value > 64 else 0)
    painted_box = painted.getbbox()
    if painted_box is None:
        raise ValueError("runner catalog sprite has no pixels above painted alpha threshold")
    painted_bytes = painted.tobytes()
    painted_count = painted_bytes.count(255)
    painted_width = painted_box[2] - painted_box[0]
    contact_start = contact_row * image.width
    contact_count = painted_bytes[contact_start : contact_start + image.width].count(255)
    tail_start = (contact_row + 1) * image.width
    tail_count = painted_bytes[tail_start:].count(255)
    tail_rows = image.height - contact_row - 1
    tail_height_fraction = tail_rows / image.height
    contact_row_coverage = contact_count / painted_width
    tail_painted_fraction = tail_count / painted_count
    tail_report.update(
        {
            "candidate_contact_row": contact_row,
            "candidate_output_height": contact_row + 1,
            "tail_rows": tail_rows,
            "tail_height_fraction": round(tail_height_fraction, 6),
            "contact_row_coverage": round(contact_row_coverage, 6),
            "tail_painted_fraction": round(tail_painted_fraction, 6),
        }
    )
    admitted = (
        0.02 <= tail_height_fraction <= 0.08
        and contact_row_coverage >= 0.25
        and tail_painted_fraction <= 0.01
    )
    if not admitted:
        return published, vertical_trim, tail_report

    cropped = image.crop((0, 0, image.width, contact_row + 1))
    stream = io.BytesIO()
    cropped.save(stream, format="PNG", optimize=False)
    tail_report.update(
        {
            "applied": True,
            "reason": "short_sparse_terminal_tail",
            "source_height": image.height,
            "output_height": cropped.height,
            "removed_rows": image.height - cropped.height,
        }
    )
    return stream.getvalue(), vertical_trim, tail_report


def _validate_catalog_candidate(data: bytes, *, family: str) -> dict[str, object]:
    """Keep meaningful-alpha trimming inside the catalog provider retry owner."""

    source = _validate_transparent_sprite(data)
    published, trim, sparse_tail_trim = canonicalize_runner_catalog_sprite(data, family=family)
    extent = measure_subject_extent(published, subject=f"runner {family}")
    return {
        "source": source,
        "trim": trim,
        "sparse_tail_trim": sparse_tail_trim,
        "painted_extent_px": extent,
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
        visible = sum(cell.histogram()[RUNNER_MOTION_SOURCE_VISIBLE_ALPHA_MIN:]) / (
            cell.width * cell.height
        )
        coverage.append(visible)
    if any(value < 0.005 for value in coverage):
        raise ValueError("motion atlas is missing a required visible cell")
    return {
        **facts,
        "cell_coverage_alpha_min": RUNNER_MOTION_SOURCE_VISIBLE_ALPHA_MIN,
        "cell_visible_fractions": [round(value, 6) for value in coverage],
    }


def _validate_motion_candidate(
    data: bytes, *, anchor: Literal["center", "bottom", "top"]
) -> dict[str, object]:
    """Keep decisive deterministic repacking inside the provider retry owner."""

    geometry = DEFAULT_MOTION_ATLAS_GEOMETRY
    source = _validate_motion_source(data)
    _canonical, repack = repack_alpha_components(
        data,
        AlphaComponentRepackContract(
            rows=geometry.rows,
            columns=geometry.columns,
            required_cells=geometry.required_cells,
            anchor=anchor,
            source_slot_policy="exact_required_slots",
        ),
    )
    return {"source": source, "repack": repack}


def _manifest_encounter(gameplay: RunnerGameplayContract) -> dict[str, object] | None:
    """The encounter block: every named field, and every number a proof read.

    Flat, like the run's own arithmetic beside it. The runtime mirrors these
    proofs rather than re-deriving them, so publishing the whole table is what
    keeps the played fight the fight admission proved.
    """

    encounter = gameplay.encounter
    if encounter is None:
        return None
    boss = encounter.boss_profile()
    thrust = encounter.thrust_profile()
    return {
        "profile": encounter.profile,
        "locomotion": encounter.locomotion,
        "interval_columns": encounter.interval_columns,
        "arena_segment_id": encounter.arena_segment_id,
        "boss_id": encounter.boss_id,
        "boss_projectile_id": encounter.boss_projectile_id,
        "player_projectile_id": encounter.player_projectile_id,
        "max_climb_rows_per_second": thrust.max_climb_rows_per_second,
        "max_fall_rows_per_second": thrust.max_fall_rows_per_second,
        "climb_acceleration_rows_per_second2": thrust.climb_acceleration_rows_per_second2,
        "firing_distance_columns": boss.firing_distance_columns,
        "projectile_speed_columns_per_second": boss.projectile_speed_columns_per_second,
        "projectile_height_rows": boss.projectile_height_rows,
        "salvo_shots": boss.salvo_shots,
        "salvo_period_seconds": boss.salvo_period_seconds,
        "salvo_budget": boss.salvo_budget,
        "lane_margin_rows": boss.lane_margin_rows,
        "hits_to_defeat": boss.hits_to_defeat,
        "player_fire_period_seconds": boss.player_fire_period_seconds,
        "player_shot_speed_columns_per_second": boss.player_shot_speed_columns_per_second,
    }


def manifest_gameplay(gameplay: RunnerGameplayContract) -> dict[str, object]:
    """The manifest's published gameplay block, one key per refusal-bearing number.

    Module-level and pure so the writer's exact key set is pinned by an
    offline test; the TS parser refuses a document missing any of these, and
    the two suites hold the same list from both sides.
    """

    jump = JUMP_PROFILES[gameplay.run.jump_profile]
    speed = SPEED_PROFILES[gameplay.run.speed_profile]
    collision = COLLISION_BOXES[gameplay.run.collision_box]
    duck = None if gameplay.run.duck_profile is None else DUCK_PROFILES[gameplay.run.duck_profile]
    vitals = gameplay.run.vitals
    return {
        "speed_profile": gameplay.run.speed_profile,
        "jump_profile": gameplay.run.jump_profile,
        "collision_box": gameplay.run.collision_box,
        "duck_profile": gameplay.run.duck_profile,
        # Always the full source table, with `shot` explicitly null when no
        # encounter can fire one: a consumer must never have to tell "absent"
        # from "unanswered".
        "consequences": {
            "hazard": gameplay.run.consequences.hazard,
            "pit": gameplay.run.consequences.pit,
            "crush": gameplay.run.consequences.crush,
            "shot": gameplay.run.consequences.shot,
        },
        "vitals": (
            None
            if vitals is None
            else {
                "profile": vitals.profile,
                "max_points": VITALS_PROFILES[vitals.profile].max_points,
                "hurt_representation": vitals.hurt_representation,
            }
        ),
        "ramp_profile": gameplay.ramp.profile,
        "max_clear_gap_columns": jump.max_clear_gap_columns,
        "max_rise_tiles": jump.max_rise_tiles,
        "jump_peak_margin_tiles": jump.peak_margin_tiles,
        "airtime_headroom": jump.airtime_headroom,
        "encounter": _manifest_encounter(gameplay),
        "base_speed_columns_per_second": speed.base_speed_columns_per_second,
        "max_speed_multiplier": speed.max_speed_multiplier,
        "avatar_half_width_columns": collision.avatar_half_width_columns,
        "hazard_column_inset": collision.hazard_column_inset,
        "ducked_height_fraction": (None if duck is None else duck.ducked_height_fraction),
        "min_overhead_clearance_rows": (None if duck is None else duck.min_overhead_clearance_rows),
    }


def _listening_verdict(pinned: PinnedTake | None) -> str:
    """A pinned take was chosen by a person; a fresh draw has not been heard."""

    return "author_selected" if pinned is not None else "not_performed"


def manifest_audio(
    audio: RunnerAudioContract,
    *,
    read_validation: Callable[[str], bytes] | None = None,
) -> dict[str, object]:
    """Project the authored event/effect closure without consumer defaults.

    A generated clip publishes what the consumer plays - the artifact path,
    its duration, and the playback mixing - and not what bought it: the
    prompt and influence live in the artifact's provenance sidecar. A spoken
    line publishes the same shape, but its duration was never authored - the
    route decides how long a read takes - so it is read off the admission
    record, the one place the measured length exists, which is why a contract
    that speaks needs ``read_validation``. The music transitions are published
    as authored; they are consumer mixing and the runtime is the only reader.
    """

    effects: list[dict[str, object]] = []
    for effect in audio.effects:
        realization = effect.realization
        projected: dict[str, object]
        if isinstance(realization, GeneratedClipRealization):
            projected = {
                "kind": realization.kind,
                "clip": f"audio/{effect.effect_id}.mp3",
                "duration_seconds": realization.duration_seconds,
                "gain": realization.gain,
                "strength_pitch_multiplier": realization.strength_pitch_multiplier,
            }
        elif isinstance(realization, SpokenLineRealization):
            if read_validation is None:
                raise ValueError(
                    f"spoken line {effect.effect_id} needs its admission record to publish"
                )
            record = json.loads(read_validation(f"audio/{effect.effect_id}.validation.json"))
            duration = record.get("duration_seconds") if isinstance(record, dict) else None
            if not isinstance(duration, (int, float)) or duration <= 0:
                raise ValueError(f"spoken line {effect.effect_id} admission carries no length")
            projected = {
                "kind": realization.kind,
                "clip": f"audio/{effect.effect_id}.mp3",
                "duration_seconds": float(duration),
                "gain": realization.gain,
                "strength_pitch_multiplier": realization.strength_pitch_multiplier,
            }
        else:
            projected = realization.model_dump(mode="json")
        effects.append(
            {
                "effect_id": effect.effect_id,
                "display_name": effect.display_name,
                "realization": projected,
            }
        )
    return {
        "bindings": audio.bindings.model_dump(mode="json"),
        "effects": effects,
        "music": audio.music.model_dump(mode="json"),
    }


def manifest_ground(track: RunnerTrack) -> dict[str, object]:
    """Project the closed atlas/structural ground union into runtime shape."""

    if isinstance(track.ground, RunnerStructuralGround):
        return {
            "mode": track.ground.mode,
            "vertical_fit": track.ground.vertical_fit,
            "cell_px": STRUCTURAL_GROUND_CELL_PX,
            "chunks": [
                {
                    "segment_id": chunk.segment_id,
                    "image": f"world/ground/{chunk.segment_id}.png",
                    "columns": len(chunk.occupancy[0]),
                    "rows": len(chunk.occupancy),
                }
                for chunk in track.segments.chunks
            ],
        }
    return {
        "atlas": "world/ground.png",
        "mode": track.ground.mode,
        "vertical_fit": track.ground.vertical_fit,
    }


def manifest_rebase_multipliers(
    record: dict[str, object], *, published_states: tuple[str, ...]
) -> dict[str, float]:
    """Read the admitted verification shape exactly and fail closed on drift."""

    raw = record.get("states")
    if not isinstance(raw, dict):
        raise ValueError("motion rebase verification must publish a states object")
    expected = set(published_states)
    actual = set(raw)
    if actual != expected:
        raise ValueError(
            "motion rebase verification states differ from published motions: "
            f"expected {sorted(expected)}, got {sorted(actual)}"
        )
    multipliers: dict[str, float] = {}
    for state in published_states:
        value = raw[state]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value <= 0
        ):
            raise ValueError(f"motion rebase verification multiplier for {state} must be positive")
        multipliers[state] = float(value)
    return multipliers


def _no_soundtrack(track_id: str) -> SoundtrackTrack:
    raise ValueError(f"runner package declares no soundtrack member (asked for {track_id})")


class SideviewRunnerNodeHandler(RecipeNodeHandler):
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
        tool_loop_service: ToolLoopService[dict[str, object]] | None = None,
        music_service: MusicGenerationService | None = None,
        sound_effect_service: SoundEffectGenerationService | None = None,
        speech_service: SpeechGenerationService | None = None,
        capability_timeout_s: float | None = None,
    ) -> None:
        self._resolved = resolved
        self._package = resolved.package
        self._runner = resolved.runner
        self._images = image_service
        self._structured = structured_service
        self._tool_loop = tool_loop_service
        self._music = music_service
        self._sound_effects = sound_effect_service
        self._speech = speech_service
        self._timeout = capability_timeout_s
        soundtrack = resolved.runner.soundtrack
        self._rebase = MotionRebaseHandlers(
            MotionRebaseHost(
                run_dir=run_dir,
                subject=self._rebase_subject,
                component=_COMPONENT,
                handler_version=RUNNER_HANDLER_VERSION,
                plate_model="sideview-runner-rebase-plate-v1",
            ),
            graph=graph,
            structured_service=structured_service,
            provider_call=lambda node, _role, _prompt, thunk: self._execute_provider_operation(
                node, thunk
            ),
        )
        self._soundtrack = SoundtrackHandlers(
            SoundtrackHost(
                run_dir=run_dir,
                track=(soundtrack.track if soundtrack is not None else _no_soundtrack),
            ),
            graph=graph,
            music_service=music_service,
            provider_call=lambda node, _role, _prompt, thunk: self._execute_provider_operation(
                node, thunk
            ),
        )
        super().__init__(
            graph,
            run_dir=run_dir,
            cache_dir=cache_dir,
            namespace=RUNNER_CACHE_NAMESPACE,
            record_kind=RUNNER_CACHE_RECORD_KIND,
            admit=self._admit_cached_bundle,
        )

    # The base handler owns the loop; the runner keeps the attempt ledger it publishes
    # beside every provider node, and refuses to turn a pre-component failure into spend.

    def _cancelled(self, node: Node, error: CancellationError) -> None:
        # The retry owner records how many operations had actually started before
        # cancellation. Preserve that count without turning the cancellation into an
        # ordinary node failure.
        raw_operations = getattr(error, "provider_operations", 0)
        provider_operations = (
            raw_operations
            if isinstance(raw_operations, int)
            and not isinstance(raw_operations, bool)
            and 0 <= raw_operations <= node.max_attempts
            else 0
        )
        self._write_failed_attempt_ledger(node, provider_operations=provider_operations)

    def _failed(self, node: Node, error: NodeExecutionError) -> None:
        self._write_failed_attempt_ledger(node, provider_operations=error.provider_operations)

    def _failure(self, node: Node, error: Exception) -> NodeExecutionError:
        # Reaching this means request construction or another pre-component step failed.
        # Only the component boundary (`_execute_provider_operation`) may turn retry-owner
        # evidence into provider spend.
        return NodeExecutionError(
            f"{type(error).__name__}: {error}", attempts=1, provider_operations=0
        )

    async def _execute_provider_operation(
        self,
        node: Node,
        operation: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Execute a built request and retain only authoritative spend evidence."""

        try:
            return await operation()
        except CancellationError:
            raise
        except NodeExecutionError:
            raise
        except Exception as error:
            raw_attempts = getattr(
                error,
                "provider_operations",
                getattr(error, "attempts", 0),
            )
            provider_operations = (
                raw_attempts
                if type(raw_attempts) is int and 0 <= raw_attempts <= node.max_attempts
                else 0
            )
            raise NodeExecutionError(
                str(error),
                attempts=max(1, provider_operations),
                provider_operations=provider_operations,
            ) from error

    # ---------------------------------------------------------- cache admission

    def _admit_cached_bundle(self, node: Node, payloads: tuple[bytes, ...]) -> bool:
        """Re-admit restored bytes against today's runner contract.

        A cache record proves only that its own bytes and lineage are internally
        consistent.  It is not an authority for media semantics or provenance:
        an attacker (or an old buggy writer) can rewrite a payload, its digest,
        its sidecar, and the cache record together.  Keep every refusal local to
        the cache tier so an invalid bundle becomes a miss and the normal node
        implementation remains the sole retry owner.
        """

        try:
            self._admit_cached_bundle_or_raise(node, payloads)
        except Exception:
            return False
        return True

    def _admit_cached_bundle_or_raise(self, node: Node, payloads: tuple[bytes, ...]) -> None:
        refs = tuple(
            ref
            for port in node.ports
            for ref in (
                (port.artifact_ref, port.sidecar_ref)
                if port.sidecar_ref is not None
                else (port.artifact_ref,)
            )
        )
        if len(refs) != len(payloads):
            raise ValueError("runner cache payload count differs from declared outputs")
        bundle = dict(zip(refs, payloads, strict=True))

        provider_operations = 0
        output_selection = "local_output"
        if node.operation != RunnerOperationKind.LOCAL:
            provider_operations, output_selection = self._admit_attempt_ledger(node, bundle)

        provider_ref = (
            self._provider_output_ref(node) if node.operation != RunnerOperationKind.LOCAL else None
        )
        for port in node.ports:
            if port.sidecar_ref is None:
                continue
            provider_owned = provider_operations > 0 and port.artifact_ref == provider_ref
            self._admit_provenance_pair(
                node,
                artifact_ref=port.artifact_ref,
                artifact_data=bundle[port.artifact_ref],
                sidecar_data=bundle[port.sidecar_ref],
                bundle=bundle,
                provider_owned=provider_owned,
                provider_operations=provider_operations,
            )

        if node.type_id == LAYER_LOOP_PAINT.type_id:
            self._admit_loop_bundle(
                node,
                bundle,
                provider_operations=provider_operations,
                output_selection=output_selection,
            )
            return
        if node.operation == RunnerOperationKind.STRUCTURED_GENERATION:
            self._admit_structured_bundle(node, bundle)
            return
        if node.operation == RunnerOperationKind.TOOL_LOOP:
            self._admit_tool_loop_bundle(node, bundle)
            return
        if node.operation != RunnerOperationKind.LOCAL:
            if output_selection != "provider_output":
                raise ValueError("ordinary provider cache output was not provider-selected")
            self._admit_provider_artifact(node, bundle[self._provider_output_ref(node)])
            return
        self._admit_local_bundle(node, bundle)

    @staticmethod
    def _strict_json_object(data: bytes, *, label: str) -> dict[str, Any]:
        def reject_constant(value: str) -> None:
            raise ValueError(f"{label} contains non-finite JSON value {value}")

        try:
            value = json.loads(data, parse_constant=reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"{label} is not strict JSON") from error
        if not isinstance(value, dict):
            raise ValueError(f"{label} must be a JSON object")
        return cast("dict[str, Any]", value)

    @staticmethod
    def _require_equal(actual: object, expected: object, *, label: str) -> None:
        if actual != expected:
            raise ValueError(f"cached {label} differs from the current contract")

    @staticmethod
    def _artifact_media_type(ref: str) -> str:
        if ref.endswith(".png"):
            return "image/png"
        if ref.endswith(".mp3"):
            return "audio/mpeg"
        if ref.endswith(".json"):
            return "application/json"
        raise ValueError(f"runner cache artifact has unknown media type: {ref}")

    def _admit_provenance_pair(
        self,
        node: Node,
        *,
        artifact_ref: str,
        artifact_data: bytes,
        sidecar_data: bytes,
        bundle: Mapping[str, bytes],
        provider_owned: bool,
        provider_operations: int,
    ) -> None:
        raw = self._strict_json_object(sidecar_data, label=f"{artifact_ref} provenance")
        provenance = ArtifactProvenance.model_validate(raw)
        media_type = self._artifact_media_type(artifact_ref)
        expected_artifact = {
            "sha256": content_sha256(artifact_data),
            "bytes": len(artifact_data),
            "media_type": media_type,
        }
        actual_artifact = (
            None if provenance.artifact is None else provenance.artifact.model_dump(mode="json")
        )
        self._require_equal(
            actual_artifact,
            expected_artifact,
            label=f"{artifact_ref} provenance artifact binding",
        )
        self._require_equal(
            provenance.prompt_sha256,
            content_sha256(provenance.prompt.encode("utf-8")),
            label=f"{artifact_ref} provenance prompt digest",
        )
        if media_type == "image/png":
            assert_image_signature(artifact_data, media_type)
            with Image.open(io.BytesIO(artifact_data)) as opened:
                opened.load()
                if opened.format != "PNG":
                    raise ValueError(f"{artifact_ref} is not a decodable PNG")
        elif media_type == "audio/mpeg":
            assert_audio_signature(artifact_data, media_type)
        else:
            self._strict_json_object(artifact_data, label=artifact_ref)

        if provider_owned:
            expected = self.expected_provider_provenance_identity(
                node,
                artifact_data,
                bundle=bundle,
                provider_response=provenance.response,
            )
            actual = {
                "schema_version": provenance.schema_version,
                "provider": provenance.provider,
                "model": provenance.model,
                "seed": provenance.seed,
                "prompt": provenance.prompt,
                "prompt_sha256": provenance.prompt_sha256,
                "references": provenance.references,
                "refs": provenance.refs,
                "inputs": [
                    item.model_dump(mode="json", exclude_none=True) for item in provenance.inputs
                ],
                "params": provenance.params,
                "validation": provenance.validation,
                "component": provenance.component.model_dump(mode="json"),
                "tool": provenance.tool.model_dump(mode="json"),
                "rights": (
                    None if provenance.rights is None else provenance.rights.model_dump(mode="json")
                ),
            }
            self._require_equal(actual, expected, label=f"{artifact_ref} provider identity")
            self._require_equal(
                provenance.attempts,
                provider_operations,
                label=f"{artifact_ref} provider attempts",
            )
        else:
            self._require_equal(
                provenance.provider, "local", label=f"{artifact_ref} local provider"
            )
            self._require_equal(
                provenance.component,
                _COMPONENT,
                label=f"{artifact_ref} local component identity",
            )

    def _admit_attempt_ledger(self, node: Node, bundle: Mapping[str, bytes]) -> tuple[int, str]:
        attempt_ref = self._attempt_port_ref(node)
        if attempt_ref is None or attempt_ref not in bundle:
            raise ValueError("provider cache bundle has no attempt ledger")
        ledger = self._strict_json_object(bundle[attempt_ref], label=f"{node.node_id} ledger")
        expected_fields = {
            "schema_version",
            "kind",
            "node_id",
            "cache_hit",
            "provider_operations",
            "output_selection",
            "prompt_sha256",
            "attempts",
        }
        self._require_equal(set(ledger), expected_fields, label=f"{node.node_id} ledger fields")
        self._require_equal(ledger["schema_version"], 2, label=f"{node.node_id} ledger schema")
        self._require_equal(
            ledger["kind"],
            "sideview-runner-attempt-ledger-v2",
            label=f"{node.node_id} ledger kind",
        )
        self._require_equal(ledger["node_id"], node.node_id, label=f"{node.node_id} ledger node")
        # A stored ledger describes the miss that authored these bytes. Cache
        # reads preserve it byte-for-byte and never write a cache_hit=true form.
        self._require_equal(ledger["cache_hit"], False, label=f"{node.node_id} ledger cache flag")
        operations = ledger["provider_operations"]
        if type(operations) is not int or not 0 <= operations <= node.max_attempts:
            raise ValueError(f"{node.node_id} ledger provider_operations is invalid")
        prompt_sha256 = content_sha256(self._provider_prompt(node).encode("utf-8"))
        self._require_equal(
            ledger["prompt_sha256"], prompt_sha256, label=f"{node.node_id} ledger prompt"
        )
        attempts = ledger["attempts"]
        if not isinstance(attempts, list) or len(attempts) != operations:
            raise ValueError(f"{node.node_id} ledger attempt count is invalid")
        selection = ledger["output_selection"]
        if selection not in {"provider_output", "fallback_output", "local_output"}:
            raise ValueError(f"{node.node_id} ledger output selection is invalid")
        if selection == "provider_output" and operations < 1:
            raise ValueError("provider-selected ledger records no provider operation")
        if selection == "fallback_output" and (
            operations < 1 or node.type_id != LAYER_LOOP_PAINT.type_id
        ):
            raise ValueError("fallback ledger is not a paid generative-loop fallback")
        if selection == "local_output" and (
            operations != 0 or node.type_id != LAYER_LOOP_PAINT.type_id
        ):
            raise ValueError("local-output ledger is not a skipped generative loop")

        selected_ref = self._provider_output_ref(node)
        for ordinal, entry in enumerate(attempts, start=1):
            if not isinstance(entry, dict):
                raise ValueError(f"{node.node_id} ledger attempt is not an object")
            selected = selection == "provider_output" and ordinal == operations
            expected_entry_fields = (
                {"attempt", "outcome", "artifact_ref", "artifact_sha256", "prompt_sha256"}
                if selected
                else {"attempt", "outcome", "prompt_sha256", "reason"}
            )
            self._require_equal(
                set(entry), expected_entry_fields, label=f"{node.node_id} attempt fields"
            )
            self._require_equal(entry["attempt"], ordinal, label=f"{node.node_id} attempt ordinal")
            self._require_equal(
                entry["prompt_sha256"], prompt_sha256, label=f"{node.node_id} attempt prompt"
            )
            if selected:
                self._require_equal(
                    entry["outcome"], "selected", label=f"{node.node_id} selected outcome"
                )
                self._require_equal(
                    entry["artifact_ref"], selected_ref, label=f"{node.node_id} selected ref"
                )
                self._require_equal(
                    entry["artifact_sha256"],
                    content_sha256(bundle[selected_ref]),
                    label=f"{node.node_id} selected digest",
                )
            else:
                self._require_equal(
                    entry["outcome"],
                    "not_selected",
                    label=f"{node.node_id} unselected outcome",
                )
                self._require_equal(
                    entry["reason"],
                    "provider attempt did not produce the selected output",
                    label=f"{node.node_id} unselected reason",
                )
        return operations, cast("str", selection)

    def _image_generation_request(self, node: Node) -> ImageGenerationRequest:
        """Build the one current OpenAI request for an image provider node."""

        output = self._run_dir / self._provider_output_ref(node)
        if node.type_id == TRACK_GROUND_GENERATE.type_id:
            template = terrain_atlas_template_path().read_bytes()
            topology = terrain_atlas_topology_reference_path().read_bytes()
            return ImageGenerationRequest(
                prompt=self._card_prompt(node),
                artifact_path=output,
                input_references=(
                    ImageReference(
                        data_url(template, "image/png"),
                        (
                            "resource://image_gen_templates/terrain_atlas_12x4_template.png"
                            f"#sha256={content_sha256(template)}"
                        ),
                    ),
                    ImageReference(
                        data_url(topology, "image/png"),
                        (
                            "resource://image_gen_templates/"
                            "terrain_atlas_godot_topology_reference.png"
                            f"#sha256={content_sha256(topology)}"
                        ),
                    ),
                    *self._authored_references(node),
                ),
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
        if node.type_id == TRACK_STRUCTURAL_GROUND_GENERATE.type_id:
            chunk = self._segment(node)
            guide_ref = self._dependency_artifact(node, kind=STRUCTURAL_GROUND_GUIDE_KIND)
            guide = (self._run_dir / guide_ref).read_bytes()
            return ImageGenerationRequest(
                prompt=self._card_prompt(node),
                artifact_path=output,
                input_references=(
                    ImageReference(
                        data_url(guide, "image/png"),
                        f"run://{guide_ref}#sha256={content_sha256(guide)}",
                    ),
                    *self._authored_references(node),
                ),
                quality="high",
                background="transparent",
                output_format="png",
                size=f"{STRUCTURAL_GROUND_GUIDE_WIDTH}x{STRUCTURAL_GROUND_GUIDE_HEIGHT}",
                timeout_seconds=600,
                metadata={
                    "track_id": self._track().track_id,
                    "segment_id": chunk.segment_id,
                    "operation": "structural_ground",
                    "native_alpha": True,
                },
                validate=lambda artifact: validate_structural_ground_source(
                    artifact.data,
                    occupancy=chunk.occupancy,
                    walk_surface_row=self._track().segments.walk_surface_row,
                    guide=guide,
                    material_identity=self._structural_material_identity(),
                    material_references=[
                        data for _source, data in self._structural_material_inputs()
                    ],
                    projection=self._structural_projection(),
                ),
            )
        if node.type_id == LAYER_GENERATE.type_id:
            layer = self._layer(node)
            transparent = layer.alpha_mode == "transparent"
            return ImageGenerationRequest(
                prompt=self._card_prompt(node),
                artifact_path=output,
                input_references=self._authored_references(node),
                quality="high",
                background="transparent" if transparent else "opaque",
                output_format="png",
                size="1536x1024",
                timeout_seconds=600,
                metadata={"track_id": self._track().track_id, "layer_id": layer.layer_id},
                validate=lambda artifact: _validate_layer_candidate(
                    artifact.data, transparent=transparent
                ),
            )
        if node.type_id == LAYER_LOOP_PAINT.type_id:
            layer = self._layer(node)
            construction = cast("LoopConstruction", node.params["construction"])
            source_ref = self._dependency_artifact(node, kind=LAYER_RAW_KIND)
            source = (self._run_dir / source_ref).read_bytes()
            conditioning = loop_conditioning(construction, source)
            return ImageGenerationRequest(
                prompt=self._provider_prompt(node),
                artifact_path=output,
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
                background=("transparent" if layer.alpha_mode == "transparent" else "opaque"),
                output_format="png",
                size=f"{conditioning.width}x{conditioning.height}",
                timeout_seconds=600,
                metadata={
                    "track_id": self._track().track_id,
                    "layer_id": layer.layer_id,
                    "operation": f"loop_{construction}",
                },
            )
        if node.type_id in (AVATAR_CONCEPT_GENERATE.type_id, BOSS_CONCEPT_GENERATE.type_id):
            subject = self._actor(node)
            return ImageGenerationRequest(
                prompt=self._card_prompt(node),
                artifact_path=output,
                input_references=self._authored_references(node),
                quality="high",
                background="transparent",
                output_format="png",
                size="1024x1536",
                timeout_seconds=600,
                metadata={f"{subject.label}_id": subject.entity_id},
                validate=lambda artifact: _validate_transparent_sprite(artifact.data),
            )
        if node.type_id in (AVATAR_MOTION_GENERATE.type_id, BOSS_MOTION_GENERATE.type_id):
            geometry = DEFAULT_MOTION_ATLAS_GEOMETRY
            subject = self._actor(node)
            state = str(node.params["state"])
            motion = subject.motion(state)
            concept_ref = self._dependency_artifact(node, kind=subject.concept_kind)
            concept = (self._run_dir / concept_ref).read_bytes()
            return ImageGenerationRequest(
                prompt=self._card_prompt(node),
                artifact_path=output,
                input_references=(
                    ImageReference(data_url(concept, "image/png"), "identity-concept"),
                ),
                quality="high",
                background="transparent",
                output_format="png",
                size=geometry.provider_size,
                timeout_seconds=600,
                metadata={f"{subject.label}_id": subject.entity_id, "state": state},
                validate=lambda artifact: _validate_motion_candidate(
                    artifact.data, anchor=motion.anchor
                ),
            )
        if node.type_id == CATALOG_ASSET_GENERATE.type_id:
            family = str(node.params["family"])
            return ImageGenerationRequest(
                prompt=self._card_prompt(node),
                artifact_path=output,
                input_references=self._authored_references(node),
                quality="high",
                background="transparent",
                output_format="png",
                size="1024x1024",
                timeout_seconds=600,
                metadata={"family": family, "entity_id": str(node.params["entity_id"])},
                validate=lambda artifact: _validate_catalog_candidate(artifact.data, family=family),
            )
        if node.type_id == FX_CUT_IN_GENERATE.type_id:
            return cut_in_generate_request(
                self._fx_host(), self._graph, node, read=self._read_run_artifact
            )
        if node.type_id == FX_SPRITE_DUST_GENERATE.type_id:
            return sprite_dust_generate_request(self._fx_host(), node)
        raise ValueError(f"runner node has no image request builder: {node.type_id}")

    def _generated_clip(self, node: Node) -> tuple[str, GeneratedClipRealization]:
        effect = self._runner.audio.effect(str(node.params["effect_id"]))
        realization = effect.realization
        if not isinstance(realization, GeneratedClipRealization):
            raise ValueError(f"runner effect {effect.effect_id} is not a generated clip")
        return effect.effect_id, realization

    def _sound_effect_request(self, node: Node) -> SoundEffectGenerationRequest:
        effect_id, realization = self._generated_clip(node)
        return SoundEffectGenerationRequest(
            prompt=self._provider_prompt(node),
            artifact_path=self._run_dir / node.port("audio").artifact_ref,
            duration_seconds=realization.duration_seconds,
            prompt_influence=realization.prompt_influence,
            loop=False,
            output_format="mp3",
            timeout_seconds=120,
            metadata={
                "effect_id": effect_id,
                "duration_seconds": realization.duration_seconds,
            },
            validate=lambda artifact: admit_sound_effect_bytes(artifact.data),
        )

    def _spoken_line(self, node: Node) -> tuple[str, SpokenLineRealization]:
        effect = self._runner.audio.effect(str(node.params["effect_id"]))
        realization = effect.realization
        if not isinstance(realization, SpokenLineRealization):
            raise ValueError(f"runner effect {effect.effect_id} is not a spoken line")
        return effect.effect_id, realization

    def _cast_voice(self, voice_id: str) -> GameVoice:
        voices = self._runner.voices
        voice = None if voices is None else voices.voice(voice_id)
        if voice is None:
            raise ValueError(
                f"spoken line names voice {voice_id!r}, which the package does not cast"
            )
        return voice

    def _speech_request(self, node: Node) -> SpeechGenerationRequest:
        effect_id, realization = self._spoken_line(node)
        voice = self._cast_voice(realization.voice_id)
        max_seconds = realization.max_seconds
        return SpeechGenerationRequest(
            text=self._provider_prompt(node),
            voice=voice.provider.voice,
            artifact_path=self._run_dir / node.port("audio").artifact_ref,
            stability=realization.stability,
            language_code=voice.language_code,
            output_format="mp3",
            timeout_seconds=120,
            metadata={
                "effect_id": effect_id,
                "voice_id": realization.voice_id,
                "max_seconds": max_seconds,
            },
            # The length ceiling is checked here, inside the retry owner, so an
            # over-long read is redrawn and never persisted - trimming is forbidden.
            validate=lambda artifact: admit_speech_bytes(artifact.data, max_seconds=max_seconds),
        )

    @staticmethod
    def _sync_artifact_validation(
        validator: Callable[[BinaryArtifact], object] | None,
        artifact: BinaryArtifact,
    ) -> dict[str, object]:
        if validator is None:
            return {}
        result = validator(artifact)
        if inspect.isawaitable(result):
            raise ValueError("runner provider cache validation must be synchronous")
        if result is None:
            return {}
        if not isinstance(result, MappingABC):
            raise ValueError("runner provider validator returned a non-mapping")
        return dict(result)

    @staticmethod
    def _reference_identity(
        references: Sequence[ImageReference | StructuredReference | ToolLoopReference],
    ) -> tuple[list[str], list[dict[str, object]]]:
        refs = [
            reference.provenance_ref or sanitize_reference(reference.url)
            for reference in references
        ]
        inputs = [
            hash_input_reference(reference.url, reference.provenance_ref).model_dump(
                mode="json", exclude_none=True
            )
            for reference in references
        ]
        return refs, inputs

    def expected_provider_provenance_identity(
        self,
        node: Node,
        artifact_data: bytes,
        *,
        bundle: Mapping[str, bytes] | None = None,
        provider_response: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """Return the exact current request identity a provider sidecar must carry.

        Replay migration uses this same helper after staging current dependencies,
        so cache admission and sidecar migration cannot drift on ordered inputs,
        mask lineage, provider params, or caller-validation facts.
        """

        if node.operation == RunnerOperationKind.IMAGE_GENERATION:
            image_request = self._image_generation_request(node)
            references = (
                image_request.input_references
                if image_request.mask_reference is None
                else (*image_request.input_references, image_request.mask_reference)
            )
            refs, inputs = self._reference_identity(references)
            params: dict[str, object] = {
                "n": 1,
                "validated": image_request.validate is not None,
                "operation": "edit" if image_request.input_references else "generation",
                "output_format": image_request.output_format or "png",
            }
            for key in ("size", "quality", "background"):
                value = getattr(image_request, key)
                if value is not None:
                    params[key] = value
            if image_request.moderation is not None and not image_request.input_references:
                params["moderation"] = image_request.moderation
            if image_request.output_compression is not None:
                params["output_compression"] = image_request.output_compression
            if image_request.metadata:
                params["metadata"] = dict(image_request.metadata)
            caller = self._sync_artifact_validation(
                image_request.validate,
                BinaryArtifact(data=artifact_data, media_type="image/png"),
            )
            validation: dict[str, object] = {
                "output_nonempty": True,
                "base64": "strict",
                "media_type": "image/png",
                "signature": "matched",
                "caller": image_request.validate is not None,
                **caller,
            }
            component = IMAGE_GENERATION_COMPONENT
            seed = None
            rights = None
        elif node.type_id == FX_CUT_IN_REVIEW.type_id:
            # The shared family's request builder is the identity: the same
            # function the handler sends, re-run over the restored run.
            review_request = cut_in_review_request(
                self._fx_host(), self._graph, node, read=self._read_run_artifact
            )
            refs, inputs = self._reference_identity(review_request.references)
            review_system = review_request.system or ""
            params = {
                "schema_name": review_request.schema.name,
                "schema_description": review_request.schema.description,
                "schema": dict(review_request.schema.json_schema),
                "strict": review_request.schema.strict,
                "require_parameters": True,
                "system": review_system,
                "system_sha256": content_sha256(review_system.encode("utf-8")),
                "max_tokens": review_request.max_tokens,
                "metadata": dict(review_request.metadata),
            }
            self._strict_json_object(artifact_data, label=f"{node.node_id} structured artifact")
            validation = {
                "output_nonempty": True,
                "json": "parsed",
                "schema": "caller-validated",
            }
            component = STRUCTURED_GENERATION_COMPONENT
            seed = None
            rights = None
        elif node.type_id == FX_CUT_IN_PLACE.type_id:
            # The episode's identity is what the agent was given, never the path
            # it took: instructions, system, tools, budget, and the admitted
            # record. Rebuilt from the restored plates by the shared builder.
            place_request = cut_in_place_request(
                self._fx_host(), self._graph, node, read=self._read_run_artifact
            )
            refs, inputs = self._reference_identity(place_request.references)
            place_system = place_request.system or ""
            params = {
                "instructions_sha256": content_sha256(place_request.instructions.encode("utf-8")),
                "tools": [
                    {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": dict(spec.parameters),
                    }
                    for spec in place_request.tool_specs
                ],
                "submit_schema": dict(place_request.submit_schema),
                "strict": True,
                "require_parameters": True,
                "max_steps": place_request.max_steps,
                "system": place_system,
                "system_sha256": content_sha256(place_system.encode("utf-8")),
                "max_total_tokens": place_request.max_total_tokens,
                "metadata": dict(place_request.metadata),
                "artifact_value": "caller-canonicalized",
                "validated": True,
            }
            canonical_placement = self._strict_json_object(
                artifact_data, label=f"{node.node_id} placement artifact"
            )
            validation = {
                "submitted": True,
                "json": "parsed",
                "schema": "caller-validated",
                **canonical_placement,
            }
            component = TOOL_LOOP_COMPONENT
            seed = None
            rights = None
        elif node.operation == RunnerOperationKind.STRUCTURED_GENERATION:
            plate_data = (
                bundle[node.port("plate").artifact_ref]
                if bundle is not None
                else (self._run_dir / node.port("plate").artifact_ref).read_bytes()
            )
            plate_ref = f"run://{node.port('plate').artifact_ref}"
            reference = StructuredReference(data_url(plate_data, "image/png"), plate_ref)
            refs, inputs = self._reference_identity((reference,))
            states = list(self._actor(node).states)
            schema_description = (
                "Per-state draw-scale multipliers against an actor's baseline"
                if node.type_id == MOTION_REBASE_JUDGE.type_id
                else "Residual per-state multipliers on the rebased plate"
            )
            schema = StructuredOutputSchema(
                name=MOTION_REBASE_SCHEMA_NAME,
                description=schema_description,
                json_schema=motion_rebase_json_schema(),
                strict=True,
            )
            system = "You are a sprite-sheet scale judge. Return only the strict structured object."
            # Named for the actor it judged: two actors' judgements share one
            # node type, so the mirrored identity is the only place a reader
            # can tell whose strips were on the plate.
            subject_label = self._actor(node).label
            kind = (
                f"{subject_label}-motion-rebase"
                if node.type_id == MOTION_REBASE_JUDGE.type_id
                else f"{subject_label}-motion-rebase-verify"
            )
            params = {
                "schema_name": schema.name,
                "schema_description": schema.description,
                "schema": dict(schema.json_schema),
                "strict": schema.strict,
                "require_parameters": True,
                "system": system,
                "system_sha256": content_sha256(system.encode("utf-8")),
                "metadata": {
                    "kind": kind,
                    "entity_id": self._actor(node).entity_id,
                    "states": states,
                    "plate_sha256": content_sha256(plate_data),
                },
                "artifact_value": "caller-canonicalized",
                "validated": True,
            }
            canonical = self._strict_json_object(
                artifact_data, label=f"{node.node_id} structured artifact"
            )
            validation = {
                "output_nonempty": True,
                "json": "parsed",
                "schema": "caller-validated",
                **canonical,
            }
            component = STRUCTURED_GENERATION_COMPONENT
            seed = None
            rights = None
        elif node.operation == RunnerOperationKind.MUSIC_GENERATION:
            music_request = self._soundtrack.request(node)
            refs, inputs = [], []
            params = {
                "output_format": music_request.output_format,
                "modalities": ["text", "audio"],
                "stream": True,
                "validated": music_request.validate is not None,
            }
            if music_request.metadata:
                params["metadata"] = dict(music_request.metadata)
            caller = self._sync_artifact_validation(
                music_request.validate,
                BinaryArtifact(data=artifact_data, media_type="audio/mpeg"),
            )
            response_shape = (
                None if provider_response is None else provider_response.get("source_shape")
            )
            if response_shape not in {"sse", "json"}:
                raise ValueError("music provenance has no valid provider response shape")
            validation = {
                "output_nonempty": True,
                "base64": "strict",
                "media_type": "audio/mpeg",
                "signature": "matched",
                "source_shape": response_shape,
                "caller": music_request.validate is not None,
                **caller,
            }
            component = MUSIC_GENERATION_COMPONENT
            seed = music_request.seed
            rights = (
                None
                if music_request.rights is None
                else music_request.rights.model_dump(mode="json")
            )
        elif node.operation == RunnerOperationKind.SOUND_EFFECT_GENERATION:
            sound_request = self._sound_effect_request(node)
            refs, inputs = [], []
            params = {
                "output_format": sound_request.output_format,
                "loop": sound_request.loop,
                "validated": sound_request.validate is not None,
            }
            if sound_request.duration_seconds is not None:
                params["duration_seconds"] = sound_request.duration_seconds
            if sound_request.prompt_influence is not None:
                params["prompt_influence"] = sound_request.prompt_influence
            if sound_request.metadata:
                params["metadata"] = dict(sound_request.metadata)
            # The live validator decodes asynchronously; the cache path must
            # restate the same facts synchronously, so it measures again here.
            caller = admit_sound_effect_bytes_sync(artifact_data)
            response_shape = (
                None if provider_response is None else provider_response.get("source_shape")
            )
            if response_shape != "binary":
                raise ValueError("sound effect provenance has no valid provider response shape")
            validation = {
                "output_nonempty": True,
                "media_type": "audio/mpeg",
                "signature": "matched",
                "source_shape": response_shape,
                "caller": True,
                **caller,
            }
            component = SOUND_EFFECT_GENERATION_COMPONENT
            seed = None
            rights = (
                None
                if sound_request.rights is None
                else sound_request.rights.model_dump(mode="json")
            )
        elif node.operation == RunnerOperationKind.SPEECH_GENERATION:
            speech_request = self._speech_request(node)
            refs, inputs = [], []
            params = {
                "voice": speech_request.voice,
                "output_format": speech_request.output_format,
                "validated": speech_request.validate is not None,
            }
            if speech_request.stability is not None:
                params["stability"] = speech_request.stability
            if speech_request.language_code is not None:
                params["language_code"] = speech_request.language_code
            if speech_request.metadata:
                params["metadata"] = dict(speech_request.metadata)
            # The live validator decodes asynchronously; the cache path must
            # restate the same facts synchronously, so it measures again here.
            caller = admit_speech_bytes_sync(
                artifact_data, max_seconds=self._spoken_line(node)[1].max_seconds
            )
            response_shape = (
                None if provider_response is None else provider_response.get("source_shape")
            )
            if response_shape != "binary":
                raise ValueError("speech provenance has no valid provider response shape")
            validation = {
                "output_nonempty": True,
                "media_type": "audio/mpeg",
                "signature": "matched",
                "source_shape": response_shape,
                "caller": True,
                **caller,
            }
            component = SPEECH_GENERATION_COMPONENT
            seed = None
            rights = (
                None
                if speech_request.rights is None
                else speech_request.rights.model_dump(mode="json")
            )
        else:
            raise ValueError(f"node {node.node_id} is not provider-backed")

        prompt = self._provider_prompt(node)
        return _json_normalize_provider_identity(
            {
                "schema_version": 2,
                "provider": node.provider,
                "model": node.model,
                "seed": seed,
                "prompt": prompt,
                "prompt_sha256": content_sha256(prompt.encode("utf-8")),
                "references": refs,
                "refs": refs,
                "inputs": inputs,
                "params": params,
                "validation": validation,
                "component": component.model_dump(mode="json"),
                "tool": STAGE_GEN_TOOL.model_dump(mode="json"),
                "rights": rights,
            }
        )

    def _admit_provider_artifact(self, node: Node, data: bytes) -> None:
        """Run the same refusal-bearing check the provider retry owner runs."""

        if node.type_id == TRACK_GROUND_GENERATE.type_id:
            require_terrain_atlas_source(data, template=terrain_atlas_template_path().read_bytes())
            return
        if node.type_id == TRACK_STRUCTURAL_GROUND_GENERATE.type_id:
            chunk = self._segment(node)
            guide_ref = self._dependency_artifact(node, kind=STRUCTURAL_GROUND_GUIDE_KIND)
            validate_structural_ground_source(
                data,
                occupancy=chunk.occupancy,
                walk_surface_row=self._track().segments.walk_surface_row,
                guide=(self._run_dir / guide_ref).read_bytes(),
                material_identity=self._structural_material_identity(),
                material_references=[data for _source, data in self._structural_material_inputs()],
                projection=self._structural_projection(),
            )
            return
        if node.type_id == LAYER_GENERATE.type_id:
            layer = self._layer(node)
            _validate_layer_candidate(data, transparent=layer.alpha_mode == "transparent")
            return
        if node.type_id in (AVATAR_CONCEPT_GENERATE.type_id, BOSS_CONCEPT_GENERATE.type_id):
            facts = _validate_transparent_sprite(data)
            self._require_equal(
                (facts["width"], facts["height"]),
                (1024, 1536),
                label=f"{self._actor(node).label} concept dimensions",
            )
            return
        if node.type_id in (AVATAR_MOTION_GENERATE.type_id, BOSS_MOTION_GENERATE.type_id):
            state = str(node.params["state"])
            _validate_motion_candidate(data, anchor=self._actor(node).motion(state).anchor)
            return
        if node.type_id == CATALOG_ASSET_GENERATE.type_id:
            facts = _validate_catalog_candidate(data, family=str(node.params["family"]))
            source = cast("dict[str, object]", facts["source"])
            self._require_equal(
                (source["width"], source["height"]),
                (1024, 1024),
                label="catalog source dimensions",
            )
            return
        if node.type_id == SOUNDTRACK_GENERATE.type_id:
            validate_music_payload(data)
            return
        if node.type_id == SOUND_EFFECT_GENERATE.type_id:
            assert_audio_signature(data, "audio/mpeg")
            admit_sound_effect_bytes_sync(data)
            return
        if node.type_id == SPEECH_GENERATE.type_id:
            assert_audio_signature(data, "audio/mpeg")
            admit_speech_bytes_sync(data, max_seconds=self._spoken_line(node)[1].max_seconds)
            return
        if node.type_id == FX_CUT_IN_GENERATE.type_id:
            if str(node.params["plate"]) == "frame":
                validate_frame_plate(data)
            else:
                validate_portrait_plate(data)
            return
        if node.type_id == FX_SPRITE_DUST_GENERATE.type_id:
            validate_dust_atlas(data)
            return
        raise ValueError(f"runner cache has no provider admission for {node.type_id}")

    def _repeat_report(self, node: Node, data: bytes) -> Any:
        layer = self._layer(node)
        alpha_policy, coverage = layer_repeat_policies(layer.alpha_mode)
        return validate_image_repeat(
            data,
            axis="x",
            alpha_policy=alpha_policy,
            coverage_policy=coverage,
            validation_policy=ImageRepeatValidationPolicy(),
        )

    def _admit_loop_bundle(
        self,
        node: Node,
        bundle: Mapping[str, bytes],
        *,
        provider_operations: int,
        output_selection: str,
    ) -> None:
        source_ref = self._dependency_artifact(node, kind=LAYER_RAW_KIND)
        source = (self._run_dir / source_ref).read_bytes()
        looped = bundle[node.port("loop_image").artifact_ref]
        report = self._strict_json_object(
            bundle[node.port("loop_report").artifact_ref], label=f"{node.node_id} loop report"
        )
        repeat = self._repeat_report(node, looped)
        if repeat.verdict != "pass":
            raise ValueError(f"{node.node_id} cached loop fails current x-repeat admission")

        construction = cast("LoopConstruction", node.params["construction"])
        from stage_gen.media import LOOP_METHODS

        generative = LOOP_METHODS[construction].is_generative
        if not generative:
            if provider_operations or output_selection != "local_output":
                raise ValueError("deterministic loop has provider provenance")
            source_admission = self._repeat_report(node, source)
            if source_admission.verdict == "pass":
                expected_image = source
                expected: dict[str, object] = {
                    "schema_version": 1,
                    "kind": "direct-loop-admission-v1",
                    "construction": "none",
                    "skipped_construction": construction,
                    "provider_operations": 0,
                }
            else:
                expected_image, expected = construct_deterministic(construction, source)
                expected["construction"] = construction
            expected["repeat"] = self._repeat_report(node, expected_image).model_dump(mode="json")
            self._require_equal(looped, expected_image, label=f"{node.node_id} loop bytes")
            self._require_equal(report, expected, label=f"{node.node_id} loop report")
            return

        edit = bundle[node.port("edit_image").artifact_ref]
        if self._repeat_report(node, source).verdict == "pass":
            if provider_operations or output_selection != "local_output":
                raise ValueError("directly admitted loop claims a provider operation")
            expected = {
                "schema_version": 1,
                "kind": "direct-loop-admission-v1",
                "construction": "none",
                "skipped_construction": construction,
                "provider_operations": 0,
                "repeat": repeat.model_dump(mode="json"),
            }
            self._require_equal(looped, source, label=f"{node.node_id} direct loop bytes")
            self._require_equal(edit, source, label=f"{node.node_id} skipped edit bytes")
            self._require_equal(report, expected, label=f"{node.node_id} direct loop report")
            return

        if provider_operations < 1:
            raise ValueError("generative loop needing construction records no provider operation")
        conditioning = loop_conditioning(construction, source)
        layer = self._layer(node)
        validate_provider_image(
            edit,
            width=conditioning.width,
            height=conditioning.height,
            transparent=layer.alpha_mode == "transparent",
        )
        try:
            candidate, candidate_record = assemble_loop(
                construction, source, edit, conditioning=conditioning
            )
        except RegistrationError as error:
            candidate = None
            candidate_record = None
            rejection = str(error)
            rejected_repeat = None
        else:
            candidate_repeat = self._repeat_report(node, cast("bytes", candidate))
            rejection = "constructed loop failed x-repeat admission"
            rejected_repeat = candidate_repeat.model_dump(mode="json")

        if output_selection == "provider_output":
            if candidate is None or candidate_record is None:
                raise ValueError("selected provider loop fails current registration")
            candidate_repeat = self._repeat_report(node, candidate)
            if candidate_repeat.verdict != "pass":
                raise ValueError("selected provider loop fails current repeat admission")
            expected = dict(candidate_record)
            expected["construction"] = construction
            expected["provider_operations"] = provider_operations
            expected["repeat"] = candidate_repeat.model_dump(mode="json")
            self._require_equal(looped, candidate, label=f"{node.node_id} selected loop bytes")
            self._require_equal(report, expected, label=f"{node.node_id} selected loop report")
            return

        if output_selection != "fallback_output":
            raise ValueError("constructed loop has unsupported output selection")
        if candidate is not None and rejected_repeat is not None:
            candidate_repeat = self._repeat_report(node, candidate)
            if candidate_repeat.verdict == "pass":
                raise ValueError("fallback ledger rejected a currently admissible provider loop")
        fallback = self._track().continuity.loop_fallback
        fallback_image, fallback_record = construct_deterministic(fallback, source)
        expected = dict(fallback_record)
        expected["construction"] = fallback
        expected["rejected_construction"] = construction
        expected["rejection"] = rejection
        if rejected_repeat is not None:
            expected["rejected_repeat"] = rejected_repeat
        expected["provider_operations"] = provider_operations
        expected["repeat"] = self._repeat_report(node, fallback_image).model_dump(mode="json")
        self._require_equal(looped, fallback_image, label=f"{node.node_id} fallback loop bytes")
        self._require_equal(report, expected, label=f"{node.node_id} fallback loop report")

    @staticmethod
    def _admit_evidence(record: Mapping[str, object], states: Sequence[str]) -> None:
        evidence = record.get("evidence")
        if not isinstance(evidence, dict) or set(evidence) != set(states):
            raise ValueError("motion-rebase evidence does not cover current states")
        if any(
            not isinstance(value, str) or not value.strip() or len(value) > 300
            for value in evidence.values()
        ):
            raise ValueError("motion-rebase evidence is malformed")

    @staticmethod
    def _numeric_state_map(
        value: object,
        states: Sequence[str],
        *,
        label: str,
    ) -> dict[str, float]:
        if not isinstance(value, dict) or set(value) != set(states):
            raise ValueError(f"{label} does not cover current states")
        result: dict[str, float] = {}
        for state, raw in value.items():
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError(f"{label} contains a non-number")
            number = float(raw)
            if not math.isfinite(number):
                raise ValueError(f"{label} contains a non-finite number")
            result[cast("str", state)] = number
        return result

    def _admit_tool_loop_bundle(self, node: Node, bundle: Mapping[str, bytes]) -> None:
        if node.type_id != FX_CUT_IN_PLACE.type_id:
            raise ValueError(f"unknown runner tool-loop cache node {node.type_id}")
        record_ref = self._provider_output_ref(node)
        record = self._strict_json_object(bundle[record_ref], label=record_ref)
        raw_ref = self._dependency_artifact(node, kind=FX_CUT_IN_RAW_KIND)
        frame_ref = self._dependency_artifact(node, kind=FX_CUT_IN_PLATE_KIND)
        expected = admit_cut_in_placement(
            record,
            portrait_sha256=content_sha256((self._run_dir / raw_ref).read_bytes()),
            frame_sha256=content_sha256((self._run_dir / frame_ref).read_bytes()),
        )
        self._require_equal(record, expected, label=f"{node.node_id} admitted placement")

    def _admit_structured_bundle(self, node: Node, bundle: Mapping[str, bytes]) -> None:
        if node.type_id == FX_CUT_IN_REVIEW.type_id:
            # The shared family's verdict: a well-formed review is the whole
            # admission, its identity is proved by the provenance pair.
            verdict_ref = self._provider_output_ref(node)
            parse_cut_in_review(self._strict_json_object(bundle[verdict_ref], label=verdict_ref))
            return
        subject = self._actor(node)
        states = list(subject.states)
        frames = self._state_frames(node)
        plate = build_motion_rebase_plate(frames, baseline_state=subject.baseline_state)
        plate_data = bundle[node.port("plate").artifact_ref]
        record_ref = self._provider_output_ref(node)
        record = self._strict_json_object(bundle[record_ref], label=record_ref)
        if node.type_id == MOTION_REBASE_JUDGE.type_id:
            self._require_equal(
                plate_data, plate.png, label=f"{node.node_id} current comparison plate"
            )
            self._require_equal(
                set(record),
                {"baseline_state", "states", "plate_sha256", "evidence"},
                label=f"{node.node_id} reading fields",
            )
            admit_first_pass_record(
                record,
                published_states=states,
                plate=plate,
                baseline_state=subject.baseline_state,
            )
            self._admit_evidence(record, states)
            return
        if node.type_id != MOTION_REBASE_VERIFY.type_id:
            raise ValueError(f"unknown runner structured cache node {node.type_id}")

        first_ref = self._dependency_artifact(node, kind=REBASE_READING_KIND, port_id="reading")
        first_record = self._strict_json_object(
            (self._run_dir / first_ref).read_bytes(), label=first_ref
        )
        first_pass = admit_first_pass_record(
            first_record,
            published_states=states,
            plate=plate,
            baseline_state=subject.baseline_state,
        )
        verification_plate = build_motion_rebase_verification_plate(
            frames, first_pass, baseline_state=subject.baseline_state
        )
        self._require_equal(
            plate_data,
            verification_plate.png,
            label=f"{node.node_id} current verification plate",
        )
        self._require_equal(
            set(record),
            {
                "baseline_state",
                "states",
                "first_pass",
                "correction",
                "plate_sha256",
                "verification_plate_sha256",
                "evidence",
            },
            label=f"{node.node_id} verification fields",
        )
        self._require_equal(
            record["baseline_state"],
            subject.baseline_state,
            label=f"{node.node_id} verification baseline",
        )
        self._require_equal(
            record["plate_sha256"], plate.sha256, label=f"{node.node_id} plate digest"
        )
        self._require_equal(
            record["verification_plate_sha256"],
            verification_plate.sha256,
            label=f"{node.node_id} verification plate digest",
        )
        recorded_first = self._numeric_state_map(
            record["first_pass"], states, label="verification first pass"
        )
        self._require_equal(
            recorded_first,
            {state: round(first_pass[state], 2) for state in states},
            label=f"{node.node_id} first-pass binding",
        )
        corrections = self._numeric_state_map(
            record["correction"], states, label="verification corrections"
        )
        if corrections[subject.baseline_state] != 1.0 or any(
            not 0.5 <= value <= 2.0 for value in corrections.values()
        ):
            raise ValueError("verification corrections lie outside the admitted residual band")
        expected_states = {
            state: (
                1.0
                if state == subject.baseline_state
                else round(first_pass[state] * corrections[state], 2)
            )
            for state in states
        }
        self._require_equal(
            self._numeric_state_map(record["states"], states, label="verification states"),
            expected_states,
            label=f"{node.node_id} composed verification",
        )
        self._admit_evidence(record, states)

    def _admit_local_bundle(self, node: Node, bundle: Mapping[str, bytes]) -> None:
        """Re-derive deterministic local cache outputs from admitted dependencies."""

        if node.type_id == PACKAGE_RESOLVE.type_id:
            actual = self._strict_json_object(
                bundle[node.port("package").artifact_ref], label="runner package identity"
            )
            self._require_equal(actual, self._resolved.identity(), label="runner package identity")
            return
        if node.type_id == TRACK_GROUND_VALIDATE.type_id:
            source_ref = self._dependency_artifact(node, kind=GROUND_RAW_KIND)
            canonical, validation = assemble_terrain_atlas(
                (self._run_dir / source_ref).read_bytes()
            )
            if validation["classification"] != "direct_pass":
                raise ValueError("cached terrain source no longer directly passes")
            self._admit_local_image_and_record(node, bundle, image=canonical, validation=validation)
            return
        if node.type_id == TRACK_STRUCTURAL_GROUND_GUIDE.type_id:
            chunk = self._segment(node)
            inputs = self._structural_material_inputs()
            guide, report = build_structural_ground_guide(
                chunk.occupancy,
                walk_surface_row=self._track().segments.walk_surface_row,
                material_identity=self._structural_material_identity(),
                material_references=[data for _ref, data in inputs],
            )
            self._admit_local_image_and_record(
                node,
                bundle,
                image=guide,
                validation={**report, "segment_id": chunk.segment_id},
            )
            return
        if node.type_id == TRACK_STRUCTURAL_GROUND_SEAM_BRIDGE.type_id:
            chunk = self._segment(node)
            raw_ref = self._dependency_artifact(node, kind=STRUCTURAL_GROUND_RAW_KIND)
            guide_ref = self._dependency_artifact(node, kind=STRUCTURAL_GROUND_GUIDE_KIND)
            inputs = self._structural_material_inputs()
            bridge, report = canonicalize_structural_ground_seam_bridge(
                (self._run_dir / raw_ref).read_bytes(),
                occupancy=chunk.occupancy,
                walk_surface_row=self._track().segments.walk_surface_row,
                material_identity=self._structural_material_identity(),
                material_references=[data for _ref, data in inputs],
                guide=(self._run_dir / guide_ref).read_bytes(),
            )
            validate_structural_ground_seam_bridge(
                bridge,
                rows=len(chunk.occupancy),
                walk_surface_row=self._track().segments.walk_surface_row,
            )
            self._admit_local_image_and_record(
                node,
                bundle,
                image=bridge,
                validation={**report, "source_segment_id": chunk.segment_id},
            )
            return
        if node.type_id == TRACK_STRUCTURAL_GROUND_VALIDATE.type_id:
            chunk = self._segment(node)
            raw_ref = self._dependency_artifact(node, kind=STRUCTURAL_GROUND_RAW_KIND)
            guide_ref = self._dependency_artifact(node, kind=STRUCTURAL_GROUND_GUIDE_KIND)
            bridge_ref = self._dependency_artifact(node, kind=STRUCTURAL_GROUND_SEAM_BRIDGE_KIND)
            bridge = (self._run_dir / bridge_ref).read_bytes()
            inputs = self._structural_material_inputs()
            canonical, report = canonicalize_structural_ground(
                (self._run_dir / raw_ref).read_bytes(),
                occupancy=chunk.occupancy,
                walk_surface_row=self._track().segments.walk_surface_row,
                material_identity=self._structural_material_identity(),
                material_references=[data for _ref, data in inputs],
                guide=(self._run_dir / guide_ref).read_bytes(),
                seam_bridge=bridge,
            )
            validate_structural_ground_canonical(
                canonical,
                occupancy=chunk.occupancy,
                walk_surface_row=self._track().segments.walk_surface_row,
                seam_bridge=bridge,
            )
            self._admit_local_image_and_record(
                node,
                bundle,
                image=canonical,
                validation={
                    **report,
                    "segment_id": chunk.segment_id,
                    "seam_bridge_ref": bridge_ref,
                },
            )
            return
        if node.type_id == LAYER_LOOP_CONSTRUCT.type_id:
            self._admit_loop_bundle(
                node,
                bundle,
                provider_operations=0,
                output_selection="local_output",
            )
            return
        if node.type_id == LAYER_VALIDATE.type_id:
            layer = self._layer(node)
            source_ref = self._dependency_artifact(node, kind=LAYER_LOOP_KIND)
            looped = (self._run_dir / source_ref).read_bytes()
            published, validation = _publish_runner_layer(layer, looped)
            self._admit_local_image_and_record(node, bundle, image=published, validation=validation)
            return
        if node.type_id in (AVATAR_MOTION_VALIDATE.type_id, BOSS_MOTION_VALIDATE.type_id):
            state = str(node.params["state"])
            geometry = DEFAULT_MOTION_ATLAS_GEOMETRY
            source_ref = self._dependency_artifact(node, kind=MOTION_RAW_KIND)
            source = (self._run_dir / source_ref).read_bytes()
            source_facts = _validate_motion_source(source)
            motion = self._actor(node).motion(state)
            canonical, repack = repack_alpha_components(
                source,
                AlphaComponentRepackContract(
                    rows=geometry.rows,
                    columns=geometry.columns,
                    required_cells=geometry.required_cells,
                    anchor=motion.anchor,
                    source_slot_policy="exact_required_slots",
                ),
            )
            validation = {
                "schema_version": 2,
                "kind": "sideview-runner-motion-validation-v2",
                "state": state,
                "columns": geometry.columns,
                "rows": geometry.rows,
                "frames": geometry.required_cells,
                "runtime_horizontal_mirroring": True,
                "source_validation": source_facts,
                "repack": repack,
            }
            self._admit_local_image_and_record(node, bundle, image=canonical, validation=validation)
            return
        if node.type_id == CATALOG_ASSET_VALIDATE.type_id:
            source_ref = self._dependency_artifact(node, kind=CATALOG_RAW_KIND)
            source = (self._run_dir / source_ref).read_bytes()
            family = str(node.params["family"])
            published, trim, sparse_tail_trim = canonicalize_runner_catalog_sprite(
                source, family=family
            )
            validation = {
                "schema_version": 3,
                "kind": "sideview-runner-catalog-validation-v3",
                "family": family,
                "entity_id": node.params["entity_id"],
                "source_validation": _validate_transparent_sprite(source),
                "trim": trim,
                "sparse_tail_trim": sparse_tail_trim,
            }
            self._admit_local_image_and_record(node, bundle, image=published, validation=validation)
            return
        if node.type_id == FX_CUT_IN_DRAW.type_id:
            self._require_equal(
                bundle[node.port("image").artifact_ref],
                draw_procedural_frame(),
                label="procedural cut-in frame",
            )
            return
        if node.type_id == FX_SPRITE_DUST_VALIDATE.type_id:
            raw_ref = self._dependency_artifact(node, kind=FX_SPRITE_DUST_RAW_KIND)
            canonical, record, _facts = derive_sprite_dust_validation(
                (self._run_dir / raw_ref).read_bytes()
            )
            self._admit_local_image_and_record(node, bundle, image=canonical, validation=record)
            return
        if node.type_id == FX_CUT_IN_VALIDATE.type_id:
            raw_ref = self._dependency_artifact(node, kind=FX_CUT_IN_RAW_KIND)
            frame_record: dict[str, object] | None = None
            frame_data: bytes | None = None
            placement_record: dict[str, object] | None = None
            if str(node.params["plate"]) == "portrait":
                record_ref = self._dependency_artifact(node, kind=FX_CUT_IN_VALIDATION_KIND)
                frame_record = self._strict_json_object(
                    (self._run_dir / record_ref).read_bytes(), label=record_ref
                )
                frame_ref = self._dependency_artifact(node, kind=FX_CUT_IN_PLATE_KIND)
                frame_data = (self._run_dir / frame_ref).read_bytes()
                placement_ref = self._dependency_artifact(node, kind=FX_CUT_IN_PLACEMENT_KIND)
                placement_record = self._strict_json_object(
                    (self._run_dir / placement_ref).read_bytes(), label=placement_ref
                )
            canonical, record, _facts = derive_cut_in_validation(
                (self._run_dir / raw_ref).read_bytes(),
                node,
                frame_record=frame_record,
                frame_data=frame_data,
                placement_record=placement_record,
            )
            self._admit_local_image_and_record(node, bundle, image=canonical, validation=record)
            return
        if node.type_id in {
            SOUNDTRACK_VALIDATE.type_id,
            SOUND_EFFECT_VALIDATE.type_id,
            SPEECH_VALIDATE.type_id,
            AUDIO_REPUBLISH.type_id,
            MANIFEST_ASSEMBLE.type_id,
        }:
            # These are cheap local publication gates. Audio validation needs
            # an actual ffprobe and manifest assembly closes over every
            # admitted output, so rerun them instead of trusting a serialized
            # verdict that cannot be decisively checked in this synchronous
            # cache callback.
            raise ValueError(f"{node.node_id} is always refreshed locally")
        raise ValueError(f"runner cache has no local admission for {node.type_id}")

    def _admit_local_image_and_record(
        self,
        node: Node,
        bundle: Mapping[str, bytes],
        *,
        image: bytes,
        validation: Mapping[str, object],
    ) -> None:
        image_ref = node.port("image").artifact_ref
        validation_ref = node.port("validation").artifact_ref
        self._require_equal(bundle[image_ref], image, label=f"{node.node_id} local image")
        self._require_equal(
            self._strict_json_object(bundle[validation_ref], label=validation_ref),
            dict(validation),
            label=f"{node.node_id} local validation",
        )

    # ---------------------------------------------------------------- dispatch

    def _handlers(self) -> tuple[tuple[NodeType, NodeMethod], ...]:
        # The boss rides the avatar's handlers: same operation, different subject,
        # resolved from the node's own params.
        return (
            (PACKAGE_RESOLVE, self._write_package),
            (TRACK_GROUND_GENERATE, self._generate_ground),
            (TRACK_GROUND_VALIDATE, self._validate_ground),
            (TRACK_STRUCTURAL_GROUND_GUIDE, self._guide_structural_ground),
            (TRACK_STRUCTURAL_GROUND_GENERATE, self._generate_structural_ground),
            (TRACK_STRUCTURAL_GROUND_SEAM_BRIDGE, self._build_structural_ground_seam_bridge),
            (TRACK_STRUCTURAL_GROUND_VALIDATE, self._validate_structural_ground),
            (LAYER_GENERATE, self._generate_layer),
            (LAYER_LOOP_CONSTRUCT, self._layer_loop),
            (LAYER_LOOP_PAINT, self._layer_loop),
            (LAYER_VALIDATE, self._validate_layer),
            (AVATAR_CONCEPT_GENERATE, self._generate_concept),
            (AVATAR_MOTION_GENERATE, self._generate_motion),
            (AVATAR_MOTION_VALIDATE, self._validate_motion),
            (BOSS_CONCEPT_GENERATE, self._generate_concept),
            (BOSS_MOTION_GENERATE, self._generate_motion),
            (BOSS_MOTION_VALIDATE, self._validate_motion),
            (MOTION_REBASE_JUDGE, self._rebase_judge),
            (MOTION_REBASE_VERIFY, self._rebase_verify),
            (CATALOG_ASSET_GENERATE, self._generate_catalog),
            (CATALOG_ASSET_VALIDATE, self._validate_catalog),
            (SOUNDTRACK_GENERATE, self._generate_track),
            (SOUNDTRACK_VALIDATE, self._validate_track),
            (SOUND_EFFECT_GENERATE, self._generate_sound_effect),
            (SOUND_EFFECT_VALIDATE, self._validate_sound_effect),
            (SPEECH_GENERATE, self._generate_speech),
            (SPEECH_VALIDATE, self._validate_speech),
            (AUDIO_REPUBLISH, self._republish_audio),
            (FX_CUT_IN_GENERATE, self._generate_fx_plate),
            (FX_CUT_IN_DRAW, self._draw_fx_frame),
            (FX_CUT_IN_PLACE, self._place_fx_portrait),
            (FX_CUT_IN_VALIDATE, self._validate_fx_plate),
            (FX_CUT_IN_REVIEW, self._review_fx_plate),
            (FX_SPRITE_DUST_GENERATE, self._generate_fx_sprite),
            (FX_SPRITE_DUST_VALIDATE, self._validate_fx_sprite),
            (MANIFEST_ASSEMBLE, self._assemble_manifest),
        )

    def _result(
        self,
        node: Node,
        *,
        attempts: int = 1,
        provider_operations: int = 0,
        known_cost_usd: float | None = None,
        provider_output_selected: bool = True,
    ) -> NodeExecutionResult:
        """The base result, after the attempt ledger every provider node publishes.

        Unlike the base, a declared port that carries nothing is a refusal here: the
        runner's ports are exact, and a missing one is a handler bug, not an optional
        intermediate.
        """

        if node.operation != RunnerOperationKind.LOCAL:
            output_selection: Literal[
                "provider_output", "fallback_output", "local_output", "none"
            ] = (
                "provider_output"
                if provider_operations and provider_output_selected
                else "fallback_output"
                if provider_operations
                else "local_output"
            )
            self._write_attempt_ledger(
                node,
                provider_operations=provider_operations,
                selected_ref=(
                    self._provider_output_ref(node)
                    if provider_operations and provider_output_selected
                    else None
                ),
                output_selection=output_selection,
                cache_hit=False,
            )
        refs: list[str] = []
        for port in node.ports:
            refs.append(port.artifact_ref)
            if port.sidecar_ref is not None:
                refs.append(port.sidecar_ref)
        missing = [ref for ref in refs if not (self._run_dir / ref).is_file()]
        if missing:
            raise ValueError(
                f"node {node.node_id} did not publish declared artifacts: {', '.join(missing)}"
            )
        artifacts = tuple(
            NodeArtifact(
                artifact_ref=ref,
                sha256=content_sha256((self._run_dir / ref).read_bytes()),
                bytes=(self._run_dir / ref).stat().st_size,
            )
            for ref in refs
        )
        return NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=attempts,
            provider_operations=provider_operations,
            artifacts=artifacts,
            known_cost_usd=known_cost_usd,
        )

    def _provider_output_ref(self, node: Node) -> str:
        if node.operation == RunnerOperationKind.IMAGE_GENERATION:
            preferred = (
                "edit_image"
                if any(port.port_id == "edit_image" for port in node.ports)
                else "image"
            )
        elif node.operation == RunnerOperationKind.STRUCTURED_GENERATION:
            preferred = (
                "verdict"
                if any(port.port_id == "verdict" for port in node.ports)
                else "verification"
                if any(port.port_id == "verification" for port in node.ports)
                else "reading"
            )
        elif node.operation == RunnerOperationKind.TOOL_LOOP:
            preferred = "placement"
        elif node.operation in {
            RunnerOperationKind.MUSIC_GENERATION,
            RunnerOperationKind.SOUND_EFFECT_GENERATION,
            RunnerOperationKind.SPEECH_GENERATION,
        }:
            preferred = "audio"
        else:
            raise ValueError(f"node {node.node_id} is not a provider operation")
        return node.port(preferred).artifact_ref

    def _attempt_port_ref(self, node: Node) -> str | None:
        return next(
            (port.artifact_ref for port in node.ports if port.kind == ATTEMPT_LEDGER_KIND),
            None,
        )

    def _write_attempt_ledger(
        self,
        node: Node,
        *,
        provider_operations: int,
        selected_ref: str | None,
        output_selection: Literal["provider_output", "fallback_output", "local_output", "none"],
        cache_hit: bool,
    ) -> Path | None:
        attempt_ref = self._attempt_port_ref(node)
        if attempt_ref is None:
            return None
        prompt = self._provider_prompt(node)
        prompt_sha256 = content_sha256(prompt.encode("utf-8"))
        not_selected = (
            provider_operations if selected_ref is None else max(0, provider_operations - 1)
        )
        records: list[dict[str, object]] = [
            {
                "attempt": ordinal,
                "outcome": "not_selected",
                "prompt_sha256": prompt_sha256,
                "reason": "provider attempt did not produce the selected output",
            }
            for ordinal in range(1, not_selected + 1)
        ]
        if selected_ref is not None:
            selected_path = self._run_dir / selected_ref
            records.append(
                {
                    "attempt": provider_operations,
                    "outcome": "selected",
                    "artifact_ref": selected_ref,
                    "artifact_sha256": content_sha256(selected_path.read_bytes()),
                    "prompt_sha256": prompt_sha256,
                }
            )
        ledger = {
            "schema_version": 2,
            "kind": "sideview-runner-attempt-ledger-v2",
            "node_id": node.node_id,
            "cache_hit": cache_hit,
            "provider_operations": provider_operations,
            "output_selection": output_selection,
            "prompt_sha256": prompt_sha256,
            "attempts": records,
        }
        path = self._run_dir / attempt_ref
        atomic_write_json(path, ledger)
        return path

    def _write_failed_attempt_ledger(self, node: Node, *, provider_operations: int) -> None:
        if node.operation != RunnerOperationKind.LOCAL:
            self._write_attempt_ledger(
                node,
                provider_operations=provider_operations,
                selected_ref=None,
                output_selection="none",
                cache_hit=False,
            )

    # ------------------------------------------------------------------ shared

    def _provider_prompt(self, node: Node) -> str:
        """Return the exact prompt sent by every provider-backed node."""

        if node.card is not None and node.card.prompt is not None:
            return node.card.prompt
        if node.type_id == LAYER_LOOP_PAINT.type_id:
            return layer_loop_prompt(self._layer(node).prompt)
        if node.type_id in (MOTION_REBASE_JUDGE.type_id, MOTION_REBASE_VERIFY.type_id):
            subject = self._actor(node)
            states = list(subject.states)
            if node.type_id == MOTION_REBASE_JUDGE.type_id:
                return motion_rebase_prompt(subject.display_name, states)
            return motion_rebase_verification_prompt(subject.display_name, states)
        if node.type_id == SOUNDTRACK_GENERATE.type_id:
            soundtrack = self._runner.soundtrack
            if soundtrack is None:
                raise ValueError("runner package declares no soundtrack member")
            track = soundtrack.track(str(node.params["track_id"]))
            return music_track_prompt(
                medium="a 2D game",
                game_id=self._package.game.game_id,
                track_id=track.track_id,
                creative_brief=track.creative_brief,
                generation=track.generation,
                direction=soundtrack_direction(),
            )
        if node.type_id == SOUND_EFFECT_GENERATE.type_id:
            # Verbatim: the authored text is the entire prompt.
            return self._generated_clip(node)[1].prompt
        if node.type_id == SPEECH_GENERATE.type_id:
            # Verbatim, delivery annotations included: nothing is compiled onto a line.
            return self._spoken_line(node)[1].text
        raise ValueError(f"provider node {node.node_id} carries no executable prompt")

    def _authored_references(self, node: Node) -> tuple[ImageReference, ...]:
        card = node.card
        if card is None:
            return ()
        references = []
        for authored in card.authored_inputs:
            data = self._package.file(authored.ref).data
            references.append(
                ImageReference(
                    data_url(data, _image_media_type(data)),
                    (
                        f"package://{self._package.game.game_id}/{authored.ref}"
                        f"#sha256={authored.sha256}"
                    ),
                )
            )
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

    def _structural_ground(self) -> RunnerStructuralGround:
        ground = self._track().ground
        if not isinstance(ground, RunnerStructuralGround):
            raise ValueError("runner track does not declare structural ground")
        return ground

    def _segment(self, node: Node) -> RunnerSegmentChunk:
        segment_id = str(node.params["segment_id"])
        for chunk in self._track().segments.chunks:
            if chunk.segment_id == segment_id:
                return chunk
        raise KeyError(segment_id)

    def _structural_material_inputs(self) -> list[tuple[str, bytes]]:
        ground = self._structural_ground()
        sources = {
            reference.reference_id: reference.source for reference in self._track().references
        }
        return [
            (sources[reference_id], self._package.file(sources[reference_id]).data)
            for reference_id in ground.reference_ids
        ]

    def _structural_material_identity(self) -> str:
        ground = self._structural_ground()
        inputs = self._structural_material_inputs()
        return structural_ground_material_identity(
            prompt=ground.prompt,
            visual_direction_sha256=visual_direction_digest(self._resolved),
            reference_sha256=[content_sha256(data) for _source, data in inputs],
            projection=ground.projection_mode(),
        )

    def _structural_projection(self) -> str:
        """The declared ground projection, or the default an absent block means."""

        return self._structural_ground().projection_mode()

    # ------------------------------------------------------------------- nodes

    async def _write_package(self, node: Node) -> NodeExecutionResult:
        atomic_write_json(
            self._run_dir / node.port("package").artifact_ref, self._resolved.identity()
        )
        return self._result(node)

    async def _generate_ground(self, node: Node) -> NodeExecutionResult:
        request = self._image_generation_request(node)
        result = await self._execute_provider_operation(
            node, lambda: self._images.generate(request)
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

    async def _guide_structural_ground(self, node: Node) -> NodeExecutionResult:
        chunk = self._segment(node)
        material_inputs = self._structural_material_inputs()
        guide, base_report = build_structural_ground_guide(
            chunk.occupancy,
            walk_surface_row=self._track().segments.walk_surface_row,
            material_identity=self._structural_material_identity(),
            material_references=[data for _source, data in material_inputs],
        )
        report = {**base_report, "segment_id": chunk.segment_id}
        await _write_local_image(
            self._run_dir / node.port("image").artifact_ref,
            guide,
            prompt=(
                f"Compose the exact authored occupancy guide for {chunk.segment_id}, with two "
                "deterministic common-material apron columns at each seam."
            ),
            inputs=[
                (
                    f"package://{self._package.game.game_id}/{source}"
                    f"#sha256={content_sha256(data)}",
                    data,
                )
                for source, data in material_inputs
            ],
            validation=report,
            model="sideview-runner-structural-ground-guide-v1",
        )
        atomic_write_json(self._run_dir / node.port("validation").artifact_ref, report)
        return self._result(node)

    async def _generate_structural_ground(self, node: Node) -> NodeExecutionResult:
        request = self._image_generation_request(node)
        result = await self._execute_provider_operation(
            node, lambda: self._images.generate(request)
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _build_structural_ground_seam_bridge(self, node: Node) -> NodeExecutionResult:
        chunk = self._segment(node)
        raw_ref = self._dependency_artifact(node, kind=STRUCTURAL_GROUND_RAW_KIND)
        guide_ref = self._dependency_artifact(node, kind=STRUCTURAL_GROUND_GUIDE_KIND)
        raw = (self._run_dir / raw_ref).read_bytes()
        guide = (self._run_dir / guide_ref).read_bytes()
        material_inputs = self._structural_material_inputs()
        bridge, base_report = canonicalize_structural_ground_seam_bridge(
            raw,
            occupancy=chunk.occupancy,
            walk_surface_row=self._track().segments.walk_surface_row,
            material_identity=self._structural_material_identity(),
            material_references=[data for _source, data in material_inputs],
            guide=guide,
        )
        report = {**base_report, "source_segment_id": chunk.segment_id}
        await _write_local_image(
            self._run_dir / node.port("image").artifact_ref,
            bridge,
            prompt=(
                f"Canonicalize the generated right two-column apron from {chunk.segment_id} "
                "as the shared structural-ground seam bridge."
            ),
            inputs=[
                (raw_ref, raw),
                (guide_ref, guide),
                *(
                    (
                        f"package://{self._package.game.game_id}/{source}"
                        f"#sha256={content_sha256(data)}",
                        data,
                    )
                    for source, data in material_inputs
                ),
            ],
            validation=report,
            model=STRUCTURAL_GROUND_SEAM_BRIDGE_CANONICALIZER_ID,
        )
        atomic_write_json(self._run_dir / node.port("validation").artifact_ref, report)
        return self._result(node)

    async def _validate_structural_ground(self, node: Node) -> NodeExecutionResult:
        chunk = self._segment(node)
        raw_ref = self._dependency_artifact(node, kind=STRUCTURAL_GROUND_RAW_KIND)
        guide_ref = self._dependency_artifact(node, kind=STRUCTURAL_GROUND_GUIDE_KIND)
        bridge_ref = self._dependency_artifact(node, kind=STRUCTURAL_GROUND_SEAM_BRIDGE_KIND)
        raw = (self._run_dir / raw_ref).read_bytes()
        guide = (self._run_dir / guide_ref).read_bytes()
        bridge = (self._run_dir / bridge_ref).read_bytes()
        material_inputs = self._structural_material_inputs()
        canonical, base_report = canonicalize_structural_ground(
            raw,
            occupancy=chunk.occupancy,
            walk_surface_row=self._track().segments.walk_surface_row,
            material_identity=self._structural_material_identity(),
            material_references=[data for _source, data in material_inputs],
            guide=guide,
            seam_bridge=bridge,
        )
        report = {
            **base_report,
            "segment_id": chunk.segment_id,
            "seam_bridge_ref": bridge_ref,
        }
        await _write_local_image(
            self._run_dir / node.port("image").artifact_ref,
            canonical,
            prompt=(
                f"Mask the {chunk.segment_id} painting to authored occupancy, install shared "
                "bridge column 1 at the left edge, and bridge column 0 at the right edge."
            ),
            inputs=[
                (raw_ref, raw),
                (guide_ref, guide),
                (bridge_ref, bridge),
                *(
                    (
                        f"package://{self._package.game.game_id}/{source}"
                        f"#sha256={content_sha256(data)}",
                        data,
                    )
                    for source, data in material_inputs
                ),
            ],
            validation=report,
            model=STRUCTURAL_GROUND_CANONICALIZER_ID,
        )
        atomic_write_json(self._run_dir / node.port("validation").artifact_ref, report)
        return self._result(node)

    async def _generate_layer(self, node: Node) -> NodeExecutionResult:
        request = self._image_generation_request(node)
        result = await self._execute_provider_operation(
            node, lambda: self._images.generate(request)
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
        generative = LOOP_METHODS[construction].is_generative
        edit_ref = node.port("edit_image").artifact_ref if generative else None
        edit_path = self._run_dir / edit_ref if edit_ref is not None else None
        edit_data: bytes | None = None
        if admission.verdict == "pass":
            looped = raw_data
            record: dict[str, object] = {
                "schema_version": 1,
                "kind": "direct-loop-admission-v1",
                "construction": "none",
                "skipped_construction": construction,
                "provider_operations": 0,
            }
            if edit_path is not None and edit_ref is not None:
                edit_data = raw_data
                await _write_local_image(
                    edit_path,
                    edit_data,
                    prompt=f"Record the skipped {layer.layer_id} loop edit without provider use.",
                    inputs=[(source_ref, raw_data)],
                    validation={"construction": "none", "provider_skipped": True},
                    model="sideview-runner-loop-edit-bypass-v1",
                )
        elif not generative:
            looped, record = construct_deterministic(construction, raw_data)
            record["construction"] = construction
        else:
            conditioning = loop_conditioning(construction, raw_data)
            assert edit_path is not None
            request = self._image_generation_request(node)
            generation = await self._execute_provider_operation(
                node, lambda: self._images.generate(request)
            )
            provider_operations = generation.attempts
            edit_data = edit_path.read_bytes()
            try:
                looped, record = assemble_loop(
                    construction, raw_data, edit_data, conditioning=conditioning
                )
                record["construction"] = construction
            except RegistrationError as error:
                looped, record = construct_deterministic(fallback, raw_data)
                record["construction"] = fallback
                record["rejected_construction"] = construction
                record["rejection"] = str(error)
            record["provider_operations"] = provider_operations
        report = admit(looped)
        if report.verdict != "pass" and generative:
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
        loop_inputs = [(source_ref, raw_data)]
        if (
            record["construction"] == construction
            and edit_ref is not None
            and edit_data is not None
        ):
            loop_inputs.append((edit_ref, edit_data))
        await _write_local_image(
            self._run_dir / node.port("loop_image").artifact_ref,
            looped,
            prompt=f"Loop the {layer.layer_id} layer by {record['construction']}.",
            inputs=loop_inputs,
            validation={"construction": record["construction"]},
        )
        atomic_write_json(self._run_dir / node.port("loop_report").artifact_ref, record)
        return self._result(
            node,
            attempts=max(1, provider_operations),
            provider_operations=provider_operations,
            provider_output_selected=(
                provider_operations > 0 and record["construction"] == construction
            ),
        )

    async def _validate_layer(self, node: Node) -> NodeExecutionResult:
        layer = self._layer(node)
        source_ref = self._dependency_artifact(node, kind=LAYER_LOOP_KIND)
        looped = (self._run_dir / source_ref).read_bytes()
        published, validation = _publish_runner_layer(layer, looped)
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
        request = self._image_generation_request(node)
        result = await self._execute_provider_operation(
            node, lambda: self._images.generate(request)
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _generate_motion(self, node: Node) -> NodeExecutionResult:
        request = self._image_generation_request(node)
        result = await self._execute_provider_operation(
            node, lambda: self._images.generate(request)
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _validate_motion(self, node: Node) -> NodeExecutionResult:
        state = str(node.params["state"])
        geometry = DEFAULT_MOTION_ATLAS_GEOMETRY
        source_ref = self._dependency_artifact(node, kind=MOTION_RAW_KIND)
        source_data = (self._run_dir / source_ref).read_bytes()
        source_facts = _validate_motion_source(source_data)
        motion = self._actor(node).motion(state)
        canonical_data, repack = repack_alpha_components(
            source_data,
            AlphaComponentRepackContract(
                rows=geometry.rows,
                columns=geometry.columns,
                required_cells=geometry.required_cells,
                anchor=motion.anchor,
                source_slot_policy="exact_required_slots",
            ),
        )
        validation = {
            "schema_version": 2,
            "kind": "sideview-runner-motion-validation-v2",
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

    def _actor(self, node: Node) -> _ActorSubject:
        """Which drawn actor this node is about, from its own params.

        Absent means the avatar, so every node authored before bosses existed
        keeps its identity and its cache key.
        """

        if str(node.params.get("actor", "avatar")) != "boss":
            avatar = self._runner.avatar.avatar
            return _ActorSubject(
                label="avatar",
                entity_id=avatar.avatar_id,
                display_name=avatar.display_name,
                motions=tuple(avatar.motions),
                states=declared_motion_states(avatar),
                baseline_state=RUNNER_BASELINE_STATE,
                artifact_dir="avatar",
                concept_kind=AVATAR_CONCEPT_KIND,
            )
        bosses = self._runner.bosses
        if bosses is None:
            raise ValueError("a boss node requires a declared boss catalog")
        boss = bosses.boss(str(node.params["boss_id"]))
        return _ActorSubject(
            label="boss",
            entity_id=boss.boss_id,
            display_name=boss.display_name,
            motions=tuple(boss.motions),
            states=declared_boss_motion_states(boss),
            baseline_state=RUNNER_BOSS_BASELINE_STATE,
            artifact_dir=f"boss/{boss.boss_id}",
            concept_kind=BOSS_CONCEPT_KIND,
        )

    def _state_frames(self, node: Node) -> dict[str, tuple[bytes, ...]]:
        subject = self._actor(node)
        frames_by_state: dict[str, tuple[bytes, ...]] = {}
        geometry = DEFAULT_MOTION_ATLAS_GEOMETRY
        for state in subject.states:
            atlas_ref = f"{subject.artifact_dir}/{state}.png"
            frames_by_state[state] = split_atlas_columns(
                (self._run_dir / atlas_ref).read_bytes(), geometry.columns, geometry.rows
            )
        return frames_by_state

    def _rebase_subject(self, node: Node) -> RebaseSubject:
        """The family's view of this node's actor: the runner's subject, atlases by convention."""

        subject = self._actor(node)
        return RebaseSubject(
            label=subject.label,
            entity_id=subject.entity_id,
            display_name=subject.display_name,
            states=subject.states,
            baseline_state=subject.baseline_state,
            atlas_refs={state: f"{subject.artifact_dir}/{state}.png" for state in subject.states},
            geometry=lambda _state: DEFAULT_MOTION_ATLAS_GEOMETRY,
        )

    async def _rebase_judge(self, node: Node) -> NodeExecutionResult:
        # The family judges; this recipe's result writes the attempt ledger beside it.
        result = await self._rebase.judge(node)
        return self._result(
            node, attempts=result.attempts, provider_operations=result.provider_operations
        )

    async def _rebase_verify(self, node: Node) -> NodeExecutionResult:
        result = await self._rebase.verify(node)
        return self._result(
            node, attempts=result.attempts, provider_operations=result.provider_operations
        )

    def _structured_reference(self, path: Path) -> StructuredReference:
        return StructuredReference(
            url=data_url(path.read_bytes(), "image/png"),
            provenance_ref=f"run://{path.relative_to(self._run_dir).as_posix()}",
        )

    async def _generate_catalog(self, node: Node) -> NodeExecutionResult:
        request = self._image_generation_request(node)
        result = await self._execute_provider_operation(
            node, lambda: self._images.generate(request)
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _validate_catalog(self, node: Node) -> NodeExecutionResult:
        source_ref = self._dependency_artifact(node, kind=CATALOG_RAW_KIND)
        source_data = (self._run_dir / source_ref).read_bytes()
        facts = _validate_transparent_sprite(source_data)
        family = str(node.params["family"])
        published, trim, sparse_tail_trim = canonicalize_runner_catalog_sprite(
            source_data, family=family
        )
        validation = {
            "schema_version": 3,
            "kind": "sideview-runner-catalog-validation-v3",
            "family": family,
            "entity_id": node.params["entity_id"],
            "source_validation": facts,
            "trim": trim,
            "sparse_tail_trim": sparse_tail_trim,
        }
        await _write_local_image(
            self._run_dir / node.port("image").artifact_ref,
            published,
            prompt=f"Publish the trimmed {node.params['entity_id']} catalog asset.",
            inputs=[(source_ref, source_data)],
            validation=validation,
            model="sideview-runner-catalog-canonicalization-v2",
        )
        atomic_write_json(self._run_dir / node.port("validation").artifact_ref, validation)
        return self._result(node)

    async def _generate_track(self, node: Node) -> NodeExecutionResult:
        # The family generates; this recipe's result writes the attempt ledger beside it.
        result = await self._soundtrack.generate(node)
        return self._result(
            node, attempts=result.attempts, provider_operations=result.provider_operations
        )

    async def _validate_track(self, node: Node) -> NodeExecutionResult:
        await self._soundtrack.validate(node)
        return self._result(node)

    # ----------------------------------------------------------- sound effects

    async def _generate_sound_effect(self, node: Node) -> NodeExecutionResult:
        service = self._sound_effects
        if service is None:
            raise ValueError("runner sound-effect execution requires a sound effect service")
        request = self._sound_effect_request(node)
        result = await self._execute_provider_operation(node, lambda: service.generate(request))
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _validate_sound_effect(self, node: Node) -> NodeExecutionResult:
        effect_id, realization = self._generated_clip(node)
        source = self._run_dir / self._dependency_artifact(node, kind=SOUND_EFFECT_CLIP_KIND)
        probe = await probe_audio(source, timeout_seconds=120)
        delta = probe.duration_seconds - realization.duration_seconds
        if abs(delta) > DURATION_TOLERANCE_SECONDS:
            raise ValueError(
                f"generated clip {effect_id} runs {probe.duration_seconds:.3f}s against an "
                f"authored {realization.duration_seconds:.3f}s"
            )
        level = await admit_sound_effect_bytes(source.read_bytes())
        atomic_write_json(
            self._run_dir / node.port("validation").artifact_ref,
            {
                "schema_version": 1,
                "kind": "sideview-runner-sound-effect-validation-v1",
                "effect_id": effect_id,
                "format_name": probe.format_name,
                "duration_seconds": round(probe.duration_seconds, 3),
                "authored_duration_seconds": realization.duration_seconds,
                "duration_delta_seconds": round(delta, 3),
                "peak_dbfs": level["peak_dbfs"],
                "clipped": level["clipped"],
                "container_valid": True,
                "listening_verdict": _listening_verdict(realization.pinned),
            },
        )
        return self._result(node)

    async def _generate_speech(self, node: Node) -> NodeExecutionResult:
        service = self._speech
        if service is None:
            raise ValueError("runner speech execution requires a speech service")
        request = self._speech_request(node)
        result = await self._execute_provider_operation(node, lambda: service.generate(request))
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _validate_speech(self, node: Node) -> NodeExecutionResult:
        effect_id, realization = self._spoken_line(node)
        source = self._run_dir / self._dependency_artifact(node, kind=SPEECH_CLIP_KIND)
        probe = await probe_audio(source, timeout_seconds=120)
        facts = await admit_speech_bytes(source.read_bytes(), max_seconds=realization.max_seconds)
        atomic_write_json(
            self._run_dir / node.port("validation").artifact_ref,
            {
                "schema_version": 1,
                "kind": "sideview-runner-speech-validation-v1",
                "effect_id": effect_id,
                "voice_id": realization.voice_id,
                "format_name": probe.format_name,
                # The length the consumer will play: measured, never authored.
                "duration_seconds": round(probe.duration_seconds, 3),
                "max_seconds": realization.max_seconds,
                "peak_dbfs": facts["peak_dbfs"],
                "clipped": facts["clipped"],
                "container_valid": True,
                "listening_verdict": _listening_verdict(realization.pinned),
            },
        )
        return self._result(node)

    async def _republish_audio(self, node: Node) -> NodeExecutionResult:
        """Install a reviewed take as the effect's artifact, sidecar and all.

        The bytes and the sidecar come from the package closure, already
        digest-locked by the resolver. They are written verbatim - the sidecar
        is the provenance of the take, and rewriting it would claim this run
        made what a person chose - and admitted on the same level and length
        gates a fresh draw meets, so a pinned take that clips is a package
        error rather than a shipped one.
        """

        effect = self._runner.audio.effect(str(node.params["effect_id"]))
        realization = effect.realization
        if not isinstance(realization, GeneratedClipRealization | SpokenLineRealization):
            raise ValueError(f"runner effect {effect.effect_id} cannot carry a pinned take")
        pinned = realization.pinned
        if pinned is None:
            raise ValueError(f"runner effect {effect.effect_id} pins no take")
        data = self._package.file(pinned.source).data
        sidecar = self._package.file(pinned.provenance_source).data
        if isinstance(realization, SpokenLineRealization):
            admit_speech_bytes_sync(data, max_seconds=realization.max_seconds)
        else:
            admit_sound_effect_bytes_sync(data)
        port = node.port("audio")
        assert port.sidecar_ref is not None
        atomic_write_bytes(self._run_dir / port.artifact_ref, data)
        atomic_write_bytes(self._run_dir / port.sidecar_ref, sidecar)
        return self._result(node)

    # ---------------------------------------------------------------- manifest

    # ------------------------------------------------------------------- fx

    def _fx_host(self) -> FxCutInHost:
        fx = self._runner.fx
        if fx is None:
            raise ValueError("runner package declares no fx member")
        return FxCutInHost(
            fx=fx,
            run_dir=self._run_dir,
            package_id=self._package.game.game_id,
            file=self._package.file,
            component=_COMPONENT,
            tool=STAGE_GEN_TOOL,
        )

    def _read_run_artifact(self, ref: str) -> bytes:
        return (self._run_dir / ref).read_bytes()

    async def _generate_fx_plate(self, node: Node) -> NodeExecutionResult:
        request = self._image_generation_request(node)
        result = await self._execute_provider_operation(
            node, lambda: self._images.generate(request)
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _draw_fx_frame(self, node: Node) -> NodeExecutionResult:
        await write_cut_in_draw(self._fx_host(), node)
        return self._result(node)

    async def _place_fx_portrait(self, node: Node) -> NodeExecutionResult:
        if self._tool_loop is None:
            raise ValueError("runner execution needs a tool-loop service to place a cut-in")
        request = cut_in_place_request(
            self._fx_host(), self._graph, node, read=self._read_run_artifact
        )
        tool_loop = self._tool_loop
        result = await self._execute_provider_operation(node, lambda: tool_loop.run(request))
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _generate_fx_sprite(self, node: Node) -> NodeExecutionResult:
        request = sprite_dust_generate_request(self._fx_host(), node)
        result = await self._execute_provider_operation(
            node, lambda: self._images.generate(request)
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _validate_fx_sprite(self, node: Node) -> NodeExecutionResult:
        await write_sprite_dust_validation(
            self._fx_host(), self._graph, node, read=self._read_run_artifact
        )
        return self._result(node)

    async def _validate_fx_plate(self, node: Node) -> NodeExecutionResult:
        await write_cut_in_validation(
            self._fx_host(), self._graph, node, read=self._read_run_artifact
        )
        return self._result(node)

    async def _review_fx_plate(self, node: Node) -> NodeExecutionResult:
        request = cut_in_review_request(
            self._fx_host(), self._graph, node, read=self._read_run_artifact
        )
        result = await self._execute_provider_operation(
            node, lambda: self._structured.generate(request)
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _assemble_manifest(self, node: Node) -> NodeExecutionResult:
        runner = self._runner
        track = runner.track
        scale = self._package.game.scale

        # Republish every authored reference the manifest names.
        for port in node.ports:
            if port.kind != "runner-reference-v1":
                continue
            data = self._package.file(port.artifact_ref).data
            package_ref = (
                f"package://{self._package.game.game_id}/{port.artifact_ref}"
                f"#sha256={content_sha256(data)}"
            )
            await _write_local_image(
                self._run_dir / port.artifact_ref,
                data,
                prompt="Republish the authored reference into the run.",
                inputs=[(package_ref, data)],
                validation={"republished": True},
            )

        def read_json(ref: str) -> dict[str, object]:
            return cast("dict[str, object]", json.loads((self._run_dir / ref).read_bytes()))

        rebase = read_json("avatar/rebase-verification.json")
        multipliers = manifest_rebase_multipliers(
            rebase, published_states=declared_motion_states(self._runner.avatar.avatar)
        )

        def calibration(
            data: bytes,
            *,
            height_units_declared: float | None,
            subject: str,
            player: bool,
            extent_axis: SubjectExtentAxis = "height",
        ) -> dict[str, object]:
            magnitude = (
                resolve_player_magnitude(None)
                if player
                else resolve_declared_magnitude(scale, height_units_declared, subject=subject)
            )
            extent = measure_subject_extent(data, subject=subject, axis=extent_axis)
            return calibrate_subject(
                magnitude=magnitude,
                subject_extent_px=extent,
                measured_sha256=content_sha256(data),
                scale=scale,
                tile_px=RUNTIME_TILE_PX,
                subject=subject,
                extent_axis=extent_axis,
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
                    "rebase_multiplier": multipliers[motion_entry.state],
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
        bosses: list[dict[str, object]] = []
        for boss_entry in runner.bosses.bosses if runner.bosses is not None else ():
            boss_dir = f"boss/{boss_entry.boss_id}"
            boss_rebase = read_json(f"{boss_dir}/rebase-verification.json")
            boss_multipliers = manifest_rebase_multipliers(
                boss_rebase, published_states=declared_boss_motion_states(boss_entry)
            )
            hover_atlas = (
                self._run_dir / f"{boss_dir}/{RUNNER_BOSS_BASELINE_STATE}.png"
            ).read_bytes()
            bosses.append(
                {
                    "boss_id": boss_entry.boss_id,
                    "display_name": boss_entry.display_name,
                    "concept": f"{boss_dir}/concept.png",
                    # Measured on the hover, which is the baseline every other
                    # strip was rebased against.
                    "calibration": calibration(
                        hover_atlas,
                        height_units_declared=boss_entry.height_units,
                        subject=f"boss {boss_entry.boss_id}",
                        player=False,
                    ),
                    "motions": [
                        {
                            "state": entry.state,
                            "playback_mode": entry.playback_mode,
                            "canonical_frame_indices": entry.canonical_frame_indices,
                            "frames_per_second": entry.frames_per_second,
                            "anchor": entry.anchor,
                            "atlas": f"{boss_dir}/{entry.state}.png",
                            "columns": DEFAULT_MOTION_ATLAS_GEOMETRY.columns,
                            "rebase_multiplier": boss_multipliers[entry.state],
                        }
                        for entry in boss_entry.motions
                    ],
                }
            )
        projectiles: list[dict[str, object]] = []
        for shot_entry in runner.projectiles.projectiles if runner.projectiles is not None else ():
            shot_ref = f"catalog/projectiles/{shot_entry.projectile_id}.png"
            shot_data = (self._run_dir / shot_ref).read_bytes()
            projectiles.append(
                {
                    "projectile_id": shot_entry.projectile_id,
                    "display_name": shot_entry.display_name,
                    "silhouette": shot_entry.silhouette,
                    "flight": shot_entry.flight,
                    "impact": shot_entry.impact,
                    "image": shot_ref,
                    # Measured across, not up: every projectile is drawn
                    # pointing right, so its travel axis is its width, and a
                    # height measurement would say how thick it is rather than
                    # how long. The published record names the axis, so a
                    # consumer never has to infer it.
                    "calibration": calibration(
                        shot_data,
                        height_units_declared=shot_entry.length_units,
                        subject=f"projectile {shot_entry.projectile_id}",
                        player=False,
                        extent_axis="width",
                    ),
                    "length_units": shot_entry.length_units,
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
                    "vertical_offset": _published_layer_offset(validation),
                    "vertical_offset_source": _published_layer_offset_source(validation),
                    "image": f"world/layers/{layer.layer_id}.png",
                    "width": validation["width"],
                    "height": validation["height"],
                    "presentation": layer.presentation.model_dump(mode="json"),
                }
            )

        if isinstance(track.ground, RunnerStructuralGround):
            ground_chunks: list[dict[str, object]] = []
            bridge_ref = "world/ground/shared-seam-bridge.png"
            bridge_data = (self._run_dir / bridge_ref).read_bytes()
            bridge_facts = validate_structural_ground_seam_bridge(
                bridge_data,
                rows=track.segments.rows,
                walk_surface_row=track.segments.walk_surface_row,
            )
            bridge_validation = read_json("world/ground/shared-seam-bridge.validation.json")
            if bridge_validation.get("canonical") != bridge_facts:
                raise ValueError("structural ground seam bridge validation is stale")
            bridge_sha256: set[str] = set()
            left_role_sha256: set[str] = set()
            right_role_sha256: set[str] = set()
            bridge_lineage: set[str] = set()
            material_identities: set[str] = set()
            for chunk in track.segments.chunks:
                image_ref = f"world/ground/{chunk.segment_id}.png"
                facts = validate_structural_ground_canonical(
                    (self._run_dir / image_ref).read_bytes(),
                    occupancy=chunk.occupancy,
                    walk_surface_row=track.segments.walk_surface_row,
                    seam_bridge=bridge_data,
                )
                validation = read_json(f"world/ground/{chunk.segment_id}.validation.json")
                if validation.get("segment_id") != chunk.segment_id:
                    raise ValueError(
                        f"structural ground validation identity drifted for {chunk.segment_id}"
                    )
                if validation.get("canonical") != facts:
                    raise ValueError(
                        f"structural ground validation is stale for {chunk.segment_id}"
                    )
                seam = cast("dict[str, object]", facts["seam"])
                left_role = cast("dict[str, object]", seam["left"])
                right_role = cast("dict[str, object]", seam["right"])
                bridge_sha256.add(str(seam["bridge_sha256"]))
                left_role_sha256.add(str(left_role["sha256"]))
                right_role_sha256.add(str(right_role["sha256"]))
                bridge_lineage.add(str(validation.get("seam_bridge_ref")))
                material_identities.add(str(validation["material_identity"]))
                ground_chunks.append(
                    {
                        "segment_id": chunk.segment_id,
                        "image": image_ref,
                        "columns": len(chunk.occupancy[0]),
                        "rows": len(chunk.occupancy),
                    }
                )
            if bridge_sha256 != {str(bridge_facts["sha256"])}:
                raise ValueError("structural ground chunks do not share one seam bridge")
            bridge_roles = cast("dict[str, object]", bridge_facts["roles"])
            expected_left = cast("dict[str, object]", bridge_roles["left"])
            expected_right = cast("dict[str, object]", bridge_roles["right"])
            if left_role_sha256 != {str(expected_left["sha256"])}:
                raise ValueError("structural ground chunks do not share the left bridge role")
            if right_role_sha256 != {str(expected_right["sha256"])}:
                raise ValueError("structural ground chunks do not share the right bridge role")
            if bridge_lineage != {bridge_ref}:
                raise ValueError("structural ground chunks do not share bridge lineage")
            if material_identities != {self._structural_material_identity()}:
                raise ValueError("structural ground chunks do not share the authored material")
            ground_manifest = manifest_ground(track)
            if ground_manifest["chunks"] != ground_chunks:
                raise ValueError("structural ground manifest projection drifted from validation")
        else:
            ground_manifest = manifest_ground(track)

        manifest = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
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
            # The published arithmetic: every number an offline refusal depends
            # on rides here, so the arc the runtime flies and the arc admission
            # proved are the same closed forms rather than a convention.
            "gameplay": manifest_gameplay(runner.gameplay),
            "ground": ground_manifest,
            "layers": layers,
            "segments": {
                "rows": track.segments.rows,
                "walk_surface_row": track.segments.walk_surface_row,
                "chunks": [
                    {
                        "segment_id": chunk.segment_id,
                        "difficulty": chunk.difficulty,
                        "role": chunk.role,
                        "occupancy": chunk.occupancy,
                        "hazards": [
                            {
                                "prop_id": hazard.prop_id,
                                "column": hazard.column,
                                "anchor": hazard.anchor,
                                "clearance_rows": hazard.clearance_rows,
                            }
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
            "bosses": bosses,
            "projectiles": projectiles,
            "audio": manifest_audio(runner.audio, read_validation=self._read_run_artifact),
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
            "fx": (
                None
                if runner.fx is None
                else fx_manifest_block(
                    runner.fx,
                    read_validation=self._read_run_artifact,
                    # The stage announces where the run is; the encounter
                    # announces what has arrived. Both are display names the
                    # package already holds.
                    lettering={
                        "stage_start": (track.display_name, self._package.game.display_name),
                        **(
                            {}
                            if runner.gameplay.encounter is None or runner.bosses is None
                            else {
                                "encounter_start": (
                                    runner.bosses.boss(
                                        runner.gameplay.encounter.boss_id
                                    ).display_name,
                                    track.display_name,
                                )
                            }
                        ),
                    },
                )
            ),
        }
        manifest["blocks"] = present_blocks(RUNNER_MANIFEST_BLOCK_VERSIONS, manifest)
        atomic_write_json(self._run_dir / node.port("manifest").artifact_ref, manifest)
        return self._result(node)


__all__ = [
    "RUNNER_CATALOG_SPARSE_TAIL_TRIM_VERSION",
    "RUNNER_BASELINE_STATE",
    "RUNTIME_TILE_PX",
    "SideviewRunnerNodeHandler",
    "canonicalize_runner_catalog_sprite",
    "manifest_audio",
    "manifest_gameplay",
    "manifest_ground",
    "manifest_rebase_multipliers",
]
