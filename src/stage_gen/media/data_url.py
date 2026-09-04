"""Bytes as a ``data:`` URL, the form a provider request carries a reference image in."""

from __future__ import annotations

import base64


def data_url(data: bytes, media_type: str) -> str:
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"


__all__ = ["data_url"]
