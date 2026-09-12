"""Iron Petal Unit runtime manifest projection from admitted inputs and prepared assets.

This is a game-owned document, not an asset SDK or cross-game schema.
"""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, cast

from demo_game_tools.input_formats.game_contract.asset_scale import (
    SubjectExtentAxis,
    calibrate_subject,
    measure_subject_extent,
    resolve_declared_magnitude,
    resolve_player_magnitude,
)
from iron_petal_unit_pipeline.audio import RunnerAudioContract
from iron_petal_unit_pipeline.audio.realizations import (
    GeneratedClipRealization,
    SpokenLineRealization,
)
from iron_petal_unit_pipeline.content import (
    RUNNER_BOSS_BASELINE_STATE,
    declared_boss_motion_states,
    declared_motion_states,
)
from iron_petal_unit_pipeline.fx.block import fx_manifest_block
from iron_petal_unit_pipeline.gameplay import (
    COLLISION_BOXES,
    DUCK_PROFILES,
    JUMP_PROFILES,
    SPEED_PROFILES,
    VITALS_PROFILES,
    RunnerGameplayContract,
)
from iron_petal_unit_pipeline.runner_types import (
    MANIFEST_KIND,
    MANIFEST_SCHEMA_VERSION,
    RUNNER_MANIFEST_BLOCK_VERSIONS,
)
from iron_petal_unit_pipeline.track import (
    STRUCTURAL_GROUND_CELL_PX,
    RunnerStructuralGround,
    validate_structural_ground_canonical,
    validate_structural_ground_seam_bridge,
)
from stage_gen.canonical import content_sha256
from stage_gen.components.sideview_actor.motion_geometry import DEFAULT_MOTION_ATLAS_GEOMETRY
from stage_gen.recipes.manifest_blocks import present_blocks

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from iron_petal_unit_pipeline.runner_request import ResolvedRunnerPackage
    from iron_petal_unit_pipeline.track import RunnerTrack

#: The one place the unit meets pixels in this recipe, matching the platformer's
#: projection so a shared avatar reads at the same magnitude in both genres.
RUNTIME_TILE_PX = 64


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


def build_manifest(
    resolved: ResolvedRunnerPackage,
    *,
    run_dir: Path,
    read_artifact: Callable[[str], bytes],
    structural_material_identity: Callable[[], str],
) -> dict[str, object]:
    """Project admitted game inputs and prepared media into this game's runtime document.

    Reading and validation belong here. The node handler owns reference publication,
    the final atomic write and execution bookkeeping. The material identity callback
    is evaluated only for structural ground, preserving the original admission path.
    """
    package = resolved.package
    runner = resolved.runner
    track = runner.track
    scale = package.game.scale

    def read_json(ref: str) -> dict[str, object]:
        return cast("dict[str, object]", json.loads((run_dir / ref).read_bytes()))

    rebase = read_json("avatar/rebase-verification.json")
    multipliers = manifest_rebase_multipliers(
        rebase, published_states=declared_motion_states(runner.avatar.avatar)
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
    run_atlas = (run_dir / "avatar/run.png").read_bytes()
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
        prop_data = (run_dir / f"catalog/props/{prop_entry.prop_id}.png").read_bytes()
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
        hover_atlas = (run_dir / f"{boss_dir}/{RUNNER_BOSS_BASELINE_STATE}.png").read_bytes()
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
        shot_data = (run_dir / shot_ref).read_bytes()
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
        item_data = (run_dir / f"catalog/items/{item_entry.item_id}.png").read_bytes()
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
        bridge_data = (run_dir / bridge_ref).read_bytes()
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
                (run_dir / image_ref).read_bytes(),
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
                raise ValueError(f"structural ground validation is stale for {chunk.segment_id}")
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
        if material_identities != {structural_material_identity()}:
            raise ValueError("structural ground chunks do not share the authored material")
        ground_manifest = manifest_ground(track)
        if ground_manifest["chunks"] != ground_chunks:
            raise ValueError("structural ground manifest projection drifted from validation")
    else:
        ground_manifest = manifest_ground(track)

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "game_id": package.game.game_id,
        "display_name": package.game.display_name,
        "track_id": track.track_id,
        "track_display_name": track.display_name,
        "package_sha256": package.package_sha256,
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
        "audio": manifest_audio(runner.audio, read_validation=read_artifact),
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
                read_validation=read_artifact,
                # The stage announces where the run is; the encounter
                # announces what has arrived. Both are display names the
                # package already holds.
                lettering={
                    "stage_start": (track.display_name, package.game.display_name),
                    **(
                        {}
                        if runner.gameplay.encounter is None or runner.bosses is None
                        else {
                            "encounter_start": (
                                runner.bosses.boss(runner.gameplay.encounter.boss_id).display_name,
                                track.display_name,
                            )
                        }
                    ),
                },
            )
        ),
    }
    manifest["blocks"] = present_blocks(RUNNER_MANIFEST_BLOCK_VERSIONS, manifest)
    return manifest
