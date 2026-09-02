"""The encounter block, the thrust locomotion, and the three proofs they carry.

`runner-gameplay-v4` adds the first locomotion the genre can wear that is not
running, and the first actor that can act back. Both arrive under the same
discipline the arc proofs already hold the track to: every number a refusal
reads is declared in the SDK table, and the proof is closed form, offline, and
provable before any spend.

These tests hold the contract half - the obligations between an encounter and
the things it requires, and the arithmetic itself at the numbers Iron Petal
authors, together with the neighbouring values that refuse.
"""

from __future__ import annotations

import dataclasses

import pytest

from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.runner_gameplay import (
    BOSS_PROFILES,
    MIN_ENCOUNTER_INTERVAL_COLUMNS,
    PLACEMENT_PROFILES,
    THRUST_PROFILES,
    boss_dodge_window_seconds,
    boss_kill_seconds,
    boss_lane_rows,
    boss_salvo_budget_seconds,
    load_runner_gameplay_bytes,
    thrust_traverse_seconds,
)
from stage_gen.components.runner_track import MAX_SEGMENT_COLUMNS

ENCOUNTER = """
[encounter]
boss_id = "root_warden"
profile = "barrage_boss_v1"
locomotion = "thrust_v1"
interval_columns = 600
arena_segment_id = "arbor_arena"
boss_projectile_id = "spore_bolt"
player_projectile_id = "seed_dart"
"""

BASE = """schema_version = 4
kind = "runner-gameplay-v4"
game_id = "bellweather"
revision = 1
track_id = "sunpetal-sprint"

[run]
speed_profile = "swift_runner_v1"
jump_profile = "double_arc_v1"
collision_box = "torso_v1"
duck_profile = "slide_v1"

[run.consequences]
hazard = "drain_v1"
pit = "drain_and_recover_v1"
crush = "end_run_v1"
shot = "drain_v1"

[run.vitals]
profile = "three_point_v1"
hurt_representation = "blink_v1"

[ramp]
profile = "brisk_ramp_v1"
"""

#: The grid Iron Petal authors, which every worked number below is measured on.
IRON_PETAL_WALK_SURFACE_ROW = 8
IRON_PETAL_PLAYER_HEIGHT_ROWS = 2.80


def test_an_encounter_declares_its_boss_arena_and_both_projectiles() -> None:
    gameplay = load_runner_gameplay_bytes((BASE + ENCOUNTER).encode())

    assert gameplay.encounter is not None
    assert gameplay.encounter.boss_id == "root_warden"
    assert gameplay.encounter.arena_segment_id == "arbor_arena"
    assert gameplay.encounter.boss_projectile_id == "spore_bolt"
    assert gameplay.encounter.player_projectile_id == "seed_dart"
    assert gameplay.encounter.boss_profile() is BOSS_PROFILES["barrage_boss_v1"]
    assert gameplay.encounter.thrust_profile() is THRUST_PROFILES["thrust_v1"]


def test_a_run_without_an_encounter_carries_none() -> None:
    plain = BASE.replace('shot = "drain_v1"\n', "")

    assert load_runner_gameplay_bytes(plain.encode()).encounter is None


def test_an_encounter_without_a_shot_answer_is_refused() -> None:
    document = BASE.replace('shot = "drain_v1"\n', "") + ENCOUNTER

    with pytest.raises(AuthoredContractLoadError, match=r"no \[run\.consequences\] shot answer"):
        load_runner_gameplay_bytes(document.encode())


def test_a_shot_answer_without_an_encounter_is_refused() -> None:
    with pytest.raises(AuthoredContractLoadError, match="no encounter can fire"):
        load_runner_gameplay_bytes(BASE.encode())


def test_one_projectile_flying_both_ways_is_refused() -> None:
    document = BASE + ENCOUNTER.replace(
        'player_projectile_id = "seed_dart"', 'player_projectile_id = "spore_bolt"'
    )

    with pytest.raises(AuthoredContractLoadError, match="draw the two roles separately"):
        load_runner_gameplay_bytes(document.encode())


def test_an_encounter_that_never_lets_the_track_be_seen_is_refused() -> None:
    too_soon = MIN_ENCOUNTER_INTERVAL_COLUMNS - 1
    document = BASE + ENCOUNTER.replace("interval_columns = 600", f"interval_columns = {too_soon}")

    with pytest.raises(AuthoredContractLoadError):
        load_runner_gameplay_bytes(document.encode())


def test_the_floor_is_two_of_the_widest_chunk_the_track_contract_admits() -> None:
    """The floor is arithmetic, not taste, and this is the arithmetic.

    Two widest chunks is the shortest gap in which a whole authored chunk is
    guaranteed to run between two fights however the boundaries fall - one
    would only guarantee it when the previous arena happened to end on one.
    The two components hold the numbers separately, so nothing but this
    assertion stops them drifting apart.
    """

    assert MIN_ENCOUNTER_INTERVAL_COLUMNS == 2 * MAX_SEGMENT_COLUMNS


def test_a_shot_is_answered_like_every_other_damage_source() -> None:
    gameplay = load_runner_gameplay_bytes((BASE + ENCOUNTER).encode())

    assert gameplay.run.consequences.by_source() == {
        "hazard": "drain_v1",
        "pit": "drain_and_recover_v1",
        "crush": "end_run_v1",
        "shot": "drain_v1",
    }


def test_the_traverse_accelerates_to_its_cap_and_then_holds_it() -> None:
    thrust = THRUST_PROFILES["thrust_v1"]

    # The cap is reached after v/a seconds, having covered v^2/2a rows.
    assert thrust_traverse_seconds(thrust, 0.0) == 0.0
    assert thrust_traverse_seconds(thrust, 1.6875) == pytest.approx(0.375)
    # Beyond it the remainder is flown at the cap: 1.6875 rows in 0.375s, then
    # 6.3125 rows at 9.0 rows per second.
    assert thrust_traverse_seconds(thrust, 8.0) == pytest.approx(0.375 + 6.3125 / 9.0)


def test_the_traverse_is_measured_on_the_climb_because_its_cap_is_lower() -> None:
    thrust = THRUST_PROFILES["thrust_v1"]

    assert thrust.max_climb_rows_per_second < thrust.max_fall_rows_per_second


def test_a_salvo_leaves_the_avatar_a_lane_it_fits_in() -> None:
    boss = BOSS_PROFILES["barrage_boss_v1"]

    lane = boss_lane_rows(boss, IRON_PETAL_WALK_SURFACE_ROW)

    assert lane == pytest.approx(5.0)
    assert lane >= IRON_PETAL_PLAYER_HEIGHT_ROWS + boss.lane_margin_rows


def test_one_shot_more_closes_the_lane_the_avatar_needs() -> None:
    boss = BOSS_PROFILES["barrage_boss_v1"]
    crowded = dataclasses.replace(boss, salvo_shots=boss.salvo_shots + 3)

    lane = boss_lane_rows(crowded, IRON_PETAL_WALK_SURFACE_ROW)

    assert lane < IRON_PETAL_PLAYER_HEIGHT_ROWS + crowded.lane_margin_rows


def test_the_dodge_window_keeps_the_placement_discipline() -> None:
    boss = BOSS_PROFILES["barrage_boss_v1"]
    thrust = THRUST_PROFILES["thrust_v1"]
    discipline = PLACEMENT_PROFILES["reaction_fair_v1"].min_hazard_clear_seconds

    window = boss_dodge_window_seconds(boss, thrust, walk_surface_row=IRON_PETAL_WALK_SURFACE_ROW)

    assert window == pytest.approx(10 / 7.5 - thrust_traverse_seconds(thrust, 8.0))
    assert window >= discipline


def test_a_faster_shot_closes_the_dodge_window_below_the_discipline() -> None:
    boss = BOSS_PROFILES["barrage_boss_v1"]
    thrust = THRUST_PROFILES["thrust_v1"]
    discipline = PLACEMENT_PROFILES["reaction_fair_v1"].min_hazard_clear_seconds
    faster = dataclasses.replace(boss, projectile_speed_columns_per_second=9.0)

    window = boss_dodge_window_seconds(faster, thrust, walk_surface_row=IRON_PETAL_WALK_SURFACE_ROW)

    assert window < discipline


def test_the_fight_can_be_won_before_the_boss_runs_out_of_salvos() -> None:
    boss = BOSS_PROFILES["barrage_boss_v1"]

    kill = boss_kill_seconds(boss)

    assert kill == pytest.approx(24 * 0.5 + 10 / 12.0)
    assert kill <= boss_salvo_budget_seconds(boss)
    # The slack is the miss allowance: a player who lands every shot finishes
    # with well over a third of the window they are given still unspent.
    assert kill < boss_salvo_budget_seconds(boss) * 0.6


def test_a_tougher_boss_than_its_budget_allows_is_unwinnable() -> None:
    boss = BOSS_PROFILES["barrage_boss_v1"]
    spongy = dataclasses.replace(boss, hits_to_defeat=64)

    assert boss_kill_seconds(spongy) > boss_salvo_budget_seconds(spongy)
