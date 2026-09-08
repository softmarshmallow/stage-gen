"""Reading a captured shot, with no dependencies.

The three turn-based gates — the room, the dialogue scene and the case — all
measure PNGs written by a Godot capture, and all of them run under whatever
`python3` is on the path (3.9.6 here), so the reader is thirty lines of `zlib`
rather than an import of Pillow. `tools/runner_shots_check.py` carries its own
copy of the same reader; it is the gate a published decision is written against
and is left exactly as it was.

Nothing here decides anything. Thresholds belong beside the measurement that
motivated them, in the checker that owns them.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

#: What a capture paints before the host draws. A pixel still wearing it is a
#: pixel nothing covered.
UNPAINTED = (255, 0, 255)


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
    """One captured picture, addressed by pixel."""

    def __init__(self, path: Path) -> None:
        self.name = path.stem
        self.path = path
        self.width, self.height, self.channels, self.pixels = read_png(path)

    def at(self, x: int, y: int) -> tuple[int, int, int]:
        offset = (y * self.width + x) * self.channels
        return (self.pixels[offset], self.pixels[offset + 1], self.pixels[offset + 2])

    def region(self, box, step: int = 1):
        x0, y0, w, h = box
        for y in range(max(0, y0), min(y0 + h, self.height), step):
            for x in range(max(0, x0), min(x0 + w, self.width), step):
                yield self.at(x, y)


def near(pixel, target, tolerance: int) -> bool:
    # Indexed rather than zipped: this runs under whatever `python3` is on the
    # path, and `zip(strict=)` — which the lint asks for — needs 3.10.
    return all(abs(pixel[channel] - target[channel]) <= tolerance for channel in range(3))


def saturation(pixel) -> float:
    """HSV saturation: how far the colour is from grey."""
    high, low = max(pixel), min(pixel)
    return 0.0 if high == 0 else (high - low) / high


def fraction_near(shot: Shot, box, target, tolerance: int, step: int = 2) -> float:
    """How much of a region is within `tolerance` of one colour."""
    sampled = list(shot.region(box, step))
    if not sampled:
        return 0.0
    return sum(1 for pixel in sampled if near(pixel, target, tolerance)) / len(sampled)


def mean_difference(first: Shot, second: Shot, box, step: int = 2) -> float:
    """How far two shots differ over the same rectangle, per channel, 0..255.

    The measurement a *state change* is held to. A still cannot say whether a
    marker is a marker, but two stills of the same rectangle either differ
    because the thing was drawn or agree because it was not.
    """
    x0, y0, w, h = box
    total, count = 0.0, 0
    for y in range(max(0, y0), min(y0 + h, first.height, second.height), step):
        for x in range(max(0, x0), min(x0 + w, first.width, second.width), step):
            here, there = first.at(x, y), second.at(x, y)
            total += sum(abs(here[c] - there[c]) for c in range(3)) / 3.0
            count += 1
    return total / count if count else 0.0


def mean_luma(shot: Shot, box, step: int = 2) -> float:
    """Rec. 601 luma over a region, 0..255."""
    sampled = list(shot.region(box, step))
    if not sampled:
        return 0.0
    return sum(0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in sampled) / len(sampled)


def ink_fraction(shot: Shot, box, ground, tolerance: int, step: int = 1) -> float:
    """How much of a region is *not* the surface it is drawn on.

    Words on a plate are the case this exists for: the plate is one colour to
    within its own grain, so anything far from it is a letter.
    """
    sampled = list(shot.region(box, step))
    if not sampled:
        return 0.0
    return sum(1 for pixel in sampled if not near(pixel, ground, tolerance)) / len(sampled)
