"""Legacy import compatibility; implementation is asset-owned."""

from typing import Any

from stage_gen.components.painted_terrain import structural_ground as _implementation
from stage_gen.components.painted_terrain.structural_ground import *  # noqa: F403


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)
