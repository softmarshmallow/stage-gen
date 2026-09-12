"""Legacy import compatibility; implementation is asset-owned."""

from typing import Any

from stage_gen.components.effects_art import sprite_nodes as _implementation
from stage_gen.components.effects_art.sprite_nodes import *  # noqa: F403


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)
