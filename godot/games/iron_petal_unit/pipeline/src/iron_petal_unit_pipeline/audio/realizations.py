"""Runner playback metadata layered over independent audio requests."""

from pydantic import Field

from stage_gen.components.sound_effect import SoundEffectRequest
from stage_gen.components.speech import SpeechRequest


class GeneratedClipRealization(SoundEffectRequest):
    gain: float = Field(gt=0.0, le=1.0)
    strength_pitch_multiplier: float = Field(ge=0.0, le=2.0)


class SpokenLineRealization(SpeechRequest):
    gain: float = Field(gt=0.0, le=1.0)
    strength_pitch_multiplier: float = Field(ge=0.0, le=2.0)


__all__ = ["GeneratedClipRealization", "SpokenLineRealization"]
