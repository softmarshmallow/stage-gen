"""Derive the packaged tileset wireframe from the canonical 12x4 role topology.

The wireframe is the layout prior handed to the image provider for the whole-sheet tileset
path. Deriving it from `tileset_alpha_mask` keeps the picture the model is shown identical to
the mask the validator enforces; an independently drawn wireframe silently disagreed with the
contract on eleven of sixteen roles and made the sheet path unsatisfiable.

Material synthesis binds this file by digest only (`geometry_usage: identity-only`), so the
bytes are an authority: regenerate with this script and update the pinned constants together.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import cast

from PIL import Image, ImageDraw

_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPOSITORY_ROOT / "src"))

from stage_gen.recipes.scrolling_preview.raster_contracts import (  # noqa: E402
    GridContract,
    grid_semantic_role,
    tileset_alpha_mask,
)
from stage_gen.reliability import atomic_write_bytes  # noqa: E402

WIDTH = 2400
HEIGHT = 800
ROWS = 4
COLUMNS = 12
GUTTER = 2

# Named RGB classes bound by `validate_tileset_wireframe`.
LAYOUT_SEPARATOR = (26, 26, 26)
SURFACE_COVER = (40, 180, 60)
UNDERGROUND_FILL = (60, 60, 60)
STRATEGY_BACKGROUND = (255, 0, 255)

# Roles that present an exposed walking surface, so the crown marks where cover belongs.
_SURFACE_KEYS = ("top", "slope", "platform")

DESTINATIONS = (
    _REPOSITORY_ROOT / "fixtures/image_gen_templates/wireframe.png",
    _REPOSITORY_ROOT / "src/stage_gen/resources/fixtures/image_gen_templates/wireframe.png",
)


def build_wireframe() -> bytes:
    """Return the deterministic wireframe PNG for the canonical tileset topology."""

    contract = GridContract(rows=ROWS, columns=COLUMNS, gutter=GUTTER, topology="tileset")
    mask = tileset_alpha_mask(WIDTH, HEIGHT, contract)
    cell_width, cell_height = WIDTH // COLUMNS, HEIGHT // ROWS

    image = Image.new("RGB", (WIDTH, HEIGHT), STRATEGY_BACKGROUND)
    image.paste(Image.new("RGB", (WIDTH, HEIGHT), UNDERGROUND_FILL), (0, 0), mask)

    draw = ImageDraw.Draw(image)
    crown = max(6, cell_height // 12)
    solid = mask.convert("L")
    for row in range(ROWS):
        for column in range(COLUMNS):
            if not any(key in grid_semantic_role(contract, row, column) for key in _SURFACE_KEYS):
                continue
            left, top = column * cell_width, row * cell_height
            for x in range(left, left + cell_width):
                exposed = next(
                    (
                        y
                        for y in range(top, top + cell_height)
                        if cast(int, solid.getpixel((x, y))) > 127
                    ),
                    None,
                )
                if exposed is None:
                    continue
                draw.line(
                    (x, exposed, x, min(top + cell_height - 1, exposed + crown - 1)),
                    fill=SURFACE_COVER,
                )

    # Separators sit inside the inter-cell gutter, so they never overwrite role geometry.
    for column in range(1, COLUMNS):
        x = column * cell_width
        draw.rectangle((x - 1, 0, x, HEIGHT - 1), fill=LAYOUT_SEPARATOR)
    for row in range(1, ROWS):
        y = row * cell_height
        draw.rectangle((0, y - 1, WIDTH - 1, y), fill=LAYOUT_SEPARATOR)
    draw.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), outline=LAYOUT_SEPARATOR, width=1)

    buffer = BytesIO()
    image.save(buffer, format="PNG", compress_level=9, optimize=False)
    return buffer.getvalue()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check or regenerate both canonical tileset wireframe copies."
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="atomically replace each canonical copy; default is read-only verification",
    )
    args = parser.parse_args(argv)
    data = build_wireframe()
    mismatches = [
        destination
        for destination in DESTINATIONS
        if not destination.is_file() or destination.read_bytes() != data
    ]
    if not args.write:
        if mismatches:
            for destination in mismatches:
                print(f"stale {destination.relative_to(_REPOSITORY_ROOT)}")
            return 1
        print(f"verified {len(DESTINATIONS)} wireframe copies ({len(data)} bytes each)")
        return 0

    for destination in DESTINATIONS:
        atomic_write_bytes(destination, data)
        print(f"wrote {destination.relative_to(_REPOSITORY_ROOT)} ({len(data)} bytes)")
    if any(destination.read_bytes() != data for destination in DESTINATIONS):
        raise RuntimeError("canonical tileset wireframe copies diverged after regeneration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
