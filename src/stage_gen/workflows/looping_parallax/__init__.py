"""A supplied-layer parallax workflow with independent preparation caches.

The exports load on first use, so ``stage-gen`` can import this package's ``cli`` to build
its parser without loading the image and numeric libraries the pipeline needs.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stage_gen.components.sideview_layers.parallax import ParallaxLayer, ParallaxSpec

    from .pipeline import create_pipeline

_EXPORTS = {
    "ParallaxLayer": "stage_gen.components.sideview_layers.parallax",
    "ParallaxSpec": "stage_gen.components.sideview_layers.parallax",
    "create_pipeline": f"{__name__}.pipeline",
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(_EXPORTS[name]), name)


__all__ = ["ParallaxLayer", "ParallaxSpec", "create_pipeline"]
