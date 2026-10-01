"""Write original geometric example layers and their spec; no provider or artwork download."""

import argparse
import json
from pathlib import Path

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


#: The ``parallax.json`` that ``stage-gen run looping-parallax`` reads beside the layers; the
#: neighbouring ``pipeline.py`` states the same spec in Python for ``stage-gen run file``.
SPEC = {
    "width": 640,
    "height": 360,
    "layers": [
        {"layer_id": "distant_hills", "source": "distant_hills.png", "order": 0, "parallax": 0.2},
        {"layer_id": "near_trees", "source": "near_trees.png", "order": 1, "parallax": 0.7},
    ],
}


def write_inputs(target: Path) -> None:
    """Draw the layers and write the spec that places them into ``target``."""
    write_layers(target)
    (target / "parallax.json").write_text(json.dumps(SPEC, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    write_inputs(parser.parse_args().directory)


if __name__ == "__main__":
    main()
