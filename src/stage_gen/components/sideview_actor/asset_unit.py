"""Resolve, measure, and admit one package's magnitudes against the canonical player height.

Nothing an image model returns carries a size. A generated subject is normalized to fill its own
canvas, so its pixels encode aspect ratio and nothing else about how large the thing is: measuring
a subject against its untrimmed canvas measures the canvas. Magnitude is therefore authored - as a
multiple of the player - and measurement exists only to establish a consistent ruler for turning
that declaration into a draw scale.

    source_px_per_unit = subject_extent_px / height_units
    sprite_scale       = (player_height_tiles * tile_px) / source_px_per_unit

`sprite_scale` is uniform on both axes, always. Width and height are never set independently.

The contract is `docs/spec/asset-unit.md`. Cross-state coherence within one actor is a different
question, owned by `motion_rebase`, and the two compose multiplicatively.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Final, Literal

from PIL import Image

from stage_gen.components.game_contract.package import PreparedScale

ASSET_UNIT_SCHEMA_NAME: Final = "scrolling_preview_asset_unit_v1"
ASSET_UNIT_ERROR_CODE: Final = "scrolling-asset-unit-v1"

#: The player is the unit, by definition. Declaring a magnitude for it is an error rather than a
#: redundancy: two authorities for one measurement is the defect this contract exists to prevent.
PLAYER_HEIGHT_UNITS: Final = 1.0

#: Alpha above which a pixel counts as painted, matching the runtime's own threshold so a subject
#: is measured at the extent the consumer will draw.
PAINTED_ALPHA_THRESHOLD: Final = 64

#: How far a subject's own pixels-per-unit may sit from its entity's identity concept before the
#: pair is treated as disagreeing about what the subject is.
ENTITY_CONSISTENCY_FACTOR: Final = 4.0

#: Downscale beyond this is recorded as a diagnostic rather than refused: it is a sharpness
#: concern, not a correctness one.
DOWNSCALE_WARN_RATIO: Final = 6.0


class AssetUnitError(ValueError):
    """A subject's magnitude could not be resolved or admitted."""

    def __init__(self, message: str) -> None:
        super().__init__(f"{ASSET_UNIT_ERROR_CODE}: {message}")
        self.code = ASSET_UNIT_ERROR_CODE


#: Which painted dimension a declared magnitude describes.
SubjectExtentAxis = Literal["height", "width"]


@dataclass(frozen=True)
class ResolvedMagnitude:
    """One subject's declared magnitude and where the declaration came from."""

    height_units: float
    source: str


@dataclass(frozen=True)
class SubjectCalibration:
    """One subject's published calibration: what it declares, and what its artwork spent on it."""

    height_units: float
    height_units_source: str
    source_px_per_unit: float
    measured_sha256: str
    subject_extent_px: int
    downscale_ratio: float | None = None
    #: Which axis `subject_extent_px` was measured along, and therefore which axis the declared
    #: magnitude describes. Published only when it is not the default, so every record written
    #: before a family needed a second axis is byte-identical to what it was.
    extent_axis: SubjectExtentAxis = "height"

    def as_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "height_units": round(self.height_units, 2),
            "height_units_source": self.height_units_source,
            "source_px_per_unit": round(self.source_px_per_unit, 3),
            "measured_sha256": self.measured_sha256,
            "subject_extent_px": self.subject_extent_px,
        }
        if self.downscale_ratio is not None:
            record["downscale_ratio"] = round(self.downscale_ratio, 3)
        if self.extent_axis != "height":
            record["extent_axis"] = self.extent_axis
        return record


def resolve_player_magnitude(declared: float | None) -> ResolvedMagnitude:
    """The player is `1.0`. Stating it is an error, because the unit is defined by it."""

    if declared is not None:
        raise AssetUnitError(
            "the player defines the unit and must not declare height_units; a second authority "
            "for one measurement is the defect this contract prevents"
        )
    return ResolvedMagnitude(PLAYER_HEIGHT_UNITS, "definition")


def resolve_declared_magnitude(
    scale: PreparedScale,
    declared: float | None,
    *,
    subject: str,
) -> ResolvedMagnitude:
    """Resolve one authored declaration, or fall back to the smallest legible step."""

    if declared is not None:
        if declared < scale.minimum:
            raise AssetUnitError(
                f"{subject} declares {declared} units, below the package floor {scale.minimum}; "
                "a subject smaller than the floor is not a readable target"
            )
        return ResolvedMagnitude(declared, "authored")
    inherited = _nearest_step_at_or_above(scale, scale.minimum)
    return ResolvedMagnitude(inherited, "inherited")


def _nearest_step_at_or_above(scale: PreparedScale, floor: float) -> float:
    for step in scale.steps:
        if step >= floor:
            return step
    return floor


def measure_subject_extent(
    artifact: bytes, *, subject: str, axis: SubjectExtentAxis = "height"
) -> int:
    """The subject's painted extent along one axis, in its own source pixels.

    Measurement runs on the trimmed subject. A subject measured against its untrimmed canvas
    measures the canvas, because generated artwork is normalized to fill its frame.

    Height for every family that stands still, because that is the dimension a declared magnitude
    means for a character, a creature, a prop, or a dropped item. Width for a projectile, and only
    for a projectile: it is drawn lying along its own travel axis, so its height is how *thick* it
    is, and a dart declared 0.5 units tall would be several player-heights long. The axis is
    published alongside the measurement so a consumer never has to infer it.
    """

    try:
        with Image.open(BytesIO(artifact)) as opened:
            image = opened.convert("RGBA")
    except OSError as error:  # pragma: no cover - Pillow raises subclasses per decode fault
        raise AssetUnitError(f"{subject} is not a decodable image") from error
    mask = image.getchannel("A").point(lambda value: 255 if value > PAINTED_ALPHA_THRESHOLD else 0)
    box = mask.getbbox()
    if box is None:
        raise AssetUnitError(f"{subject} has no painted pixels above the alpha threshold")
    return box[2] - box[0] if axis == "width" else box[3] - box[1]


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
    """Turn one declaration plus one measurement into a published calibration record."""

    if subject_extent_px <= 0:
        raise AssetUnitError(f"{subject} measured a non-positive extent")
    if magnitude.height_units <= 0:
        raise AssetUnitError(f"{subject} resolved a non-positive magnitude")
    source_px_per_unit = subject_extent_px / magnitude.height_units
    target_px = scale.player_height_tiles * tile_px * magnitude.height_units
    downscale_ratio = subject_extent_px / target_px if target_px > 0 else None
    return SubjectCalibration(
        height_units=magnitude.height_units,
        height_units_source=magnitude.source,
        source_px_per_unit=source_px_per_unit,
        measured_sha256=measured_sha256,
        subject_extent_px=subject_extent_px,
        downscale_ratio=downscale_ratio,
        extent_axis=extent_axis,
    )


def sprite_scale(
    calibration: Mapping[str, object], *, player_height_tiles: float, tile_px: int
) -> float:
    """The one projection from the unit onto the screen, applied uniformly on both axes."""

    source_px_per_unit = calibration.get("source_px_per_unit")
    if not isinstance(source_px_per_unit, (int, float)) or source_px_per_unit <= 0:
        raise AssetUnitError("calibration carries no usable source_px_per_unit")
    return (player_height_tiles * tile_px) / float(source_px_per_unit)


def admit_entity_consistency(
    *,
    subject: str,
    subject_px_per_unit: float,
    concept_px_per_unit: float,
) -> None:
    """A subject and its own identity concept must agree about what they depict."""

    if subject_px_per_unit <= 0 or concept_px_per_unit <= 0:
        raise AssetUnitError(f"{subject} cannot be compared against its concept")
    ratio = max(subject_px_per_unit, concept_px_per_unit) / min(
        subject_px_per_unit, concept_px_per_unit
    )
    if ratio > ENTITY_CONSISTENCY_FACTOR:
        raise AssetUnitError(
            f"{subject} spends {subject_px_per_unit:.1f} px per unit against its concept's "
            f"{concept_px_per_unit:.1f}, a factor of {ratio:.1f}"
        )


def recovery_plate_steps(scale: PreparedScale) -> Sequence[float]:
    """The ladder a vision model chooses from when a magnitude was never declared.

    The recovered value is a *proposed* declaration, subject to review, and it is selected as an
    index rather than estimated as a number: the model performs recognition, not measurement.
    """

    if not scale.steps:
        raise AssetUnitError("the game declares no [scale] steps to recover a magnitude from")
    return tuple(scale.steps)
