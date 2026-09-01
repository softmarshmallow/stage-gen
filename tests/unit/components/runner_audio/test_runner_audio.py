"""Runner audio event bindings and provider-free realization tests."""

from __future__ import annotations

import pytest

from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.runner_audio import (
    RunnerAudioContract,
    canonical_runner_audio_json,
    load_runner_audio_bytes,
    runner_audio_sha256,
)


def _source(*, reverse: bool = False) -> str:
    effects = [
        """\
[[effects]]
effect_id = "jump_tone"
display_name = "Jump Tone"

[effects.realization]
kind = "oscillator_sweep_v1"
waveform = "triangle"
start_frequency_hz = 330
end_frequency_hz = 660
duration_milliseconds = 120
gain = 0.16
strength_pitch_multiplier = 0.0
""",
        """\
[[effects]]
effect_id = "collect_tone"
display_name = "Collect Tone"

[effects.realization]
kind = "oscillator_sweep_v1"
waveform = "sine"
start_frequency_hz = 660
end_frequency_hz = 880
duration_milliseconds = 90
gain = 0.12
strength_pitch_multiplier = 1.0
""",
    ]
    if reverse:
        effects.reverse()
    return """schema_version = 1
kind = "runner-audio-v1"
game_id = "test-game"
revision = 1

[bindings]
takeoff = "jump_tone"
air_jump = "jump_tone"
land = "jump_tone"
slide = "jump_tone"
hazard_cleared = "collect_tone"
collect = "collect_tone"
death = "jump_tone"

""" + "\n".join(effects)


def _load(source: str) -> RunnerAudioContract:
    return load_runner_audio_bytes(source.encode("utf-8"))


def test_audio_is_explicit_provider_neutral_and_canonical_by_effect_id() -> None:
    audio = _load(_source(reverse=True))

    assert [effect.effect_id for effect in audio.effects] == ["collect_tone", "jump_tone"]
    assert audio.bindings.collect == "collect_tone"
    assert audio.effect("collect_tone").realization.strength_pitch_multiplier == 1.0
    assert runner_audio_sha256(audio) == runner_audio_sha256(_load(_source()))
    serialized = canonical_runner_audio_json(audio)
    assert b"provider" not in serialized
    assert b"model" not in serialized


def test_audio_refuses_unresolved_or_unused_effects() -> None:
    with pytest.raises(AuthoredContractLoadError, match="unknown effects"):
        _load(_source().replace('takeoff = "jump_tone"', 'takeoff = "missing_tone"'))
    with pytest.raises(AuthoredContractLoadError, match="unused effects"):
        _load(
            _source()
            .replace('hazard_cleared = "collect_tone"', 'hazard_cleared = "jump_tone"')
            .replace('collect = "collect_tone"', 'collect = "jump_tone"')
        )


def test_audio_refuses_unknown_fields_and_out_of_range_realization_values() -> None:
    with pytest.raises(AuthoredContractLoadError):
        _load(_source().replace("start_frequency_hz =", "startFrequencyHz =", 1))
    with pytest.raises(AuthoredContractLoadError):
        _load(_source().replace("duration_milliseconds = 120", "duration_milliseconds = 2"))
    with pytest.raises(AuthoredContractLoadError):
        _load(
            _source().replace("strength_pitch_multiplier = 1.0", "strength_pitch_multiplier = 3.0")
        )
