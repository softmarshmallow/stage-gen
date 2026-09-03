"""Generated sound-effect clips: the authored realization and its objective admission."""

from .admission import (
    DURATION_TOLERANCE_SECONDS,
    SOUND_EFFECT_CLIPPING_PEAK_DBFS,
    SOUND_EFFECT_MINIMUM_PEAK_DBFS,
    admission_facts,
    admit_sound_effect_bytes,
    admit_sound_effect_bytes_sync,
)
from .models import (
    FIRST_TAKE,
    GENERATED_CLIP_OUTPUT_FORMAT,
    GENERATED_CLIP_REALIZATION_KIND,
    MAX_GENERATED_CLIP_PROMPT_CHARACTERS,
    MAX_TAKE,
    GeneratedClipRealization,
    PinnedTake,
    TakeRightsStatus,
)

__all__ = [
    "DURATION_TOLERANCE_SECONDS",
    "FIRST_TAKE",
    "GENERATED_CLIP_OUTPUT_FORMAT",
    "GENERATED_CLIP_REALIZATION_KIND",
    "MAX_GENERATED_CLIP_PROMPT_CHARACTERS",
    "MAX_TAKE",
    "SOUND_EFFECT_CLIPPING_PEAK_DBFS",
    "SOUND_EFFECT_MINIMUM_PEAK_DBFS",
    "GeneratedClipRealization",
    "PinnedTake",
    "TakeRightsStatus",
    "admission_facts",
    "admit_sound_effect_bytes",
    "admit_sound_effect_bytes_sync",
]
