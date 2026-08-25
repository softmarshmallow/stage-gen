"""Every predicate that decides how a mob strip is validated must agree, by construction.

A mob's states were spelled out independently in five predicates - the prompt builder, the
producer grid contract, the scale-reference gate, the scale-reference frame choice, and the facing
review. Adding a state meant editing all five, and four of them fail *silently* when one is
missed: no grid validation at all, no scale reference, a head measured inside the anticipation
crouch, and no facing review on artwork that arrives mirrored about half the time.

That is the same defect class that produced three separate silent failures in the village work.
So the states live in `mob_states` and the predicates ask it. These tests assert the agreement
directly, so a predicate that stops asking fails here rather than in a paid run.
"""

from __future__ import annotations

import pytest

from stage_gen.recipes.scrolling_preview.mob_states import (
    BASE_MOB_STRIP_STATES,
    MOB_STRIP_STATES,
    is_mob_strip_runtime_role,
    is_mob_strip_stage,
    mob_strip_artifact,
    mob_strip_runtime_role,
    mob_strip_stage,
    mob_strip_state,
    parse_mob_strip_stage,
)
from stage_gen.recipes.scrolling_preview.raster_contracts import (
    contract_for_runtime_role,
    contract_for_stage,
)
from stage_gen.recipes.scrolling_preview.review_criteria import reviews_facing
from stage_gen.recipes.scrolling_preview.scale_reference import (
    measures_scale_reference,
    scale_reference_frame,
)

STATE_NAMES = tuple(entry.state for entry in MOB_STRIP_STATES)


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_state_is_validated_by_every_predicate(state: str) -> None:
    """The whole point of the module: no state can be half-wired.

    Each assertion here is one of the four silent failures, made loud.
    """

    stage = mob_strip_stage(state, 3)

    contract = contract_for_stage(stage)
    assert contract is not None, "no grid contract means no cell isolation check at all"
    assert (contract.rows, contract.columns) == (1, 4)
    # The mirror check applies only where the state says it does. See the next test.
    assert contract.fixed_side_view_frames is mob_strip_state(state).holds_fixed_side_view

    assert measures_scale_reference(stage) is True, "no reference means an arbitrary drawn size"
    assert reviews_facing(stage) is True, "unreviewed strips arrive mirrored about half the time"

    role_contract = contract_for_runtime_role(mob_strip_runtime_role(3, state))
    assert role_contract is not None
    assert (role_contract.rows, role_contract.columns) == (1, 4)


def test_an_attack_is_measured_on_the_frame_that_stands_the_subject_up() -> None:
    # Frame zero of an attack is the anticipation crouch with the head tucked toward the body.
    # Measuring it reports a head smaller than the creature has, and the head-matched runtime
    # then scales the whole creature up - the exact defect the scale reference exists to prevent.
    assert scale_reference_frame(mob_strip_stage("attack", 0)) == 1
    assert scale_reference_frame(mob_strip_stage("idle", 0)) == 0
    assert scale_reference_frame(mob_strip_stage("hurt", 0)) == 0
    # The character attack rule it mirrors is untouched.
    assert scale_reference_frame("character-attack") == 1


def test_the_states_that_predate_the_attack_system_are_unchanged() -> None:
    # An undirected run must keep its exact two-strip cost, and its prompts must be byte-identical
    # or every cached mob sheet in every existing run stops resuming.
    assert BASE_MOB_STRIP_STATES == ("idle", "hurt")
    assert mob_strip_state("idle").motion == (
        "four visibly distinct phases of a subtle breathing cycle; it stays planted"
    )
    assert mob_strip_state("hurt").motion == (
        "four phases of impact, stagger, settling, and recovery"
    )


def test_an_attack_names_what_it_strikes_with() -> None:
    # `character-attack` was the one pose whose horizontally extended weapon broke cell isolation.
    # A lunging creature extends further than a breathing one, because the reach is the pose.
    attack = mob_strip_state("attack")
    assert "claws" in attack.appendages and "jaws" in attack.appendages
    assert attack.appendages != mob_strip_state("idle").appendages


def test_names_are_constructed_here_and_nowhere_else() -> None:
    assert mob_strip_stage("attack", 7) == "mob-attack-7"
    assert mob_strip_artifact("run-tag", 7, "attack") == "mob_run-tag_7_attack.png"
    # The runtime role deliberately reverses the order, because that is what the manifest and the
    # web runtime already publish for idle and hurt.
    assert mob_strip_runtime_role(7, "attack") == "mob-7-attack"
    assert mob_strip_stage("idle", 0) == "mob-idle-0"
    assert mob_strip_artifact("t", 0, "idle") == "mob_t_0_idle.png"


def test_a_turnaround_is_not_a_strip() -> None:
    # Both directions. A predicate that matched a bare `mob-` prefix would pull the three-view
    # concept sheet into the four-frame side-view contract and reject correct artwork.
    assert is_mob_strip_stage("mob-concept-0") is False
    assert is_mob_strip_runtime_role("mob-concept-0") is False
    assert parse_mob_strip_stage("mob-concept-0") is None
    concept = contract_for_stage("mob-concept-0")
    assert concept is not None and concept.columns == 3


@pytest.mark.parametrize(
    "stage", ["mob-", "mob-idle-", "mob-idle-x", "mob-bogus-1", "mobidle-1", "", "village-npc-0"]
)
def test_a_malformed_name_is_not_a_strip(stage: str) -> None:
    assert is_mob_strip_stage(stage) is False
    assert parse_mob_strip_stage(stage) is None


def test_parsing_recovers_the_state_and_slot() -> None:
    assert parse_mob_strip_stage("mob-attack-11") == ("attack", 11)
    assert parse_mob_strip_stage("mob-idle-0") == ("idle", 0)


def test_an_unknown_state_fails_by_name() -> None:
    with pytest.raises(ValueError, match="unknown mob strip state"):
        mob_strip_state("rampage")


def test_a_strike_is_exempt_from_the_mirror_check_exactly_as_the_player_is() -> None:
    """The deterministic mirror check cannot tell a big pose reversal from a flip.

    It measures how much better two frames match when one is flipped. That is a sound proxy for a
    breathing or staggering creature, whose pose barely moves. A strike is different: a serpentine
    body coils one way and lashes the other, which is a legitimate reversal of curvature and is
    indistinguishable from a mirror under pixel overlap.

    Measured, not assumed - a Ribbon Newt ("serpentine, with fins, whiskers, and no legs")
    exhausted all six provider attempts at 0.10 over its ceiling. `character-attack` was already
    the one character state excluded from this check for the same reason, so a mob's attack
    follows the precedent rather than inventing a new rule.
    """

    attack = contract_for_stage(mob_strip_stage("attack", 3))
    character = contract_for_stage("character-attack")
    assert attack is not None and character is not None
    assert attack.fixed_side_view_frames is False
    # Identical to the contract the player's attack already uses.
    assert (attack.rows, attack.columns, attack.gutter, attack.anchor) == (
        character.rows,
        character.columns,
        character.gutter,
        character.anchor,
    )
    assert attack.fixed_side_view_frames == character.fixed_side_view_frames

    # The states whose pose barely moves keep the check.
    for state in ("idle", "hurt"):
        held = contract_for_stage(mob_strip_stage(state, 3))
        assert held is not None and held.fixed_side_view_frames is True


def test_dropping_the_mirror_check_does_not_drop_the_facing_contract() -> None:
    # This is the guard that makes the exemption safe: facing is still enforced, by the vision
    # review that reads where the eyes point rather than by counting overlapping pixels.
    assert reviews_facing(mob_strip_stage("attack", 3)) is True
