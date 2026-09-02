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
    GENERATED_CLIP_OUTPUT_FORMAT,
    GENERATED_CLIP_REALIZATION_KIND,
    MAX_GENERATED_CLIP_PROMPT_CHARACTERS,
    GeneratedClipRealization,
)

__all__ = [
    "DURATION_TOLERANCE_SECONDS",
    "GENERATED_CLIP_OUTPUT_FORMAT",
    "GENERATED_CLIP_REALIZATION_KIND",
    "MAX_GENERATED_CLIP_PROMPT_CHARACTERS",
    "SOUND_EFFECT_CLIPPING_PEAK_DBFS",
    "SOUND_EFFECT_MINIMUM_PEAK_DBFS",
    "GeneratedClipRealization",
    "admission_facts",
    "admit_sound_effect_bytes",
    "admit_sound_effect_bytes_sync",
]
