"""Game import adapter; implementation is asset-owned."""

from typing import Any

from stage_gen.components.ui_art import icons as _implementation
from stage_gen.components.ui_art.icons import *  # noqa: F403


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)
