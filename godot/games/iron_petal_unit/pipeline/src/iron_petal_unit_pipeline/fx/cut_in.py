"""Game import adapter; implementation is asset-owned."""

from typing import Any

from stage_gen.components.effects_art import cut_in as _implementation
from stage_gen.components.effects_art.cut_in import *  # noqa: F403


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)
