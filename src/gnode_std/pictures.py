"""Pictures for node bodies: ``ctx.read.image`` returns a PIL image, ``ctx.out.png`` encodes one."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from PIL import Image

from gnode import register_reader, register_writer


def _read(path: Path) -> Image.Image:
    with Image.open(path) as picture:
        picture.load()
        return picture.copy()


def _png(picture: Any) -> bytes:
    if not isinstance(picture, Image.Image):
        raise TypeError(f"ctx.out.png takes a PIL image, not {type(picture).__name__}")
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def register_pictures() -> None:
    register_reader("image", _read)
    register_writer("png", _png, "image/png")
