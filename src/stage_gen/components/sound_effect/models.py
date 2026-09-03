"""The authored, provider-neutral shape of one generated sound-effect clip.

A cue that asks for a generated clip states the prompt the provider receives
verbatim, the exact duration to fill, and how literally to follow the text.
That is the whole request: the recipe compiles nothing onto the prompt, so the
author owns what the model hears and should read the model boundary in
``docs/spec/model-eleven-text-to-sound-v2.md`` before writing it.

Playback mixing - gain and the strength-driven rate lift - is consumer data.
It travels with the clip in the manifest but stays out of the generation
identity, so rebalancing a set after listening never re-bills a draw. No
provider or model identifier belongs here.

Two fields exist because a draw is a lottery and a person picks the winner.
``take`` is the reroll ordinal: it enters the identity and nothing else, so
bumping it redraws this one effect and leaves every other node a cache hit.
``pinned`` is the pick: a reviewed audition committed into the package by
digest, with the sidecar that produced it and a rights statement, republished
through the same admission with no provider call - the way a digest-locked
reference pins a reviewed image.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    SHA256_PATTERN,
    normalized_text,
    portable_relative_path,
    unique_values,
)

GENERATED_CLIP_REALIZATION_KIND = "generated_clip_v1"
GENERATED_CLIP_OUTPUT_FORMAT = "mp3"
MAX_GENERATED_CLIP_PROMPT_CHARACTERS = 450
#: The first draw. A take above it re-keys the draw and nothing else.
FIRST_TAKE = 1
MAX_TAKE = 99

TakeRightsStatus = Literal["unreviewed", "restricted", "redistribution-approved"]


class PinnedTake(PersistedContractModel):
    """One reviewed audition, committed into the package and republished as the effect.

    The bytes and the sidecar that produced them are both digest-locked, so the
    package carries what was heard and how it was made. Rights are the
    author's statement, never inferred from a provider's terms; a status other
    than ``unreviewed`` needs a basis.
    """

    source: str
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    provenance_source: str
    provenance_sha256: str = Field(pattern=SHA256_PATTERN)
    rights_status: TakeRightsStatus
    rights_basis: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        source = portable_relative_path(value, "pinned take source")
        if PurePosixPath(source).suffix.lower() != ".mp3":
            raise ValueError("a pinned take must be an .mp3 file")
        return source

    @field_validator("provenance_source")
    @classmethod
    def validate_provenance_source(cls, value: str) -> str:
        source = portable_relative_path(value, "pinned take provenance source")
        if not source.endswith(".mp3.meta.json"):
            raise ValueError("a pinned take's provenance must be its .mp3.meta.json sidecar")
        return source

    @field_validator("rights_basis")
    @classmethod
    def validate_rights_basis(cls, value: list[str]) -> list[str]:
        normalized = [normalized_text(entry, "pinned take rights basis") for entry in value]
        unique_values(normalized, "pinned take rights basis")
        return normalized

    @model_validator(mode="after")
    def validate_pair(self) -> PinnedTake:
        if self.provenance_source != f"{self.source}.meta.json":
            raise ValueError("a pinned take's provenance must sit beside its source")
        if self.rights_status != "unreviewed" and not self.rights_basis:
            raise ValueError(f"pinned take claims {self.rights_status} rights without a basis")
        return self


class GeneratedClipRealization(PersistedContractModel):
    """One provider-generated clip, requested with the parameters the route honours."""

    kind: Literal["generated_clip_v1"]
    #: Sent to the provider exactly as written.
    prompt: str = Field(min_length=1, max_length=MAX_GENERATED_CLIP_PROMPT_CHARACTERS)
    #: Required: the model fills whatever window it is given, so the window is
    #: the repetition control, and letting it choose overshoots badly.
    duration_seconds: float = Field(ge=0.5, le=30.0)
    #: Omitted means the provider default.
    prompt_influence: float | None = Field(default=None, ge=0.0, le=1.0)
    #: Playback gain applied by the consumer; the bytes are never touched.
    gain: float = Field(gt=0.0, le=1.0)
    #: Multiplies playback rate by ``1 + event_strength * value``. Zero disables it.
    strength_pitch_multiplier: float = Field(ge=0.0, le=2.0)
    #: The reroll ordinal. Bump it to redraw this effect alone.
    take: int = Field(default=FIRST_TAKE, ge=FIRST_TAKE, le=MAX_TAKE)
    #: The reviewed pick. When present the graph buys nothing for this effect.
    pinned: PinnedTake | None = None

    @model_validator(mode="after")
    def validate_prompt(self) -> GeneratedClipRealization:
        self.prompt = normalized_text(self.prompt, "generated clip prompt")
        return self

    def generation_identity(self) -> dict[str, object]:
        """The fields that decide whether a draw must be re-bought.

        Deliberately excludes ``gain`` and ``strength_pitch_multiplier``: they
        change how a clip is played, not which clip was made. ``take`` enters
        only above the first draw, so an existing key is undisturbed until a
        person asks for another.
        """

        identity: dict[str, object] = {
            "prompt": self.prompt,
            "duration_seconds": self.duration_seconds,
            "output_format": GENERATED_CLIP_OUTPUT_FORMAT,
        }
        if self.prompt_influence is not None:
            identity["prompt_influence"] = self.prompt_influence
        if self.take != FIRST_TAKE:
            identity["take"] = self.take
        return identity


__all__ = [
    "FIRST_TAKE",
    "GENERATED_CLIP_OUTPUT_FORMAT",
    "GENERATED_CLIP_REALIZATION_KIND",
    "MAX_GENERATED_CLIP_PROMPT_CHARACTERS",
    "MAX_TAKE",
    "GeneratedClipRealization",
    "PinnedTake",
    "TakeRightsStatus",
]
