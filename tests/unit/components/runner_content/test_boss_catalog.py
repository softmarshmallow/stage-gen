"""The runner's boss catalog (`boss-content-v1`).

A boss is the first runner actor that is not the avatar, and the first drawn
thing in the genre with a facing that matters: it holds a position against a
moving avatar and fires at it, so it is drawn facing left and the runtime
mirrors nothing.

These tests hold the catalog's own promises. What an encounter then requires of
it is a cross-member obligation and lives with the package validator.
"""

from __future__ import annotations

import pytest

from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.runner_content import (
    RUNNER_BOSS_BASELINE_STATE,
    RUNNER_BOSS_MOTION_ORDER,
    declared_boss_motion_states,
    load_runner_boss_bytes,
)
from tests.unit._runner_fixture import RUNNER_BOSSES


def test_a_boss_declares_every_state_it_owes() -> None:
    catalog = load_runner_boss_bytes(RUNNER_BOSSES.encode())

    boss = catalog.boss("bramble_harvester")
    assert declared_boss_motion_states(boss) == RUNNER_BOSS_MOTION_ORDER
    assert boss.height_units == 1.8


def test_the_boss_may_loom_over_the_avatar_it_threatens() -> None:
    catalog = load_runner_boss_bytes(RUNNER_BOSSES.encode())

    assert catalog.boss("bramble_harvester").height_units > 1.0


def test_a_missing_state_is_refused() -> None:
    without_death = RUNNER_BOSSES.split('[[bosses.motions]]\nstate = "death"')[0]

    with pytest.raises(AuthoredContractLoadError, match="missing required motion states"):
        load_runner_boss_bytes(without_death.encode())


def test_a_state_outside_the_vocabulary_is_refused() -> None:
    document = RUNNER_BOSSES.replace('state = "attack"', 'state = "taunt"', 1)

    with pytest.raises(AuthoredContractLoadError):
        load_runner_boss_bytes(document.encode())


def test_hover_holds_and_every_other_state_plays_once() -> None:
    catalog = load_runner_boss_bytes(RUNNER_BOSSES.encode())

    modes = {
        entry.state: entry.playback_mode for entry in catalog.boss("bramble_harvester").motions
    }
    assert modes[RUNNER_BOSS_BASELINE_STATE] == "loop"
    assert modes["attack"] == "once"
    assert modes["death"] == "once"


def test_a_looping_attack_is_refused() -> None:
    document = RUNNER_BOSSES.replace(
        'state = "attack"\nplayback_mode = "once"',
        'state = "attack"\nplayback_mode = "loop"',
        1,
    )

    with pytest.raises(AuthoredContractLoadError, match="attack motion must play once"):
        load_runner_boss_bytes(document.encode())


def test_a_hover_that_plays_once_is_refused() -> None:
    document = RUNNER_BOSSES.replace(
        'state = "hover"\nplayback_mode = "loop"',
        'state = "hover"\nplayback_mode = "once"',
        1,
    )

    with pytest.raises(AuthoredContractLoadError, match="hover motion must play loop"):
        load_runner_boss_bytes(document.encode())


def test_a_frame_outside_the_runner_atlas_is_refused() -> None:
    document = RUNNER_BOSSES.replace(
        "canonical_frame_indices = [0, 1, 2, 3]",
        "canonical_frame_indices = [0, 1, 2, 9]",
        1,
    )

    with pytest.raises(AuthoredContractLoadError, match="outside the 4-column runner atlas"):
        load_runner_boss_bytes(document.encode())


def test_an_unused_reference_is_refused() -> None:
    document = RUNNER_BOSSES.replace('reference_ids = ["cover_style"]', "reference_ids = []", 1)

    with pytest.raises(AuthoredContractLoadError):
        load_runner_boss_bytes(document.encode())


def test_a_retired_kind_is_refused() -> None:
    document = RUNNER_BOSSES.replace('kind = "boss-content-v1"', 'kind = "runner-boss-v1"', 1)

    with pytest.raises(AuthoredContractLoadError):
        load_runner_boss_bytes(document.encode())
