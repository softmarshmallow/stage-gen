"""The published gameplay block: the writer's half of the cross-language pin.

The TS parser refuses a manifest missing any of these keys, and its fixture
(`web/lib/sideview-runner/fixture.ts`) declares the same values; this test
holds the writer to the exact same list from the Python side, so renaming or
dropping a published key fails offline instead of after paid provider work.
"""

from __future__ import annotations

from typing import cast

from stage_gen.components.runner_audio import load_runner_audio_bytes
from stage_gen.components.runner_gameplay import load_runner_gameplay_bytes
from stage_gen.recipes.sideview_runner.prepared_runner import manifest_audio, manifest_gameplay

from ..._runner_fixture import RUNNER_AUDIO

GAMEPLAY = b"""schema_version = 3
kind = "runner-gameplay-v3"
game_id = "bellweather"
revision = 1
track_id = "sunpetal-sprint"

[run]
speed_profile = "steady_runner_v1"
jump_profile = "double_arc_v1"
collision_box = "torso_v1"
duck_profile = "slide_v1"

[run.consequences]
hazard = "drain_v1"
pit = "drain_and_recover_v1"
crush = "end_run_v1"

[run.vitals]
profile = "three_point_v1"
hurt_representation = "blink_v1"

[ramp]
profile = "gentle_ramp_v1"
"""


def test_the_published_gameplay_block_is_exactly_the_parsers_contract() -> None:
    block = manifest_gameplay(load_runner_gameplay_bytes(GAMEPLAY))

    assert block == {
        "speed_profile": "steady_runner_v1",
        "jump_profile": "double_arc_v1",
        "collision_box": "torso_v1",
        "duck_profile": "slide_v1",
        "consequences": {
            "hazard": "drain_v1",
            "pit": "drain_and_recover_v1",
            "crush": "end_run_v1",
        },
        "vitals": {
            "profile": "three_point_v1",
            "max_points": 3,
            "hurt_representation": "blink_v1",
        },
        "ramp_profile": "gentle_ramp_v1",
        "max_clear_gap_columns": 3,
        "max_rise_tiles": 2,
        "jump_peak_margin_tiles": 0.75,
        "airtime_headroom": 1.15,
        "base_speed_columns_per_second": 6.0,
        "max_speed_multiplier": 1.5,
        "avatar_half_width_columns": 0.3,
        "hazard_column_inset": 0.15,
        "ducked_height_fraction": 0.5,
        "min_overhead_clearance_rows": 0.25,
    }


def test_the_brisk_profiles_publish_their_proved_speed_and_runtime_ramp_names() -> None:
    brisk = GAMEPLAY.replace(
        b'speed_profile = "steady_runner_v1"', b'speed_profile = "brisk_runner_v1"'
    ).replace(b'profile = "gentle_ramp_v1"', b'profile = "brisk_ramp_v1"')

    block = manifest_gameplay(load_runner_gameplay_bytes(brisk))

    assert block["speed_profile"] == "brisk_runner_v1"
    assert block["ramp_profile"] == "brisk_ramp_v1"
    assert block["base_speed_columns_per_second"] == 7.5
    assert block["max_speed_multiplier"] == 1.5


def test_a_duckless_gameplay_publishes_null_duck_arithmetic() -> None:
    duckless = GAMEPLAY.replace(b'duck_profile = "slide_v1"\n', b"")
    block = manifest_gameplay(load_runner_gameplay_bytes(duckless))

    assert block["duck_profile"] is None
    assert block["ducked_height_fraction"] is None
    assert block["min_overhead_clearance_rows"] is None


def test_the_published_audio_block_is_exactly_the_authored_contract() -> None:
    # The fixture owns these bytes now: bellweather's runner member was retired
    # when Iron Petal became the canonical runner game, so the authored contract
    # under test is the one the fixture authors rather than a committed file.
    block = manifest_audio(load_runner_audio_bytes(RUNNER_AUDIO.encode()))

    assert block["bindings"] == {
        "takeoff": "takeoff_whistle",
        "hurt": "soft_landing",
        "air_jump": "air_jump_whistle",
        "land": "soft_landing",
        "slide": "leaf_slide",
        "hazard_cleared": "clear_sparkle",
        "collect": "token_chime",
        "death": "run_ended",
    }
    effects = {
        entry["effect_id"]: entry for entry in cast(list[dict[str, object]], block["effects"])
    }
    assert effects["token_chime"]["realization"] == {
        "kind": "oscillator_sweep_v1",
        "waveform": "sine",
        "start_frequency_hz": 660.0,
        "end_frequency_hz": 880.0,
        "duration_milliseconds": 90,
        "gain": 0.12,
        "strength_pitch_multiplier": 1.0,
    }
