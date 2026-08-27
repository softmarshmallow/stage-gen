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


def motion_semantic_direction(kind: MotionActorKind, state: str) -> str:
    """Return recipe-owned visual meaning where a state name alone is ambiguous."""

    if kind == "player" and state == "crouch":
        return (
            "four sequential phases of a low stationary crouch loop: the character stays on both "
            "feet with bent knees and a lowered torso, using only subtle balance and breathing "
            "variation; the character does not crawl, kneel, move forward, or touch hands to the "
            "ground"
        )
    return f"four clear game-animation key poses that communicate {state}"


def runtime_mirrors_source(facing: MotionSourceFacing) -> bool:
    """Whether runtime creates the opposite gameplay facing by horizontal reflection."""

    return facing == CANONICAL_SIDE_SOURCE_FACING
