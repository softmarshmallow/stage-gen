"""Game import adapter; implementation is asset-owned."""

from typing import Any

from stage_gen.components.screen_art import layouts as _implementation
from stage_gen.components.screen_art.layouts import *  # noqa: F403


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)
