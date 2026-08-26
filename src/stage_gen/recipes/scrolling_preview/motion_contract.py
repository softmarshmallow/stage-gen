"""Canonical source-facing motion-strip geometry for scrolling-preview actors."""

from __future__ import annotations

from typing import Literal

MotionActorKind = Literal["player", "mob", "npc"]
MotionSourceFacing = Literal["right", "back"]

MOTION_ATLAS_COLUMNS = 4
MOTION_ATLAS_ROWS = 1
MOTION_ATLAS_REQUIRED_CELLS = 4
CANONICAL_SIDE_SOURCE_FACING: Literal["right"] = "right"


def motion_source_facing(kind: MotionActorKind, state: str) -> MotionSourceFacing:
    """Return the one authored facing that runtime projection consumes for a state."""

    if kind == "player" and state == "climb":
        return "back"
    return CANONICAL_SIDE_SOURCE_FACING


def runtime_mirrors_source(facing: MotionSourceFacing) -> bool:
    """Whether runtime creates the opposite gameplay facing by horizontal reflection."""

    return facing == CANONICAL_SIDE_SOURCE_FACING
