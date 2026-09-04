"""The validator: every rule it enforces comes from the profile it was handed, not from a game.

Most rules here are proved by a PAIR of assertions on one identical grid: the profile that
forbids the shape reports it, and the profile that permits it stays silent. A rejecting
assertion alone would still pass if the rule were hard-coded rather than read from the profile,
so the accepting half is what makes each of these a proof about the profile and not about the
map.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence

import pytest

from stage_gen.components.sideview_map_design import (
    PLATFORMER_MAP_DESIGN_KIND,
    PLATFORMER_MAP_DESIGN_SCHEMA_VERSION,
    Climbable,
    DesignedMap,
    PlatformerChunkMapDesign,
    PlatformerMapDesignLoadError,
    PlatformerProfile,
    canonical_platformer_chunk_map_design_json,
    check,
    expand_chunks,
    load_platformer_chunk_map_design_bytes,
    translate,
    unreachable,
)

from ._profiles import CHAINED_SHAFT_PROFILE, GROUND_FOOTED_PROFILE

#: (start_column, end_column, height_tiles); the end column is exclusive.
Platform = tuple[int, int, int]


def _build(
    profile: PlatformerProfile,
    *,
    columns: int,
    rows: int,
    floor: Sequence[int],
    platforms: Sequence[Platform] = (),
    climbables: Sequence[Climbable] = (),
    column_biomes: list[str] | None = None,
) -> DesignedMap:
    """Draw a grid the way a consumer would: a heightfield, then floating platforms on top."""

    ground = profile.ground_role.symbol
    platform = profile.platform_roles[0].symbol
    empty = profile.empty_role.symbol
    grid = [
        "".join(
            ground
            if height <= floor[column]
            else platform
            if any(height == top and start <= column < end for start, end, top in platforms)
            else empty
            for column in range(columns)
        )
        for height in range(1, rows + 1)
    ]
    return DesignedMap(
        profile.profile_id,
        columns,
        rows,
        grid,
        list(climbables),
        column_biomes=column_biomes,
    )


def _ladder_fed_map(column_biomes: list[str] | None = None) -> DesignedMap:
    """A small, sound ground-footed map: flat floor, one platform, three ladders to it."""

    return _build(
        GROUND_FOOTED_PROFILE,
        columns=24,
        rows=16,
        floor=[2] * 24,
        platforms=[(4, 16, 6)],
        climbables=[
            Climbable("a", "root_ladder", 5, 4),
            Climbable("b", "root_ladder", 8, 4),
            Climbable("c", "rope_climb", 11, 4),
        ],
        column_biomes=column_biomes,
    )


def _handed_to_the_chained_game(
    designed: DesignedMap, climbables: Sequence[Climbable]
) -> DesignedMap:
    """The IDENTICAL grid, offered to the other game with climbables that game can name.

    The two profiles declare different climbable variants and different climbable counts, so a
    map cannot carry one list across both. Everything that decides the rule under test -- the
    grid itself -- is shared by reference.
    """

    return DesignedMap(
        CHAINED_SHAFT_PROFILE.profile_id,
        designed.columns,
        designed.rows,
        designed.grid,
        list(climbables),
    )


def _chained_shaft(
    climbables: Sequence[Climbable], column_biomes: list[str] | None = None
) -> DesignedMap:
    """Four stacked platforms in one column, the shape a chained shaft is drawn as."""

    return _build(
        CHAINED_SHAFT_PROFILE,
        columns=64,
        rows=32,
        floor=[2] * 64,
        platforms=[(10, 19, 6), (10, 17, 10), (10, 18, 14), (10, 16, 18)],
        climbables=climbables,
        column_biomes=column_biomes,
    )


def _ground_footed_sentence() -> dict[str, object]:
    return {
        "design_notes": "a breather, a climb, a dip, and a jump chain",
        "start_height_tiles": 3,
        "chunks": [
            {"kind": "run", "len": 10},
            {"kind": "stairs", "steps": 2, "step_h": 1, "tread": 4, "dir": "up"},
            {"kind": "perch", "platform_width": 6, "climb_rise": 4, "variant": "root_ladder"},
            {"kind": "hollow", "width": 8, "depth": 2},
            {"kind": "perch", "platform_width": 5, "climb_rise": 4, "variant": "rope_climb"},
            {
                "kind": "hop_chain",
                "count": 3,
                "jump_rise": 1,
                "gap": 4,
                "platform_width": 4,
                "dir": "up",
            },
            {
                "kind": "perch",
                "platform_width": 7,
                "climb_rise": 4,
                "variant": "shrine_rope_ladder",
            },
            {"kind": "run", "len": 20},
        ],
    }


def test_a_sound_ground_footed_sentence_validates_clean() -> None:
    designed, errors, spans = expand_chunks(_ground_footed_sentence(), GROUND_FOOTED_PROFILE, 128)

    assert errors + translate(check(designed, GROUND_FOOTED_PROFILE), spans) == []


def test_a_chained_shaft_validates_where_climbables_may_stand_on_platforms() -> None:
    """Four ladders share one column at four foot heights: a shaft, not a mistake.

    ``climbable_footing`` is the single field this profile exists to exercise, so the same shaft
    is judged again under a copy that differs in that one field and nothing else. Three of the
    four ladders stand on platforms rather than on terrain, and a ground-footed game must say so.
    """

    shaft = _chained_shaft(
        [
            Climbable(f"m{index}", "iron_ladder", 12, 4, foot)
            for index, foot in enumerate([2, 6, 10, 14])
        ]
    )
    ground_footing_only = dataclasses.replace(
        CHAINED_SHAFT_PROFILE,
        movement=dataclasses.replace(CHAINED_SHAFT_PROFILE.movement, climbable_footing="ground"),
    )

    assert check(shaft, CHAINED_SHAFT_PROFILE) == []
    assert check(shaft, ground_footing_only) == [
        "climbable m1 has no ground surface to stand on at column 12",
        "climbable m2 has no ground surface to stand on at column 12",
        "climbable m3 has no ground surface to stand on at column 12",
    ]


def test_the_same_grid_is_stranded_under_ground_footing_and_sound_where_the_game_chains() -> None:
    """The agnosticism proof: one grid, two games, two honest verdicts and no branch.

    A platform four tiles above another platform is out of reach for a game whose jump was
    measured at rises 1 and 2, and an ordinary hop for a game that measured rise 4. Nothing in
    the component knows which game it is looking at.

    The contrast here is ``jump_reach`` ALONE. Read no footing claim into it: the chained game
    reaches the upper platform by jumping, and the same grid with an empty climbable list still
    answers ``unreachable() == []``. ``climbable_footing`` is proved separately, in
    ``test_a_chained_shaft_validates_where_climbables_may_stand_on_platforms``.
    """

    columns, rows, floor = 24, 16, [2] * 24
    two_storey = _build(
        GROUND_FOOTED_PROFILE,
        columns=columns,
        rows=rows,
        floor=floor,
        platforms=[(4, 16, 6), (8, 18, 10)],
        climbables=[
            Climbable("a", "root_ladder", 5, 4),
            Climbable("b", "root_ladder", 9, 4),
            Climbable("c", "rope_climb", 13, 4),
        ],
    )
    same_grid = DesignedMap(
        CHAINED_SHAFT_PROFILE.profile_id,
        columns,
        rows,
        two_storey.grid,
        [
            Climbable("a", "iron_ladder", 5, 4),
            Climbable("b", "iron_ladder", 9, 4),
            Climbable("c", "chain", 13, 4),
            Climbable("d", "chain", 15, 4),
        ],
    )

    assert same_grid.grid == two_storey.grid
    # The claim in the docstring, made executable: strip every climbable and the chained game
    # still reaches everything, because it is the jump envelope doing the work here.
    without_climbables = DesignedMap(
        CHAINED_SHAFT_PROFILE.profile_id, columns, rows, two_storey.grid, []
    )
    assert unreachable(without_climbables, CHAINED_SHAFT_PROFILE) == []
    assert unreachable(two_storey, GROUND_FOOTED_PROFILE) == ["s-h10-c8"]
    assert check(two_storey, GROUND_FOOTED_PROFILE) == ["1 surface(s) cannot be reached: s-h10-c8"]
    assert unreachable(same_grid, CHAINED_SHAFT_PROFILE) == []
    assert check(same_grid, CHAINED_SHAFT_PROFILE) == []


def test_a_platform_nobody_can_reach_is_reported_as_stranded() -> None:
    """Three platforms, three ladders -- but two ladders serve the same platform."""

    platforms: list[Platform] = [(20, 28, 7), (60, 66, 7), (100, 107, 7)]
    served = _build(
        GROUND_FOOTED_PROFILE,
        columns=128,
        rows=16,
        floor=[3] * 128,
        platforms=platforms,
        climbables=[
            Climbable(f"c{index}", "root_ladder", column, 4, 3)
            for index, column in enumerate([22, 62, 102])
        ],
    )
    lonely = _build(
        GROUND_FOOTED_PROFILE,
        columns=128,
        rows=16,
        floor=[3] * 128,
        platforms=platforms,
        climbables=[
            Climbable("c0", "root_ladder", 22, 4, 3),
            Climbable("c1", "root_ladder", 62, 4, 3),
            Climbable("c2", "root_ladder", 23, 4, 3),
        ],
    )

    assert check(served, GROUND_FOOTED_PROFILE) == []
    assert unreachable(lonely, GROUND_FOOTED_PROFILE) == ["s-h7-c100"]
    assert check(lonely, GROUND_FOOTED_PROFILE) == ["1 surface(s) cannot be reached: s-h7-c100"]


def test_a_column_floor_outside_the_profiles_depth_range_is_rejected() -> None:
    """A six-tile floor: within one game's rendering budget, and eating the other's playfield."""

    deep = _build(
        GROUND_FOOTED_PROFILE,
        columns=24,
        rows=16,
        floor=[6] * 24,
        platforms=[(4, 16, 10)],
        climbables=[
            Climbable("a", "root_ladder", 5, 4, 6),
            Climbable("b", "root_ladder", 8, 4, 6),
            Climbable("c", "rope_climb", 11, 4, 6),
        ],
    )
    same_grid = _handed_to_the_chained_game(
        deep,
        [
            Climbable("a", "iron_ladder", 5, 4, 6),
            Climbable("b", "iron_ladder", 8, 4, 6),
            Climbable("c", "chain", 11, 4, 6),
            Climbable("d", "chain", 14, 4, 6),
        ],
    )

    assert check(deep, GROUND_FOOTED_PROFILE) == []
    assert check(same_grid, CHAINED_SHAFT_PROFILE) == [
        "column 0 floor is 6 tiles, outside the profile's 1..4"
    ]


def test_a_step_above_the_profiles_unassisted_maximum_is_rejected() -> None:
    """A three-tile step: a wall to a game that measured two, a stride to one that measured 3."""

    stepped = _build(
        GROUND_FOOTED_PROFILE,
        columns=24,
        rows=16,
        floor=[1] * 12 + [4] * 12,
        platforms=[(2, 10, 5)],
        climbables=[
            Climbable("a", "root_ladder", 3, 4, 1),
            Climbable("b", "root_ladder", 5, 4, 1),
            Climbable("c", "rope_climb", 7, 4, 1),
        ],
    )
    same_grid = _handed_to_the_chained_game(
        stepped,
        [
            Climbable("a", "iron_ladder", 3, 4, 1),
            Climbable("b", "iron_ladder", 5, 4, 1),
            Climbable("c", "chain", 7, 4, 1),
            Climbable("d", "chain", 8, 4, 1),
        ],
    )

    assert check(stepped, GROUND_FOOTED_PROFILE) == [
        "columns 11-12 step 3 tiles, above the profile's unassisted maximum of 2"
    ]
    assert check(same_grid, CHAINED_SHAFT_PROFILE) == []


def test_a_surface_above_the_profiles_walkable_ceiling_is_rejected() -> None:
    """The ceiling is a framing budget, not a grid bound: the same 16-row grid fits one game only.

    Five overlapping platforms climb by two tiles each, a rise both games can jump, so nothing
    here is stranded under either profile. Only the topmost one crosses the shorter game's
    twelve-tile framing budget, and that is the surface named.
    """

    staircase = _build(
        GROUND_FOOTED_PROFILE,
        columns=42,
        rows=16,
        floor=[2] * 42,
        platforms=[(3, 12, 6), (11, 20, 8), (19, 28, 10), (27, 36, 12), (35, 42, 14)],
        climbables=[
            Climbable("a", "root_ladder", 4, 4, 2),
            Climbable("b", "root_ladder", 6, 4, 2),
            Climbable("c", "rope_climb", 8, 4, 2),
        ],
    )
    same_grid = _handed_to_the_chained_game(
        staircase,
        [
            Climbable("a", "iron_ladder", 4, 4, 2),
            Climbable("b", "iron_ladder", 6, 4, 2),
            Climbable("c", "chain", 8, 4, 2),
            Climbable("d", "chain", 10, 4, 2),
        ],
    )

    assert check(staircase, GROUND_FOOTED_PROFILE) == [
        "surface s-h14-c35 sits at 14 tiles, above the profile's walkable ceiling of 12"
    ]
    assert check(same_grid, CHAINED_SHAFT_PROFILE) == []


def test_a_two_tile_thick_platform_is_rejected_only_where_the_profile_demands_one_tile() -> None:
    """One map, two profiles differing in ``platforms_single_thickness`` and in nothing else.

    A rejecting assertion alone would pass just as happily against a validator that always
    demanded single-thickness platforms, which is precisely the hard-coded reading of this
    field. The accepting half is what proves the field is read: a game whose consumer gives a
    platform's whole body collision is entitled to draw one two tiles deep.
    """

    thick = _build(
        GROUND_FOOTED_PROFILE,
        columns=24,
        rows=16,
        floor=[2] * 24,
        # The same span drawn at two adjacent heights: one platform with a body, not two.
        platforms=[(4, 20, 5), (4, 20, 6)],
        climbables=[
            Climbable("a", "root_ladder", 5, 4, 2),
            Climbable("b", "root_ladder", 8, 4, 2),
            Climbable("c", "rope_climb", 11, 4, 2),
        ],
    )
    thickness_free = dataclasses.replace(
        GROUND_FOOTED_PROFILE,
        geometry=dataclasses.replace(
            GROUND_FOOTED_PROFILE.geometry, platforms_single_thickness=False
        ),
    )

    assert check(thick, thickness_free) == []
    assert check(thick, GROUND_FOOTED_PROFILE) == [
        "platform s-h6-c4 is more than one tile thick; the profile says only its top surface "
        "would carry collision"
    ]


def test_ten_climbables_sit_inside_one_games_budget_and_overrun_the_others() -> None:
    """The count is a range each game declares, not a number the validator knows.

    Ten is comfortably inside the chained game's 4..12 and two over the ground-footed game's
    3..8. The grid is shared by reference; only the climbable lists differ, and they differ
    solely because the two games declare disjoint variant names.
    """

    columns, rows = 60, 16
    footed_ladders = [
        Climbable(f"c{index}", "root_ladder", column, 4, 2)
        for index, column in enumerate(range(5, 35, 3))
    ]
    crowded = _build(
        GROUND_FOOTED_PROFILE,
        columns=columns,
        rows=rows,
        floor=[2] * columns,
        platforms=[(4, 56, 6)],
        climbables=footed_ladders,
    )
    same_grid = _handed_to_the_chained_game(
        crowded,
        [
            Climbable(f"c{index}", "iron_ladder", column, 4, 2)
            for index, column in enumerate(range(5, 35, 3))
        ],
    )

    assert len(crowded.climbables) == len(same_grid.climbables) == 10
    assert check(same_grid, CHAINED_SHAFT_PROFILE) == []
    assert check(crowded, GROUND_FOOTED_PROFILE) == ["10 climbables, outside the profile's 3..8"]


def test_a_game_that_draws_every_variant_rejects_a_design_that_skips_one() -> None:
    """The rule is declared, not assumed: the same map passes the profile that does not ask."""

    columns, rows = 40, 16
    ladders_only = [
        Climbable("c0", "root_ladder", 5, 4, 2),
        Climbable("c1", "root_ladder", 12, 4, 2),
        Climbable("c2", "shrine_rope_ladder", 19, 4, 2),
    ]
    designed = _build(
        GROUND_FOOTED_PROFILE,
        columns=columns,
        rows=rows,
        floor=[2] * columns,
        platforms=[(4, 36, 6)],
        climbables=ladders_only,
    )
    demanding = dataclasses.replace(GROUND_FOOTED_PROFILE, climbable_variants_each_placed=True)

    assert check(designed, GROUND_FOOTED_PROFILE) == []
    assert check(designed, demanding) == [
        "declared climbable variant(s) never placed: rope_climb; this game draws every "
        "declared variant, so the design must use each at least once"
    ]


def test_a_climbable_naming_a_variant_this_game_cannot_draw_is_rejected() -> None:
    """A variant the consumer cannot draw is a lie the designer would otherwise be free to tell."""

    iron = _build(
        GROUND_FOOTED_PROFILE,
        columns=24,
        rows=16,
        floor=[2] * 24,
        platforms=[(4, 20, 6)],
        climbables=[
            Climbable("a", "iron_ladder", 5, 4, 2),
            Climbable("b", "iron_ladder", 8, 4, 2),
            Climbable("c", "iron_ladder", 11, 4, 2),
            Climbable("d", "iron_ladder", 14, 4, 2),
        ],
    )
    same_grid = _handed_to_the_chained_game(iron, iron.climbables)

    assert check(iron, GROUND_FOOTED_PROFILE) == [
        "climbable a names an undeclared variant",
        "climbable b names an undeclared variant",
        "climbable c names an undeclared variant",
        "climbable d names an undeclared variant",
    ]
    # The other game declares ``iron_ladder``, and the very same climbables are fine there.
    assert check(same_grid, CHAINED_SHAFT_PROFILE) == []


def test_a_climbable_rise_the_profile_does_not_permit_is_rejected() -> None:
    """One game pins the rise at exactly four tiles; the other offers a choice of four lengths."""

    tall = _build(
        GROUND_FOOTED_PROFILE,
        columns=24,
        rows=16,
        floor=[2] * 24,
        platforms=[(4, 20, 7)],
        climbables=[
            Climbable("a", "root_ladder", 5, 5, 2),
            Climbable("b", "root_ladder", 8, 5, 2),
            Climbable("c", "rope_climb", 11, 5, 2),
            Climbable("d", "rope_climb", 14, 5, 2),
        ],
    )
    same_grid = _handed_to_the_chained_game(
        tall,
        [
            Climbable("a", "iron_ladder", 5, 5, 2),
            Climbable("b", "iron_ladder", 8, 5, 2),
            Climbable("c", "chain", 11, 5, 2),
            Climbable("d", "chain", 14, 5, 2),
        ],
    )

    assert check(tall, GROUND_FOOTED_PROFILE) == [
        "climbable a rises 5, and the profile permits [4]",
        "climbable b rises 5, and the profile permits [4]",
        "climbable c rises 5, and the profile permits [4]",
        "climbable d rises 5, and the profile permits [4]",
    ]
    assert check(same_grid, CHAINED_SHAFT_PROFILE) == []


def test_a_climbable_whose_foot_column_is_off_the_grid_is_rejected() -> None:
    """The grid's own width, not a profile threshold, so both games answer identically."""

    base = _ladder_fed_map()
    off_grid = DesignedMap(
        GROUND_FOOTED_PROFILE.profile_id,
        24,
        16,
        base.grid,
        [*base.climbables, Climbable("d", "rope_climb", 30, 4, 2)],
    )
    same_grid = _handed_to_the_chained_game(
        off_grid,
        [
            Climbable("a", "iron_ladder", 5, 4),
            Climbable("b", "iron_ladder", 8, 4),
            Climbable("c", "chain", 11, 4),
            Climbable("d", "chain", 30, 4),
        ],
    )

    assert check(base, GROUND_FOOTED_PROFILE) == []
    assert check(off_grid, GROUND_FOOTED_PROFILE) == ["climbable d is outside the grid"]
    assert check(same_grid, CHAINED_SHAFT_PROFILE) == ["climbable d is outside the grid"]


def test_two_climbables_sharing_a_column_and_a_foot_height_are_rejected() -> None:
    """Collision is keyed on column AND height: sharing a column is how a shaft chains upward.

    The accepting half is the four-storey shaft itself, where every ladder shares column 12.
    Only the fifth ladder, which repeats an existing foot height, is a real duplicate.
    """

    shaft = _chained_shaft(
        [
            Climbable(f"m{index}", "iron_ladder", 12, 4, foot)
            for index, foot in enumerate([2, 6, 10, 14])
        ]
    )
    doubled = _chained_shaft(
        [
            Climbable("m0", "iron_ladder", 12, 4, 2),
            Climbable("m1", "iron_ladder", 12, 4, 6),
            Climbable("m2", "chain", 12, 4, 6),
            Climbable("m3", "iron_ladder", 12, 4, 10),
            Climbable("m4", "iron_ladder", 12, 4, 14),
        ]
    )

    assert check(shaft, CHAINED_SHAFT_PROFILE) == []
    assert check(doubled, CHAINED_SHAFT_PROFILE) == ["two climbables stand at column 12 height 6"]


def test_a_climbable_with_no_footing_surface_at_its_column_is_rejected() -> None:
    """A declared foot height that no surface occupies leaves the climbable standing on nothing."""

    base = _build(
        GROUND_FOOTED_PROFILE,
        columns=24,
        rows=16,
        floor=[2] * 24,
        platforms=[(4, 16, 6)],
        climbables=[
            Climbable("a", "root_ladder", 5, 4, 2),
            Climbable("b", "root_ladder", 8, 4, 2),
            Climbable("c", "rope_climb", 11, 4, 2),
        ],
    )
    footless = DesignedMap(
        GROUND_FOOTED_PROFILE.profile_id,
        24,
        16,
        base.grid,
        [*base.climbables[:2], Climbable("c", "rope_climb", 11, 4, 4)],
    )

    assert check(base, GROUND_FOOTED_PROFILE) == []
    assert check(footless, GROUND_FOOTED_PROFILE) == [
        "climbable c has no ground surface to stand on at column 11"
    ]


def test_a_climbable_whose_rise_lands_on_empty_air_is_rejected() -> None:
    airborne = _build(
        GROUND_FOOTED_PROFILE,
        columns=24,
        rows=16,
        floor=[2] * 24,
        platforms=[(4, 16, 7)],
        climbables=[
            Climbable("a", "root_ladder", 5, 4),
            Climbable("b", "root_ladder", 8, 4),
            Climbable("c", "root_ladder", 11, 4),
        ],
    )

    problems = check(airborne, GROUND_FOOTED_PROFILE)

    assert "climbable a rises to 6 tiles where there is no surface to step onto" in problems


def test_a_climbable_on_the_last_column_is_rejected_where_the_profile_needs_flat_footing() -> None:
    edged = _build(
        GROUND_FOOTED_PROFILE,
        columns=24,
        rows=16,
        floor=[2] * 24,
        platforms=[(4, 24, 6)],
        climbables=[
            Climbable("a", "root_ladder", 5, 4),
            Climbable("b", "root_ladder", 8, 4),
            Climbable("z", "root_ladder", 23, 4),
        ],
    )

    same_grid = _handed_to_the_chained_game(
        edged,
        [
            Climbable("a", "iron_ladder", 5, 4),
            Climbable("b", "iron_ladder", 8, 4),
            Climbable("y", "chain", 14, 4),
            Climbable("z", "chain", 23, 4),
        ],
    )

    assert check(edged, GROUND_FOOTED_PROFILE) == [
        "climbable z is on the last column and the profile needs a right-hand neighbour"
    ]
    # The other game asks for no neighbour, so the very same map is wholly sound there.
    assert check(same_grid, CHAINED_SHAFT_PROFILE) == []


def test_a_climbable_standing_on_a_step_is_rejected_where_the_profile_needs_flat_footing() -> None:
    floor = [2] * 24
    floor[6] = 3
    stepped = _build(
        GROUND_FOOTED_PROFILE,
        columns=24,
        rows=16,
        floor=floor,
        platforms=[(4, 16, 6)],
        climbables=[
            Climbable("a", "root_ladder", 5, 4),
            Climbable("b", "root_ladder", 9, 4),
            Climbable("c", "rope_climb", 11, 4),
        ],
    )

    problems = check(stepped, GROUND_FOOTED_PROFILE)

    assert "climbable a needs level footing: columns 5 and 6 differ" in problems


def test_a_cell_labelled_ground_that_does_not_reach_the_floor_is_rejected() -> None:
    base = _ladder_fed_map()
    rows = list(base.grid)
    rows[5] = rows[5][:6] + GROUND_FOOTED_PROFILE.ground_role.symbol + rows[5][7:]
    floating_ground = DesignedMap(GROUND_FOOTED_PROFILE.profile_id, 24, 16, rows, base.climbables)

    problems = check(floating_ground, GROUND_FOOTED_PROFILE)

    assert problems[0] == "column 6 height 6 is labelled ground but does not reach the floor"


def test_a_floor_depth_problem_does_not_hide_a_mislabelled_cell() -> None:
    """Two independent faults, two messages. The scans must not read each other's verdicts.

    The floor-depth complaint and the role-honesty complaint both begin with the word "column",
    so a role-honesty scan that stopped on ``problems[-1].startswith("column")`` would abandon
    itself on its first iteration on any map that already had a floor problem -- and every
    mislabelled cell on such a map would go unreported.
    """

    base = _build(
        CHAINED_SHAFT_PROFILE,
        columns=24,
        rows=16,
        floor=[5] * 24,
        platforms=[(3, 12, 9)],
        climbables=[
            Climbable("a", "iron_ladder", 4, 4, 5),
            Climbable("b", "iron_ladder", 6, 4, 5),
            Climbable("c", "chain", 8, 4, 5),
            Climbable("d", "chain", 10, 4, 5),
        ],
    )
    rows = list(base.grid)
    rows[7] = rows[7][:20] + CHAINED_SHAFT_PROFILE.ground_role.symbol + rows[7][21:]
    both = DesignedMap(CHAINED_SHAFT_PROFILE.profile_id, 24, 16, rows, list(base.climbables))

    assert check(base, CHAINED_SHAFT_PROFILE) == [
        "column 0 floor is 5 tiles, outside the profile's 1..4"
    ]
    assert check(both, CHAINED_SHAFT_PROFILE) == [
        "column 0 floor is 5 tiles, outside the profile's 1..4",
        "column 20 height 8 is labelled ground but does not reach the floor",
    ]


def test_a_cell_labelled_platform_inside_the_floor_stack_is_rejected() -> None:
    """A platform symbol buried in the terrain breaks the column it was drawn into.

    The floor stack is defined as unbroken ground rising from the bottom, so a platform placed
    inside it necessarily cuts the stack short: the ground above the intrusion is what the
    validator names, and the platform itself is reported as thicker than one tile.
    """

    base = _build(
        GROUND_FOOTED_PROFILE,
        columns=24,
        rows=16,
        floor=[3] * 24,
        platforms=[(4, 16, 7)],
        climbables=[
            Climbable("a", "root_ladder", 5, 4, 3),
            Climbable("b", "root_ladder", 8, 4, 3),
            Climbable("c", "rope_climb", 11, 4, 3),
        ],
    )
    assert check(base, GROUND_FOOTED_PROFILE) == []

    rows = list(base.grid)
    buried = GROUND_FOOTED_PROFILE.platform_roles[0].symbol
    rows[1] = rows[1][:9] + buried + rows[1][10:]
    intruded = DesignedMap(GROUND_FOOTED_PROFILE.profile_id, 24, 16, rows, base.climbables)

    problems = check(intruded, GROUND_FOOTED_PROFILE)

    assert "column 9 height 3 is labelled ground but does not reach the floor" in problems
    assert any("is more than one tile thick" in problem for problem in problems)


def test_a_grid_with_the_wrong_number_of_rows_is_rejected() -> None:
    base = _ladder_fed_map()
    short = DesignedMap(GROUND_FOOTED_PROFILE.profile_id, 24, 16, base.grid[:-1], [])

    assert check(short, GROUND_FOOTED_PROFILE) == ["grid has 15 rows, expected 16"]


def test_a_row_of_the_wrong_width_is_rejected() -> None:
    base = _ladder_fed_map()
    ragged = DesignedMap(
        GROUND_FOOTED_PROFILE.profile_id, 24, 16, [base.grid[0][:-1], *base.grid[1:]], []
    )

    assert check(ragged, GROUND_FOOTED_PROFILE) == ["row 0 has 23 cells, expected 24"]


def test_a_symbol_outside_the_declared_alphabet_is_rejected() -> None:
    base = _ladder_fed_map()
    rows = list(base.grid)
    rows[9] = "X" + rows[9][1:]
    alien = DesignedMap(GROUND_FOOTED_PROFILE.profile_id, 24, 16, rows, [])

    assert check(alien, GROUND_FOOTED_PROFILE) == ["row 9 uses symbols outside the alphabet: ['X']"]


def test_an_undeclared_biome_tag_is_rejected() -> None:
    tagged = _ladder_fed_map(["meadow"] * 12 + ["tundra"] * 12)

    assert check(tagged, GROUND_FOOTED_PROFILE) == ["undeclared biome tag(s): ['tundra']"]


def test_a_biome_region_narrower_than_the_profile_can_paint_is_rejected() -> None:
    narrow = _ladder_fed_map(["meadow"] * 4 + ["root_forest"] * 20)

    assert check(narrow, GROUND_FOOTED_PROFILE) == [
        "biome region 'meadow' at column 0 is only 4 wide; the consumer needs at least 8 to "
        "paint a region"
    ]


def test_a_six_wide_biome_region_is_paintable_under_one_game_and_too_narrow_under_another() -> None:
    """The minimum span is a consumer's painting budget, so only the profile can say what it is.

    The rejecting case above is written against the ground-footed game, whose minimum is 8 --
    the same number a validator would reach for if it hard-coded one. Six columns of ``cavern``
    is the case that tells the two apart: paintable for the chained game that asks for six, too
    narrow the moment a profile asks for eight, with the identical grid and tags either way.
    """

    shaft = _chained_shaft(
        [
            Climbable(f"m{index}", "iron_ladder", 12, 4, foot)
            for index, foot in enumerate([2, 6, 10, 14])
        ],
        ["cavern"] * 6 + ["rust_works"] * 58,
    )
    needs_eight = dataclasses.replace(CHAINED_SHAFT_PROFILE, biome_min_span_tiles=8)

    assert shaft.column_biomes is not None
    assert shaft.column_biomes.count("cavern") == 6
    assert check(shaft, CHAINED_SHAFT_PROFILE) == []
    assert check(shaft, needs_eight) == [
        "biome region 'cavern' at column 0 is only 6 wide; the consumer needs at least 8 to "
        "paint a region"
    ]


def test_column_biomes_left_unset_leaves_the_biome_channel_unchecked() -> None:
    """A format that does not speak biomes is not silently failed for staying silent."""

    assert check(_ladder_fed_map(None), GROUND_FOOTED_PROFILE) == []
    assert (
        check(_ladder_fed_map(["meadow"] * 12 + ["root_forest"] * 12), GROUND_FOOTED_PROFILE) == []
    )


def _persisted_design() -> PlatformerChunkMapDesign:
    # The model pins both fields as literals, so they are written out as literals here; the
    # exported constants are checked against them in the round-trip test below.
    return PlatformerChunkMapDesign(
        schema_version=1,
        kind="platformer-chunk-map-v1",
        profile_id=GROUND_FOOTED_PROFILE.profile_id,
        columns=128,
        start_height_tiles=3,
        design_notes="a breather, a climb, a dip, and a jump chain",
        chunks=[{"kind": "run", "len": 10}, {"kind": "hollow", "width": 8, "depth": 2}],
        brief="a quiet opening that grows teeth",
    )


def test_a_persisted_chunk_map_design_round_trips_through_canonical_json() -> None:
    design = _persisted_design()

    data = canonical_platformer_chunk_map_design_json(design)

    assert load_platformer_chunk_map_design_bytes(data) == design
    assert data.startswith(b'{"brief":')
    assert b'"kind":"platformer-chunk-map-v1"' in data
    assert design.kind == PLATFORMER_MAP_DESIGN_KIND == "platformer-chunk-map-v1"
    assert design.schema_version == PLATFORMER_MAP_DESIGN_SCHEMA_VERSION == 1


def test_a_persisted_design_naming_another_kind_is_rejected() -> None:
    payload = canonical_platformer_chunk_map_design_json(_persisted_design()).replace(
        b"platformer-chunk-map-v1", b"platformer-chunk-map-v2"
    )

    with pytest.raises(PlatformerMapDesignLoadError, match="invalid platformer chunk map design"):
        load_platformer_chunk_map_design_bytes(payload)


def test_a_persisted_design_at_another_schema_version_is_rejected() -> None:
    payload = canonical_platformer_chunk_map_design_json(_persisted_design()).replace(
        b'"schema_version":1', b'"schema_version":2'
    )

    with pytest.raises(PlatformerMapDesignLoadError, match="invalid platformer chunk map design"):
        load_platformer_chunk_map_design_bytes(payload)
