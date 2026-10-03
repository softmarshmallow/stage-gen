"""Long provider jobs: submitted once, collected after a crash, never paid for twice."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from gnode import (
    CallRecord,
    HostServices,
    JobLog,
    LongJob,
    Route,
    RoutePrice,
    RouteTable,
    Store,
    WorkflowRun,
    cli,
    make_plan,
    make_planner,
)
from gnode_std import file_facts, standard_types
from tests.unit.gnode.workflow._project import PNG, project

VIDEO = Route(
    "video.generate",
    "clip-a",
    "acme",
    RoutePrice(
        0.03,
        0.375,
        unit="second",
        max_units=10,
        by="resolution",
        tiers={"360p": (0.03, 0.0375), "4k": (0.30, 0.375)},
    ),
    frozenset({"first_last_frame"}),
)

FLOW = """
gnode: workflow/v1
id: flow
title: Flow
inputs:
  picture: { type: file, kind: image }
steps:
  take:
    uses: gnode/video.generate@1
    requires: [first_last_frame]
    with:
      prompt: a lantern sways
      first_frame: ${{ inputs.picture }}
      last_frame: ${{ inputs.picture }}
      duration: 3
      resolution: 360p
outputs:
  video: ${{ steps.take.outputs.video }}
"""

MP4 = b"\\x00\\x00\\x00\\x18ftypisom" + b"\\x00" * 16


class Interrupted(Exception):
    """The connection, or the process, died here."""


class FakeVideo:
    """A provider whose jobs take one submission and one collection."""

    def __init__(self, store: Store, *, die: str | None = None) -> None:
        self.store = store
        self.die = die
        self.submitted: list[str] = []
        self.collected: list[str] = []

    def job(self) -> LongJob:
        async def start(
            route: Route, request: Mapping[str, Any], take: int, log: JobLog
        ) -> CallRecord:
            log.submitting()
            if self.die == "submitting":
                raise Interrupted
            handle = {"request_id": f"job-{len(self.submitted) + 1}"}
            self.submitted.append(handle["request_id"])
            log.submitted(handle)
            if self.die == "polling":
                raise Interrupted
            return await collect(route, request, take, handle, log)

        async def collect(
            route: Route,
            request: Mapping[str, Any],
            take: int,
            handle: Mapping[str, Any],
            log: JobLog,
        ) -> CallRecord:
            self.collected.append(str(handle["request_id"]))
            video = self.store.put_bytes(MP4, kind="video/mp4", name="video")
            return CallRecord({"video": video}, {"job": handle["request_id"]}, 0.09)

        return LongJob(start, collect)


def _planner(path: Path):  # type: ignore[no-untyped-def]
    return make_planner(
        path,
        inputs={"picture": "in.png"},
        cwd=path.parent.parent,
        builtins=standard_types(),
        routes=RouteTable([VIDEO]),
        facts_reader=file_facts,
    )


async def _run(path: Path, run_dir: Path, provider: FakeVideo):  # type: ignore[no-untyped-def]
    services = HostServices(
        store=provider.store, capabilities={"video.generate": provider.job()}, live=True
    )
    plan = await make_plan(_planner(path))
    return await WorkflowRun(plan, run_dir=run_dir, services=services).run()


def _project(tmp_path: Path) -> Path:
    path = project(tmp_path, FLOW, **{"in.png": PNG})
    gnode_yaml = tmp_path / "gnode.yaml"
    gnode_yaml.write_text(
        gnode_yaml.read_text() + "  video.generate: clip-a@acme\n", encoding="utf-8"
    )
    return path


async def test_the_plan_prices_a_take_by_its_resolution_and_length(tmp_path: Path) -> None:
    plan = await make_plan(_planner(_project(tmp_path)))
    assert plan.ok, plan.problems
    assert plan.estimate() == (0.09, 0.1125)


async def test_a_job_submitted_before_a_crash_is_collected_not_submitted_again(
    tmp_path: Path,
) -> None:
    path = _project(tmp_path)
    store = _planner(path).store
    dying = FakeVideo(store, die="polling")
    assert not (await _run(path, tmp_path / "runs/one", dying)).ok
    assert dying.submitted == ["job-1"] and [job.state for job in store.jobs()] == ["submitted"]

    resumed = FakeVideo(store)
    outcome = await _run(path, tmp_path / "runs/one", resumed)

    assert outcome.ok, outcome.failed
    assert resumed.submitted == [] and resumed.collected == ["job-1"]
    assert list(store.jobs()) == []


async def test_a_crash_while_submitting_stops_for_a_person(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _project(tmp_path)
    store = _planner(path).store
    assert not (await _run(path, tmp_path / "runs/one", FakeVideo(store, die="submitting"))).ok

    careful = FakeVideo(store)
    outcome = await _run(path, tmp_path / "runs/one", careful)

    assert not outcome.ok and careful.submitted == []
    assert "gnode jobs forget" in (outcome.results["take#1"].error or "")
    assert cli.main(["jobs"], cwd=tmp_path) == 0
    (key,) = [job.key for job in store.jobs()]
    assert key in capsys.readouterr().out

    assert cli.main(["jobs", "--forget", key], cwd=tmp_path) == 0
    again = FakeVideo(store)
    outcome = await _run(path, tmp_path / "runs/two", again)
    assert outcome.ok, outcome.failed
    assert again.submitted == ["job-1"]
