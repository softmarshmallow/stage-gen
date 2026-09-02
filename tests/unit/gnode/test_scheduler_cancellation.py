from __future__ import annotations

import asyncio

import pytest

from gnode import (
    AbortError,
    CacheDisposition,
    Graph,
    MemoryTraceSink,
    Node,
    NodeExecutionContext,
    NodeExecutionResult,
    Resource,
    RetryOwner,
    Scheduler,
    build_node_cache_key,
    seal_graph,
)


def _node(node_id: str, *, depends_on: tuple[str, ...] = ()) -> Node:
    return Node(
        node_id=node_id,
        type_id="test/step.run",
        domain="test",
        description=node_id,
        depends_on=depends_on,
        operation="local",
        resource_id="local",
        retry_owner=RetryOwner.NONE,
        max_attempts=1,
        cache_key=build_node_cache_key(
            node_id=node_id,
            type_id="test/step.run",
            operation="local",
            provider=None,
            model=None,
            input_sha256=(),
            dependency_cache_keys=(),
            contract_version="test-v1",
        ),
        estimated_duration_seconds=0.0,
        estimated_cost_low_usd=0.0,
        estimated_cost_high_usd=0.0,
    )


def _graph() -> Graph:
    first = _node("first")
    return seal_graph(
        Graph,
        resources=[Resource(resource_id="local", max_in_flight=4, rate_limit_owner="none")],
        nodes=[first, _node("second", depends_on=("first",))],
        terminal_node_id="second",
        schema_version=1,
        kind="test-graph-v1",
    )


def _provider_graph() -> Graph:
    node = Node(
        node_id="provider",
        type_id="test/provider.run",
        domain="test",
        description="provider",
        operation="image_generation",
        resource_id="provider",
        provider="example",
        model="image-v1",
        retry_owner=RetryOwner.COMPONENT,
        max_attempts=6,
        cache_key=build_node_cache_key(
            node_id="provider",
            type_id="test/provider.run",
            operation="image_generation",
            provider="example",
            model="image-v1",
            input_sha256=(),
            dependency_cache_keys=(),
            contract_version="test-v1",
        ),
        estimated_duration_seconds=0.0,
        estimated_cost_low_usd=0.0,
        estimated_cost_high_usd=0.0,
    )
    return seal_graph(
        Graph,
        resources=[Resource(resource_id="provider", max_in_flight=1, rate_limit_owner="none")],
        nodes=[node],
        terminal_node_id=node.node_id,
        schema_version=1,
        kind="test-provider-graph-v1",
    )


async def test_an_interrupted_run_records_that_it_was_canceled() -> None:
    """The scheduler is where an interrupt lands while the trace sink is open."""

    graph = _graph()
    sink = MemoryTraceSink()
    entered = asyncio.Event()

    async def handler(node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        entered.set()
        await asyncio.sleep(30)
        return NodeExecutionResult(cache=CacheDisposition.MISS, attempts=1, provider_operations=0)

    run = asyncio.create_task(
        Scheduler(graph.resources).run(
            graph, handler, invocation_id="cancel-fixture", trace_sink=sink
        )
    )
    await entered.wait()
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run

    events = [event["event"] for event in sink.events]
    assert events == ["run_started", "node_started", "run_canceled"]

    canceled = sink.events[-1]
    assert canceled["invocation_id"] == "cancel-fixture"
    assert canceled["graph_sha256"] == graph.graph_sha256
    # The nodes that were in flight when the interrupt arrived, named so a reader
    # knows what was abandoned rather than never attempted.
    assert canceled["started_node_ids"] == ["first"]


async def test_a_completed_run_records_no_cancellation() -> None:
    graph = _graph()
    sink = MemoryTraceSink()

    async def handler(node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        return NodeExecutionResult(cache=CacheDisposition.MISS, attempts=1, provider_operations=0)

    summary = await Scheduler(graph.resources).run(
        graph, handler, invocation_id="finish-fixture", trace_sink=sink
    )

    assert summary.ok is True
    assert [event["event"] for event in sink.events][-1] == "run_finished"
    assert not any(event["event"] == "run_canceled" for event in sink.events)


async def test_provider_cancellation_preserves_started_operation_count_in_trace() -> None:
    graph = _provider_graph()

    async def handler(node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        raise AbortError("cancelled during retry backoff", provider_operations=1)

    summary = await Scheduler(graph.resources).run(
        graph,
        handler,
        invocation_id="provider-cancel-fixture",
    )

    assert summary.ok is False
    assert summary.provider_operation_counts == {"image_generation": 1}
    assert summary.nodes[0].attempts == 1
    assert summary.nodes[0].provider_operations == 1
