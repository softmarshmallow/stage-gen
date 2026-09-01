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

from ..._runner_fixture import SOURCE_PACKAGE

GAMEPLAY = b"""schema_version = 2
kind = "runner-gameplay-v2"
game_id = "bellweather"
revision = 1
track_id = "sunpetal-sprint"

[run]
speed_profile = "steady_runner_v1"
jump_profile = "double_arc_v1"
collision_policy = "end_run_v1"
duck_profile = "slide_v1"

[ramp]
profile = "gentle_ramp_v1"
"""


def test_the_published_gameplay_block_is_exactly_the_parsers_contract() -> None:
    block = manifest_gameplay(load_runner_gameplay_bytes(GAMEPLAY))

    assert block == {
        "speed_profile": "steady_runner_v1",
        "jump_profile": "double_arc_v1",
        "collision_policy": "end_run_v1",
        "duck_profile": "slide_v1",
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


def test_a_duckless_gameplay_publishes_null_duck_arithmetic() -> None:
    duckless = GAMEPLAY.replace(b'duck_profile = "slide_v1"\n', b"")
    block = manifest_gameplay(load_runner_gameplay_bytes(duckless))

    assert block["duck_profile"] is None
    assert block["ducked_height_fraction"] is None
    assert block["min_overhead_clearance_rows"] is None


def test_the_published_audio_block_is_exactly_the_authored_contract() -> None:
    source = (SOURCE_PACKAGE / "runner/audio.toml").read_bytes()
    block = manifest_audio(load_runner_audio_bytes(source))

    assert block["bindings"] == {
        "takeoff": "takeoff_whistle",
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
