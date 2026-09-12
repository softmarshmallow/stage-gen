"""Shared player/tile scale policy over independent asset calibration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from demo_game_tools.input_formats.game_contract.package import PreparedScale
from stage_gen.components.sideview_actor.asset_unit import (
    ASSET_UNIT_ERROR_CODE,
    DOWNSCALE_WARN_RATIO,
    ENTITY_CONSISTENCY_FACTOR,
    PAINTED_ALPHA_THRESHOLD,
    AssetScale,
    AssetUnitError,
    ResolvedMagnitude,
    SubjectCalibration,
    SubjectExtentAxis,
    admit_entity_consistency,
    measure_subject_extent,
)
from stage_gen.components.sideview_actor.asset_unit import calibrate_subject as _calibrate
from stage_gen.components.sideview_actor.asset_unit import resolve_declared_magnitude as _resolve
from stage_gen.components.sideview_actor.asset_unit import sprite_scale as _sprite_scale

PLAYER_HEIGHT_UNITS = 1.0


def _asset_scale(scale: PreparedScale, tile_px: int = 1) -> AssetScale:
    return AssetScale(
        target_pixels_per_unit=scale.player_height_tiles * tile_px,
        minimum=scale.minimum,
        steps=scale.steps,
    )


def resolve_player_magnitude(declared: float | None) -> ResolvedMagnitude:
    if declared is not None:
        raise AssetUnitError(
            "the player defines the unit and must not declare height_units; a second authority "
            "for one measurement is the defect this contract prevents"
        )
    return ResolvedMagnitude(PLAYER_HEIGHT_UNITS, "definition")


def resolve_declared_magnitude(
    scale: PreparedScale, declared: float | None, *, subject: str
) -> ResolvedMagnitude:
    return _resolve(_asset_scale(scale), declared, subject=subject)


def calibrate_subject(
    *,
    magnitude: ResolvedMagnitude,
    subject_extent_px: int,
    measured_sha256: str,
    scale: PreparedScale,
    tile_px: int,
    subject: str,
    extent_axis: SubjectExtentAxis = "height",
) -> SubjectCalibration:
    return _calibrate(
        magnitude=magnitude,
        subject_extent_px=subject_extent_px,
        measured_sha256=measured_sha256,
        scale=_asset_scale(scale, tile_px),
        subject=subject,
        extent_axis=extent_axis,
    )


def sprite_scale(
    calibration: Mapping[str, object], *, player_height_tiles: float, tile_px: int
) -> float:
    return _sprite_scale(calibration, target_pixels_per_unit=player_height_tiles * tile_px)


def recovery_plate_steps(scale: PreparedScale) -> Sequence[float]:
    if not scale.steps:
        raise AssetUnitError("the game declares no [scale] steps to recover a magnitude from")
    return tuple(scale.steps)


__all__ = [
    "ASSET_UNIT_ERROR_CODE",
    "DOWNSCALE_WARN_RATIO",
    "ENTITY_CONSISTENCY_FACTOR",
    "PAINTED_ALPHA_THRESHOLD",
    "PLAYER_HEIGHT_UNITS",
    "AssetUnitError",
    "ResolvedMagnitude",
    "SubjectCalibration",
    "SubjectExtentAxis",
    "admit_entity_consistency",
    "calibrate_subject",
    "measure_subject_extent",
    "recovery_plate_steps",
    "resolve_declared_magnitude",
    "resolve_player_magnitude",
    "sprite_scale",
]
