"""Stable run/cache identity helpers."""

from __future__ import annotations

import hashlib
import re

from stage_gen.config import TransparencyMode

SLUG_MAX = 40
SHORT_HASH_LENGTH = 8


def slugify(prompt: str) -> str:
    collapsed = re.sub(r"[^a-z0-9]+", "-", prompt.lower())
    trimmed = collapsed.strip("-")
    if not trimmed:
        return "untitled"
    return trimmed[:SLUG_MAX].rstrip("-")


def short_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:SHORT_HASH_LENGTH]


def tag_for(prompt: str) -> str:
    return f"{slugify(prompt)}-{short_hash(prompt)}"


def tag_for_transparency_mode(base_tag: str, mode: TransparencyMode) -> str:
    suffix = f"-{mode}"
    return f"{base_tag[: 128 - len(suffix)]}{suffix}"
