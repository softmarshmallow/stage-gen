"""What a run settles whatever order the plan reaches steps in, and what a node is given."""

from __future__ import annotations

from pathlib import Path

import pytest

from gnode import WorkflowRun, make_plan
from tests.unit.gnode.workflow._project import FakeProvider, planner, project

#: A group whose condition reads a judge's facts in another group, so the plan reaches the
#: judge before the step it judges.
JUDGE_FIRST = """
gnode: workflow/v1
id: flow
title: Flow
steps:
  first:
    steps:
      draw:
        uses: gnode/image.generate@1
        with: { prompt: a lantern }
      ok:
        uses: ./nodes/test_nodes.py#verdict
        judges: draw
        with: { subject: "${{ steps.draw.outputs.image }}", accept_take: ACCEPT }
        on_reject: { regenerate: { max: 3, then: fail } }
      after:
        if: ${{ steps.ok.facts.verdict == 'accept' }}
        uses: ./nodes/test_nodes.py#shout
        with: { text: kept }
  second:
    if: ${{ steps.first.after.outputs.text }}
    steps:
      last:
        uses: ./nodes/test_nodes.py#shout
        with: { text: done }
"""

OPTIONAL = """
gnode: workflow/v1
id: flow
title: Flow
inputs:
  run_it: { type: boolean, default: false }
steps:
  maybe:
    if: ${{ inputs.run_it }}
    uses: ./nodes/test_nodes.py#shout
    with: { text: here }
  either:
    uses: ./nodes/extra.py#either
    with: { text: "${{ steps.maybe.outputs.text }}" }
"""

EITHER = """
from gnode import Ctx, node


@node("either", inputs={"text": "text?"}, outputs={"text": "text"})
def either(ctx: Ctx) -> dict:
    return {"text": ctx.out.text("given" if "text" in ctx.inputs else "left out")}
"""


@pytest.mark.parametrize("accept", [1, 3])
async def test_takes_settle_when_a_condition_reaches_the_judge_first(
    tmp_path: Path, accept: int
) -> None:
    """Accepted at once, the later takes close; rejected, the next take is drawn."""

    built = planner(project(tmp_path, JUDGE_FIRST.replace("ACCEPT", str(accept))))
    plan = await make_plan(built)
    assert plan.ok, plan.problems
    provider = FakeProvider(built.store)
    run_dir = tmp_path / "runs/one"
    outcome = await WorkflowRun(plan, run_dir=run_dir, services=provider.services()).run()

    assert outcome.ok, outcome.failed
    assert [name for name, _ in provider.calls] == ["image.generate"] * accept
    assert (run_dir / "events.jsonl").read_text(encoding="utf-8").count('"second.last#1"') >= 1


async def test_an_optional_input_whose_step_did_not_run_is_left_out(tmp_path: Path) -> None:
    built = planner(project(tmp_path, OPTIONAL, **{"nodes/extra.py": EITHER}))
    plan = await make_plan(built)
    assert plan.ok, plan.problems
    run_dir = tmp_path / "runs/one"
    outcome = await WorkflowRun(
        plan, run_dir=run_dir, services=FakeProvider(built.store).services()
    ).run()

    assert outcome.ok, outcome.failed
    [made] = [p for p in (run_dir / "files").rglob("*") if p.is_file() and "either" in p.as_posix()]
    assert made.read_text(encoding="utf-8") == "left out"
