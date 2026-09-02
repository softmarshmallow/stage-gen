"""Strict media envelope validation shared by modality services and adapters.

Byte-signature checks are the deterministic floor every modality result must
clear before caller validation runs: declared media type and leading bytes
must agree, or the attempt fails inside the retry owner.
"""

from __future__ import annotations

import re
from typing import Literal

#: Mirrors ring 0's ``ARTIFACT_MEDIA_FAMILIES``. ``text`` has no modality
#: service and therefore no signature check here: its deterministic floor
#: (``assert_text_payload``) is enforced by the artifact write, not by a
#: retry owner.
MediaFamily = Literal["image", "audio", "application", "text"]


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


def normalize_audio_media_type(value: str) -> str:
    normalized = value.strip().lower().split(";", 1)[0]
    if normalized in {"mp3", "audio/mp3", "audio/mpeg3"}:
        return "audio/mpeg"
    if normalized in {"wav", "audio/x-wav", "audio/wave"}:
        return "audio/wav"
    if not normalized.startswith("audio/"):
        raise ValueError(f"expected audio media type, received {normalized}")
    return normalized


def assert_audio_signature(data: bytes, media_type: str) -> None:
    media_type = normalize_audio_media_type(media_type)
    mp3 = media_type == "audio/mpeg" and (
        data.startswith(b"ID3") or (len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0)
    )
    wav = (
        media_type == "audio/wav"
        and len(data) >= 12
        and data[:4] == b"RIFF"
        and data[8:12] == b"WAVE"
    )
    if not mp3 and not wav:
        raise ValueError(f"audio bytes do not match declared media type {media_type}")
