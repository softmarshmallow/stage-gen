"""Loop-construction dispatch in the scrolling recipe."""

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from stage_gen.components.sideview_layers.pipeline import (
    assemble_loop,
    construct_deterministic,
    loop_conditioning,
)
from stage_gen.media import LOOP_METHODS, LoopConstruction


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
