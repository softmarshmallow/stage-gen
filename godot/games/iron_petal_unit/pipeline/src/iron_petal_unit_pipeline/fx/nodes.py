"""Game import adapter; implementation is asset-owned."""

from typing import Any

from iron_petal_unit_pipeline.fx.block import (
    FX_MANIFEST_BLOCK_VERSION as FX_MANIFEST_BLOCK_VERSION,
)
from iron_petal_unit_pipeline.fx.block import (
    fx_manifest_block as fx_manifest_block,
)
from stage_gen.components.effects_art import nodes as _implementation
from stage_gen.components.effects_art.nodes import *  # noqa: F403


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)
