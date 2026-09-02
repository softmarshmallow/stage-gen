"""Runner audio event bindings and provider-free realization tests."""

from __future__ import annotations

import pytest

from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.runner_audio import (
    GeneratedClipRealization,
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
    return """schema_version = 3
kind = "runner-audio-v3"
game_id = "test-game"
revision = 1

[music.death]
action = "stop"
fade_seconds = 1.2
curve = "exponential"

[music.restart]
action = "play"
fade_seconds = 0.5
curve = "linear"

[bindings]
takeoff = "jump_tone"
air_jump = "jump_tone"
land = "jump_tone"
slide = "jump_tone"
hazard_cleared = "collect_tone"
collect = "collect_tone"
hurt = "jump_tone"
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


GENERATED_CLIP = """\
[[effects]]
effect_id = "collect_tone"
display_name = "Collect Tone"

[effects.realization]
kind = "generated_clip_v1"
prompt = "small brass coin dropping onto stone"
duration_seconds = 0.6
gain = 0.5
strength_pitch_multiplier = 1.0
"""


def _mixed_source() -> str:
    source = _source()
    start = source.index('[[effects]]\neffect_id = "collect_tone"')
    end = (
        source.index("[[effects]]", start + 1)
        if "[[effects]]" in source[start + 1 :]
        else len(source)
    )
    return source[:start] + GENERATED_CLIP + source[end:]


def test_a_generated_clip_realization_sits_beside_the_oscillator_in_one_binding_table() -> None:
    audio = _load(_mixed_source())

    clip = audio.effect("collect_tone").realization
    assert clip.kind == "generated_clip_v1"
    assert clip.prompt == "small brass coin dropping onto stone"
    assert [effect.effect_id for effect in audio.generated_effects()] == ["collect_tone"]
    assert audio.effect("jump_tone").realization.kind == "oscillator_sweep_v1"
    serialized = canonical_runner_audio_json(audio)
    assert b"provider" not in serialized
    assert b"model" not in serialized


def _clip(audio: RunnerAudioContract) -> GeneratedClipRealization:
    realization = audio.effect("collect_tone").realization
    assert isinstance(realization, GeneratedClipRealization)
    return realization


def test_a_generated_clip_keys_its_draw_on_the_request_and_not_the_mix() -> None:
    audio = _load(_mixed_source())
    louder = _load(_mixed_source().replace("gain = 0.5", "gain = 0.9"))
    reworded = _load(_mixed_source().replace("coin dropping", "coin landing"))

    identity = _clip(audio).generation_identity()
    assert identity == {
        "prompt": "small brass coin dropping onto stone",
        "duration_seconds": 0.6,
        "output_format": "mp3",
    }
    assert identity == _clip(louder).generation_identity()
    assert identity != _clip(reworded).generation_identity()
    assert runner_audio_sha256(audio) != runner_audio_sha256(louder)


@pytest.mark.parametrize(
    "mutation",
    [
        ("duration_seconds = 0.6", "duration_seconds = 0.4"),
        ("duration_seconds = 0.6", "duration_seconds = 31"),
        ("gain = 0.5", "gain = 0"),
        ('prompt = "small brass coin dropping onto stone"', 'prompt = "   "'),
        ('prompt = "small brass coin dropping onto stone"', 'prompt = " padded authoring "'),
        ('kind = "generated_clip_v1"', 'kind = "generated_file_v1"'),
    ],
)
def test_a_generated_clip_is_bounded_before_any_spend(mutation: tuple[str, str]) -> None:
    old, new = mutation
    with pytest.raises(AuthoredContractLoadError):
        _load(_mixed_source().replace(old, new, 1))


def test_the_retired_headers_are_refused() -> None:
    for retired in ("runner-audio-v1", "runner-audio-v2"):
        with pytest.raises(AuthoredContractLoadError):
            _load(_source().replace('kind = "runner-audio-v3"', f'kind = "{retired}"'))


DUCK = """
[music.hurt]
duck_gain = 0.4
fade_seconds = 0.05
hold_seconds = 0.2
recovery_seconds = 0.8
curve = "linear"
"""


def _with_duck(source: str) -> str:
    return source.replace("\n[bindings]", DUCK + "\n[bindings]", 1)


def test_music_transitions_are_authored_in_the_interactive_music_vocabulary() -> None:
    audio = _load(_source())

    assert audio.music.death.action == "stop"
    assert audio.music.death.fade_seconds == 1.2
    assert audio.music.death.curve == "exponential"
    assert audio.music.restart.action == "play"
    assert audio.music.hurt is None
    assert b'"music"' in canonical_runner_audio_json(audio)

    ducked = _load(_with_duck(_source()))
    assert ducked.music.hurt is not None
    assert ducked.music.hurt.duck_gain == 0.4
    assert ducked.music.hurt.recovery_seconds == 0.8
    assert runner_audio_sha256(ducked) != runner_audio_sha256(audio)


@pytest.mark.parametrize(
    ("death", "restart"),
    [("stop", "resume"), ("pause", "play"), ("continue", "play"), ("stop", "continue")],
)
def test_music_death_and_restart_actions_must_pair(death: str, restart: str) -> None:
    source = _source().replace('action = "stop"', f'action = "{death}"', 1)
    source = source.replace('action = "play"', f'action = "{restart}"', 1)
    with pytest.raises(AuthoredContractLoadError, match="must be"):
        _load(source)


def test_music_pause_resumes_and_continue_continues() -> None:
    paused = (
        _source()
        .replace('action = "stop"', 'action = "pause"')
        .replace('action = "play"', 'action = "resume"')
    )
    assert _load(paused).music.restart.action == "resume"
    untouched = (
        _source()
        .replace('action = "stop"', 'action = "continue"')
        .replace('action = "play"', 'action = "continue"')
    )
    assert _load(untouched).music.death.action == "continue"


@pytest.mark.parametrize(
    "mutation",
    [
        ("fade_seconds = 1.2", "fade_seconds = -0.1"),
        ("fade_seconds = 1.2", "fade_seconds = 11"),
        ('curve = "exponential"', 'curve = "s_curve"'),
        ('action = "stop"', 'action = "fade"'),
        ("duck_gain = 0.4", "duck_gain = 1.0"),
        ("duck_gain = 0.4", "duck_gain = 0"),
        ("hold_seconds = 0.2", "hold_seconds = 12"),
    ],
)
def test_music_transitions_are_bounded(mutation: tuple[str, str]) -> None:
    old, new = mutation
    with pytest.raises(AuthoredContractLoadError):
        _load(_with_duck(_source()).replace(old, new, 1))


def test_music_is_required() -> None:
    source = _source()
    start = source.index("[music.death]")
    end = source.index("[bindings]")
    with pytest.raises(AuthoredContractLoadError):
        _load(source[:start] + source[end:])
