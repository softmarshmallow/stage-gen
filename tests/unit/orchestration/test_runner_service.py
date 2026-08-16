from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from stage_gen.config import StageGenConfig, TransparencyMode
from stage_gen.orchestration.runner import run_recipe
from stage_gen.orchestration.service import GenerateRequest, prepare_generate_request
from stage_gen.recipes.base import Recipe, RunOptions, StageContext, StageSpec


async def test_runner_stops_at_first_failure_and_publishes_run_json(tmp_path: Path) -> None:
    visited: list[str] = []

    async def pass_stage(_context: StageContext) -> tuple[str, ...]:
        visited.append("one")
        return ("one.txt",)

    async def fail_stage(_context: StageContext) -> tuple[str, ...]:
        visited.append("two")
        raise RuntimeError("synthetic failure")

    async def unreachable(_context: StageContext) -> tuple[str, ...]:
        visited.append("three")
        return ()

    recipe = Recipe(
        id="test",
        description="test",
        required_capabilities=(),
        parse_input=lambda value: {"prompt": str(value)},
        tag_for=lambda _value: "safe-tag",
        stages=(
            StageSpec("one", 1, "first", pass_stage),
            StageSpec("two", 2, "second", fail_stage),
            StageSpec("three", 3, "third", unreachable),
        ),
    )
    summary = await run_recipe(
        RunOptions(
            recipe=recipe,
            input={"prompt": "hello"},
            config=StageGenConfig(out_dir=str(tmp_path), transparency_mode="chroma"),
        )
    )
    assert visited == ["one", "two"]
    assert summary.ok is False
    assert summary.failed_stage == "two"
    saved = json.loads((Path(summary.run_dir) / "run.json").read_text())
    assert saved["failedStage"] == "two"
    assert saved["stages"][0]["artifacts"] == ["one.txt"]


async def test_runner_enforces_stage_timeout(tmp_path: Path) -> None:
    async def slow(_context: StageContext) -> tuple[str, ...]:
        await asyncio.sleep(1)
        return ()

    recipe = Recipe(
        id="timeout",
        description="timeout",
        required_capabilities=(),
        parse_input=lambda _value: {"prompt": "x"},
        tag_for=lambda _value: "timeout",
        stages=(StageSpec("slow", 1, "slow", slow),),
    )
    summary = await run_recipe(
        RunOptions(
            recipe=recipe,
            input={"prompt": "x"},
            config=StageGenConfig(
                out_dir=str(tmp_path), stage_timeout_ms=10, transparency_mode="chroma"
            ),
        )
    )
    assert summary.failed_stage == "slow"
    assert "timed out after 10ms" in (summary.stages[0].error or "")


async def test_runner_reports_task_group_leaf_and_cancels_sibling(tmp_path: Path) -> None:
    sibling_cancelled = asyncio.Event()

    async def fail_child() -> None:
        await asyncio.sleep(0)
        raise RuntimeError("child-cause")

    async def sleeping_child() -> None:
        try:
            await asyncio.sleep(60)
        finally:
            sibling_cancelled.set()

    async def parallel_stage(_context: StageContext) -> tuple[str, ...]:
        async with asyncio.TaskGroup() as group:
            group.create_task(fail_child())
            group.create_task(sleeping_child())
        return ()

    recipe = Recipe(
        id="parallel",
        description="parallel failure",
        required_capabilities=(),
        parse_input=lambda _value: {"prompt": "x"},
        tag_for=lambda _value: "parallel",
        stages=(StageSpec("parallel", 1, "parallel", parallel_stage),),
    )
    summary = await run_recipe(
        RunOptions(
            recipe=recipe,
            input={"prompt": "x"},
            config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
        )
    )
    assert sibling_cancelled.is_set()
    assert summary.stages[0].error == "child-cause"


def test_prepare_validates_mode_before_capability_and_preserves_tag() -> None:
    config = StageGenConfig(open_router_api_key="fake", fal_key="fake")
    prepared = prepare_generate_request(
        GenerateRequest(input={"prompt": "neutral prompt", "transparencyMode": "chroma"}),
        config,
    )
    assert prepared.input["transparencyMode"] == "chroma"
    assert prepared.tag.endswith("-chroma")
    with pytest.raises(ValueError, match="conflicts"):
        prepare_generate_request(
            GenerateRequest(
                input={"prompt": "neutral", "transparencyMode": "ai"},
                transparency_mode="chroma",
            ),
            config,
        )
