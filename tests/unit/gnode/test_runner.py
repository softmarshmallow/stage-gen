"""The engine's one runner: one record per run, a ceiling over every invocation, clean stops."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path

import pytest

from gnode import (
    CacheDisposition,
    Graph,
    Node,
    NodeExecutionContext,
    NodeExecutionResult,
    Resource,
    RetryOwner,
    RunCanceled,
    RunLocked,
    RunView,
    build_node_cache_key,
    build_run_view,
    read_run_events,
    run_graph,
    seal_graph,
    write_graph,
)


def _node(
    node_id: str,
    *,
    depends_on: tuple[str, ...] = (),
    provider: bool = False,
    cost_high_usd: float = 0.0,
    resource_id: str | None = None,
) -> Node:
    operation = "image_generation" if provider else "local"
    return Node(
        node_id=node_id,
        type_id="test/step.run",
        domain="test",
        description=node_id,
        depends_on=depends_on,
        operation=operation,
        resource_id=resource_id or ("provider" if provider else "local"),
        provider="example" if provider else None,
        model="image-v1" if provider else None,
        retry_owner=RetryOwner.COMPONENT if provider else RetryOwner.NONE,
        max_attempts=1,
        cache_key=build_node_cache_key(
            node_id=node_id,
            type_id="test/step.run",
            operation=operation,
            provider="example" if provider else None,
            model="image-v1" if provider else None,
            input_sha256=(),
            dependency_cache_keys=depends_on,
            contract_version="test-v1",
        ),
        estimated_duration_seconds=0.0,
        estimated_cost_low_usd=0.0,
        estimated_cost_high_usd=cost_high_usd,
    )


def _graph(nodes: Sequence[Node], *, resources: Sequence[Resource] | None = None) -> Graph:
    return seal_graph(
        Graph,
        resources=resources
        or [
            Resource(resource_id="local", max_in_flight=4, rate_limit_owner="none"),
            Resource(resource_id="provider", max_in_flight=4, rate_limit_owner="none"),
        ],
        nodes=list(nodes),
        terminal_node_id=nodes[-1].node_id,
        schema_version=1,
        kind="test-graph-v1",
    )


def _planned(root: Path, graph: Graph) -> Path:
    run_dir = root / "run"
    run_dir.mkdir()
    write_graph(run_dir / "execution-plan.json", graph)
    return run_dir


class Worker:
    """A handler with a cache: what ran, what it reported, and nodes told to wait."""

    def __init__(self, *, hold: Sequence[str] = (), cost_usd: float = 0.4) -> None:
        self.calls: list[str] = []
        self.started = defaultdict[str, asyncio.Event](asyncio.Event)
        self.started_at: dict[str, float] = {}
        self.done: set[str] = set()
        self.hold = set(hold)
        self.cost_usd = cost_usd

    async def __call__(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        if node.node_id in self.done:
            return NodeExecutionResult(
                cache=CacheDisposition.HIT, attempts=1, provider_operations=0, known_cost_usd=0.0
            )
        await context.begin_dispatch()
        self.calls.append(node.node_id)
        self.started[node.node_id].set()
        self.started_at[node.node_id] = time.monotonic()
        if node.node_id in self.hold:
            await asyncio.Event().wait()
        self.done.add(node.node_id)
        return NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=1,
            provider_operations=0 if node.is_local else 1,
            known_cost_usd=None if node.is_local else self.cost_usd,
        )


async def _started(worker: Worker, node_id: str) -> None:
    async with asyncio.timeout(5):
        await worker.started[node_id].wait()


def _events(run_dir: Path, name: str) -> list[dict[str, object]]:
    return [event for event in read_run_events(run_dir) if event["event"] == name]


async def _killed(run: asyncio.Task[object]) -> None:
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run


async def test_a_killed_run_continues_in_place_with_one_record(tmp_path: Path) -> None:
    graph = _graph([_node("first"), _node("second", depends_on=("first",))])
    run_dir = _planned(tmp_path, graph)
    worker = Worker(hold=("second",))
    first = asyncio.create_task(
        run_graph(graph, worker, run_dir=run_dir, invocation_id="one", handle_signals=False)
    )
    await _started(worker, "second")
    await _killed(first)

    worker.hold.clear()
    summary = await run_graph(
        graph, worker, run_dir=run_dir, invocation_id="two", handle_signals=False
    )

    assert summary.ok
    assert worker.calls == ["first", "second", "second"]
    events = read_run_events(run_dir)
    assert {event["kind"] for event in events} == {"gnode-run-events-v1"}
    assert [event["invocation_id"] for event in _events(run_dir, "run_started")] == ["one", "two"]
    assert _events(run_dir, "run_started")[1]["resumed"] is True
    assert _events(run_dir, "run_canceled")[0]["reason"] == "caller"
    view = build_run_view(run_dir, graph_type=Graph, view_type=RunView)
    assert (view.invocation_id, view.run_state) == ("two", "succeeded")
    assert [(node.state, node.cache) for node in view.nodes] == [
        ("succeeded", CacheDisposition.HIT),
        ("succeeded", CacheDisposition.MISS),
    ]


async def test_a_line_cut_by_a_crash_is_dropped_before_the_log_grows(tmp_path: Path) -> None:
    graph = _graph([_node("only")])
    run_dir = _planned(tmp_path, graph)
    await run_graph(graph, Worker(), run_dir=run_dir, invocation_id="one", handle_signals=False)
    with (run_dir / "execution-trace.jsonl").open("a", encoding="utf-8") as log:
        log.write('{"event": "node_fin')

    await run_graph(graph, Worker(), run_dir=run_dir, invocation_id="two", handle_signals=False)

    assert [event["invocation_id"] for event in _events(run_dir, "run_finished")] == [
        "one",
        "two",
    ]


async def test_a_node_that_does_not_fit_the_ceiling_is_refused_before_it_runs(
    tmp_path: Path,
) -> None:
    graph = _graph(
        [
            _node("a", provider=True, cost_high_usd=1.0),
            _node("b", provider=True, cost_high_usd=1.0, depends_on=("a",)),
            _node("c", depends_on=("b",)),
        ]
    )
    run_dir = _planned(tmp_path, graph)
    worker = Worker(cost_usd=0.4)

    summary = await run_graph(
        graph,
        worker,
        run_dir=run_dir,
        invocation_id="one",
        ceiling_usd=1.2,
        handle_signals=False,
    )

    assert not summary.ok
    assert worker.calls == ["a"]
    states = {trace.node_id: (trace.status, trace.attempts) for trace in summary.nodes}
    assert states["b"] == ("failed", 0) and states["c"][0] == "skipped"
    (refused,) = _events(run_dir, "budget_refused")
    assert (refused["node_id"], refused["needed_usd"], refused["remaining_usd"]) == ("b", 1.0, 0.8)
    assert [event["charged_usd"] for event in _events(run_dir, "budget_settled")] == [0.4]

    # The ceiling covers the run, not the invocation: what "a" cost still counts.
    again = await run_graph(
        graph,
        worker,
        run_dir=run_dir,
        invocation_id="two",
        ceiling_usd=1.2,
        handle_signals=False,
    )
    assert not again.ok and worker.calls == ["a"]
    assert _events(run_dir, "run_started")[1]["charged_usd"] == 0.4


async def test_a_reservation_a_killed_invocation_left_open_stays_charged(tmp_path: Path) -> None:
    graph = _graph([_node("slow", provider=True, cost_high_usd=1.0)])
    run_dir = _planned(tmp_path, graph)
    worker = Worker(hold=("slow",))
    first = asyncio.create_task(
        run_graph(
            graph,
            worker,
            run_dir=run_dir,
            invocation_id="one",
            ceiling_usd=1.5,
            handle_signals=False,
        )
    )
    await _started(worker, "slow")
    await _killed(first)

    worker.hold.clear()
    summary = await run_graph(
        graph,
        worker,
        run_dir=run_dir,
        invocation_id="two",
        ceiling_usd=1.5,
        handle_signals=False,
    )

    # Nobody can say the interrupted call did not bill, so its full hold counts, and
    # a second attempt at the same worst case no longer fits.
    assert _events(run_dir, "run_started")[1]["charged_usd"] == 1.0
    assert not summary.ok and worker.calls == ["slow"]


async def test_the_wall_clock_limit_stops_the_run_and_says_so(tmp_path: Path) -> None:
    graph = _graph([_node("forever")])
    run_dir = _planned(tmp_path, graph)

    with pytest.raises(RunCanceled) as stopped:
        await run_graph(
            graph,
            Worker(hold=("forever",)),
            run_dir=run_dir,
            invocation_id="one",
            wall_timeout_seconds=0.05,
            handle_signals=False,
        )

    assert stopped.value.reason == "wall_timeout"
    (canceled,) = _events(run_dir, "run_canceled")
    assert canceled["reason"] == "wall_timeout"
    assert canceled["started_node_ids"] == ["forever"]
    assert build_run_view(run_dir, graph_type=Graph, view_type=RunView).run_state == "canceled"


async def test_a_second_invocation_of_a_running_run_is_refused(tmp_path: Path) -> None:
    graph = _graph([_node("busy")])
    run_dir = _planned(tmp_path, graph)
    worker = Worker(hold=("busy",))
    first = asyncio.create_task(
        run_graph(graph, worker, run_dir=run_dir, invocation_id="one", handle_signals=False)
    )
    await _started(worker, "busy")

    with pytest.raises(RunLocked):
        await run_graph(graph, worker, run_dir=run_dir, invocation_id="two", handle_signals=False)
    await _killed(first)


async def test_a_folder_holding_another_plan_is_refused(tmp_path: Path) -> None:
    run_dir = _planned(tmp_path, _graph([_node("old")]))

    with pytest.raises(ValueError, match="holds a different plan"):
        await run_graph(
            _graph([_node("new")]),
            Worker(),
            run_dir=run_dir,
            invocation_id="one",
            handle_signals=False,
        )


async def test_the_scheduler_paces_request_starts_on_a_route_it_owns(tmp_path: Path) -> None:
    paced = Resource(
        resource_id="paced",
        max_in_flight=3,
        requests_per_minute=1_200,
        rate_limit_owner="scheduler",
    )
    graph = _graph(
        [
            *(_node(f"call{index}", provider=True, resource_id="paced") for index in range(3)),
            _node("end", depends_on=("call0", "call1", "call2")),
        ],
        resources=[
            Resource(resource_id="local", max_in_flight=4, rate_limit_owner="none"),
            paced,
        ],
    )
    worker = Worker()

    await run_graph(
        graph,
        worker,
        run_dir=_planned(tmp_path, graph),
        invocation_id="one",
        handle_signals=False,
    )

    starts = sorted(worker.started_at[f"call{index}"] for index in range(3))
    assert all(later - earlier >= 0.045 for earlier, later in pairwise(starts))
