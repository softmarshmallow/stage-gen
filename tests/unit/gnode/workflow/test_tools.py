"""A declared program: found by ``GNODE_TOOL_<NAME>`` or on PATH, run in a session of its own."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from gnode import RunOutcome, RunRefused, WorkflowRun, make_plan, resolve_tool
from tests.unit.gnode.workflow._project import FakeProvider, planner, project

FLOW = """
gnode: workflow/v1
id: flow
title: Flow
inputs:
  script: { type: string }
  timeout: { type: number, default: 30 }
steps:
  shell:
    uses: ./nodes/extra.py#shell
    with: { script: "${{ inputs.script }}", timeout: "${{ inputs.timeout }}" }
"""

SHELL = """
from gnode import Ctx, node


@node("shell", params={"script": str, "timeout": float}, outputs={"text": "text"}, tools=["sh"])
def shell(ctx: Ctx) -> dict:
    done = ctx.tool("sh").run(
        ["-c", ctx.params["script"]], timeout_s=ctx.params["timeout"], env={"ONLY": "this"}
    )
    return {"text": ctx.out.text(done.stdout)}
"""


NEEDS_A_PROGRAM = """
gnode: workflow/v1
id: flow
title: Flow
steps:
  convert:
    uses: ./nodes/programs.py#convert
"""

PROGRAM_NODES = """
from gnode import Ctx, node


@node("convert", outputs={}, tools=["no-such-program>=2"])
def convert(ctx: Ctx) -> dict:
    raise AssertionError("never runs")
"""


def _text(outcome: RunOutcome) -> str:
    return Path(outcome.results["shell#1"].outputs["text"].location).read_text(encoding="utf-8")


async def _run(tmp_path: Path, script: str, seconds: float) -> RunOutcome:
    built = planner(
        project(tmp_path, FLOW, **{"nodes/extra.py": SHELL}), script=script, timeout=seconds
    )
    plan = await make_plan(built)
    assert plan.ok, plan.problems
    return await WorkflowRun(
        plan, run_dir=tmp_path / "runs/one", services=FakeProvider(built.store).services()
    ).run()


async def test_a_program_sees_only_the_environment_it_is_given(tmp_path: Path) -> None:
    outcome = await _run(tmp_path, 'echo "$ONLY ${HOME:-no home}"', 30)
    assert outcome.ok
    assert _text(outcome) == "this no home\n"


async def test_a_program_past_its_timeout_is_ended_with_everything_it_started(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "survived"
    outcome = await _run(tmp_path, f"(sleep 1; touch {marker}) & sleep 5", 0.3)
    assert not outcome.ok
    assert "ran past 0.3 seconds" in (outcome.results["shell#1"].error or "")
    await asyncio.sleep(1.5)
    assert not _exists(marker)


def _exists(path: Path) -> bool:
    return path.exists()


def test_a_configured_path_wins_over_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    program = tmp_path / "my-blender"
    program.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("GNODE_TOOL_BLENDER", str(program))
    assert resolve_tool("blender") == str(program)
    monkeypatch.setenv("GNODE_TOOL_BLENDER", str(tmp_path / "missing"))
    assert resolve_tool("blender") is None
    monkeypatch.delenv("GNODE_TOOL_BLENDER")
    assert resolve_tool("sh") is not None


async def test_a_run_whose_steps_need_a_missing_program_is_refused_before_it_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GNODE_TOOL_NO_SUCH_PROGRAM", str(tmp_path / "absent"))
    path = project(tmp_path, NEEDS_A_PROGRAM, **{"nodes/programs.py": PROGRAM_NODES})
    plan = await make_plan(planner(path))
    assert plan.ok, plan.problems

    with pytest.raises(RunRefused, match="no-such-program \\(for convert\\)"):
        await WorkflowRun(
            plan,
            run_dir=tmp_path / "runs/one",
            services=FakeProvider(plan.planner.store).services(),
        ).run()
    assert not (tmp_path / "runs/one").exists()
