"""Loop-construction dispatch in the scrolling recipe."""

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from stage_gen.components.sideview_layers.contract import resolve_layer_placement
from stage_gen.components.sideview_layers.pipeline import (
    assemble_loop,
    construct_deterministic,
    loop_conditioning,
    validate_provider_image,
)
from stage_gen.media import LOOP_METHODS, LoopConstruction
from stage_gen.media.layer_rasters import (
    seal_offset_fraction,
    top_seal_offset_fraction,
    trim_layer_to_alpha_box,
)


def _strip(width: int = 1536, height: int = 1024) -> bytes:
    """A production-shaped layer raster; the repaint constructions need the real window to fit."""

    image = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        level = round(y * 255 / (height - 1))
        draw.line([0, y, width - 1, y], fill=(level, 60, 255 - level, 255))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


@pytest.mark.parametrize("construction", sorted(LOOP_METHODS))
def test_every_registered_construction_has_a_dispatcher(construction: LoopConstruction) -> None:
    """The registry drives node kind, so an entry with no dispatcher ships and fails live.

    Without this, adding a construction to `LOOP_METHODS` and forgetting either dispatcher passes
    every other test: the graph builds, the node kind resolves correctly, and the failure only
    surfaces mid-run — for the assemble path, after the image operation has already been billed.
    """

    source = _strip()
    if LOOP_METHODS[construction].is_generative:
        conditioning = loop_conditioning(construction, source)
        assert conditioning.editable_span > 0
        # The stand-in return is the conditioning itself: enough to prove the assembler is wired
        # and the geometry closes, without asserting anything about provider quality.
        looped, record = assemble_loop(
            construction, source, conditioning.conditioning_png, conditioning=conditioning
        )
    else:
        looped, record = construct_deterministic(construction, source)
    assert record["kind"] == LOOP_METHODS[construction].version
    with Image.open(io.BytesIO(looped)) as opened:
        assert opened.width == record["period_width"]


def test_transparent_provider_admission_requires_meaningful_alpha() -> None:
    image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((4, 4, 27, 27), fill=(80, 140, 220, 1))
    stream = io.BytesIO()
    image.save(stream, format="PNG")

    with pytest.raises(ValueError, match="meaningful alpha"):
        validate_provider_image(stream.getvalue(), width=32, height=32, transparent=True)


class _Layer:
    def __init__(self, anchor: str, offset: float | None) -> None:
        self.layer_id = "band"
        self.vertical_anchor = anchor
        self.vertical_offset = offset


def _trim() -> dict[str, object]:
    """A band with a ragged upper fringe over a bar every column spans.

    Measured rather than hand-written, so these tests move with the measurement instead of
    encoding a second opinion about what the raster says.
    """

    source = Image.new("RGBA", (40, 100), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    for x in range(0, 40, 8):
        draw.rectangle((x, 10, x + 3, 19), fill=(40, 120, 60, 255))
    draw.rectangle((0, 20, 39, 59), fill=(40, 120, 60, 255))
    stream = io.BytesIO()
    source.save(stream, format="PNG")
    _trimmed, record = trim_layer_to_alpha_box(stream.getvalue())
    return record


def test_the_measured_top_seal_is_used_when_no_one_has_authored_one() -> None:
    resolved = resolve_layer_placement(_Layer("screen_top", None), _trim())
    assert resolved["vertical_offset_source"] == "measured"
    assert resolved["vertical_offset"] == top_seal_offset_fraction(_trim())


def test_an_author_may_place_a_top_layer_below_its_seal() -> None:
    """The top edge is not the mirror of the bottom edge.

    Sealing exists so a gap does not show whatever sits behind the layer. Every map declares
    exactly one opaque layer and the contract makes it canvas_cover, so a gap above a horizon
    reveals that full-bleed sky plate -- which is what belongs above a mountain. Holding the
    measurement as a floor here pushed the peaks and the castle off the top of the frame.
    """

    seal = top_seal_offset_fraction(_trim())
    assert seal is not None
    resolved = resolve_layer_placement(_Layer("screen_top", seal + 0.3), _trim())
    assert resolved["vertical_offset"] == seal + 0.3
    assert resolved["vertical_offset_source"] == "authored"
    # The measurement is still reported, so the composite records what was overridden.
    assert resolved["minimum_seal_offset"] == seal


def test_the_bottom_edge_keeps_its_floor() -> None:
    """There, a gap is a hole in the world rather than more sky."""

    seal = seal_offset_fraction(_trim())
    assert seal is not None
    with pytest.raises(ValueError, match="sealing requires at least"):
        resolve_layer_placement(_Layer("screen_bottom", seal - 0.1), _trim())
