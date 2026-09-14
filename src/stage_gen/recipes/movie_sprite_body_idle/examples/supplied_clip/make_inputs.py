"""Write an original geometric RGBA loop without a provider; requires FFmpeg."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

WIDTH = 96
HEIGHT = 160
FRAME_COUNT = 12
SOURCE_FPS = 6


def make_frame(index: int) -> Image.Image:
    """Draw a fixed head with a gently moving scarf and hand, closing exactly."""
    if not 0 <= index < FRAME_COUNT:
        raise ValueError("frame index is outside the example loop")
    shift = round(3 * math.sin(2 * math.pi * index / (FRAME_COUNT - 1)))
    frame = Image.new("RGBA", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(frame)
    draw.rounded_rectangle((34, 74, 61, 126), radius=8, fill="#507b9d")
    draw.rectangle((35, 118, 44, 148), fill="#294455")
    draw.rectangle((51, 118, 60, 148), fill="#294455")
    draw.rounded_rectangle((35, 28, 60, 57), radius=10, fill="#efcfa2")
    draw.rectangle((44, 56, 51, 74), fill="#efcfa2")
    draw.ellipse((40, 40, 42, 42), fill="#294455")
    draw.ellipse((52, 40, 54, 42), fill="#294455")
    draw.line((44, 48, 50, 48), fill="#294455", width=1)
    draw.line((35, 78, 26 + shift, 100), fill="#507b9d", width=8)
    draw.ellipse((22 + shift, 96, 30 + shift, 104), fill="#efcfa2")
    draw.line((60, 78, 68, 101), fill="#507b9d", width=8)
    draw.ellipse((64, 97, 72, 105), fill="#efcfa2")
    draw.polygon(
        [(39, 65), (56, 65), (76 + shift, 91), (65 + shift, 96), (45, 72)],
        fill="#e99a62",
    )
    return frame


def make_inputs(target: Path) -> None:
    """Create a portable supplied-video input root and finishing settings."""
    target.mkdir(parents=True, exist_ok=True)
    frames = [make_frame(index) for index in range(FRAME_COUNT)]
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pixel_format",
            "rgba",
            "-video_size",
            f"{WIDTH}x{HEIGHT}",
            "-framerate",
            str(SOURCE_FPS),
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            "ffv1",
            "-level",
            "3",
            "-pix_fmt",
            "bgra",
            str(target / "actor.mkv"),
        ],
        input=b"".join(frame.tobytes() for frame in frames),
        check=True,
        capture_output=True,
    )
    (target / "finish.json").write_text(
        json.dumps(
            {
                "source_mode": "finished",
                "loop_closure": "none",
                "playback_seconds": 3,
                "export_frames": True,
                "preview_max_size": [WIDTH, HEIGHT],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    make_inputs(parser.parse_args().directory)


if __name__ == "__main__":
    main()
