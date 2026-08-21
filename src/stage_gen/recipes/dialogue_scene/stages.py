"""Dialogue recipe stage DAG."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from stage_gen.recipes.base import StageContext, StageSpec


async def _delegate(stage: str, context: StageContext) -> Sequence[str]:
    runtime = context.runtime
    if runtime is None:
        raise RuntimeError(f"dialogue-scene stage {stage} requires a composed recipe runtime")
    return await runtime.run_recipe_stage("dialogue-scene", stage, context)


def _runner(stage: str) -> Callable[[StageContext], Awaitable[Sequence[str]]]:
    async def run(context: StageContext) -> Sequence[str]:
        return await _delegate(stage, context)

    return run


STAGES: tuple[StageSpec, ...] = (
    StageSpec("prepare", 0.5, "normalize request and ingest references", _runner("prepare")),
    StageSpec(
        "style-selection",
        0.75,
        "select and materialize the canonical image style anchor",
        _runner("style-selection"),
        ("prepare",),
    ),
    StageSpec(
        "appearance-concept",
        1,
        "select the adult appearance identity anchor",
        _runner("appearance-concept"),
        ("style-selection",),
    ),
    StageSpec(
        "scene-plan",
        1.5,
        "compile the strict dialogue visual plan",
        _runner("scene-plan"),
        ("appearance-concept",),
    ),
    StageSpec(
        "background",
        2,
        "select the scene background",
        _runner("background"),
        ("scene-plan",),
    ),
    StageSpec(
        "neutral",
        2,
        "generate the identity-locked neutral source",
        _runner("neutral"),
        ("scene-plan",),
    ),
    StageSpec(
        "expressions",
        3,
        "derive the non-neutral expression sources",
        _runner("expressions"),
        ("neutral",),
    ),
    StageSpec(
        "canonicalize",
        4,
        "derive validated portable expression assets",
        _runner("canonicalize"),
        ("expressions",),
    ),
    StageSpec(
        "bundle",
        5,
        "write the portable dialogue bundle",
        _runner("bundle"),
        ("background", "canonicalize"),
    ),
)


PROFILE_STAGES: tuple[StageSpec, ...] = (
    STAGES[0],
    StageSpec(
        "profile-resolve",
        0.6,
        "validate and materialize the authored character profile",
        _runner("profile-resolve"),
        ("prepare",),
    ),
    StageSpec(
        "style-selection",
        0.75,
        "select and materialize the canonical image style anchor",
        _runner("style-selection"),
        ("profile-resolve",),
    ),
    *STAGES[2:],
)


def dialogue_scene_stages(input_value: Mapping[str, Any]) -> tuple[StageSpec, ...]:
    """Select the V4 profile graph without changing the V3 legacy graph."""

    return PROFILE_STAGES if input_value.get("schema_version") == 3 else STAGES
