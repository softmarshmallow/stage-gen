"""Reusable portrait-motion workflow, including contained face-crop runs.

Preparation and verification are offline. Execution consumes caller-owned services
or an explicitly injected live host factory; gameplay is outside this workflow.

The exports load on first use, so ``stage-gen`` can import this package's ``cli`` to build
its parser without loading the image and numeric libraries the pipeline needs.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stage_gen.components.portrait_motion import PortraitMotionSpec
    from stage_gen.workflows.portrait_motion.pipeline import (
        PortraitMotionGraph,
        RuntimeProfile,
        graph_for,
        load_plan,
        prepare_run,
        run_pipeline,
        verify_run,
    )
    from stage_gen.workflows.portrait_motion.pipeline import prepare_run as prepare
    from stage_gen.workflows.portrait_motion.pipeline import run_pipeline as run
    from stage_gen.workflows.portrait_motion.pipeline import verify_run as verify
    from stage_gen.workflows.portrait_motion.services import (
        PortraitServiceFactory,
        PortraitServices,
    )

_PIPELINE = f"{__name__}.pipeline"
#: Each export: the module that defines it and its name there.
_EXPORTS = {
    "PortraitMotionSpec": ("stage_gen.components.portrait_motion", "PortraitMotionSpec"),
    "PortraitMotionGraph": (_PIPELINE, "PortraitMotionGraph"),
    "RuntimeProfile": (_PIPELINE, "RuntimeProfile"),
    "graph_for": (_PIPELINE, "graph_for"),
    "load_plan": (_PIPELINE, "load_plan"),
    "prepare_run": (_PIPELINE, "prepare_run"),
    "run_pipeline": (_PIPELINE, "run_pipeline"),
    "verify_run": (_PIPELINE, "verify_run"),
    "prepare": (_PIPELINE, "prepare_run"),
    "run": (_PIPELINE, "run_pipeline"),
    "verify": (_PIPELINE, "verify_run"),
    "PortraitServiceFactory": (f"{__name__}.services", "PortraitServiceFactory"),
    "PortraitServices": (f"{__name__}.services", "PortraitServices"),
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module, attribute = _EXPORTS[name]
    return getattr(importlib.import_module(module), attribute)


__all__ = [
    "PortraitMotionGraph",
    "PortraitMotionSpec",
    "RuntimeProfile",
    "PortraitServiceFactory",
    "PortraitServices",
    "graph_for",
    "load_plan",
    "prepare",
    "run",
    "verify",
    "prepare_run",
    "run_pipeline",
    "verify_run",
]
