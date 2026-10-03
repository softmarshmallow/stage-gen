"""Prompt files: rendered with the step's ``vars`` and the workflow's ``inputs`` when they exist."""

from __future__ import annotations

from pathlib import Path

from gnode import WorkflowRun, make_plan
from tests.unit.gnode.workflow._project import FakeProvider, planner, project

FLOW = """
gnode: workflow/v1
id: flow
title: Flow
inputs:
  topic: { type: string }
steps:
  name:
    uses: ./nodes/test_nodes.py#shout
    with: { text: lantern }
  draw:
    uses: gnode/image.generate@1
    with:
      prompt: ./prompts/draw.md
      vars: { thing: "${{ steps.name.outputs.text }}", count: 2 }
"""

PROMPT = "Draw ${{ vars.count }} of ${{ vars.thing }} for ${{ inputs.topic }}.\n"


async def test_a_prompt_file_is_rendered_once_what_it_reads_exists(tmp_path: Path) -> None:
    path = project(tmp_path, FLOW, **{"prompts/draw.md": PROMPT})
    built = planner(path, topic="a harbour")
    plan = await make_plan(built)
    assert plan.ok, plan.problems
    provider = FakeProvider(built.store)
    outcome = await WorkflowRun(
        plan, run_dir=tmp_path / "runs/one", services=provider.services()
    ).run()

    assert outcome.ok, outcome.failed
    ((name, request),) = provider.calls
    assert name == "image.generate"
    assert request["prompt"] == "Draw 2 of LANTERN for a harbour.\n"
    assert "vars" not in request


async def test_a_name_the_prompt_cannot_see_is_a_plan_problem(tmp_path: Path) -> None:
    path = project(tmp_path, FLOW, **{"prompts/draw.md": "Draw ${{ steps.name }}.\n"})
    plan = await make_plan(planner(path, topic="a harbour"))
    assert any("a prompt sees vars and inputs" in p.message for p in plan.problems)
