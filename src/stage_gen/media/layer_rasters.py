"""Deterministic vertical reference frames for horizontally looping layer rasters.

A placement contract has to name *which* line it registers. Four frames are measurable on one
raster, and they are not interchangeable:

``source box``
    The full raster. This is the frame the layer was painted in, so it stays the scale datum
    even after empty rows are trimmed away.
``alpha box``
    Axis-aligned bounds of ``alpha >= alpha_threshold``. The conventional trim box.
``coverage line``
    The extreme scanline that *every* column still spans. Registering a ragged bottom edge by
    its deepest tip leaves the gaps between tips uncovered; registering by this line does not.
``opaque band``
    The same "every column" question asked at an opacity threshold rather than a meaningful-alpha
    threshold.

The last two are one family: ``any column`` gives the alpha box, ``all columns`` gives a coverage
line, and the threshold picks which of the two lines you get. Generated PNGs do not reliably reach
``alpha == 255``, so the opaque threshold is a declared part of the contract rather than a literal
opacity test.

Horizontal extent is deliberately never trimmed. A looping layer's width is its repeat period,
owned by the map's ``continuity.seamless_axis``, and cropping it would break the loop.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

LAYER_RASTER_BOUNDS_VERSION = "layer-raster-bounds-v1"
LAYER_VERTICAL_TRIM_VERSION = "layer-vertical-trim-v1"


@dataclass(frozen=True, slots=True)
class LayerRasterBoundsContract:
    """Declared thresholds for the vertical reference frames of one layer raster."""

    alpha_threshold: int = 16
    opaque_threshold: int = 240

    def __post_init__(self) -> None:
        if not 0 < self.alpha_threshold < 255:
            raise ValueError("layer alpha threshold must be between 1 and 254")
        if not 0 < self.opaque_threshold <= 255:
            raise ValueError("layer opaque threshold must be between 1 and 255")
        if self.opaque_threshold <= self.alpha_threshold:
            raise ValueError("layer opaque threshold must exceed the meaningful-alpha threshold")


def _row_span_counts(alpha: Image.Image, threshold: int, width: int, height: int) -> list[int]:
    """Return, for each row, how many columns hold at least ``threshold`` alpha."""

    mask = alpha.point(lambda value: 255 if value >= threshold else 0)
    raw = mask.tobytes()
    return [raw[row * width : (row + 1) * width].count(255) for row in range(height)]


def _full_span_extremes(counts: list[int], width: int) -> tuple[int | None, int | None]:
    rows = [row for row, count in enumerate(counts) if count == width]
    if not rows:
        return None, None
    return rows[0], rows[-1]


def measure_layer_raster_bounds(
    data: bytes,
    *,
    contract: LayerRasterBoundsContract | None = None,
) -> dict[str, object]:
    """Measure every declared vertical reference frame of one layer raster.

    Row coordinates are inclusive. ``None`` coverage or band lines mean no row is spanned by
    every column at that threshold, which is a meaningful answer rather than a failure.
    """

    policy = contract or LayerRasterBoundsContract()
    with Image.open(io.BytesIO(data)) as opened:
        source = opened.convert("RGBA")
        width, height = source.size
        alpha = source.getchannel("A")
    if width <= 0 or height <= 0:
        raise ValueError("layer raster must have positive dimensions")
    meaningful = alpha.point(lambda value: 255 if value >= policy.alpha_threshold else 0)
    box = meaningful.getbbox()
    if box is None:
        raise ValueError("layer raster holds no meaningful alpha")
    left, top, right_exclusive, bottom_exclusive = box
    alpha_counts = _row_span_counts(alpha, policy.alpha_threshold, width, height)
    opaque_counts = _row_span_counts(alpha, policy.opaque_threshold, width, height)
    coverage_top, coverage_bottom = _full_span_extremes(alpha_counts, width)
    band_top, band_bottom = _full_span_extremes(opaque_counts, width)
    return {
        "schema_version": 1,
        "kind": LAYER_RASTER_BOUNDS_VERSION,
        "alpha_threshold": policy.alpha_threshold,
        "opaque_threshold": policy.opaque_threshold,
        "source_width": width,
        "source_height": height,
        "alpha_box_left": left,
        "alpha_box_top": top,
        "alpha_box_right": right_exclusive - 1,
        "alpha_box_bottom": bottom_exclusive - 1,
        "full_coverage_top": coverage_top,
        "full_coverage_bottom": coverage_bottom,
        "opaque_band_top": band_top,
        "opaque_band_bottom": band_bottom,
    }


def _require_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"layer raster record field {label} must be an integer")
    return value


def trim_layer_to_alpha_box(
    data: bytes,
    *,
    contract: LayerRasterBoundsContract | None = None,
) -> tuple[bytes, dict[str, object]]:
    """Crop a layer raster to its alpha box vertically, preserving the full repeat period.

    The returned record keeps the untrimmed source height so consumers can recover the original
    painted frame, which remains the scale datum. Trimming an already tight raster is a no-op that
    still returns the same record shape.
    """

    policy = contract or LayerRasterBoundsContract()
    bounds = measure_layer_raster_bounds(data, contract=policy)
    top = _require_int(bounds["alpha_box_top"], "alpha_box_top")
    bottom = _require_int(bounds["alpha_box_bottom"], "alpha_box_bottom")
    width = _require_int(bounds["source_width"], "source_width")
    height = _require_int(bounds["source_height"], "source_height")
    with Image.open(io.BytesIO(data)) as opened:
        source = opened.convert("RGBA")
        cropped = source.crop((0, top, width, bottom + 1))
    stream = io.BytesIO()
    cropped.save(stream, format="PNG", optimize=False)
    record = {
        "schema_version": 1,
        "kind": LAYER_VERTICAL_TRIM_VERSION,
        "bounds": bounds,
        "trimmed_top": top,
        "trimmed_bottom": bottom,
        "trimmed_height": bottom - top + 1,
        "source_height": height,
        "removed_top_rows": top,
        "removed_bottom_rows": height - 1 - bottom,
    }
    return stream.getvalue(), record


def seal_offset_fraction(record: dict[str, object]) -> float | None:
    """Fraction of the trimmed height that must sit past a bottom anchor to leave no gap.

    A ragged bottom edge only seals once its highest gap — the full-coverage line — reaches the
    anchor datum. Returns ``None`` when no row is spanned by every column, because such a layer
    cannot seal at any offset.
    """

    bounds = record["bounds"]
    if not isinstance(bounds, dict):
        raise ValueError("layer trim record must carry its measured bounds")
    coverage_bottom = bounds.get("full_coverage_bottom")
    if coverage_bottom is None:
        return None
    coverage = _require_int(coverage_bottom, "full_coverage_bottom")
    trimmed_height = _require_int(record["trimmed_height"], "trimmed_height")
    trimmed_bottom = _require_int(record["trimmed_bottom"], "trimmed_bottom")
    if trimmed_height <= 0:
        raise ValueError("layer trim record must carry a positive trimmed height")
    return (trimmed_bottom - coverage) / trimmed_height
