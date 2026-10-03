"""What a run settles whatever order the plan reaches steps in, and what a node is given."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


UNREVIEWED = """
gnode: workflow/v1
id: flow
title: Flow
inputs:
  review: { type: boolean, default: false }
steps:
  draw:
    uses: gnode/image.generate@1
    with: { prompt: a lantern }
  ok:
    if: ${{ inputs.review }}
    uses: ./nodes/test_nodes.py#verdict
    judges: draw
    with: { subject: "${{ steps.draw.outputs.image }}", accept_take: 3 }
    on_reject: { regenerate: { max: 3, then: fail } }
  after:
    uses: ./nodes/test_nodes.py#shout
    with: { text: "take ${{ steps.draw.take }}" }
"""


@pytest.mark.parametrize(("review", "calls"), [(False, 1), (True, 3)])
async def test_a_judge_left_out_by_its_condition_leaves_the_step_unjudged(
    tmp_path: Path, review: bool, calls: int
) -> None:
    built = planner(project(tmp_path, UNREVIEWED), review=review)
    plan = await make_plan(built)
    assert plan.ok, plan.problems
    provider = FakeProvider(built.store)
    outcome = await WorkflowRun(
        plan, run_dir=tmp_path / "runs/one", services=provider.services()
    ).run()

    assert outcome.ok, outcome.failed
    assert [name for name, _ in provider.calls] == ["image.generate"] * calls


FEEDBACK = """
gnode: workflow/v1
id: flow
title: Flow
steps:
  draw:
    uses: ./nodes/extra.py#draft
    with: { said: "${{ feedback }}" }
  ok:
    uses: ./nodes/test_nodes.py#verdict
    judges: draw
    with: { subject: "${{ steps.draw.outputs.text }}", accept_take: 3 }
    on_reject: { regenerate: { max: 3, feedback: true } }
"""

DRAFT = """
from gnode import Ctx, node


@node("draft", params={"said": {"type": "object", "default": {}}}, outputs={"text": "text"})
def draft(ctx: Ctx) -> dict:
    said = sorted((ctx.params["said"] or {}).get("ok", {}).items())
    return {"text": ctx.out.text(f"take {ctx.instance.take} after {said}")}
"""


def _texts(outcome: Any, ids: list[str]) -> list[str]:
    return [
        Path(outcome.results[i].outputs["text"].location).read_text(encoding="utf-8") for i in ids
    ]


async def test_a_redraw_is_told_what_the_judge_said_of_the_take_before(tmp_path: Path) -> None:
    built = planner(project(tmp_path, FEEDBACK, **{"nodes/extra.py": DRAFT}))
    plan = await make_plan(built)
    assert plan.ok, plan.problems
    run_dir = tmp_path / "runs/one"
    outcome = await WorkflowRun(
        plan, run_dir=run_dir, services=FakeProvider(built.store).services()
    ).run()

    assert outcome.ok, outcome.failed
    assert _texts(outcome, [f"draw#{take}" for take in (1, 2, 3)]) == [
        "take 1 after []",
        "take 2 after [('take', 1), ('verdict', 'reject')]",
        "take 3 after [('take', 2), ('verdict', 'reject')]",
    ]


GROUP_FEEDBACK = """
gnode: workflow/v1
id: flow
title: Flow
inputs:
  rounds: { type: integer, default: 3 }
steps:
  build:
    steps:
      draw:
        uses: ./nodes/extra.py#draft
        with: { said: "${{ feedback }}" }
      ok:
        uses: ./nodes/test_nodes.py#verdict
        with: { subject: "${{ steps.draw.outputs.text }}", accept_take: 99 }
    regenerate:
      max: ${{ inputs.rounds }}
      until: ${{ steps.ok.facts.verdict == 'accept' }}
      feedback: true
      then: continue
"""

GROUP_DRAFT = """
from gnode import Ctx, node


@node("draft", params={"said": {"type": "object", "default": {}}}, outputs={"text": "text"})
def draft(ctx: Ctx) -> dict:
    said = ctx.params["said"] or {}
    seen = sorted((name, facts.get("verdict")) for name, facts in said.items())
    return {"text": ctx.out.text(f"{len(ctx.instance.takes)} {seen}")}
"""


@pytest.mark.parametrize("rounds", [2, 3])
async def test_a_regenerating_group_takes_its_max_from_inputs_and_hears_its_last_take(
    tmp_path: Path, rounds: int
) -> None:
    built = planner(
        project(tmp_path, GROUP_FEEDBACK, **{"nodes/extra.py": GROUP_DRAFT}), rounds=rounds
    )
    plan = await make_plan(built)
    assert plan.ok, plan.problems
    outcome = await WorkflowRun(
        plan, run_dir=tmp_path / "runs/one", services=FakeProvider(built.store).services()
    ).run()

    drafts = sorted(i for i in outcome.results if i.startswith("build.draw#"))
    assert drafts == [f"build.draw#{take}.1" for take in range(1, rounds + 1)]
    texts = _texts(outcome, drafts)
    assert texts[0] == "2 []"
    assert all(text == "2 [('draw', None), ('ok', 'reject')]" for text in texts[1:])
