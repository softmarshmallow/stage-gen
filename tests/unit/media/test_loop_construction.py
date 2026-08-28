from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from stage_gen.media import (
    LOOP_METHODS,
    LoopConstruction,
    RegistrationError,
    SeamConditioning,
    assemble_fold_repaint,
    assemble_generated_bridge,
    assemble_seam_repaint,
    build_bridge_conditioning,
    build_fold_repaint_conditioning,
    build_seam_repaint_conditioning,
    measure_registration,
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


def _textured(width: int = 64, height: int = 128) -> Image.Image:
    """A strip that varies down the column as well as across it, without repeating.

    Registration measures a *vertical* translation, so two fixture properties matter. Columns that
    are constant make the offset unidentifiable outright. Columns that are merely *periodic* make
    it ambiguous, which is worse to debug: the estimator confidently returns a shift one period
    away from the truth. The monotonic ramp below is aperiodic over the full height, so exactly
    one offset explains the return.
    """

    source = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(source)
    for y in range(height):
        level = round(y * 255 / max(height - 1, 1))
        draw.line([0, y, width - 1, y], fill=(level, 40, 255 - level, 255))
    for x in range(0, width, 7):
        draw.line([x, 0, x, height], fill=(20, 220, 20, 255))
    draw.rectangle([0, height // 3, width - 1, height // 3 + 2], fill=(255, 255, 255, 255))
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

    conditioning = build_bridge_conditioning(_png(source), context_span=16, editable_span=8)

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
    conditioning = build_bridge_conditioning(_png(source), context_span=16, editable_span=8)
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
    conditioning = build_bridge_conditioning(_png(source), context_span=16, editable_span=8)
    hostile = _png(Image.new("RGBA", (conditioning.width, conditioning.height), (255, 0, 255, 255)))

    looped, _record = assemble_generated_bridge(
        _png(source), hostile, conditioning=conditioning, anchor_band=4
    )

    # The source survives byte-for-byte: only the bridge span is taken from the return.
    with Image.open(io.BytesIO(looped)) as opened:
        assert opened.convert("RGBA").crop((0, 0, 64, 16)).tobytes() == source.tobytes()


def test_generated_bridge_normalizes_a_missized_provider_return() -> None:
    source = _gradient()
    conditioning = build_bridge_conditioning(_png(source), context_span=16, editable_span=8)
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
        build_bridge_conditioning(_png(_gradient(width=16)), context_span=32, editable_span=8)


def _returned(conditioning: SeamConditioning, *, shift: int = 0) -> bytes:
    """A stand-in provider return: the conditioning repainted, optionally displaced vertically.

    Real returns are never byte-identical, so a fixture that hands back the exact input would
    exercise a path production never takes. Displacing it is the behaviour that actually matters:
    the endpoint re-registers whatever canvas it is given.
    """

    with Image.open(io.BytesIO(conditioning.conditioning_png)) as opened:
        sent = opened.convert("RGBA")
    canvas = Image.new("RGBA", sent.size, (0, 0, 0, 0))
    canvas.paste(sent, (0, shift))
    draw = ImageDraw.Draw(canvas)
    start = conditioning.context_span
    draw.rectangle(
        [start, 0, start + conditioning.editable_span - 1, sent.height - 1],
        fill=(90, 160, 90, 255),
    )
    return _png(canvas)


@pytest.mark.parametrize(
    ("construction", "guarantee", "mutates_source", "is_generative"),
    [
        ("mirror_repeat", "reflection", False, False),
        ("generated_bridge", "anchored", False, True),
        ("seam_repaint", "interior", True, True),
        ("fold_repaint", "reflection", True, True),
    ],
)
def test_registry_declares_each_construction(
    construction: LoopConstruction, guarantee: str, mutates_source: bool, is_generative: bool
) -> None:
    """The registry is what the graph and the docs both read, so it is worth pinning exactly."""

    method = LOOP_METHODS[construction]
    assert method.guarantee == guarantee
    assert method.mutates_source is mutates_source
    assert method.is_generative is is_generative
    assert method.identity()["version"] == method.version


@pytest.mark.parametrize(
    ("construction", "expected"),
    [
        ("mirror_repeat", 128),
        ("generated_bridge", 64 + 8),
        ("seam_repaint", 64),
        ("fold_repaint", 128),
    ],
)
def test_period_arithmetic_matches_the_construction(
    construction: LoopConstruction, expected: int
) -> None:
    assert LOOP_METHODS[construction].period_of(64, span=8) == expected


def test_seam_repaint_leaves_the_period_unchanged_and_closes_the_wrap() -> None:
    """The repainted span straddles the wrap, so its halves land at both ends of the source."""

    source = _gradient(width=64)
    conditioning = build_seam_repaint_conditioning(_png(source), window_span=32, repaint_span=8)

    looped, record = assemble_seam_repaint(
        _png(source), _returned(conditioning), conditioning=conditioning, anchor_band=2
    )

    assert record["kind"] == "seam-repaint-v1"
    assert record["guarantee"] == "interior"
    assert record["mutates_source"] is True
    # No growth: this is the only construction whose period equals the source width.
    assert record["period_width"] == source.width
    with Image.open(io.BytesIO(looped)) as opened:
        assert opened.size == source.size


def test_seam_repaint_writes_the_span_to_both_ends_of_the_source() -> None:
    source = _gradient(width=64)
    conditioning = build_seam_repaint_conditioning(_png(source), window_span=32, repaint_span=8)

    looped, _ = assemble_seam_repaint(
        _png(source), _returned(conditioning), conditioning=conditioning, anchor_band=1
    )

    # Half the span belongs to the tail and half to the head; the middle of each is untouched by
    # anchoring, so it carries the provider's fill.
    assert _column(looped, 62)[0][:3] == (90, 160, 90)
    assert _column(looped, 1)[0][:3] == (90, 160, 90)
    # Content a full span away from the wrap is not the provider's to change.
    assert _column(looped, 32) == _column(_png(source), 32)


def test_fold_repaint_keeps_the_untouched_wrap_fold_exact() -> None:
    """Repainting the reflection axis must not disturb the join the loop actually depends on."""

    source = _gradient(width=64)
    conditioning = build_fold_repaint_conditioning(_png(source), window_span=32, repaint_span=8)

    looped, record = assemble_fold_repaint(
        _png(source), _returned(conditioning), conditioning=conditioning, anchor_band=2
    )

    assert record["kind"] == "fold-repaint-v1"
    assert record["guarantee"] == "reflection"
    assert record["period_width"] == 128
    # The wrap fold is still a reflection, so the last column repeats the first exactly.
    assert _column(looped, 127) == _column(looped, 0)


def test_registration_recovers_an_injected_vertical_shift() -> None:
    """The two context bands are the instrument; a known displacement must come back measured."""

    # Search is kept small relative to the height, as it is in production: a search window that
    # approaches the image height leaves too little overlap for a residual to mean anything.
    source = _textured(width=64, height=128)
    conditioning = build_bridge_conditioning(_png(source), context_span=16, editable_span=8)

    registration = measure_registration(
        conditioning, _returned(conditioning, shift=5), search_px=16
    )

    assert registration.vertical_offset == 5
    assert registration.left_offset == registration.right_offset == 5


def test_registration_rejects_a_return_the_bands_disagree_about() -> None:
    """Disagreement means a fresh composition, not a displaced copy, so nothing can land it."""

    source = _textured(width=64, height=128)
    conditioning = build_bridge_conditioning(_png(source), context_span=16, editable_span=8)
    with Image.open(io.BytesIO(conditioning.conditioning_png)) as opened:
        sent = opened.convert("RGBA")
    canvas = Image.new("RGBA", sent.size, (0, 0, 0, 0))
    # Displace only the left band. No single translation explains both sides.
    canvas.paste(sent.crop((0, 0, 16, sent.height)), (0, 12))
    canvas.paste(sent.crop((16, 0, sent.width, sent.height)), (16, 0))

    with pytest.raises(RegistrationError, match="disagree"):
        measure_registration(conditioning, _png(canvas), search_px=16)


def test_seam_repaint_rejects_a_span_whose_halves_would_overlap() -> None:
    """The two halves land at opposite ends, so together they must not exceed the source width.

    Comparing one half against the whole width lets an overlapping span through, and the second
    paste then silently overwrites part of the first rather than failing.
    """

    source = _gradient(width=64)
    conditioning = build_seam_repaint_conditioning(_png(source), window_span=112, repaint_span=80)
    assert conditioning.editable_span // 2 < source.width  # the old guard would have passed

    with pytest.raises(ValueError, match="must not exceed the source width"):
        assemble_seam_repaint(
            _png(source), _returned(conditioning), conditioning=conditioning, anchor_band=2
        )
