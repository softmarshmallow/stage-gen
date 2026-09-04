"""Every PNG encoder in the tree, and the bytes each one produces today.

There are five, at two compression levels, and the level decides the bytes and
so the sha256 that cache lineage binds. Two pixel-identical images encoded on
different paths therefore hash differently. The consolidation into one codec
is planned and it is a deliberate re-bill; until then, this test makes any
change to any encoder's output a red diff rather than a surprise on a cold run.
"""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256

import pytest
from PIL import Image

from stage_gen.components.image_repeat.processing import _encode_png as image_repeat_encode
from stage_gen.components.painted_terrain.canonicalize import _png as painted_terrain_encode
from stage_gen.media.guide_lattice import png_bytes as guide_lattice_encode
from stage_gen.media.images import _encode_png as images_encode
from stage_gen.media.sprite_sheets import _png_bytes as sprite_sheets_encode

# PIL's default level and level 9 produce these two byte streams for the probe.
DEFAULT_LEVEL_SHA256 = "fd57af12582b11b93caf83df7b1a43f0168a7fb1459da28ca2086f830d196ede"
LEVEL_NINE_SHA256 = "54e28695df9e4548d2f2b74370cf42d482d5c75ab52f10e484b7063101a77701"


def _probe() -> Image.Image:
    image = Image.new("RGBA", (64, 48))
    pixels = image.load()
    assert pixels is not None
    for y in range(48):
        for x in range(64):
            pixels[x, y] = ((x * 4) % 256, (y * 5) % 256, (x * y) % 256, 255 if (x + y) % 7 else 0)
    return image


@pytest.mark.parametrize(
    ("encoder", "expected"),
    [
        pytest.param(guide_lattice_encode, DEFAULT_LEVEL_SHA256, id="media.guide_lattice"),
        pytest.param(sprite_sheets_encode, DEFAULT_LEVEL_SHA256, id="media.sprite_sheets"),
        pytest.param(painted_terrain_encode, DEFAULT_LEVEL_SHA256, id="painted_terrain"),
        pytest.param(images_encode, LEVEL_NINE_SHA256, id="media.images"),
        pytest.param(image_repeat_encode, LEVEL_NINE_SHA256, id="image_repeat"),
    ],
)
def test_each_encoder_produces_its_pinned_bytes(
    encoder: Callable[[Image.Image], bytes], expected: str
) -> None:
    assert sha256(encoder(_probe())).hexdigest() == expected
