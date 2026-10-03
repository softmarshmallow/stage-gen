"""Running a workflow offline with fake paid calls: results, judges, resume, cache, ceiling."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gnode import RunRefused, WorkflowRun, make_plan
from tests.unit.gnode.workflow._project import FakeProvider, planner, project

REGENERATING = """
gnode: workflow/v1
id: flow
title: Flow
steps:
  draw:
    uses: gnode/image.generate@1
    with: { prompt: a lantern }
  check:
    uses: ./nodes/test_nodes.py#verdict
    judges: draw
    with: { subject: "${{ steps.draw.outputs.image }}", accept_take: 2 }
    on_reject: { regenerate: { max: 3, then: fail } }
  label:
    uses: ./nodes/test_nodes.py#shout
    with: { text: "take ${{ steps.draw.take }}" }
outputs:
  image: ${{ steps.draw.outputs.image }}
  label: ${{ steps.label.outputs.text }}
"""


def _events(run_dir: Path) -> list[dict[str, object]]:
    lines = (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


async def _run(path: Path, run_dir: Path, provider: FakeProvider, **options: object):  # type: ignore[no-untyped-def]
    built = planner(path)
    plan = await make_plan(built, max_usd=options.pop("max_usd", None))  # type: ignore[arg-type]
    return await WorkflowRun(plan, run_dir=run_dir, services=provider.services(), **options).run()  # type: ignore[arg-type]


async def test_a_rejected_take_is_regenerated_and_downstream_gets_the_accepted_one(
    tmp_path: Path,
) -> None:
    path = project(tmp_path, REGENERATING)
    provider = FakeProvider(planner(path).store)
    outcome = await _run(path, tmp_path / "runs/one", provider)

    assert outcome.ok, outcome.failed
    assert [name for name, _ in provider.calls] == ["image.generate", "image.generate"]
    assert outcome.results["check#1"].verdict == "reject"
    assert outcome.results["check#2"].verdict == "accept"
    assert "draw#3" not in outcome.results
    assert outcome.outputs["label"].content == "TAKE 2"
    assert outcome.cost_usd == pytest.approx(0.02)
    assert (tmp_path / "runs/one/outputs/image.png").is_file()
    assert (tmp_path / "runs/one/files/draw/image.png").is_file()


async def test_running_again_answers_everything_from_the_cache(tmp_path: Path) -> None:
    path = project(tmp_path, REGENERATING)
    provider = FakeProvider(planner(path).store)
    await _run(path, tmp_path / "runs/one", provider)
    provider.calls.clear()

    again = await _run(path, tmp_path / "runs/two", provider)

    assert again.ok and provider.calls == []
    finished = [e for e in _events(tmp_path / "runs/two") if e["event"] == "node_finished"]
    assert {e["cache"] for e in finished} == {"hit"}


async def test_a_run_continues_in_its_own_folder_with_one_record(tmp_path: Path) -> None:
    path = project(tmp_path, REGENERATING)
    provider = FakeProvider(planner(path).store)
    run_dir = tmp_path / "runs/one"
    await _run(path, run_dir, provider)

    again = await _run(path, run_dir, provider)

    assert again.ok
    started = [e for e in _events(run_dir) if e["event"] == "run_started"]
    assert [e["resumed"] for e in started] == [False, True]
    # The second invocation had nothing left to do: every step was already recorded.
    assert [e["event"] for e in _events(run_dir)].count("node_started") == 5


async def test_a_folder_of_another_run_is_refused(tmp_path: Path) -> None:
    path = project(tmp_path, REGENERATING)
    provider = FakeProvider(planner(path).store)
    run_dir = tmp_path / "runs/one"
    await _run(path, run_dir, provider)
    path.write_text(path.read_text().replace("a lantern", "a kettle"), encoding="utf-8")

    with pytest.raises(RunRefused, match="another workflow or other inputs"):
        await _run(path, run_dir, provider)


async def test_a_paid_call_is_kept_by_its_request_when_the_node_runs_again(
    tmp_path: Path,
) -> None:
    flow = """
        gnode: workflow/v1
        id: flow
        title: Flow
        inputs:
          picture: { type: file, kind: image }
        steps:
          paint:
            uses: ./nodes/test_nodes.py#paint
            with: { image: "${{ inputs.picture }}", prompt: "paint it" }
        """
    from tests.unit.gnode.workflow._project import PNG

    path = project(tmp_path, flow, **{"in.png": PNG})
    provider = FakeProvider(planner(path, picture="in.png").store)
    first = planner(path, picture="in.png")
    await WorkflowRun(
        await make_plan(first), run_dir=tmp_path / "runs/a", services=provider.services()
    ).run()
    # Editing the node's source changes its identity, so it runs again ...
    nodes = tmp_path / "nodes/test_nodes.py"
    nodes.write_text(nodes.read_text() + "\n# a harmless edit\n", encoding="utf-8")
    second = planner(path, picture="in.png")
    outcome = await WorkflowRun(
        await make_plan(second), run_dir=tmp_path / "runs/b", services=provider.services()
    ).run()

    # ... but its identical paid request is answered from the call cache.
    assert outcome.ok, outcome.failed
    assert [name for name, _ in provider.calls] == ["image.edit"]
    calls = [e for e in _events(tmp_path / "runs/b") if e["event"] == "call"]
    assert [call["cached"] for call in calls] == [True]


async def test_a_call_that_would_cross_the_ceiling_is_not_made(tmp_path: Path) -> None:
    flow = """
        gnode: workflow/v1
        id: flow
        title: Flow
        steps:
          one: { uses: gnode/image.generate@1, with: { prompt: one } }
          two: { uses: gnode/image.generate@1, with: { prompt: two }, needs: [one] }
        """
    path = project(tmp_path, flow)
    provider = FakeProvider(planner(path).store, cost_usd=0.03)

    outcome = await _run(path, tmp_path / "runs/one", provider, max_usd=0.06)

    assert not outcome.ok
    assert [name for name, _ in provider.calls] == ["image.generate"]
    assert outcome.results["two#1"].status == "failed"
    assert "ceiling" in (outcome.results["two#1"].error or "")
    refused = [e for e in _events(tmp_path / "runs/one") if e["event"] == "budget_refused"]
    assert refused and refused[0]["needed_usd"] == 0.04


async def test_without_live_a_paid_call_fails_the_step_and_spends_nothing(tmp_path: Path) -> None:
    path = project(
        tmp_path,
        """
        gnode: workflow/v1
        id: flow
        title: Flow
        steps:
          draw: { uses: gnode/image.generate@1, with: { prompt: x } }
        """,
    )
    built = planner(path)
    provider = FakeProvider(built.store)
    outcome = await WorkflowRun(
        await make_plan(built),
        run_dir=tmp_path / "runs/one",
        services=provider.services(live=False),
    ).run()

    assert not outcome.ok and provider.calls == []
    assert "--live" in (outcome.results["draw#1"].error or "")


async def test_an_agent_calls_its_tools_and_replays_paid_turns(tmp_path: Path) -> None:
    flow = """
        gnode: workflow/v1
        id: flow
        title: Flow
        steps:
          notes:
            uses: ./nodes/test_nodes.py#note_taker
            with: { topic: the harbour }
        """
    path = project(tmp_path, flow)
    provider = FakeProvider(planner(path).store, cost_usd=0.002)
    first = await _run(path, tmp_path / "runs/a", provider)

    assert first.ok, first.failed
    notes = first.results["notes#1"].outputs["notes"]
    assert notes.content == {"answer": "done", "words": ["tide"]}
    assert [name for name, _ in provider.calls] == ["agent.turn", "agent.turn"]

    nodes = tmp_path / "nodes/test_nodes.py"
    nodes.write_text(nodes.read_text() + "\n# edited\n", encoding="utf-8")
    again = await _run(path, tmp_path / "runs/b", provider)

    assert again.ok and len(provider.calls) == 2, "both turns came from the call cache"
