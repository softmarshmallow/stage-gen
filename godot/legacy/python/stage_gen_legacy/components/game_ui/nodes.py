"""Legacy import compatibility; implementation is asset-owned."""

from typing import Any

from stage_gen.components.ui_art import nodes as _implementation
from stage_gen.components.ui_art.nodes import *  # noqa: F403


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)
