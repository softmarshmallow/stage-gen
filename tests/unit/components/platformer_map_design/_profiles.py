"""Two test games, and the reason there are two.

The component contains no game. These profiles are the games this suite invents to exercise it,
and they live in the tests precisely so that no game constant can leak back into the component.

``GROUND_FOOTED_PROFILE`` is the ordinary case: a climbable spans exactly four tiles, may only be
founded on terrain connected to the world floor, and needs level footing beside it.

``CHAINED_SHAFT_PROFILE`` exists specifically to keep the module honest. Every value in it
disagrees with the first profile -- a taller grid, a stronger jump, climbables of four different
lengths, and footing permitted anywhere -- so a designer that quietly assumed the first game's
tuning cannot pass both. It is the profile that makes the agnosticism proof in
``test_design_check.py`` mean something: the same grid is stranded under one game and sound under
the other, with no branch anywhere in the component.

``CLIMBLESS_PROFILE`` is the third case the first two cannot express: a game that declares no
climbable variant at all. Two profiles that both have climbables leave "only where the profile
declares climbable variants" untested, because the branch that withholds a word is never taken.
"""

from __future__ import annotations

from stage_gen.components.platformer_map_design import (
    STANDARD_TILE_ROLES,
    GeometryProfile,
    MovementProfile,
    PlatformerProfile,
)

#: A fixed-rise, ground-founded side-scroller: the tuning a map designer is tempted to hard-code.
GROUND_FOOTED_PROFILE = PlatformerProfile(
    profile_id="ground-footed-test-game",
    movement=MovementProfile(
        max_step_up_tiles=2,
        # As if measured with this game's own jump simulation, not assumed.
        jump_reach={1: 8, 2: 6},
        # Conservative: the measured rise-1 reach. A level jump carries at least this far.
        level_gap_tiles=8,
        climbable_rise_tiles=(4,),
        climbable_footing="ground",
        climbable_needs_flat_footing=True,
    ),
    geometry=GeometryProfile(
        columns=128,
        rows=16,
        ground_depth_tiles=(1, 8),
        max_walkable_height_tiles=12,
        platforms_single_thickness=True,
    ),
    roles=STANDARD_TILE_ROLES,
    climbable_variants=("root_ladder", "shrine_rope_ladder", "rope_climb"),
    climbable_count=(3, 8),
    biomes=("meadow", "root_forest", "shrine_stone"),
    biome_min_span_tiles=8,
    notes="A 2-tile step needs the double jump. A climbable is the only way up four tiles.",
)


#: A deliberately different game: taller grid, stronger jump, climbables of several lengths that
#: may be founded on platforms, so storeys chain upward.
CHAINED_SHAFT_PROFILE = PlatformerProfile(
    profile_id="chained-shaft-test-game",
    movement=MovementProfile(
        max_step_up_tiles=3,
        jump_reach={1: 10, 2: 8, 3: 6, 4: 3},
        level_gap_tiles=10,
        climbable_rise_tiles=(3, 4, 5, 6),
        climbable_footing="any",
        climbable_needs_flat_footing=False,
    ),
    geometry=GeometryProfile(
        columns=64,
        rows=32,
        ground_depth_tiles=(1, 4),
        max_walkable_height_tiles=28,
        platforms_single_thickness=True,
    ),
    roles=STANDARD_TILE_ROLES,
    climbable_variants=("iron_ladder", "chain"),
    climbable_count=(4, 12),
    biomes=("cavern", "rust_works", "glow_moss"),
    biome_min_span_tiles=6,
    notes="Climbables may be founded on platforms, so shafts can chain upward.",
)


#: A game with no climbables whatsoever, and the ONE rule it exists to discriminate: that a
#: climbable-fed word reaches the grammar only where the profile declares climbable variants.
#:
#: Its ``climbable_variants`` is empty, and its ``climbable_footing`` is deliberately ``"any"``
#: -- the permissive setting -- so that footing cannot be what withholds ``tower`` from its
#: vocabulary. With footing ruled out, the empty variant tuple is the only thing left that can
#: remove ``perch`` and ``tower``, which is what makes their absence a proof rather than a
#: coincidence. Everything else it declares is unremarkable on purpose.
CLIMBLESS_PROFILE = PlatformerProfile(
    profile_id="climbless-test-game",
    movement=MovementProfile(
        max_step_up_tiles=2,
        jump_reach={1: 7, 2: 5, 3: 3},
        level_gap_tiles=7,
        # A profile must permit at least one rise even where it declares no variant to draw:
        # the rise is what a climbable WOULD span, and this game simply never draws one.
        climbable_rise_tiles=(4,),
        climbable_footing="any",
        climbable_needs_flat_footing=False,
    ),
    geometry=GeometryProfile(
        columns=96,
        rows=20,
        ground_depth_tiles=(1, 6),
        max_walkable_height_tiles=14,
        platforms_single_thickness=True,
    ),
    roles=STANDARD_TILE_ROLES,
    climbable_variants=(),
    climbable_count=(0, 0),
    biomes=("dune", "salt_flat"),
    biome_min_span_tiles=10,
    notes="Every height gain is a jump: this game draws no ladders and no ropes.",
)

__all__ = ["CHAINED_SHAFT_PROFILE", "CLIMBLESS_PROFILE", "GROUND_FOOTED_PROFILE"]
