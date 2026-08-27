from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from stage_gen.media import (
    LayerRasterBoundsContract,
    measure_layer_raster_bounds,
    seal_offset_fraction,
    trim_layer_to_alpha_box,
)


def _png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _ragged_strip() -> Image.Image:
    """A looping strip whose bottom edge is ragged, like near-camera foliage."""

    source = Image.new("RGBA", (40, 100), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    # Solid band every column spans.
    draw.rectangle((0, 60, 39, 79), fill=(40, 120, 60, 255))
    # Tips that reach lower in only some columns.
    for x in range(0, 40, 8):
        draw.rectangle((x, 80, x + 3, 89), fill=(40, 120, 60, 255))
    return source


def test_alpha_box_bounds_the_any_column_question() -> None:
    bounds = measure_layer_raster_bounds(_png(_ragged_strip()))

    assert bounds["kind"] == "layer-raster-bounds-v1"
    assert bounds["source_height"] == 100
    assert bounds["alpha_box_top"] == 60
    # The deepest tip, not the line every column spans.
    assert bounds["alpha_box_bottom"] == 89
    # Width is never trimmed: the repeat period is owned by the loop contract.
    assert bounds["alpha_box_left"] == 0
    assert bounds["alpha_box_right"] == 39


def test_coverage_line_bounds_the_all_columns_question() -> None:
    bounds = measure_layer_raster_bounds(_png(_ragged_strip()))

    assert bounds["full_coverage_top"] == 60
    # The highest gap between tips, which is where a bottom anchor must seal.
    assert bounds["full_coverage_bottom"] == 79


def test_opaque_band_asks_the_same_question_at_the_opacity_threshold() -> None:
    source = _ragged_strip()
    # A soft upper edge is meaningful alpha but not opaque.
    ImageDraw.Draw(source).rectangle((0, 55, 39, 59), fill=(40, 120, 60, 90))

    bounds = measure_layer_raster_bounds(_png(source))

    assert bounds["full_coverage_top"] == 55
    assert bounds["opaque_band_top"] == 60
    assert bounds["opaque_band_bottom"] == 79


def test_trim_removes_empty_rows_and_preserves_the_repeat_period() -> None:
    trimmed, record = trim_layer_to_alpha_box(_png(_ragged_strip()))

    with Image.open(io.BytesIO(trimmed)) as opened:
        assert opened.size == (40, 30)
    assert record["kind"] == "layer-vertical-trim-v1"
    assert record["trimmed_height"] == 30
    # The painted frame is retained because it stays the scale datum.
    assert record["source_height"] == 100
    assert record["removed_top_rows"] == 60
    assert record["removed_bottom_rows"] == 10


def test_trimming_an_already_tight_raster_is_a_no_op() -> None:
    opaque = Image.new("RGBA", (40, 24), (10, 20, 30, 255))

    trimmed, record = trim_layer_to_alpha_box(_png(opaque))

    with Image.open(io.BytesIO(trimmed)) as opened:
        assert opened.size == (40, 24)
    assert record["removed_top_rows"] == 0
    assert record["removed_bottom_rows"] == 0
    assert seal_offset_fraction(record) == 0.0


def test_seal_offset_is_the_fraction_below_the_coverage_line() -> None:
    _trimmed, record = trim_layer_to_alpha_box(_png(_ragged_strip()))

    # Trimmed rows 60..89; the coverage line is 79, so ten of thirty rows must be buried.
    assert seal_offset_fraction(record) == pytest.approx(10 / 30)


def test_a_layer_no_column_spans_cannot_seal() -> None:
    source = Image.new("RGBA", (40, 100), (0, 0, 0, 0))
    ImageDraw.Draw(source).rectangle((0, 20, 19, 39), fill=(40, 120, 60, 255))

    _trimmed, record = trim_layer_to_alpha_box(_png(source))

    assert seal_offset_fraction(record) is None


def test_fully_transparent_raster_is_rejected() -> None:
    empty = Image.new("RGBA", (16, 16), (0, 0, 0, 0))

    with pytest.raises(ValueError, match="no meaningful alpha"):
        measure_layer_raster_bounds(_png(empty))


def test_opaque_threshold_must_exceed_the_meaningful_alpha_threshold() -> None:
    with pytest.raises(ValueError, match="must exceed"):
        LayerRasterBoundsContract(alpha_threshold=240, opaque_threshold=240)
