"""Deterministic composition of one comparison plate from artifacts that have already shipped.

A plate answers a question a bounding box cannot: is this the same subject, drawn at the same
scale, as the one beside it? Alpha extent conflates pose with draw scale - a crouch is shorter
because of the pose and a mis-scaled sheet is shorter because of the artwork - so the reading is
taken by a vision model, and this module's job is to give that model an image where the answer is
visible.

Two properties make that possible, and both are structural rather than cosmetic:

* **One uniform source scale across every frame.** Nothing is normalised, fit, or padded to a
  common height. A group the model drew small must look small, because that difference is the
  entire signal. Refitting each group to a common height would erase the thing being measured.
* **A shared ground line per group, and the baseline's crown drawn across all of them.** A ratio
  is only readable against a reference the model can see in the same image.

The plate is not a fiducial. A reference composited into a *generation* is redrawn by the provider
and carries no ground truth; a plate assembled locally from bytes that have already shipped is
exact, costs no provider operation, and cannot be redrawn.

This module is provider-neutral and knows nothing about actors, states, or games. Callers supply
labelled groups of frames; the recipe that owns the vocabulary decides what a group means.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Final

from PIL import Image, ImageDraw, ImageFont

from gnode import sha256_hex

COMPARISON_PLATE_SCHEMA_NAME: Final = "comparison_plate_v1"
COMPARISON_PLATE_ERROR_CODE: Final = "comparison-plate-v1"

#: Alpha above which a pixel counts as painted, matching the runtime's own threshold so a plate
#: measures the subject the consumer draws.
PAINTED_ALPHA_THRESHOLD: Final = 64

#: Largest drawn height the tallest frame may take. One uniform scale still applies to every
#: frame - that invariant is the whole point - and the scale is chosen to spend as much of the
#: pixel budget as the plate can, because the judge is being asked to read head mass and line
#: weight rather than a printed number. An actor whose states are drawn at wildly different
#: canvas sizes therefore fills the plate instead of collapsing the baseline to a few pixels.
TALLEST_TARGET_PX: Final = 420

#: Never shrink past this: below it the comparison stops being legible and the plate should be
#: split into tiles with the baseline repeated in each instead.
MINIMUM_TALLEST_PX: Final = 90

#: Refuse to compose a plate so large that the model reads it downscaled past legibility.
MAXIMUM_PLATE_PIXELS: Final = 4_000_000

_PAGE: Final = (250, 248, 245)
_PANEL: Final = (240, 236, 229)
_BASELINE_PANEL: Final = (233, 240, 236)
_INK: Final = (26, 24, 22)
_MUTED: Final = (124, 117, 108)
_GROUND: Final = (158, 149, 136)
_CROWN: Final = (11, 125, 92)
_BASELINE_MARK: Final = (11, 125, 92)


class ComparisonPlateError(ValueError):
    """A plate could not be composed from the frames it was given."""

    def __init__(self, message: str) -> None:
        super().__init__(f"{COMPARISON_PLATE_ERROR_CODE}: {message}")
        self.code = COMPARISON_PLATE_ERROR_CODE


@dataclass(frozen=True)
class PlateGroup:
    """One labelled group of frames that share a generation canvas, and so share one scale.

    `prescale` pre-multiplies this group before the plate's uniform scale. It exists for
    verification plates: a caller that has already judged one multiplier per group composes the
    plate with those multipliers applied, so the judge sees the *result* of the correction and
    reads only the residual. On a first-pass judging plate it stays `1.0` for every group,
    which is the uniform-source-scale invariant unchanged.
    """

    key: str
    frames: tuple[bytes, ...]
    baseline: bool = False
    prescale: float = 1.0


@dataclass(frozen=True)
class PlateFrameRecord:
    """What one frame contributed, so a caller can bind the plate to its sources."""

    group_key: str
    frame_index: int
    sha256: str
    trimmed_width: int
    trimmed_height: int
    drawn_height: int
    baseline_percent: float


@dataclass(frozen=True)
class ComparisonPlate:
    """One composed plate and the exact lineage it was composited from."""

    png: bytes
    sha256: str
    width: int
    height: int
    uniform_scale: float
    baseline_key: str
    baseline_drawn_height: int
    frames: tuple[PlateFrameRecord, ...]

    @property
    def group_keys(self) -> tuple[str, ...]:
        seen: list[str] = []
        for frame in self.frames:
            if frame.group_key not in seen:
                seen.append(frame.group_key)
        return tuple(seen)


def _decode_trimmed(data: bytes, *, label: str) -> Image.Image:
    """Decode one frame and crop it to the pixels the runtime would treat as painted."""
    try:
        with Image.open(BytesIO(data)) as opened:
            frame = opened.convert("RGBA")
    except OSError as error:  # pragma: no cover - Pillow raises subclasses for every decode fault
        raise ComparisonPlateError(f"{label} is not a decodable image") from error
    mask = frame.getchannel("A").point(lambda value: 255 if value > PAINTED_ALPHA_THRESHOLD else 0)
    box = mask.getbbox()
    if box is None:
        raise ComparisonPlateError(f"{label} has no painted pixels above the alpha threshold")
    return frame.crop(box)


def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Pillow's bundled face only.

    A plate's digest binds it to the reading taken from it, so composition must not depend on
    which fonts happen to be installed on the machine that ran the recipe.
    """
    return ImageFont.load_default(size)


_HEADING_HEIGHT: Final = 22
_LABEL_HEIGHT: Final = 18
_PADDING: Final = 18
_GAP_X: Final = 26
_GAP_Y: Final = 20


@dataclass(frozen=True)
class _PlateLayout:
    """Every derived dimension of one candidate plate at one uniform scale."""

    width: int
    height: int
    cell_width: int
    band_height: int
    group_width: int
    group_height: int
    groups_per_row: int
    baseline_drawn_height: int


def _plate_layout(
    trimmed: Mapping[str, list[Image.Image]],
    prescales: Mapping[str, float],
    baseline_key: str,
    uniform_scale: float,
) -> _PlateLayout:
    def height_of(key: str, frame: Image.Image) -> int:
        return max(1, round(frame.height * uniform_scale * prescales[key]))

    baseline_drawn_height = max(height_of(baseline_key, frame) for frame in trimmed[baseline_key])
    tallest = max(height_of(key, frame) for key, frames in trimmed.items() for frame in frames)
    widest = max(
        max(1, round(frame.width * uniform_scale * prescales[key]))
        for key, frames in trimmed.items()
        for frame in frames
    )
    most_frames = max(len(frames) for frames in trimmed.values())
    cell_width = widest + 14
    # The crown rule is drawn inside every panel, so a group whose frames all collapse still
    # needs a band tall enough to carry the baseline's height.
    band_height = max(tallest, baseline_drawn_height) + 12
    group_width = most_frames * cell_width
    group_height = _HEADING_HEIGHT + band_height + _LABEL_HEIGHT
    groups_per_row = _near_square_columns(len(trimmed), group_width + _GAP_X, group_height + _GAP_Y)
    rows = (len(trimmed) + groups_per_row - 1) // groups_per_row
    return _PlateLayout(
        width=_PADDING * 2 + groups_per_row * group_width + (groups_per_row - 1) * _GAP_X,
        height=_PADDING * 2 + rows * group_height + (rows - 1) * _GAP_Y,
        cell_width=cell_width,
        band_height=band_height,
        group_width=group_width,
        group_height=group_height,
        groups_per_row=groups_per_row,
        baseline_drawn_height=baseline_drawn_height,
    )


def _near_square_columns(count: int, cell_width: int, cell_height: int) -> int:
    """Columns that bring one grid of `count` cells closest to a square overall aspect."""

    best, best_penalty = 1, float("inf")
    for columns in range(1, count + 1):
        rows = (count + columns - 1) // columns
        aspect = (columns * cell_width) / (rows * cell_height)
        penalty = max(aspect, 1 / aspect)
        if penalty < best_penalty:
            best, best_penalty = columns, penalty
    return best


def compose_comparison_plate(groups: Sequence[PlateGroup]) -> ComparisonPlate:
    """Compose one plate carrying every frame of every group at one uniform source scale."""
    if not groups:
        raise ComparisonPlateError("a plate needs at least one group")
    baselines = [group for group in groups if group.baseline]
    if len(baselines) != 1:
        raise ComparisonPlateError(
            f"a plate needs exactly one baseline group, got {len(baselines)}"
        )
    keys = [group.key for group in groups]
    if len(set(keys)) != len(keys):
        raise ComparisonPlateError("group keys must be unique on a plate")
    for group in groups:
        if not group.frames:
            raise ComparisonPlateError(f"group {group.key!r} carries no frames")
        if not math.isfinite(group.prescale) or group.prescale <= 0:
            raise ComparisonPlateError(
                f"group {group.key!r} has prescale {group.prescale!r}; it must be a positive "
                "finite factor"
            )

    trimmed: dict[str, list[Image.Image]] = {}
    for group in groups:
        trimmed[group.key] = [
            _decode_trimmed(frame, label=f"{group.key} frame {index}")
            for index, frame in enumerate(group.frames)
        ]
    prescales = {group.key: group.prescale for group in groups}

    baseline = baselines[0]
    tallest_source = max(
        frame.height * prescales[key] for key, frames in trimmed.items() for frame in frames
    )
    # Spend the budget: start at the most legible scale and step down only as far as the pixel
    # ceiling forces, so a plate is never smaller than it needs to be.
    target = TALLEST_TARGET_PX
    while True:
        uniform_scale = target / tallest_source
        layout = _plate_layout(trimmed, prescales, baseline.key, uniform_scale)
        if layout.width * layout.height <= MAXIMUM_PLATE_PIXELS:
            break
        shrink = (MAXIMUM_PLATE_PIXELS / (layout.width * layout.height)) ** 0.5
        target = int(target * min(shrink, 0.95))
        if target < MINIMUM_TALLEST_PX:
            raise ComparisonPlateError(
                f"these groups cannot be composed above {MINIMUM_TALLEST_PX}px within the "
                f"{MAXIMUM_PLATE_PIXELS} pixel ceiling; split them across tiles and repeat the "
                "baseline in each"
            )

    def drawn(key: str, frame: Image.Image) -> tuple[int, int]:
        effective = uniform_scale * prescales[key]
        return (
            max(1, round(frame.width * effective)),
            max(1, round(frame.height * effective)),
        )

    baseline_drawn_height = layout.baseline_drawn_height
    label_font = _font(13)
    heading_font = _font(15)
    cell_width = layout.cell_width
    heading_height = _HEADING_HEIGHT
    group_width = layout.group_width
    group_height = layout.group_height
    band_height = layout.band_height
    groups_per_row = layout.groups_per_row
    padding, gap_x, gap_y = _PADDING, _GAP_X, _GAP_Y
    width, height = layout.width, layout.height

    canvas = Image.new("RGB", (width, height), _PAGE)
    draw = ImageDraw.Draw(canvas)
    records: list[PlateFrameRecord] = []

    for position, group in enumerate(groups):
        column = position % groups_per_row
        row = position // groups_per_row
        x0 = padding + column * (group_width + gap_x)
        y0 = padding + row * (group_height + gap_y)
        heading = f"{group.key}  (baseline)" if group.baseline else group.key
        draw.text((x0, y0), heading, fill=_INK, font=heading_font)
        band_top = y0 + heading_height
        ground_y = band_top + band_height
        draw.rectangle(
            (x0, band_top, x0 + group_width, ground_y),
            fill=_BASELINE_PANEL if group.baseline else _PANEL,
        )
        crown_y = ground_y - baseline_drawn_height
        for dash_x in range(x0, x0 + group_width, 12):
            draw.line(((dash_x, crown_y), (dash_x + 6, crown_y)), fill=_CROWN, width=1)
        draw.line(((x0, ground_y), (x0 + group_width, ground_y)), fill=_GROUND, width=1)
        if group.baseline:
            draw.rectangle((x0, band_top, x0 + 3, ground_y), fill=_BASELINE_MARK)
        for index, frame in enumerate(trimmed[group.key]):
            frame_width, frame_height = drawn(group.key, frame)
            resized = frame.resize((frame_width, frame_height), Image.Resampling.LANCZOS)
            frame_x = x0 + index * cell_width + (cell_width - frame_width) // 2
            canvas.paste(resized, (frame_x, ground_y - frame_height), resized)
            percent = round(frame_height / baseline_drawn_height * 100, 1)
            draw.text(
                (x0 + index * cell_width + 4, ground_y + 3),
                f"{group.key[:12]} f{index}  {percent:.0f}%",
                fill=_MUTED,
                font=label_font,
            )
            records.append(
                PlateFrameRecord(
                    group_key=group.key,
                    frame_index=index,
                    sha256=sha256_hex(group.frames[index]),
                    trimmed_width=frame.width,
                    trimmed_height=frame.height,
                    drawn_height=frame_height,
                    baseline_percent=percent,
                )
            )

    stream = BytesIO()
    canvas.save(stream, format="PNG", compress_level=9, optimize=False)
    png = stream.getvalue()
    return ComparisonPlate(
        png=png,
        sha256=sha256_hex(png),
        width=width,
        height=height,
        uniform_scale=uniform_scale,
        baseline_key=baseline.key,
        baseline_drawn_height=baseline_drawn_height,
        frames=tuple(records),
    )


#: Two groups belong on different bands when the taller one's source frames exceed the shorter's
#: by this factor. One uniform scale across such a pair costs the smaller group most of its
#: resolution, and resolution is what the judge is being asked to read.
BAND_RATIO: Final = 2.0


@dataclass(frozen=True)
class BandedComparisonPlate:
    """One image carrying several independently scaled bands, each repeating the baseline.

    A single uniform scale across every group is ideal, and it is what one band gives. It stops
    being ideal the moment one group's artwork dwarfs the rest: the shared scale then collapses
    every other group, including the baseline they are all judged against. Splitting into bands
    keeps the invariant where it matters - uniform *within* a comparison - and repeats the
    baseline in each so ratios stay readable across bands. Bands that never shared a baseline
    would drift against each other, which reintroduces the original defect one level up.
    """

    png: bytes
    sha256: str
    width: int
    height: int
    bands: tuple[ComparisonPlate, ...]

    @property
    def frames(self) -> tuple[PlateFrameRecord, ...]:
        return tuple(frame for band in self.bands for frame in band.frames)

    @property
    def group_keys(self) -> tuple[str, ...]:
        seen: list[str] = []
        for band in self.bands:
            for key in band.group_keys:
                if key not in seen:
                    seen.append(key)
        return tuple(seen)


def band_groups(
    groups: Sequence[PlateGroup],
    *,
    band_ratio: float = BAND_RATIO,
) -> list[list[PlateGroup]]:
    """Partition groups so each band's source frames sit within `band_ratio` of one another."""

    baselines = [group for group in groups if group.baseline]
    if len(baselines) != 1:
        raise ComparisonPlateError(
            f"a plate needs exactly one baseline group, got {len(baselines)}"
        )
    baseline = baselines[0]

    def tallest(group: PlateGroup) -> float:
        # Effective height, prescale included: bands exist to protect legibility of what will
        # actually be drawn, and a group already corrected close to its neighbours belongs on
        # their band even when its raw canvas does not.
        return group.prescale * max(
            _decode_trimmed(frame, label=f"{group.key} frame {index}").height
            for index, frame in enumerate(group.frames)
        )

    others = sorted((g for g in groups if not g.baseline), key=tallest)
    if not others:
        return [[baseline]]
    bands: list[list[PlateGroup]] = []
    current: list[PlateGroup] = []
    floor = 0.0
    for group in others:
        height = tallest(group)
        if current and height > floor * band_ratio:
            bands.append(current)
            current, floor = [], 0.0
        if not current:
            floor = height
        current.append(group)
    if current:
        bands.append(current)
    # The baseline leads every band: a band judged without it has nothing to be a ratio against.
    return [[baseline, *band] for band in bands]


def compose_banded_comparison_plate(
    groups: Sequence[PlateGroup],
    *,
    band_ratio: float = BAND_RATIO,
) -> BandedComparisonPlate:
    """Compose one plate whose bands are each internally uniform-scaled."""

    bands = [compose_comparison_plate(band) for band in band_groups(groups, band_ratio=band_ratio)]
    gap = 26
    width = max(band.width for band in bands)
    height = sum(band.height for band in bands) + gap * (len(bands) - 1)
    canvas = Image.new("RGB", (width, height), _PAGE)
    draw = ImageDraw.Draw(canvas)
    y = 0
    for index, band in enumerate(bands):
        with Image.open(BytesIO(band.png)) as opened:
            canvas.paste(opened.convert("RGB"), (0, y))
        y += band.height
        if index < len(bands) - 1:
            draw.rectangle((0, y, width, y + gap), fill=_PANEL)
            draw.line(((0, y + gap // 2), (width, y + gap // 2)), fill=_GROUND, width=1)
            y += gap
    stream = BytesIO()
    canvas.save(stream, format="PNG", compress_level=9, optimize=False)
    png = stream.getvalue()
    return BandedComparisonPlate(
        png=png,
        sha256=sha256_hex(png),
        width=width,
        height=height,
        bands=tuple(bands),
    )
