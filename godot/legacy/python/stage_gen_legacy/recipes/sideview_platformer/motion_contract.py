"""The platformer's motion-state vocabulary over the shared strip geometry.

Strip geometry (the canvases, the cell grammar, the mirror rule) is
camera-scoped and lives in `stage_gen.components.sideview_actor.motion_geometry`.
What stays here is genre vocabulary: which states exist, which face away from
the camera, which select the climb canvas, and the per-state generation
directives measured against this recipe's providers.
"""

from __future__ import annotations

from typing import Literal

from stage_gen.components.sideview_actor.motion_geometry import (
    CANONICAL_SIDE_SOURCE_FACING,
    DEFAULT_MOTION_ATLAS_GEOMETRY,
    MOTION_ATLAS_ROWS,
    MotionAtlasGeometry,
    MotionSourceFacing,
)

MotionActorKind = Literal["player", "mob", "npc"]
NpcWorldOrientation = Literal["front"]

#: Traversal states the player performs facing into the screen, hands on a climbable the runtime
#: draws in front of them. Rear facing is not mirrored for left-facing play.
PLAYER_REAR_FACING_STATES = frozenset({"climb_ladder", "climb_rope"})

#: Climb states advance frame by frame from the player's position on the climbable rather than on
#: a clock, so they are the only states whose playback the runtime drives.
PLAYER_GAMEPLAY_DRIVEN_STATES = PLAYER_REAR_FACING_STATES

CLIMB_ATLAS_COLUMNS = 2
CLIMB_ATLAS_REQUIRED_CELLS = 2
CLIMB_ATLAS_WIDTH = 2464
CLIMB_ATLAS_HEIGHT = 3328


#: A climb has two distinct poses - reach and pull - and a four-cell strip spends two of its cells
#: on near-duplicates of the other two. Two cells on the larger canvas buy roughly eleven times the
#: painted character area at the same cell aspect.
CLIMB_MOTION_ATLAS_GEOMETRY = MotionAtlasGeometry(
    columns=CLIMB_ATLAS_COLUMNS,
    rows=MOTION_ATLAS_ROWS,
    required_cells=CLIMB_ATLAS_REQUIRED_CELLS,
    width=CLIMB_ATLAS_WIDTH,
    height=CLIMB_ATLAS_HEIGHT,
)


def motion_atlas_geometry(kind: MotionActorKind, state: str) -> MotionAtlasGeometry:
    """Return the strip shape for one state. Every state but the player climbs is the default."""

    if kind == "player" and state in PLAYER_REAR_FACING_STATES:
        return CLIMB_MOTION_ATLAS_GEOMETRY
    return DEFAULT_MOTION_ATLAS_GEOMETRY


def motion_source_facing(
    kind: MotionActorKind,
    state: str,
    *,
    npc_world_orientation: NpcWorldOrientation | None = None,
) -> MotionSourceFacing:
    """Return the one authored facing that runtime projection consumes for a state."""

    if kind == "npc":
        if npc_world_orientation is None:
            raise ValueError("NPC motion source facing requires world_orientation")
        return npc_world_orientation
    if npc_world_orientation is not None:
        raise ValueError("npc_world_orientation is valid only for NPC motion")
    if kind == "player" and state in PLAYER_REAR_FACING_STATES:
        return "back"
    return CANONICAL_SIDE_SOURCE_FACING


def recipe_owned_motion_direction(kind: MotionActorKind, state: str) -> str | None:
    """Return the override for a state whose name alone reads as the wrong action, else None.

    Separate from `motion_semantic_direction` because the cache digest needs to distinguish an
    override from the default. The default is a pure function of the state name, which the digest
    already carries, so hashing it would add nothing; an override is the only part of the
    directive a caller cannot derive from what is already hashed.
    """

    if kind == "player" and state == "crouch":
        return (
            "four sequential phases of a low stationary crouch loop: the character stays on both "
            "feet with bent knees and a lowered torso, using only subtle balance and breathing "
            "variation; the character does not crawl, kneel, move forward, or touch hands to the "
            "ground"
        )
    if kind == "player" and state == "climb_ladder":
        # "four sequential frames ... key poses" asks for a beginning-middle-end arc, and a ladder
        # ascent has no ending. Measured on this state the provider resolved that by substituting
        # an action that can be an arc - reach high, pull, arms drop, torso rotates upright, which
        # is a mantle over a wall or fence. Naming the motion a cycle is what removes the defect:
        # a mantle cannot loop. Held here rather than in the authored package because `motions`
        # carries no per-state prompt, and because this is generation-specific visual meaning.
        return (
            "two sequential phases of one seamless in-place ladder ascent cycle seen from "
            "directly behind: the torso stays vertical, upright, and centered while only the arms "
            "and legs move, the hands grip unseen rungs at head height or above, the feet rest on "
            "unseen rungs at different heights, and the cycle alternates between two phases: "
            "phase one reaches with the left hand high and the right foot high, phase two reaches "
            "with the right hand high and the left foot high, so that phase two leads back into "
            "phase one; the character does not climb over a wall, fence, ledge, or cliff, does "
            "not mantle or pull itself up over an edge, does not lean or turn sideways, and does "
            "not travel horizontally; the ladder itself is never drawn and no ladder, rung, rope, "
            "cord, or climbing prop of any kind appears anywhere in the image - only the "
            "character is painted, gripping empty space"
        )
    if kind == "player" and state == "climb_rope":
        # Same cycle framing as the ladder, but measured on this state the failure mode moved: the
        # state name already reads as the right action, and what went wrong instead was the
        # provider painting the rope itself edge to edge through every cell. The repack then fuses
        # that band into the character component and bottom-anchors the sprite on the rope's tail
        # rather than on the feet, and the strip double-draws against the rope the map already
        # owns. Calling the rope "unseen" did not prevent that in 7 of 8 measured strips and
        # removing the noun altogether did not either; only naming the prohibition outright did.
        # The rope stays named as a grip target because the propless phrasing lost the sword more
        # often than it kept it. The pose amplitude is bounded on purpose: asking for a fully
        # extended pose against a fully compressed one produced cells whose painted heights
        # differed by a quarter of the figure, which over a two-cell cycle reads as a lurch rather
        # than a climb. Pinning the head, shoulders, and fists to one height states the intent the
        # top anchor then registers, so prompt and geometry agree instead of fighting.
        return (
            "two sequential phases of one seamless in-place rope ascent cycle seen from directly "
            "behind: a single unseen rope hangs straight down the vertical centerline of the "
            "body, both closed fists grip that one line directly above the head and stacked one "
            "above the other rather than apart at shoulder width, the ankles and insides of both "
            "feet pinch the same line together with the knees close together, and the cycle "
            "alternates between two closely matched poses that differ only in the limbs: in phase "
            "one the legs hang nearly straight below with the feet low, and in phase two the "
            "knees rise only as far as hip height with the feet clamped a short distance higher, "
            "so that phase two leads back into phase one; the head, shoulders, and both gripping "
            "fists are drawn at exactly the same height in both cells, and the two cells differ "
            "only below the waist and in the bend of the forearms; the torso stays vertical, "
            "upright, and centered and the figure stays in the same place; the character does not "
            "swing, sway, "
            "or hang sideways, does not slide down, descend, or rappel, does not pull a rope "
            "toward itself horizontally, does not climb over a wall, fence, ledge, or cliff, does "
            "not mantle or pull itself up over an edge, and does not travel horizontally; the "
            "rope itself is never drawn and no rope, cord, line, ladder, or climbing prop of any "
            "kind appears anywhere in the image - only the character is painted, gripping empty "
            "space"
        )
    return None


def motion_semantic_direction(kind: MotionActorKind, state: str) -> str:
    """Return recipe-owned visual meaning where a state name alone is ambiguous."""

    override = recipe_owned_motion_direction(kind, state)
    if override is not None:
        return override
    return f"four clear game-animation key poses that communicate {state}"


__all__ = [
    "CLIMB_ATLAS_COLUMNS",
    "CLIMB_ATLAS_HEIGHT",
    "CLIMB_ATLAS_REQUIRED_CELLS",
    "CLIMB_ATLAS_WIDTH",
    "CLIMB_MOTION_ATLAS_GEOMETRY",
    "MotionActorKind",
    "NpcWorldOrientation",
    "PLAYER_GAMEPLAY_DRIVEN_STATES",
    "PLAYER_REAR_FACING_STATES",
    "motion_atlas_geometry",
    "motion_semantic_direction",
    "motion_source_facing",
    "recipe_owned_motion_direction",
]
