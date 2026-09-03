"""Objective admission for a spoken-line draw.

Two facts a decoder can state about the bytes, each refusing rather than
repairing: the level gates the sound-effect route already proved (a dead draw
and a clipped draw are both refused, never normalized), and the one gate a
speech route needs that a sound route does not - a length ceiling. The route
has no duration control, so the cue states the longest read its frame budget
tolerates and a longer draw is refused inside the retry owner and redrawn.
Trimming it would be post-processing, which is forbidden repository-wide.

Whether the line *sounds like* the character is a person's call and is
recorded as ``listening_verdict``, never inferred.
"""

from __future__ import annotations

from stage_gen.components.sound_effect.admission import admission_facts
from stage_gen.media import (
    LevelAndDuration,
    measure_level_and_duration,
    measure_level_and_duration_sync,
)

#: mp3 frame quantization: a read is never refused for a few milliseconds.
DURATION_CEILING_TOLERANCE_SECONDS = 0.05


def speech_admission_facts(
    data: bytes, measured: LevelAndDuration, *, max_seconds: float | None
) -> dict[str, object]:
    """Level facts plus the measured length, refused above the authored ceiling."""

    facts = admission_facts(data, measured.peak_dbfs)
    duration = round(measured.duration_seconds, 3)
    if max_seconds is not None and duration > max_seconds + DURATION_CEILING_TOLERANCE_SECONDS:
        raise ValueError(
            f"spoken line runs {duration:.3f}s against an authored ceiling of {max_seconds:.3f}s"
        )
    return {**facts, "duration_seconds": duration}


async def admit_speech_bytes(data: bytes, *, max_seconds: float | None = None) -> dict[str, object]:
    """The live validator, run inside the provider's retry owner before persistence."""

    return speech_admission_facts(
        data, await measure_level_and_duration(data), max_seconds=max_seconds
    )


def admit_speech_bytes_sync(data: bytes, *, max_seconds: float | None = None) -> dict[str, object]:
    """The same verdict for synchronous cache admission and provenance reconstruction."""

    return speech_admission_facts(
        data, measure_level_and_duration_sync(data), max_seconds=max_seconds
    )


__all__ = [
    "DURATION_CEILING_TOLERANCE_SECONDS",
    "admit_speech_bytes",
    "admit_speech_bytes_sync",
    "speech_admission_facts",
]
