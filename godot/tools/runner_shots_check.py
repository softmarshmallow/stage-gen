#!/usr/bin/env python3
"""Measure the runner's gate sheet.

    python3 tools/runner_shots_check.py <shot directory>

Decision 0065 retired the browser runner on a state proof — six hundred frame
hashes, exact — and said out loud that the picture was one measurement short.
Every defect the port then shipped was in that missing measurement: a foreground
band drawn three and a half times too tall, two hundred pixels of bare engine
grey down the right of every frame, a boss that fought and killed the player
without being drawn, a moment that stopped the world over nothing, no dust, no
sound, and coins that did not turn. Not one of them could move a frame hash.

So this is the measurement, and each check below is one of those defects. It is
deliberately not a pixel diff against a reference: there is no browser left to
diff against, and this repository already retired cross-renderer pixel equality
for survival for the reason it was never going to be an equality. What a picture
*can* be held to is that the things which must be in it are in it, in the region
they belong to, at a strength nothing else in the frame reaches.

Thresholds are stated with the measurement that motivated them, so a future
reader can tell a margin from a coincidence.

No dependencies: the PNG reader below is thirty lines of zlib.
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

#: What the capture paints before the host draws. A pixel still wearing it is a
#: pixel nothing covered.
UNPAINTED = (255, 0, 255)

#: The cut-in's interior. `HostCutInView.BACKDROP_COLOR`, as bytes.
CUT_IN_BACKDROP = (255, 74, 28)

#: Where the boss's bar is, from `RunnerHud.boss_bar_rect` at the design width.
BOSS_BAR = (1280 - 24 - 320, 26, 320, 14)

#: A gauge bar is one colour down each of its columns; foliage is not. Measured
#: over the bar's rectangle: 100.8 mean per-column variance with the bar drawn,
#: 671.1 with the canopy showing through where it should have been. An earlier
#: draft of this check only asked whether the region was *saturated*, and the
#: build with no bar at all passed it, because the leaves behind it were.
BOSS_BAR_COLUMN_VARIANCE = 300.0

#: The window of sky the oversized canopy used to fill. Measured on the two
#: builds: with the band scaled by its own trimmed height, 0.0% of this region
#: is sky — it is foreground pipework and leaves, end to end. With it scaled by
#: the frame it was painted against, 92.7%. The bar sits between them with room
#: on both sides.
SKY_WINDOW = (400, 120, 500, 120)
SKY_WINDOW_MINIMUM = 0.80

#: There is deliberately no check here for the bands' depth grading, and the
#: absence is a measurement rather than an oversight. Mean saturation over this
#: window reads 0.400 graded against 0.560 ungraded, but the ungraded frame's
#: window was full of *canopy* rather than sky, so the gap is the sizing defect
#: showing through, not the grading; over a region both builds agree on — the
#: ground — the two read 0.413 and 0.418, which separates nothing. A picture
#: cannot hold that transform to account without a reference frame there is no
#: longer any way to produce, so it is held to account where it can be: the
#: arithmetic against the browser's own in `test_layer_presentation.gd`, and the
#: host path that carries it in `test_runner_view.gd`.


def read_png(path: Path) -> tuple[int, int, int, bytes]:
    """Width, height, bytes per pixel, and the unfiltered pixel data."""
    data = path.read_bytes()
    position, width, height, colour_type, chunks = 8, 0, 0, 6, []
    while position < len(data):
        length = struct.unpack(">I", data[position : position + 4])[0]
        kind = data[position + 4 : position + 8]
        body = data[position + 8 : position + 8 + length]
        if kind == b"IHDR":
            width, height, _depth, colour_type = struct.unpack(">IIBB", body[:10])
        elif kind == b"IDAT":
            chunks.append(body)
        position += 12 + length
    raw = zlib.decompress(b"".join(chunks))
    channels = 4 if colour_type == 6 else 3
    stride = width * channels
    out, previous, index = bytearray(), bytearray(stride), 0
    for _ in range(height):
        filter_kind = raw[index]
        index += 1
        line = bytearray(raw[index : index + stride])
        index += stride
        for x in range(stride):
            left = line[x - channels] if x >= channels else 0
            up = previous[x]
            corner = previous[x - channels] if x >= channels else 0
            if filter_kind == 1:
                line[x] = (line[x] + left) & 255
            elif filter_kind == 2:
                line[x] = (line[x] + up) & 255
            elif filter_kind == 3:
                line[x] = (line[x] + (left + up) // 2) & 255
            elif filter_kind == 4:
                estimate = left + up - corner
                da, db, dc = (
                    abs(estimate - left),
                    abs(estimate - up),
                    abs(estimate - corner),
                )
                nearest = left if (da <= db and da <= dc) else (up if db <= dc else corner)
                line[x] = (line[x] + nearest) & 255
        out += line
        previous = line
    return width, height, channels, bytes(out)


class Shot:
    def __init__(self, path: Path) -> None:
        self.name = path.stem
        self.width, self.height, self.channels, self.pixels = read_png(path)

    def at(self, x: int, y: int) -> tuple[int, int, int]:
        offset = (y * self.width + x) * self.channels
        return (self.pixels[offset], self.pixels[offset + 1], self.pixels[offset + 2])

    def region(self, box: tuple[int, int, int, int], step: int = 1):
        x0, y0, w, h = box
        for y in range(y0, min(y0 + h, self.height), step):
            for x in range(x0, min(x0 + w, self.width), step):
                yield self.at(x, y)


def saturation(pixel: tuple[int, int, int]) -> float:
    """HSV saturation: how far the colour is from grey."""
    high, low = max(pixel), min(pixel)
    return 0.0 if high == 0 else (high - low) / high


def is_sky(pixel: tuple[int, int, int]) -> bool:
    """Blue-leading and bright: the glasshouse behind everything."""
    red, green, blue = pixel
    return blue > red and blue > 120


def near(pixel: tuple[int, int, int], target: tuple[int, int, int], tolerance: int) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(pixel, target))


def mean_column_variance(shot: Shot, box: tuple[int, int, int, int]) -> float:
    """How much each column of a region varies down its own height."""
    x0, y0, width, height = box
    total = 0.0
    for x in range(x0, x0 + width):
        column = [shot.at(x, y) for y in range(y0, y0 + height)]
        for channel in range(3):
            values = [pixel[channel] for pixel in column]
            mean = sum(values) / len(values)
            total += sum((value - mean) ** 2 for value in values) / len(values)
    return total / (width * 3)


def check(shot: Shot) -> list[str]:
    """Every problem this shot has, named. Empty is a pass."""
    problems: list[str] = []

    # Nothing unpainted, anywhere. This is the band-coverage defect: the cover
    # tile is narrower than the canvas, and at the wrong wrap phase the picture
    # simply ended 200 px short of the right edge.
    unpainted = sum(1 for pixel in shot.region((0, 0, shot.width, shot.height), 2)
                    if near(pixel, UNPAINTED, 8))
    if unpainted:
        problems.append(f"{unpainted} sampled pixels are unpainted background")

    if shot.name == "boot":
        # The moment is drawn over the world it stopped. Measured at this step:
        # 13.4% of the frame is the cut-in's own interior, against 0.7% on the
        # build that ran the moment and drew nothing.
        interior = sum(1 for pixel in shot.region((0, 0, shot.width, shot.height), 4)
                       if near(pixel, CUT_IN_BACKDROP, 40))
        total = len(range(0, shot.height, 4)) * len(range(0, shot.width, 4))
        if interior / total < 0.05:
            problems.append(
                f"the cut-in covers {interior / total:.1%} of the frame; the moment is not drawn"
            )

    if shot.name == "run":
        # The canopy is a 286-row strip of a 1024-row painted frame. Scaled by
        # its own height instead it filled the screen, and this window of sky
        # was pipework end to end.
        window = list(shot.region(SKY_WINDOW, 2))
        sky = sum(1 for pixel in window if is_sky(pixel)) / len(window)
        if sky < SKY_WINDOW_MINIMUM:
            problems.append(
                f"the sky window is {sky:.1%} sky; a foreground band is oversized"
            )

    if shot.name == "fight":
        # A fight with no bar drew nothing here at all, so the question is
        # whether what is here is a *gauge*. Two things say so and neither is
        # true of scenery: every column is one colour, and the colours run warm
        # to cool along it.
        variance = mean_column_variance(shot, BOSS_BAR)
        if variance > BOSS_BAR_COLUMN_VARIANCE:
            problems.append(
                f"the boss bar region varies {variance:.0f} down its columns; no bar is drawn"
            )
        else:
            vivid = [pixel for pixel in shot.region(BOSS_BAR) if saturation(pixel) > 0.5]
            warm = [pixel for pixel in vivid if pixel[0] > pixel[1]]
            cool = [pixel for pixel in vivid if pixel[1] > pixel[0]]
            if not warm or not cool:
                problems.append("the boss bar carries no spectrum; it is not a gauge")

    if shot.name == "death":
        # The card is a dark panel across the middle of the frame.
        panel = list(shot.region((360, 245, 560, 230), 4))
        dark = sum(1 for pixel in panel if max(pixel) < 90) / len(panel)
        if dark < 0.5:
            problems.append(f"the death card covers {dark:.1%} of its panel; it is not drawn")

    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    directory = Path(argv[1])
    shots = sorted(directory.glob("*.png"))
    if not shots:
        print(f"runner shots: no pictures in {directory}")
        return 1
    failures = 0
    for path in shots:
        shot = Shot(path)
        problems = check(shot)
        if problems:
            failures += 1
            for problem in problems:
                print(f"   {shot.name}: {problem}")
        else:
            print(f"   {shot.name}: ok")
    if failures:
        print(f"runner shots: {failures} of {len(shots)} pictures failed")
        return 1
    print(f"   {len(shots)} of {len(shots)} pictures carry what they must")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
