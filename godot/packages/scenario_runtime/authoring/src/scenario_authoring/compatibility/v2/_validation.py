"""Scalar invariants owned by the supported Scenario language."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable

SNAKE_ID_PATTERN = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"


def normalized_text(value: str, label: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if not normalized or normalized != normalized.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")
    return normalized


def unique_values(values: Iterable[str], label: str) -> None:
    collected = list(values)
    if len(set(collected)) != len(collected):
        raise ValueError(f"{label} values must be unique")
