#!/usr/bin/env python3
"""Build the brand-neutral local terrain topology-silhouette template."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
LOOKUP = ROOT / "src/stage_gen/resources/terrain/godot_3x3_minimal_lookup_v1.json"
OUTPUTS = (
    ROOT / "fixtures/image_gen_templates/terrain_atlas_12x4_template.png",
    ROOT / "src/stage_gen/resources/fixtures/image_gen_templates/terrain_atlas_12x4_template.png",
)
CANVAS = (1600, 900)
CELL = 124
GUIDE = 4
GRID_WIDTH = CELL * 12 + GUIDE * 13
GRID_HEIGHT = CELL * 4 + GUIDE * 5
ORIGIN = ((CANVAS[0] - GRID_WIDTH) // 2, (CANVAS[1] - GRID_HEIGHT) // 2)
MAGENTA = (255, 0, 255)
CYAN = (0, 255, 255)
FILL = (89, 86, 98)
CAP = (174, 184, 200)


def _mask_pixels(bits: str) -> Image.Image:
    """Create a neutral silhouette from peering bits without copying upstream pixels."""

    nw, n, ne, w, _, e, sw, s, se = (value == "1" for value in bits)
    mask = Image.new("L", (CELL, CELL), 0)
    draw = ImageDraw.Draw(mask)
    inset = 12
    radius = 10
    left = 0 if w else inset
    top = 0 if n else inset
    right = CELL if e else CELL - inset
    bottom = CELL if s else CELL - inset
    draw.rounded_rectangle((left, top, right - 1, bottom - 1), radius=radius, fill=255)
    middle = CELL // 2
    if n:
        draw.rectangle((middle - 20, 0, middle + 20, top + 20), fill=255)
    if e:
        draw.rectangle((right - 20, middle - 20, CELL - 1, middle + 20), fill=255)
    if s:
        draw.rectangle((middle - 20, bottom - 20, middle + 20, CELL - 1), fill=255)
    if w:
        draw.rectangle((0, middle - 20, left + 20, middle + 20), fill=255)
    corner_radius = 24
    for diagonal, px, py in (
        (nw, 0, 0),
        (ne, CELL - corner_radius, 0),
        (sw, 0, CELL - corner_radius),
        (se, CELL - corner_radius, CELL - corner_radius),
    ):
        if diagonal:
            draw.rectangle((px, py, px + corner_radius - 1, py + corner_radius - 1), fill=255)
    return mask


def build() -> Image.Image:
    payload = json.loads(LOOKUP.read_text(encoding="utf-8"))
    image = Image.new("RGB", CANVAS, MAGENTA)
    draw = ImageDraw.Draw(image)
    x0, y0 = ORIGIN
    for index in range(13):
        x = x0 + index * (CELL + GUIDE)
        draw.rectangle((x, y0, x + GUIDE - 1, y0 + GRID_HEIGHT - 1), fill=CYAN)
    for index in range(5):
        y = y0 + index * (CELL + GUIDE)
        draw.rectangle((x0, y, x0 + GRID_WIDTH - 1, y + GUIDE - 1), fill=CYAN)
    for bits, coordinate in payload["lookup"].items():
        column, row = coordinate
        cell = Image.new("RGB", (CELL, CELL), MAGENTA)
        mask = _mask_pixels(bits)
        material = Image.new("RGB", (CELL, CELL), FILL)
        material_draw = ImageDraw.Draw(material)
        if bits[1] == "0":
            material_draw.rectangle((0, 0, CELL - 1, 13), fill=CAP)
        cell.paste(material, mask=mask)
        left = x0 + GUIDE + column * (CELL + GUIDE)
        top = y0 + GUIDE + row * (CELL + GUIDE)
        image.paste(cell, (left, top))
    placeholder_column, placeholder_row = payload["placeholder_cell"]
    left = x0 + GUIDE + placeholder_column * (CELL + GUIDE)
    top = y0 + GUIDE + placeholder_row * (CELL + GUIDE)
    checker = Image.new("RGB", (CELL, CELL))
    checker_draw = ImageDraw.Draw(checker)
    block = 16
    for y in range(0, CELL, block):
        for x in range(0, CELL, block):
            color = (54, 57, 67) if (x // block + y // block) % 2 else (214, 218, 226)
            checker_draw.rectangle(
                (x, y, min(CELL - 1, x + block - 1), min(CELL - 1, y + block - 1)),
                fill=color,
            )
    image.paste(checker, (left, top))
    return image


def main() -> None:
    image = build()
    for output in OUTPUTS:
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output, format="PNG", optimize=False)
        print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
