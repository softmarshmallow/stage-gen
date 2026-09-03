"""Spoken-line realization bounds and the objective admission gates."""

from __future__ import annotations

import pytest

from stage_gen.components.sound_effect import SOUND_EFFECT_CLIPPING_PEAK_DBFS
from stage_gen.components.speech import SpokenLineRealization, speech_admission_facts
from stage_gen.media import MINIMUM_SOUND_EFFECT_PAYLOAD_BYTES, LevelAndDuration

PAYLOAD = b"\xff\xfb" + b"\x00" * MINIMUM_SOUND_EFFECT_PAYLOAD_BYTES


def _line(**overrides: object) -> SpokenLineRealization:
    fields: dict[str, object] = {
        "kind": "spoken_line_v1",
        "text": "[excited] いくよっ!",
        "voice_id": "mira",
        "stability": 0.5,
        "max_seconds": 3.0,
        "gain": 0.7,
        "strength_pitch_multiplier": 0.0,
    }
    fields.update(overrides)
    return SpokenLineRealization.model_validate(fields)


def test_generation_identity_is_the_read_and_only_the_read() -> None:
    identity = _line().generation_identity(provider="elevenlabs", voice="v-7", language_code="ja")
    assert identity == {
        "text": "[excited] いくよっ!",
        "provider": "elevenlabs",
        "voice": "v-7",
        "output_format": "mp3",
        "stability": 0.5,
        "language_code": "ja",
    }
    # Mixing and the frame budget change how a line is played or judged, not
    # which line was read: a rebalance after listening never re-bills.
    rebalanced = _line(gain=0.3, strength_pitch_multiplier=0.5, max_seconds=2.0)
    assert (
        rebalanced.generation_identity(provider="elevenlabs", voice="v-7", language_code="ja")
        == identity
    )
    # Recasting the same catalog name to another provider voice is a new asset.
    assert (
        _line().generation_identity(provider="elevenlabs", voice="v-8", language_code="ja")
        != identity
    )


def test_optional_parameters_stay_out_of_the_identity_when_absent() -> None:
    identity = _line(stability=None).generation_identity(
        provider="elevenlabs", voice="v-7", language_code=None
    )
    assert "stability" not in identity
    assert "language_code" not in identity


def test_bounds_are_the_cue_bounds() -> None:
    with pytest.raises(ValueError):
        _line(text="")
    with pytest.raises(ValueError):
        _line(text="a" * 1001)
    with pytest.raises(ValueError):
        _line(voice_id="Mira")
    with pytest.raises(ValueError):
        _line(stability=1.5)
    with pytest.raises(ValueError):
        _line(max_seconds=0.2)
    with pytest.raises(ValueError):
        _line(gain=0.0)
    # Verbatim means verbatim: an untrimmed line is refused, not quietly cleaned.
    with pytest.raises(ValueError):
        _line(text="  よし  ")


def test_admission_refuses_a_read_over_its_ceiling_and_keeps_the_level_gates() -> None:
    facts = speech_admission_facts(
        PAYLOAD, LevelAndDuration(peak_dbfs=-1.1, duration_seconds=2.0), max_seconds=3.0
    )
    assert facts["peak_dbfs"] == -1.1
    assert facts["clipped"] is False
    assert facts["duration_seconds"] == 2.0

    with pytest.raises(ValueError, match="ceiling"):
        speech_admission_facts(
            PAYLOAD, LevelAndDuration(peak_dbfs=-1.1, duration_seconds=7.68), max_seconds=3.0
        )
    # A few milliseconds of mp3 frame quantization is never a refusal.
    speech_admission_facts(
        PAYLOAD, LevelAndDuration(peak_dbfs=-1.1, duration_seconds=3.04), max_seconds=3.0
    )
    with pytest.raises(ValueError, match="clipped"):
        speech_admission_facts(
            PAYLOAD,
            LevelAndDuration(peak_dbfs=SOUND_EFFECT_CLIPPING_PEAK_DBFS, duration_seconds=1.0),
            max_seconds=3.0,
        )
    with pytest.raises(ValueError, match="silent"):
        speech_admission_facts(
            PAYLOAD, LevelAndDuration(peak_dbfs=-44.0, duration_seconds=1.0), max_seconds=None
        )
