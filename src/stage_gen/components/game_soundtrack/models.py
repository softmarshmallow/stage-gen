"""Provider-neutral authored soundtrack catalog contracts.

A soundtrack belongs to a game, not to one generated map.  Maps and other
consumers may select tracks by ``track_id`` later, while this catalog remains
the single owner of their creative and playback intent.  No provider or model
identifier appears here: orchestration chooses an implementation for the
generic generation intent at the boundary where generation actually happens.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator

from gnode import PersistedContractModel

GAME_SOUNDTRACK_SCHEMA_VERSION = 1
_JS_SAFE_INTEGER_MAX = 9_007_199_254_740_991

_GAME_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
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
    """One stable, game-global entry that maps and scenes may reference by ID."""

    track_id: str = Field(pattern=_TRACK_ID.pattern, max_length=64)
    display_name: str
    creative_brief: str
    generation: TrackGenerationIntent

    @field_validator("display_name", "creative_brief")
    @classmethod
    def validate_authored_text(cls, value: str, info: ValidationInfo) -> str:
        return _normalized_text(value, info.field_name or "track text")


class SoundtrackPlaybackPolicy(PersistedContractModel):
    """The v1 game-global selection policy.

    Both values are literal because a consumer must not silently degrade the
    authored policy to sequential playback or permit an immediate repeat.
    """

    selection: Literal["shuffle"]
    no_immediate_repeat: Literal[True]


class GameSoundtrackBinding(PersistedContractModel):
    """Digest-bound reference to one authored ``soundtrack.toml`` source."""

    schema_version: Literal[1]
    kind: Literal["game-soundtrack-binding-v1"]
    ref: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("ref")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        normalized = _normalized_text(value, "game soundtrack ref")
        if "\\" in normalized or ":" in normalized or normalized.startswith("/"):
            raise ValueError("game soundtrack ref must be a portable relative path")
        parts = normalized.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("game soundtrack ref must not contain empty, dot, or parent segments")
        return normalized


class GameSoundtrack(PersistedContractModel):
    """A game-owned catalog of music definitions with stable track identities."""

    schema_version: Literal[1]
    kind: Literal["game-soundtrack-v1"]
    game_id: str = Field(pattern=_GAME_ID.pattern, max_length=96)
    revision: int = Field(ge=1, le=_JS_SAFE_INTEGER_MAX)
    playback: SoundtrackPlaybackPolicy
    tracks: list[SoundtrackTrack] = Field(min_length=2, max_length=64)

    @field_validator("tracks")
    @classmethod
    def validate_and_canonicalize_tracks(
        cls, value: list[SoundtrackTrack]
    ) -> list[SoundtrackTrack]:
        track_ids = [track.track_id for track in value]
        if len(set(track_ids)) != len(track_ids):
            raise ValueError("soundtrack track_id values must be unique")
        # Shuffle makes authored list order non-semantic.  Canonicalizing by the
        # stable ID keeps equivalent catalogs identical after parsing.
        return sorted(value, key=lambda track: track.track_id)

    @property
    def track_ids(self) -> tuple[str, ...]:
        return tuple(track.track_id for track in self.tracks)

    def track(self, track_id: str) -> SoundtrackTrack:
        """Return the catalog entry a later map or scene binding names."""

        for track in self.tracks:
            if track.track_id == track_id:
                return track
        raise ValueError(f"unknown soundtrack track_id: {track_id}")


__all__ = [
    "GAME_SOUNDTRACK_SCHEMA_VERSION",
    "GameSoundtrack",
    "GameSoundtrackBinding",
    "SoundtrackPlaybackPolicy",
    "SoundtrackTrack",
    "TrackGenerationIntent",
]
