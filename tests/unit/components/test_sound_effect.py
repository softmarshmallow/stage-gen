"""Generated clip realization bounds and the objective admission gates."""

from __future__ import annotations

import pytest

from stage_gen.components.sound_effect import (
    SOUND_EFFECT_CLIPPING_PEAK_DBFS,
    SOUND_EFFECT_MINIMUM_PEAK_DBFS,
    GeneratedClipRealization,
    admission_facts,
)
from stage_gen.media import MINIMUM_SOUND_EFFECT_PAYLOAD_BYTES

PAYLOAD = b"\xff\xfb" + b"\x00" * MINIMUM_SOUND_EFFECT_PAYLOAD_BYTES


def _clip(**overrides: object) -> GeneratedClipRealization:
    fields: dict[str, object] = {
        "kind": "generated_clip_v1",
        "prompt": "metal hatch latch release",
        "duration_seconds": 0.6,
        "gain": 0.5,
        "strength_pitch_multiplier": 0.0,
    }
    fields.update(overrides)
    return GeneratedClipRealization.model_validate(fields)


def test_generation_identity_is_the_request_and_only_the_request() -> None:
    assert _clip().generation_identity() == {
        "prompt": "metal hatch latch release",
        "duration_seconds": 0.6,
        "output_format": "mp3",
    }
    assert _clip(prompt_influence=0.7).generation_identity()["prompt_influence"] == 0.7
    assert _clip(gain=0.2).generation_identity() == _clip(gain=0.9).generation_identity()
    assert (
        _clip(strength_pitch_multiplier=1.0).generation_identity() == _clip().generation_identity()
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"prompt": ""},
        {"prompt": " padded "},
        {"prompt": "x" * 451},
        {"duration_seconds": 0.49},
        {"duration_seconds": 30.5},
        {"prompt_influence": 1.01},
        {"gain": 0.0},
        {"gain": 1.5},
        {"strength_pitch_multiplier": -0.1},
        {"kind": "generated_file_v1"},
    ],
)
def test_out_of_range_authoring_is_refused(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        _clip(**overrides)


def test_admission_records_a_healthy_peak_as_facts() -> None:
    assert admission_facts(PAYLOAD, -12.345) == {
        "minimum_bytes": MINIMUM_SOUND_EFFECT_PAYLOAD_BYTES,
        "bytes": len(PAYLOAD),
        "peak_dbfs": -12.35,
        "clipped": False,
    }


def test_admission_refuses_silence_clipping_and_truncation() -> None:
    with pytest.raises(ValueError, match="effectively silent"):
        admission_facts(PAYLOAD, SOUND_EFFECT_MINIMUM_PEAK_DBFS - 0.1)
    with pytest.raises(ValueError, match="clipped"):
        admission_facts(PAYLOAD, SOUND_EFFECT_CLIPPING_PEAK_DBFS)
    with pytest.raises(ValueError, match="clipped"):
        admission_facts(PAYLOAD, 0.0)
    with pytest.raises(ValueError, match="too small"):
        admission_facts(PAYLOAD[: MINIMUM_SOUND_EFFECT_PAYLOAD_BYTES - 1], -12.0)
    # The floor itself is admitted; one tenth below it is not.
    assert admission_facts(PAYLOAD, SOUND_EFFECT_MINIMUM_PEAK_DBFS)["peak_dbfs"] == -40.0


def test_the_take_ordinal_re_keys_the_draw_and_a_pin_replaces_it() -> None:
    first = _clip().generation_identity()
    assert "take" not in first
    assert _clip(take=2).generation_identity() == {**first, "take": 2}
    pinned = _clip(
        pinned={
            "source": "runner/audio/hull_clank.mp3",
            "source_sha256": "a" * 64,
            "provenance_source": "runner/audio/hull_clank.mp3.meta.json",
            "provenance_sha256": "b" * 64,
            "rights_status": "unreviewed",
        }
    )
    assert pinned.pinned is not None
    assert pinned.generation_identity() == first
