#!/usr/bin/env python3
"""Render offline structural QA for the repository terrain-atlas implementation."""

from __future__ import annotations

import argparse
import json
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from stage_gen.recipes.scrolling_preview.terrain_atlas import (
    assemble_terrain_atlas,
    compose_canonical_terrain,
)

MAPS = {
    "solid-ground": ("1111111111", "1111111111", "1111111111", "1111111111"),
    "one-cell-floating": ("0000000000", "0111111110", "0000000000"),
    "stairs": ("0000000111", "0000011111", "0001111111", "0111111111"),
    "concavity-and-hole": (
        "0011111100",
        "0110000110",
        "1110110111",
        "1111111111",
    ),
}


def _opaque_material_fixture() -> bytes:
    image = Image.new("RGB", (1536, 1024), (132, 86, 50))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, image.width, 307), fill=(76, 142, 61))
    for x in range(0, image.width, 48):
        draw.rectangle((x, 0, x + 18, 307), fill=(94, 160, 72))
    for y in range(430, image.height, 52):
        draw.rectangle((0, y, image.width, y + 18), fill=(115, 72, 42))
    stream = BytesIO()
    image.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.output.mkdir(parents=True, exist_ok=True)
    material_source = _opaque_material_fixture()
    canonical, validation = assemble_terrain_atlas(material_source)
    (arguments.output / "material-source.png").write_bytes(material_source)
    (arguments.output / "canonical-atlas.png").write_bytes(canonical)
    map_reports: dict[str, object] = {}
    rendered: list[tuple[str, Image.Image]] = []
    for name, rows in MAPS.items():
        direct, direct_report = compose_canonical_terrain(canonical, rows)
        (arguments.output / f"{name}.direct.png").write_bytes(direct)
        map_reports[name] = direct_report
        with Image.open(BytesIO(direct)) as opened:
            rendered.append((name, opened.convert("RGBA")))
    width = 1180
    padding = 28
    label_height = 34
    scales = [min(1.0, (width - padding * 2) / image.width) for _, image in rendered]
    heights = [
        round(image.height * scale) + label_height + padding
        for (_, image), scale in zip(rendered, scales, strict=True)
    ]
    board = Image.new("RGB", (width, padding + sum(heights)), (19, 25, 35))
    draw = ImageDraw.Draw(board)
    y = padding
    for (name, image), scale, section_height in zip(rendered, scales, heights, strict=True):
        draw.text((padding, y), name.replace("-", " ").upper(), fill=(224, 232, 242))
        resized = image.resize(
            (round(image.width * scale), round(image.height * scale)),
            Image.Resampling.NEAREST,
        )
        checker = Image.new("RGB", resized.size, (49, 57, 69))
        checker_draw = ImageDraw.Draw(checker)
        for cy in range(0, checker.height, 16):
            for cx in range(0, checker.width, 16):
                if (cx // 16 + cy // 16) % 2:
                    checker_draw.rectangle((cx, cy, cx + 15, cy + 15), fill=(68, 77, 91))
        checker.paste(resized, mask=resized.getchannel("A"))
        board.paste(checker, (padding, y + label_height))
        y += section_height
    board.save(arguments.output / "terrain-atlas-structural-qa.png", format="PNG", optimize=False)
    report = {"atlas": validation, "maps": map_reports}
    (arguments.output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(arguments.output),
                "classification": validation["classification"],
                "maps": list(MAPS),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
