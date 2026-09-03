"""Provider-neutral spoken-line realization and its objective admission."""

from .admission import (
    DURATION_CEILING_TOLERANCE_SECONDS,
    admit_speech_bytes,
    admit_speech_bytes_sync,
    speech_admission_facts,
)
from .models import (
    MAX_SPOKEN_LINE_CHARACTERS,
    MAX_SPOKEN_LINE_SECONDS,
    MIN_SPOKEN_LINE_SECONDS,
    SPOKEN_LINE_OUTPUT_FORMAT,
    SPOKEN_LINE_REALIZATION_KIND,
    SpokenLineRealization,
)

__all__ = [
    "DURATION_CEILING_TOLERANCE_SECONDS",
    "MAX_SPOKEN_LINE_CHARACTERS",
    "MAX_SPOKEN_LINE_SECONDS",
    "MIN_SPOKEN_LINE_SECONDS",
    "SPOKEN_LINE_OUTPUT_FORMAT",
    "SPOKEN_LINE_REALIZATION_KIND",
    "SpokenLineRealization",
    "admit_speech_bytes",
    "admit_speech_bytes_sync",
    "speech_admission_facts",
]
