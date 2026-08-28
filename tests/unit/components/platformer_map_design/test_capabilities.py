"""What a profile refuses to describe, and what its movement envelope actually promises."""

from __future__ import annotations

import pytest

from stage_gen.components.platformer_map_design import (
    EMPTY_TILE_ROLE,
    GROUND_TILE_ROLE,
    PLATFORM_TILE_ROLE,
    GeometryProfile,
    MovementProfile,
    PlatformerProfile,
    TileRole,
)

from ._profiles import CHAINED_SHAFT_PROFILE, GROUND_FOOTED_PROFILE


def test_a_tile_role_symbol_must_be_exactly_one_character() -> None:
    with pytest.raises(ValueError, match="exactly one character"):
        TileRole("##", "ground", "two characters is not a tile")
    with pytest.raises(ValueError, match="exactly one character"):
        TileRole("", "nothing", "no symbol at all")


def test_a_profile_without_a_grounded_role_is_rejected() -> None:
    with pytest.raises(ValueError, match="grounded role"):
        PlatformerProfile(
            profile_id="floorless",
            movement=GROUND_FOOTED_PROFILE.movement,
            geometry=GROUND_FOOTED_PROFILE.geometry,
            roles=(EMPTY_TILE_ROLE, PLATFORM_TILE_ROLE),
        )


def test_a_profile_with_duplicate_role_symbols_is_rejected() -> None:
    twin = TileRole("#", "scaffold", "a second role wearing the ground's symbol")
    with pytest.raises(ValueError, match="unique"):
        PlatformerProfile(
            profile_id="ambiguous-alphabet",
            movement=GROUND_FOOTED_PROFILE.movement,
            geometry=GROUND_FOOTED_PROFILE.geometry,
            roles=(EMPTY_TILE_ROLE, GROUND_TILE_ROLE, twin),
        )


def test_a_profile_without_an_empty_role_cannot_name_one() -> None:
    profile = PlatformerProfile(
        profile_id="airless",
        movement=GROUND_FOOTED_PROFILE.movement,
        geometry=GROUND_FOOTED_PROFILE.geometry,
        roles=(GROUND_TILE_ROLE, PLATFORM_TILE_ROLE),
    )
    with pytest.raises(ValueError, match="empty role"):
        _ = profile.empty_role


def test_an_inverted_ground_depth_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="inverted"):
        GeometryProfile(
            columns=32,
            rows=16,
            ground_depth_tiles=(6, 2),
            max_walkable_height_tiles=12,
        )


def test_a_ground_depth_below_one_tile_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one floor tile"):
        GeometryProfile(
            columns=32,
            rows=16,
            ground_depth_tiles=(0, 4),
            max_walkable_height_tiles=12,
        )


def test_a_framing_budget_above_the_grid_height_is_rejected() -> None:
    with pytest.raises(ValueError, match="framing budget"):
        GeometryProfile(
            columns=32,
            rows=16,
            ground_depth_tiles=(1, 4),
            max_walkable_height_tiles=17,
        )


def test_a_movement_profile_needs_at_least_one_positive_climbable_rise() -> None:
    with pytest.raises(ValueError, match="at least one climbable rise"):
        MovementProfile(max_step_up_tiles=2, jump_reach={1: 4}, climbable_rise_tiles=())
    with pytest.raises(ValueError, match="climbable rises must be positive"):
        MovementProfile(max_step_up_tiles=2, jump_reach={1: 4}, climbable_rise_tiles=(0,))
    with pytest.raises(ValueError, match="cannot be negative"):
        MovementProfile(max_step_up_tiles=-1, jump_reach={1: 4}, climbable_rise_tiles=(4,))


def test_reachable_honours_jump_reach_and_refuses_a_rise_the_game_never_measured() -> None:
    movement = GROUND_FOOTED_PROFILE.movement

    assert movement.reachable(1, 8) is True
    assert movement.reachable(1, 9) is False
    assert movement.reachable(2, 6) is True
    assert movement.reachable(2, 7) is False
    # Rise 3 is absent from this game's measurements, so it is impossible at any gap.
    assert movement.reachable(3, 0) is False
    assert movement.max_jumpable_rise == 2
    # The other game measured further, and the same call answers differently.
    assert CHAINED_SHAFT_PROFILE.movement.reachable(3, 6) is True
    assert CHAINED_SHAFT_PROFILE.movement.max_jumpable_rise == 4


def test_a_level_or_downward_move_is_bounded_by_level_gap_tiles() -> None:
    """Treating any drop as free silently connects surfaces a whole screen apart."""

    movement = GROUND_FOOTED_PROFILE.movement

    assert movement.reachable(0, 8) is True
    assert movement.reachable(0, 9) is False
    assert movement.reachable(-5, 8) is True
    assert movement.reachable(-5, 9) is False

    unbounded_by_default = MovementProfile(
        max_step_up_tiles=2, jump_reach={1: 4}, climbable_rise_tiles=(4,)
    )
    assert unbounded_by_default.level_gap_tiles == 0
    assert unbounded_by_default.reachable(0, 0) is True
    assert unbounded_by_default.reachable(0, 1) is False
    assert unbounded_by_default.reachable(-9, 1) is False


def test_a_profile_sorts_its_own_alphabet_into_floor_platforms_and_solids() -> None:
    profile = GROUND_FOOTED_PROFILE

    assert profile.empty_role is EMPTY_TILE_ROLE
    assert profile.ground_role is GROUND_TILE_ROLE
    assert profile.platform_roles == (PLATFORM_TILE_ROLE,)
    assert profile.solid_symbols == frozenset({"#", "="})
