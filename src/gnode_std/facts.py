"""Intrinsic file facts for ``facts(file)``: size and alpha for images, length for audio.

Facts are measurements of the bytes, never judgements: ``width``, ``height``,
``has_alpha`` and ``opaque`` for an image; ``duration`` (seconds) for a WAV file.
"""

from __future__ import annotations

import io
import wave
from collections.abc import Mapping
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
    data = _bytes(file)
    facts: dict[str, Any] = {}
    if data is not None and file.kind.startswith("image"):
        with Image.open(io.BytesIO(data)) as picture:
            facts["width"], facts["height"] = picture.size
            bands = picture.getbands()
            facts["has_alpha"] = "A" in bands or "transparency" in picture.info
            if facts["has_alpha"]:
                alpha = picture.convert("RGBA").getchannel("A")
                facts["opaque"] = alpha.getextrema() == (255, 255)
            else:
                facts["opaque"] = True
    elif data is not None and file.kind in {"audio/wav", "audio/x-wav", "audio"}:
        try:
            with wave.open(io.BytesIO(data)) as clip:
                facts["duration"] = round(clip.getnframes() / clip.getframerate(), 6)
        except wave.Error:
            pass
    _CACHE[file.digest] = facts
    return facts
