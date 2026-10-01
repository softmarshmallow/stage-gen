"""Body-loop assets; pass the resulting canonical to the separate portrait workflow.

The exports load on first use, so ``stage-gen`` can import this package's ``cli`` to build
its parser without loading the video, image and numeric libraries the pipeline needs.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .authoring import Authoring, GenerationSettings, compile_prompt
    from .pipeline import VideoGenerator, create_pipeline

_EXPORTS = {
    "Authoring": "authoring",
    "GenerationSettings": "authoring",
    "compile_prompt": "authoring",
    "VideoGenerator": "pipeline",
    "create_pipeline": "pipeline",
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(f"{__name__}.{_EXPORTS[name]}"), name)


__all__ = ["Authoring", "GenerationSettings", "VideoGenerator", "compile_prompt", "create_pipeline"]
