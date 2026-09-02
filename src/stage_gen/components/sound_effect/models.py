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
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import normalized_text

GENERATED_CLIP_REALIZATION_KIND = "generated_clip_v1"
GENERATED_CLIP_OUTPUT_FORMAT = "mp3"
MAX_GENERATED_CLIP_PROMPT_CHARACTERS = 450


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

    @model_validator(mode="after")
    def validate_prompt(self) -> GeneratedClipRealization:
        self.prompt = normalized_text(self.prompt, "generated clip prompt")
        return self

    def generation_identity(self) -> dict[str, object]:
        """The fields that decide whether a draw must be re-bought.

        Deliberately excludes ``gain`` and ``strength_pitch_multiplier``: they
        change how a clip is played, not which clip was made.
        """

        identity: dict[str, object] = {
            "prompt": self.prompt,
            "duration_seconds": self.duration_seconds,
            "output_format": GENERATED_CLIP_OUTPUT_FORMAT,
        }
        if self.prompt_influence is not None:
            identity["prompt_influence"] = self.prompt_influence
        return identity


__all__ = [
    "GENERATED_CLIP_OUTPUT_FORMAT",
    "GENERATED_CLIP_REALIZATION_KIND",
    "MAX_GENERATED_CLIP_PROMPT_CHARACTERS",
    "GeneratedClipRealization",
]
