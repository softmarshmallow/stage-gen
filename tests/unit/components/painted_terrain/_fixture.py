"""One synthetic map and one synthetic painting, shared by every painted-terrain test.

The painting matters more than it looks. Every threshold in this family is a claim about
what real art does, so the tests need a mask that is *plausibly* organic -- a silhouette
that wanders in and out of its authored blocks and rounds its corners -- rather than a
rectangle or a field of noise. It is generated deterministically from a blurred occupancy
ramp cut with a low-frequency value-noise threshold, which is the cheapest thing that
wobbles coherently.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from stage_gen.components.painted_terrain import (
    PAINTED_TERRAIN_CELL_PX,
    PaintedTerrainSegment,
    build_painted_terrain_guide,
    painted_terrain_guide_layout,
    painted_terrain_material_identity,
)

#: A flat three-row bank under two floating one-tile decks with a one-tile hop gap between
#: them: the smallest grid carrying every case this family reasons about -- a walking
#: surface, a deck end exposed on two sides at once, a gap the player jumps through, and
#: the air a deck hangs in.
#:
#: The decks sit TWO rows above the bank rather than one, which is the difference between a
#: grid that can express a support and one that cannot: a single empty row under a deck can
#: only ever be a thick underside, so a fixture with one would let the anti-pillar rule pass
#: its tests without ever being the rule that fired.
OCCUPANCY: tuple[str, ...] = (
    "0000000000000000",
    "0000000000000000",
    "0011110111100000",
    "0000000000000000",
    "0000000000000000",
    "1111111111111111",
    "1111111111111111",
    "1111111111111111",
)

MATERIAL_IDENTITY = painted_terrain_material_identity(
    prompt="warm cream paving over old roots",
    visual_direction_sha256="a" * 64,
    reference_sha256=["b" * 64],
)


def material_reference() -> bytes:
    """A two-tone plate, so the derived palette has a real cap and fill to separate."""

    image = Image.new("RGBA", (64, 64), (196, 176, 128, 255))
    ImageDraw.Draw(image).rectangle((0, 32, 63, 63), fill=(78, 84, 56, 255))
    return _png(image)


def segment(index: int = 0, start_column: int = 0, columns: int = 16) -> PaintedTerrainSegment:
    return PaintedTerrainSegment(index=index, start_column=start_column, columns=columns)


def guide(seg: PaintedTerrainSegment | None = None) -> bytes:
    data, _ = build_painted_terrain_guide(
        OCCUPANCY,
        seg or segment(),
        material_identity=MATERIAL_IDENTITY,
        material_references=[material_reference()],
    )
    return data


def organic_alpha(
    seg: PaintedTerrainSegment | None = None,
    *,
    amplitude: int = 90,
    blur: int = 8,
    seed: int = 0xBEEF,
) -> Image.Image:
    """A wobbled silhouette of the guide, on the provider canvas."""

    seg = seg or segment()
    source = Image.open(BytesIO(guide(seg))).convert("RGBA")
    width, height = source.size
    ramp = source.getchannel("A").filter(ImageFilter.GaussianBlur(blur))
    threshold = _value_noise(width, height, seed).point(
        lambda value: int(128 + amplitude * (value - 128) / 128)
    )
    # ``ramp >= threshold``, as a channel operation: subtract clamps at zero, so the
    # offset of one is what keeps an exact tie on the solid side of the cut.
    return ImageChops.subtract(ramp, threshold, offset=1).point(lambda value: 255 if value else 0)


def painting(alpha: Image.Image, *, tint: tuple[int, int, int] = (150, 118, 84)) -> bytes:
    """Paint an alpha in a colour far from the guide's palette, so residue stays zero."""

    art = Image.new("RGBA", alpha.size, (*tint, 255))
    art.putalpha(alpha)
    return _png(art)


def full_plate(alpha_or_painting: Image.Image, seg: PaintedTerrainSegment) -> Image.Image:
    """Crop a provider canvas to the segment's published window, at full map height."""

    layout = painted_terrain_guide_layout(OCCUPANCY, seg)
    window = alpha_or_painting.crop(layout.central_box)
    plate = Image.new(
        window.mode,
        (seg.columns * PAINTED_TERRAIN_CELL_PX, len(OCCUPANCY) * PAINTED_TERRAIN_CELL_PX),
        0 if window.mode == "L" else (0, 0, 0, 0),
    )
    plate.paste(window, (0, layout.window_top_row * PAINTED_TERRAIN_CELL_PX))
    return plate


def cell_box(seg: PaintedTerrainSegment, row: int, column: int) -> tuple[int, int, int, int]:
    return painted_terrain_guide_layout(OCCUPANCY, seg).cell_box(column, row)


def _value_noise(width: int, height: int, seed: int, cells: int = 24) -> Image.Image:
    small = Image.new("L", (width // cells + 2, height // cells + 2))
    pixels = small.load()
    assert pixels is not None
    for y in range(small.height):
        for x in range(small.width):
            value = (seed ^ (x * 0x45D9F3B) ^ (y * 0x119DE1F3)) & 0xFFFFFFFF
            value ^= value >> 16
            pixels[x, y] = value % 256
    return small.resize((width, height), Image.Resampling.BICUBIC)


def _png(image: Image.Image) -> bytes:
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()
