"""Objective admission for a generated sound-effect draw.

These are the only automated verdicts the evidence supports. Each is a fact a
decoder can state about the bytes, and each refuses rather than repairs: the
asset is whatever the provider returned, and a bad draw is redrawn inside the
retry owner, never normalized or trimmed. Whether a clip *sounds like* its cue
is a person's call and is recorded as ``listening_verdict``, never inferred.
"""

from __future__ import annotations

from stage_gen.media import (
    measure_peak_dbfs,
    measure_peak_dbfs_sync,
    validate_sound_effect_payload,
)

#: A draw peaking below this was heard as no sound at all; treat it as empty media.
SOUND_EFFECT_MINIMUM_PEAK_DBFS = -40.0
#: A draw peaking at full scale was clipped by the model and heard as too loud.
SOUND_EFFECT_CLIPPING_PEAK_DBFS = -0.1
#: The route honours ``duration_seconds`` to within mp3 frame quantization.
DURATION_TOLERANCE_SECONDS = 0.15


def admission_facts(data: bytes, peak_dbfs: float) -> dict[str, object]:
    """Combine the byte floor with a measured peak into one refusal-or-facts verdict."""

    facts = validate_sound_effect_payload(data)
    if peak_dbfs < SOUND_EFFECT_MINIMUM_PEAK_DBFS:
        raise ValueError(
            f"generated sound effect peaks at {peak_dbfs:.1f} dBFS, below the "
            f"{SOUND_EFFECT_MINIMUM_PEAK_DBFS:.0f} dBFS floor: effectively silent"
        )
    clipped = peak_dbfs >= SOUND_EFFECT_CLIPPING_PEAK_DBFS
    if clipped:
        raise ValueError(
            f"generated sound effect peaks at {peak_dbfs:.1f} dBFS: clipped by the provider"
        )
    return {**facts, "peak_dbfs": round(peak_dbfs, 2), "clipped": False}


async def admit_sound_effect_bytes(data: bytes) -> dict[str, object]:
    """The live validator, run inside the provider's retry owner before persistence."""

    return admission_facts(data, await measure_peak_dbfs(data))


def admit_sound_effect_bytes_sync(data: bytes) -> dict[str, object]:
    """The same verdict for synchronous cache admission and provenance reconstruction."""

    return admission_facts(data, measure_peak_dbfs_sync(data))


__all__ = [
    "DURATION_TOLERANCE_SECONDS",
    "SOUND_EFFECT_CLIPPING_PEAK_DBFS",
    "SOUND_EFFECT_MINIMUM_PEAK_DBFS",
    "admission_facts",
    "admit_sound_effect_bytes",
    "admit_sound_effect_bytes_sync",
]
