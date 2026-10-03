"""Write original geometric example layers and their inputs; no provider or artwork download.

``uv run python make_inputs.py out/looping-parallax-input`` draws two layers there and an
``inputs.yaml`` that places them, for ``gnode run looping-parallax --inputs <dir>/inputs.yaml``.
"""

import argparse
from pathlib import Path

import yaml
from PIL import Image, ImageDraw


def write_layers(target: Path) -> None:
    """Draw the two example layers into ``target``."""
    target.mkdir(parents=True, exist_ok=True)
    hills = Image.new("RGBA", (320, 360), "#c5e2df")
    draw = ImageDraw.Draw(hills)
    draw.ellipse((45, 38, 107, 100), fill="#fff2ba")
    draw.polygon(
        [(0, 245), (60, 150), (150, 245), (246, 172), (320, 245), (320, 360), (0, 360)],
        fill="#719e9a",
    )
    hills.save(target / "distant_hills.png")
    trees = Image.new("RGBA", (320, 360))
    draw = ImageDraw.Draw(trees)
    draw.rectangle((0, 321, 320, 360), fill="#204b49")
    for x, y in ((45, 182), (210, 215), (288, 167)):
        draw.rectangle((x - 5, y, x + 5, 332), fill="#204b49")
        draw.polygon([(x, y - 55), (x - 32, y + 62), (x + 32, y + 62)], fill="#315e59")
    trees.save(target / "near_trees.png")


#: The workflow's inputs; each layer's file is relative to the inputs file.
INPUTS = {
    "canvas": {"width": 640, "height": 360},
    "layers": [
        {"layer_id": "distant_hills", "file": "distant_hills.png", "order": 0, "parallax": 0.2},
        {"layer_id": "near_trees", "file": "near_trees.png", "order": 1, "parallax": 0.7},
    ],
}


def write_inputs(target: Path) -> Path:
    """Draw the layers and write the inputs that place them into ``target``."""
    write_layers(target)
    path = target / "inputs.yaml"
    path.write_text(yaml.safe_dump(INPUTS, sort_keys=False), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    write_inputs(parser.parse_args().directory)


if __name__ == "__main__":
    main()
