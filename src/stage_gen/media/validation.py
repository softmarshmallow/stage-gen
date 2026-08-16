"""Strict binary envelope validation shared by provider adapters."""

from __future__ import annotations

import base64
import binascii
import re
from typing import Literal

MediaFamily = Literal["image", "audio", "application"]

_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")


def decode_base64_strict(value: object, label: str = "base64 data") -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty base64 string")
    if len(value) % 4 != 0 or not _BASE64_RE.fullmatch(value):
        raise ValueError(f"{label} is not valid base64")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(f"{label} is not valid base64") from exc
    if not decoded:
        raise ValueError(f"{label} decoded to empty data")
    return decoded


def normalize_media_type(value: object, family: MediaFamily) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("media type must be a non-empty string")
    media_type = value.split(";", 1)[0].strip().lower()
    if not re.fullmatch(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+", media_type):
        raise ValueError(f"invalid media type: {media_type}")
    if not media_type.startswith(f"{family}/"):
        raise ValueError(f"expected {family} media type, received {media_type}")
    return media_type


def assert_image_signature(data: bytes, media_type: str) -> None:
    media_type = normalize_media_type(media_type, "image")
    matches = (
        (media_type == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n"))
        or (media_type in {"image/jpeg", "image/jpg"} and data.startswith(b"\xff\xd8\xff"))
        or (
            media_type == "image/webp"
            and len(data) >= 12
            and data[:4] == b"RIFF"
            and data[8:12] == b"WEBP"
        )
        or (media_type == "image/gif" and len(data) >= 6 and data[:6] in {b"GIF87a", b"GIF89a"})
    )
    if not matches:
        raise ValueError(f"image bytes do not match declared media type {media_type}")
