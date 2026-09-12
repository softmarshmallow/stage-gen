"""Write original geometric example layers; no provider or artwork download."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    target = parser.parse_args().directory
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


if __name__ == "__main__":
    main()
