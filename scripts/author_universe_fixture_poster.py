#!/usr/bin/env python3
"""Draw the fixture poster for the universe recipe's committed test package.

The universe recipe reads a poster as visual evidence and art grammar - palette,
shape language, staging - and never as world fact. Its committed package
therefore needs a poster whose bytes are stable, whose rights basis is this
repository, and whose content no reviewer has to judge, so the fixture is drawn
from fixed constants here rather than generated.

The Lantern Ferry is a river crossing between two shores, worked by crews who
read the water by lantern light. The field states that and nothing else: two
banks, the water between them, one ferry on it, one lantern hung high enough to
light both sides. Flat bands and hard edges keep every colour and every shape
nameable, which is the only thing a reader is meant to take from it.

This is a fixture, not art. It calls no provider, reads no clock, and draws no
random number, so two runs on one Pillow produce identical bytes.

    uv run python scripts/author_universe_fixture_poster.py
    uv run python scripts/author_universe_fixture_poster.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import io
from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw

_Color = tuple[int, int, int]
_Point = tuple[int, int]

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
POSTER_PATH: Final = REPOSITORY_ROOT / "library/games/lantern_ferry/references/poster.png"

WIDTH: Final = 768
HEIGHT: Final = 1024

# The three horizontal datums every other constant is measured from: the far
# bank meets the water at the horizon, the near bank climbs out of it, and the
# ferry rides between the two.
HORIZON_Y: Final = 470
WATERLINE_Y: Final = 744
NEAR_BANK_Y: Final = 936

# Dusk in flat steps rather than a ramp, so the palette can be read off as a
# short list of colours instead of sampled out of a gradient.
SKY_BANDS: Final[tuple[tuple[int, _Color], ...]] = (
    (118, (16, 20, 40)),
    (214, (28, 32, 58)),
    (298, (46, 46, 78)),
    (368, (78, 62, 92)),
    (424, (126, 84, 88)),
    (HORIZON_Y, (176, 116, 82)),
)

WATER_BANDS: Final[tuple[tuple[int, _Color], ...]] = (
    (618, (46, 76, 96)),
    (798, (32, 58, 78)),
    (HEIGHT, (20, 40, 58)),
)

LANTERN_CENTER: Final[_Point] = (556, 214)
LANTERN_RADIUS: Final = 84
LANTERN_CORE_RADIUS: Final = 46
LANTERN_HALOS: Final[tuple[tuple[int, int, _Color], ...]] = (
    (112, 4, (196, 138, 88)),
    (146, 3, (142, 100, 82)),
    (186, 2, (104, 76, 78)),
)
LANTERN_AMBER: Final[_Color] = (240, 186, 96)
LANTERN_CORE: Final[_Color] = (252, 232, 176)

FAR_SHORE: Final[tuple[_Point, ...]] = (
    (0, HORIZON_Y),
    (0, 438),
    (86, 404),
    (168, 430),
    (258, 396),
    (352, 428),
    (430, 410),
    (520, 436),
    (612, 402),
    (700, 430),
    (768, 414),
    (768, HORIZON_Y),
)
FAR_SHORE_COLOR: Final[_Color] = (26, 30, 52)

NEAR_SHORE: Final[tuple[_Point, ...]] = (
    (0, HEIGHT),
    (0, 966),
    (118, 946),
    (252, 970),
    (392, 942),
    (540, 966),
    (668, NEAR_BANK_Y),
    (768, 960),
    (768, HEIGHT),
)
NEAR_SHORE_COLOR: Final[_Color] = (10, 13, 24)

# Two mooring posts and the rail between them: the landing, said in rectangles.
LANDING_POSTS: Final[tuple[tuple[int, int, int, int], ...]] = (
    (92, 872, 106, 962),
    (138, 898, 150, 966),
    (92, 884, 150, 892),
)

HULL: Final[tuple[_Point, ...]] = (
    (180, WATERLINE_Y),
    (452, WATERLINE_Y),
    (424, 792),
    (208, 792),
)
HULL_COLOR: Final[_Color] = (12, 16, 28)
HULL_LIT_BAND: Final[tuple[int, int, int, int]] = (180, WATERLINE_Y, 452, 754)
HULL_LIT_COLOR: Final[_Color] = (150, 96, 66)
# The stern post is raked and its base sits under the deck line, so the hull
# drawn over it reads as one solid form rather than two touching shapes.
PROW: Final[tuple[_Point, ...]] = (
    (446, 752),
    (470, 700),
    (482, 704),
    (464, 752),
)
MAST: Final[tuple[int, int, int, int]] = (300, 622, 312, WATERLINE_Y)
YARD: Final[tuple[int, int, int, int]] = (262, 650, 350, 658)
BOAT_LANTERN_CENTER: Final[_Point] = (306, 610)
BOAT_LANTERN_RADIUS: Final = 13
BOAT_LANTERN_CORE_RADIUS: Final = 6

WAKE: Final[tuple[tuple[int, int, int], ...]] = ((804, 196, 442), (822, 224, 410))
WATER_LINES: Final[tuple[tuple[int, int, int], ...]] = (
    (520, 60, 300),
    (556, 470, 700),
    (604, 96, 264),
    (652, 520, 690),
    (700, 130, 380),
    (742, 560, 720),
    (838, 80, 260),
    (884, 470, 640),
)
WATER_LINE_COLOR: Final[_Color] = (64, 100, 116)
WATER_LINE_WIDTH: Final = 4

# The reflection is the poster's one vertical: a broken amber column under the
# lantern, widening and narrowing on a fixed cycle so it reads as water.
REFLECTION_TOP: Final = HORIZON_Y + 14
REFLECTION_BOTTOM: Final = 918
REFLECTION_STEP: Final = 22
REFLECTION_HEIGHT: Final = 7
REFLECTION_HALF_WIDTHS: Final = (48, 31, 39, 22, 44, 27, 35, 20)
REFLECTION_NEAR: Final[_Color] = (236, 178, 96)
REFLECTION_FAR: Final[_Color] = (58, 84, 96)
HORIZON_GLARE: Final[tuple[int, int, int, int]] = (466, HORIZON_Y, 646, 478)
HORIZON_GLARE_COLOR: Final[_Color] = (244, 198, 128)

BORDER_INSET: Final = 28
BORDER_WIDTH: Final = 3
BORDER_COLOR: Final[_Color] = (168, 122, 78)

MAXIMUM_BYTES: Final = 512 * 1024


def _mix(near: _Color, far: _Color, fraction: float) -> _Color:
    """Return ``near`` carried ``fraction`` of the way toward ``far``."""
    return (
        round(near[0] + (far[0] - near[0]) * fraction),
        round(near[1] + (far[1] - near[1]) * fraction),
        round(near[2] + (far[2] - near[2]) * fraction),
    )


def _draw_bands(draw: ImageDraw.ImageDraw, top: int, bands: tuple[tuple[int, _Color], ...]) -> None:
    for bottom, color in bands:
        draw.rectangle((0, top, WIDTH, bottom), fill=color)
        top = bottom


def _draw_disc(draw: ImageDraw.ImageDraw, center: _Point, radius: int, color: _Color) -> None:
    x, y = center
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)


def _draw_ring(
    draw: ImageDraw.ImageDraw, center: _Point, radius: int, width: int, color: _Color
) -> None:
    x, y = center
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=color, width=width)


def _draw_lantern(draw: ImageDraw.ImageDraw) -> None:
    for radius, width, color in LANTERN_HALOS:
        _draw_ring(draw, LANTERN_CENTER, radius, width, color)
    _draw_disc(draw, LANTERN_CENTER, LANTERN_RADIUS, LANTERN_AMBER)
    _draw_disc(draw, LANTERN_CENTER, LANTERN_CORE_RADIUS, LANTERN_CORE)


def _draw_reflection(draw: ImageDraw.ImageDraw) -> None:
    x = LANTERN_CENTER[0]
    tops = range(REFLECTION_TOP, REFLECTION_BOTTOM, REFLECTION_STEP)
    last = len(tops) - 1
    for index, top in enumerate(tops):
        half = REFLECTION_HALF_WIDTHS[index % len(REFLECTION_HALF_WIDTHS)]
        color = _mix(REFLECTION_NEAR, REFLECTION_FAR, index / last)
        draw.rectangle((x - half, top, x + half, top + REFLECTION_HEIGHT), fill=color)


def _draw_ferry(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle(MAST, fill=HULL_COLOR)
    draw.rectangle(YARD, fill=HULL_COLOR)
    draw.polygon(PROW, fill=HULL_COLOR)
    draw.polygon(HULL, fill=HULL_COLOR)
    draw.rectangle(HULL_LIT_BAND, fill=HULL_LIT_COLOR)
    _draw_disc(draw, BOAT_LANTERN_CENTER, BOAT_LANTERN_RADIUS, LANTERN_AMBER)
    _draw_disc(draw, BOAT_LANTERN_CENTER, BOAT_LANTERN_CORE_RADIUS, LANTERN_CORE)


def render_poster() -> Image.Image:
    """Return the poster field, drawn back to front from fixed constants."""
    canvas = Image.new("RGB", (WIDTH, HEIGHT), SKY_BANDS[0][1])
    draw = ImageDraw.Draw(canvas)

    _draw_bands(draw, 0, SKY_BANDS)
    _draw_lantern(draw)
    draw.polygon(FAR_SHORE, fill=FAR_SHORE_COLOR)
    _draw_bands(draw, HORIZON_Y, WATER_BANDS)
    draw.rectangle(HORIZON_GLARE, fill=HORIZON_GLARE_COLOR)
    _draw_reflection(draw)
    for y, start, end in WATER_LINES:
        draw.line(((start, y), (end, y)), fill=WATER_LINE_COLOR, width=WATER_LINE_WIDTH)
    _draw_ferry(draw)
    for y, start, end in WAKE:
        draw.line(((start, y), (end, y)), fill=WATER_LINE_COLOR, width=WATER_LINE_WIDTH)
    draw.polygon(NEAR_SHORE, fill=NEAR_SHORE_COLOR)
    for post in LANDING_POSTS:
        draw.rectangle(post, fill=NEAR_SHORE_COLOR)

    draw.rectangle(
        (BORDER_INSET, BORDER_INSET, WIDTH - 1 - BORDER_INSET, HEIGHT - 1 - BORDER_INSET),
        outline=BORDER_COLOR,
        width=BORDER_WIDTH,
    )
    return canvas


def encode_png(image: Image.Image) -> bytes:
    """Encode ``image`` to PNG bytes without touching the tree, so --check is read-only."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def decoded_pixels(path: Path) -> bytes:
    """Return the committed image's pixels, which survive an encoder change."""
    with Image.open(path) as opened:
        return opened.convert("RGB").tobytes()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=POSTER_PATH)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report whether the committed poster still matches a fresh render",
    )
    args = parser.parse_args(argv)
    output: Path = args.output

    poster = render_poster()
    encoded = encode_png(poster)

    if args.check:
        if not output.is_file():
            print(f"poster-check: no poster at {output}")
            return 1
        # Pixels rather than bytes: a Pillow encoder change must not read as a
        # changed poster.
        if decoded_pixels(output) != poster.tobytes():
            print(f"poster-check: {output} does not match a fresh render")
            return 1
        committed = output.read_bytes()
        digest = hashlib.sha256(committed).hexdigest()
        print(f"poster-check: ok {output} ({len(committed)} bytes, sha256 {digest})")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded)
    digest = hashlib.sha256(encoded).hexdigest()
    print(f"wrote {output} ({poster.width}x{poster.height}, {len(encoded)} bytes)")
    print(f"sha256 {digest}")
    if len(encoded) > MAXIMUM_BYTES:
        print(f"poster is {len(encoded)} bytes, over the {MAXIMUM_BYTES} byte fixture ceiling")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
