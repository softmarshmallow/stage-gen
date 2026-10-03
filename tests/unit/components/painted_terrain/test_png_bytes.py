"""The painted terrain kit encodes PNGs at PIL's default level, like the product's media."""

from __future__ import annotations

from hashlib import sha256

from PIL import Image

from demo_game_tools.kits.painted_terrain.canonicalize import _png

# The product's media encoders pin the same bytes for this probe (tests/unit/media).
DEFAULT_LEVEL_SHA256 = "fd57af12582b11b93caf83df7b1a43f0168a7fb1459da28ca2086f830d196ede"


def test_the_painted_terrain_encoder_produces_the_default_level_bytes() -> None:
    image = Image.new("RGBA", (64, 48))
    pixels = image.load()
    assert pixels is not None
    for y in range(48):
        for x in range(64):
            pixels[x, y] = ((x * 4) % 256, (y * 5) % 256, (x * y) % 256, 255 if (x + y) % 7 else 0)
    assert sha256(_png(image)).hexdigest() == DEFAULT_LEVEL_SHA256
