"""Reusable portrait-motion asset recipe, including contained face-crop workflows.

Preparation and verification are offline. Execution consumes caller-owned services
or an explicitly injected live host factory; gameplay is outside this recipe.
"""

from stage_gen.components.portrait_motion import PortraitMotionSpec
from stage_gen.recipes.portrait_motion.pipeline import (
    PortraitMotionGraph,
    RuntimeProfile,
    graph_for,
    load_plan,
    prepare_run,
    run_pipeline,
    verify_run,
)
from stage_gen.recipes.portrait_motion.services import PortraitServiceFactory, PortraitServices

prepare = prepare_run
run = run_pipeline
verify = verify_run

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
