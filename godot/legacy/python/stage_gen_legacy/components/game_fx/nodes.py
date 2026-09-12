"""Legacy import compatibility; implementation is asset-owned."""

from typing import Any

from stage_gen.components.effects_art import nodes as _implementation
from stage_gen.components.effects_art.nodes import *  # noqa: F403
from stage_gen_legacy.components.game_fx.block import (
    FX_MANIFEST_BLOCK_VERSION as FX_MANIFEST_BLOCK_VERSION,
)
from stage_gen_legacy.components.game_fx.block import (
    fx_manifest_block as fx_manifest_block,
)


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)
