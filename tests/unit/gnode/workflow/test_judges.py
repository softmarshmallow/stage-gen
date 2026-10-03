"""Judges inside groups, takes that fail, and inputs that name files a run did not make."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from gnode import CallRecord, CallRefused, HostServices, Route, WorkflowRun, make_plan
from tests.unit.gnode.workflow._project import PNG, FakeProvider, planner, project, write

GROUPED = """
gnode: workflow/v1
id: flow
title: Flow
steps:
  art:
    steps:
      draw:
        uses: gnode/image.generate@1
        with: { prompt: a lantern }
      check:
        uses: ./nodes/test_nodes.py#verdict
        judges: draw
        with: { subject: "${{ steps.art.draw.outputs.image }}", accept_take: 2 }
        on_reject: { regenerate: { max: 3, then: fail } }
outputs:
  image: ${{ steps.art.draw.outputs.image }}
"""

JUDGED = """
gnode: workflow/v1
id: flow
title: Flow
steps:
  draw:
    uses: gnode/image.generate@1
    with: { prompt: a lantern }
  check:
    uses: ./nodes/test_nodes.py#JUDGE
    judges: draw
    with: { subject: "${{ steps.draw.outputs.image }}", accept_take: 1 }
    on_reject: { regenerate: { max: 6, then: fail } }
outputs:
  image: ${{ steps.draw.outputs.image }}
"""

BROKEN_JUDGE = """
from gnode import Ctx, node


@node("broken", inputs={"subject": "file"}, params={"accept_take": int}, judge=True)
def broken(ctx: Ctx) -> dict:
    raise ValueError("the judge has a bug")
"""

SLOW = """
import asyncio

from gnode import Ctx, node


@node("slow", outputs={"text": "text"})
async def slow(ctx: Ctx) -> dict:
    await asyncio.sleep(0.3)
    return {"text": ctx.out.text("done")}
"""

HOLE = """
gnode: workflow/v1
id: flow
title: Flow
steps:
  sketch:
    if: ${{ false }}
    uses: gnode/image.generate@1
    with: { prompt: a sketch }
  paint:
    uses: gnode/image.edit@1
    with:
      image: ./art/base.png
      references: ["${{ steps.sketch.outputs.image }}"]
      prompt: a lantern
"""

MAP = """
gnode: workflow/v1
id: flow
title: Flow
steps:
  joined:
    uses: ./nodes/test_nodes.py#join
    with: { parts: { a: ./notes/a.txt, b: ./notes/b.txt } }
outputs:
  text: ${{ steps.joined.outputs.text }}
"""


class Refusing(FakeProvider):
    """Every picture call fails the way a provider does after its own retries."""

    takes: list[int]

    def __init__(self, store: Any) -> None:
        super().__init__(store)
        self.takes = []

    def services(self, *, live: bool = True) -> HostServices:
        async def refuse(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
            self.calls.append(("image.generate", dict(request)))
            self.takes.append(take)
            raise CallRefused("the provider failed every attempt")

        services = super().services(live=live)
        return HostServices(
            store=services.store,
            capabilities={**services.capabilities, "image.generate": refuse},
            live=live,
        )


async def _run(path: Path, run_dir: Path, provider: FakeProvider):  # type: ignore[no-untyped-def]
    plan = await make_plan(planner(path))
    assert plan.ok, plan.problems
    return await WorkflowRun(plan, run_dir=run_dir, services=provider.services()).run()


async def test_a_judge_reads_its_own_take_however_the_judged_step_is_named(
    tmp_path: Path,
) -> None:
    path = project(tmp_path, GROUPED)
    provider = FakeProvider(planner(path).store)

    outcome = await _run(path, tmp_path / "run", provider)

    assert outcome.ok, outcome.failed
    assert len(provider.calls) == 2
    assert outcome.results["art.check#1"].facts["take"] == 1
    assert outcome.results["art.check#2"].verdict == "accept"


@pytest.mark.parametrize("workflow", [JUDGED.replace("JUDGE", "verdict"), GROUPED])
async def test_a_take_that_failed_is_not_drawn_again(tmp_path: Path, workflow: str) -> None:
    path = project(tmp_path, workflow)
    provider = Refusing(planner(path).store)

    outcome = await _run(path, tmp_path / "run", provider)

    assert not outcome.ok
    assert len(provider.calls) == 1
    assert not {"draw#2", "art.draw#2"} & set(outcome.results)


async def test_a_failed_take_stays_failed_while_the_rest_of_the_run_goes_on(
    tmp_path: Path,
) -> None:
    # Another step finishing after the judge was skipped makes the run decide again; the
    # skipped judge must not read as a rejection then either.
    workflow = GROUPED.replace("outputs:\n", "  slow:\n    uses: ./nodes/slow.py#slow\noutputs:\n")
    path = project(tmp_path, workflow)
    write(tmp_path, {"nodes/slow.py": SLOW})
    provider = Refusing(planner(path).store)

    outcome = await _run(path, tmp_path / "run", provider)

    assert not outcome.ok
    assert outcome.results["slow#1"].status == "succeeded"
    assert provider.takes == [1]


async def test_a_judge_that_fails_fails_the_step_instead_of_drawing_again(
    tmp_path: Path,
) -> None:
    path = project(tmp_path, JUDGED.replace("test_nodes.py#JUDGE", "broken.py#broken"))
    write(tmp_path, {"nodes/broken.py": BROKEN_JUDGE})
    provider = FakeProvider(planner(path).store)

    outcome = await _run(path, tmp_path / "run", provider)

    assert not outcome.ok
    assert len(provider.calls) == 1
    assert "draw#2" not in outcome.results


async def test_a_list_with_a_file_the_run_did_not_make_leaves_the_step_out(
    tmp_path: Path,
) -> None:
    path = project(tmp_path, HOLE, **{"art/base.png": PNG})
    provider = FakeProvider(planner(path).store)

    outcome = await _run(path, tmp_path / "run", provider)

    assert provider.calls == []
    assert "paint#1" not in outcome.results


async def test_a_map_of_project_files_is_read_by_content(tmp_path: Path) -> None:
    path = project(tmp_path, MAP, **{"notes/a.txt": "tide", "notes/b.txt": "salt"})
    provider = FakeProvider(planner(path).store)

    outcome = await _run(path, tmp_path / "run", provider)

    assert outcome.ok, outcome.failed
    assert outcome.outputs["text"].content == "a=tide|b=salt"
