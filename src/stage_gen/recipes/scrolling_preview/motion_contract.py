"""Canonical source-facing motion-strip geometry for scrolling-preview actors."""

from __future__ import annotations

import math
from typing import Literal

MotionActorKind = Literal["player", "mob", "npc"]
MotionSourceFacing = Literal["right", "back", "front"]
NpcWorldOrientation = Literal["front"]

MOTION_ATLAS_COLUMNS = 4
MOTION_ATLAS_ROWS = 1
MOTION_ATLAS_REQUIRED_CELLS = 4
CANONICAL_SIDE_SOURCE_FACING: Literal["right"] = "right"


def dialogue_atlas_grid(expression_count: int) -> tuple[int, int]:
    """Return the one provider and runtime topology for an expression atlas."""

    if expression_count <= 0:
        raise ValueError("dialogue expression count must be positive")
    if expression_count <= 4:
        return 2, 2
    return 3, math.ceil(expression_count / 3)


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
    if kind == "player" and state == "climb":
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
    if kind == "player" and state == "climb":
        # "four sequential frames ... key poses" asks for a beginning-middle-end arc, and a ladder
        # ascent has no ending. Measured on this state the provider resolved that by substituting
        # an action that can be an arc - reach high, pull, arms drop, torso rotates upright, which
        # is a mantle over a wall or fence. Naming the motion a cycle is what removes the defect:
        # a mantle cannot loop. Held here rather than in the authored package because `motions`
        # carries no per-state prompt, and because this is generation-specific visual meaning.
        return (
            "four sequential phases of one seamless in-place ladder ascent cycle seen from "
            "directly behind: the torso stays vertical, upright, and centered while only the arms "
            "and legs move, the hands grip unseen rungs at head height or above, the feet rest on "
            "unseen rungs at different heights, and the limbs alternate hand-over-hand and "
            "foot-over-foot so that phase four leads back into phase one; the character does not "
            "climb over a wall, fence, ledge, or cliff, does not mantle or pull itself up over an "
            "edge, does not lean or turn sideways, and does not travel horizontally"
        )
    return None


def motion_semantic_direction(kind: MotionActorKind, state: str) -> str:
    """Return recipe-owned visual meaning where a state name alone is ambiguous."""

    override = recipe_owned_motion_direction(kind, state)
    if override is not None:
        return override
    return f"four clear game-animation key poses that communicate {state}"


def runtime_mirrors_source(facing: MotionSourceFacing) -> bool:
    """Whether runtime creates the opposite gameplay facing by horizontal reflection."""

    return facing == CANONICAL_SIDE_SOURCE_FACING
