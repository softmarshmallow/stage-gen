"""The vitals gauge and the per-source consequence table.

`runner-gameplay-v3` split what v2's `collision_policy` conflated: the torso box
admission proves, and what a contact costs. These tests hold the second half —
the closed vocabularies, the obligation between a gauge and something that can
spend it, and the fact that no damage source is silently defaulted.
"""

from __future__ import annotations

import pytest

from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.runner_gameplay import (
    COLLISION_BOXES,
    DRAINING_CONSEQUENCES,
    VITALS_PROFILES,
    load_runner_gameplay_bytes,
)

BASE = """schema_version = 4
kind = "runner-gameplay-v4"
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

TERMINAL_CONSEQUENCES = """[run.consequences]
hazard = "end_run_v1"
pit = "end_run_v1"
crush = "end_run_v1"
"""


def _without_vitals(document: str) -> str:
    head, _, _ = document.partition("\n[run.vitals]")
    return head + '\n\n[ramp]\nprofile = "gentle_ramp_v1"\n'


def test_a_survivable_package_resolves_its_gauge_and_every_consequence() -> None:
    gameplay = load_runner_gameplay_bytes(BASE.encode())

    assert gameplay.run.consequences.by_source() == {
        "hazard": "drain_v1",
        "pit": "drain_and_recover_v1",
        "crush": "end_run_v1",
    }
    profile = gameplay.vitals_profile()
    assert profile is not None
    assert profile.max_points == 3


def test_a_one_hit_kill_package_declares_no_gauge() -> None:
    document = _without_vitals(BASE).replace(
        '[run.consequences]\nhazard = "drain_v1"\npit = "drain_and_recover_v1"\n'
        'crush = "end_run_v1"\n',
        TERMINAL_CONSEQUENCES,
    )
    gameplay = load_runner_gameplay_bytes(document.encode())

    assert gameplay.run.vitals is None
    assert gameplay.vitals_profile() is None
    assert not gameplay.run.consequences.drains()


def test_a_draining_consequence_without_a_gauge_is_refused() -> None:
    with pytest.raises(AuthoredContractLoadError, match="draining consequence with no"):
        load_runner_gameplay_bytes(_without_vitals(BASE).encode())


def test_a_gauge_no_consequence_can_drain_is_refused() -> None:
    document = BASE.replace(
        '[run.consequences]\nhazard = "drain_v1"\npit = "drain_and_recover_v1"\n'
        'crush = "end_run_v1"\n',
        TERMINAL_CONSEQUENCES,
    )
    with pytest.raises(AuthoredContractLoadError, match="no consequence can drain"):
        load_runner_gameplay_bytes(document.encode())


@pytest.mark.parametrize("source", ["hazard", "pit", "crush"])
def test_every_damage_source_is_answered_explicitly(source: str) -> None:
    # No source defaults: a silent default is how a pit stops being final.
    document = "\n".join(line for line in BASE.splitlines() if not line.startswith(f"{source} = "))
    with pytest.raises(AuthoredContractLoadError):
        load_runner_gameplay_bytes(document.encode())


def test_the_collision_box_carries_geometry_only() -> None:
    gameplay = load_runner_gameplay_bytes(BASE.encode())
    box = gameplay.collision_profile()

    # The same numbers v2 published under `end_run_v1`, now under a name that
    # says what they are: admission's proofs are untouched by the split.
    assert box.avatar_half_width_columns == 0.3
    assert box.hazard_column_inset == 0.15
    assert set(COLLISION_BOXES) == {"torso_v1"}


def test_an_unknown_consequence_or_profile_name_is_refused() -> None:
    with pytest.raises(AuthoredContractLoadError):
        load_runner_gameplay_bytes(BASE.replace('"drain_v1"', '"shrug_it_off_v1"').encode())
    with pytest.raises(AuthoredContractLoadError):
        load_runner_gameplay_bytes(BASE.replace('"three_point_v1"', '"nine_lives_v1"').encode())


def test_the_vitals_vocabulary_is_closed_and_ascending() -> None:
    counts = [VITALS_PROFILES[name].max_points for name in VITALS_PROFILES]
    assert counts == sorted(counts)
    assert all(count >= 1 for count in counts)
    assert frozenset({"drain_v1", "drain_and_recover_v1"}) == DRAINING_CONSEQUENCES
