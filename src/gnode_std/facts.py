"""Intrinsic file facts for ``facts(file)``: size and alpha for images, length for sound
and video.

Facts are measurements of the bytes, never judgements: ``width``, ``height``,
``has_alpha`` and ``opaque`` for an image; ``duration`` (seconds) for a WAV file; and
``width``, ``height``, ``duration``, ``fps``, ``frames`` and ``has_alpha`` for a video,
read by ``ffprobe`` when it is installed.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import wave
from collections.abc import Mapping
from fractions import Fraction
from pathlib import Path
from typing import Any

from PIL import Image

from gnode import FileValue

_CACHE: dict[str, Mapping[str, Any]] = {}


def _bytes(file: FileValue) -> bytes | None:
    if file.location is None:
        return None
    return Path(file.location).read_bytes()


def file_facts(file: FileValue) -> Mapping[str, Any]:
    """What can be measured from ``file``'s bytes; empty when its kind has no facts."""

    cached = _CACHE.get(file.digest)
    if cached is not None:
        return cached
    data = _bytes(file) if not file.kind.startswith("video") else None
    facts: dict[str, Any] = {}
    if data is not None and file.kind.startswith("image"):
        with Image.open(io.BytesIO(data)) as picture:
            facts["width"], facts["height"] = picture.size
            bands = picture.getbands()
            facts["has_alpha"] = "A" in bands or "transparency" in picture.info
            try:
                if facts["has_alpha"]:
                    alpha = picture.convert("RGBA").getchannel("A")
                    facts["opaque"] = alpha.getextrema() == (255, 255)
                else:
                    facts["opaque"] = True
            except OSError:
                pass  # the header reads but the pixels do not: only what was measured
    elif file.location is not None and file.kind.startswith("video"):
        facts.update(_video_facts(Path(file.location)))
    elif data is not None and file.kind in {"audio/wav", "audio/x-wav", "audio"}:
        try:
            with wave.open(io.BytesIO(data)) as clip:
                facts["duration"] = round(clip.getnframes() / clip.getframerate(), 6)
        except wave.Error:
            pass
    _CACHE[file.digest] = facts
    return facts


#: Pixel formats that carry an alpha channel.
_ALPHA_FORMATS = frozenset(
    {"rgba", "bgra", "argb", "abgr", "yuva420p", "yuva422p", "yuva444p", "gbrap", "ya8"}
)


def _video_facts(path: Path) -> dict[str, Any]:
    """The first video stream's size, length, rate and frame count; empty without ffprobe."""

    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return {}
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-count_packets",
        "-show_entries",
        "stream=width,height,r_frame_rate,duration,nb_read_packets,pix_fmt:format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=120, check=True)
        probe = json.loads(result.stdout)
        stream = probe["streams"][0]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError):
        return {}
    facts: dict[str, Any] = {}
    if isinstance(stream.get("width"), int) and isinstance(stream.get("height"), int):
        facts["width"], facts["height"] = stream["width"], stream["height"]
    try:
        rate = Fraction(str(stream["r_frame_rate"]))
        if rate > 0:
            facts["fps"] = round(float(rate), 6)
    except (KeyError, ValueError, ZeroDivisionError):
        pass
    duration = stream.get("duration") or probe.get("format", {}).get("duration")
    with contextlib.suppress(TypeError, ValueError):
        facts["duration"] = round(float(duration), 6)
    if str(stream.get("nb_read_packets", "")).isdigit():
        facts["frames"] = int(stream["nb_read_packets"])
    if isinstance(stream.get("pix_fmt"), str):
        facts["has_alpha"] = stream["pix_fmt"] in _ALPHA_FORMATS
    return facts
