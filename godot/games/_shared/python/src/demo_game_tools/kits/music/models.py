"""Provider-neutral requests for independently generated music tracks."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator

from gnode import PersistedContractModel

_JS_SAFE_INTEGER_MAX = 9_007_199_254_740_991

_TRACK_ID = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


def _normalized_text(value: str, label: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if not normalized or normalized != normalized.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")
    return normalized


class TrackGenerationIntent(PersistedContractModel):
    """Provider-neutral instructions for producing one original music track."""

    intent: Literal["generate"]
    instrumental: bool
    seamless_loop: bool
    target_duration_seconds: int = Field(ge=15, le=600)


class SoundtrackTrack(PersistedContractModel):
    """One independently generated music asset with a stable caller-owned identity."""

    track_id: str = Field(pattern=_TRACK_ID.pattern, max_length=64)
    display_name: str
    creative_brief: str
    generation: TrackGenerationIntent

    @field_validator("display_name", "creative_brief")
    @classmethod
    def validate_authored_text(cls, value: str, info: ValidationInfo) -> str:
        return _normalized_text(value, info.field_name or "track text")


MusicTrack = SoundtrackTrack

__all__ = ["MusicTrack", "SoundtrackTrack", "TrackGenerationIntent"]
