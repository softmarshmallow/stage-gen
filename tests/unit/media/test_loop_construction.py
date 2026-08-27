from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from stage_gen.media import (
    assemble_generated_bridge,
    build_bridge_conditioning,
    mirror_repeat,
    tile_to_width,
)


def _png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _gradient(width: int = 64, height: int = 16) -> Image.Image:
    """A strip whose two ends are unrelated, so it does not loop on its own."""

    source = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(source)
    for x in range(width):
        draw.line([x, 0, x, height], fill=(x * 4 % 256, 40, 200 - x, 255))
    return source


def _column(data: bytes, x: int) -> list[tuple[int, ...]]:
    with Image.open(io.BytesIO(data)) as opened:
        image = opened.convert("RGBA")
    return [image.getpixel((x, y)) for y in range(image.height)]  # type: ignore[misc]


def test_mirror_repeat_makes_the_wrap_a_reflection() -> None:
    source = _gradient()

    looped, record = mirror_repeat(_png(source))

    assert record["kind"] == "mirror-repeat-v1"
    assert record["period_width"] == 128
    assert record["provider_operations"] == 0
    # The wrap join is a reflection, so the last column repeats the first exactly.
    assert _column(looped, 127) == _column(looped, 0)


def test_mirror_repeat_keeps_the_source_recoverable() -> None:
    source = _gradient()

    looped, _record = mirror_repeat(_png(source))

    with Image.open(io.BytesIO(looped)) as opened:
        assert opened.convert("RGBA").crop((0, 0, 64, 16)).tobytes() == source.tobytes()


def test_bridge_conditioning_shows_the_provider_the_real_neighbours() -> None:
    source = _gradient()

    conditioning = build_bridge_conditioning(_png(source), context_span=16, bridge_span=8)

    assert conditioning.width == 40
    with Image.open(io.BytesIO(conditioning.conditioning_png)) as opened:
        canvas = opened.convert("RGBA")
    # Left context is the source tail; right context is the source head.
    assert canvas.crop((0, 0, 16, 16)).tobytes() == source.crop((48, 0, 64, 16)).tobytes()
    assert canvas.crop((24, 0, 40, 16)).tobytes() == source.crop((0, 0, 16, 16)).tobytes()
    with Image.open(io.BytesIO(conditioning.mask_png)) as opened:
        mask = opened.convert("RGBA")
    # Transparent marks the editable span; everything else is opaque.
    assert mask.getpixel((20, 8))[3] == 0  # type: ignore[index]
    assert mask.getpixel((4, 8))[3] == 255  # type: ignore[index]


def test_generated_bridge_anchors_both_joins_exactly() -> None:
    source = _gradient()
    conditioning = build_bridge_conditioning(_png(source), context_span=16, bridge_span=8)
    # A provider that ignores the mask entirely and returns unrelated pixels.
    hostile = _png(Image.new("RGBA", (conditioning.width, conditioning.height), (255, 0, 255, 255)))

    looped, record = assemble_generated_bridge(
        _png(source), hostile, conditioning=conditioning, anchor_band=4
    )

    assert record["kind"] == "generated-bridge-v1"
    assert record["period_width"] == 72
    assert record["provider_owns_alpha"] is True
    # Anchoring forces both joins regardless of what the provider returned.
    assert _column(looped, 64) == _column(looped, 63)
    assert _column(looped, 71) == _column(looped, 0)


def test_generated_bridge_discards_the_provider_context_regions() -> None:
    source = _gradient()
    conditioning = build_bridge_conditioning(_png(source), context_span=16, bridge_span=8)
    hostile = _png(Image.new("RGBA", (conditioning.width, conditioning.height), (255, 0, 255, 255)))

    looped, _record = assemble_generated_bridge(
        _png(source), hostile, conditioning=conditioning, anchor_band=4
    )

    # The source survives byte-for-byte: only the bridge span is taken from the return.
    with Image.open(io.BytesIO(looped)) as opened:
        assert opened.convert("RGBA").crop((0, 0, 64, 16)).tobytes() == source.tobytes()


def test_generated_bridge_normalizes_a_missized_provider_return() -> None:
    source = _gradient()
    conditioning = build_bridge_conditioning(_png(source), context_span=16, bridge_span=8)
    oversized = _png(Image.new("RGBA", (80, 32), (10, 200, 10, 255)))

    looped, record = assemble_generated_bridge(
        _png(source), oversized, conditioning=conditioning, anchor_band=2
    )

    assert record["period_width"] == 72
    assert _column(looped, 71) == _column(looped, 0)


def test_tile_to_width_repeats_a_short_period() -> None:
    source = _gradient(width=16)

    tiled = tile_to_width(_png(source), 40)

    with Image.open(io.BytesIO(tiled)) as opened:
        image = opened.convert("RGBA")
    assert image.width == 40
    assert image.crop((16, 0, 32, 16)).tobytes() == source.tobytes()


def test_bridge_conditioning_rejects_an_oversized_context() -> None:
    with pytest.raises(ValueError, match="context span"):
        build_bridge_conditioning(_png(_gradient(width=16)), context_span=32, bridge_span=8)
