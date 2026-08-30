"""Resource-aware scheduling: one offline projection and one live scheduler.

The scheduler never retries. A provider operation has exactly one retry owner,
and it lives inside the node handler.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence
from contextlib import AsyncExitStack
from typing import Literal

from pydantic import Field

from gnode.contracts.artifacts import SHA256_PATTERN, PersistedContractModel
from gnode.graph import (
    Graph,
    Node,
    NodeExecutionContext,
    NodeExecutionError,
    NodeExecutionResult,
    NodeHandler,
    NodeStatus,
    Resource,
    node_closure,
    topological_node_ids,
)
from gnode.reliability import redact_secrets
from gnode.trace import (
    MemoryTraceSink,
    NodeTrace,
    RunSummary,
    TraceSink,
    elapsed_ms,
    node_event,
    run_event,
)


class ProjectedSpan(PersistedContractModel):
    node_id: str
    operation: str
    resource_id: str
    started_offset_ms: int = Field(ge=0)
    ended_offset_ms: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    blocked_by_node_id: str | None = None
    blocked_by_reason: Literal["dependency", "rate_limit", "concurrency"] | None = None


class Projection(PersistedContractModel):
    """One offline schedule projection: what a run would cost and how long.

    Never calls a provider (D7), so opening a plan is always free.
    """

    schema_version: int = Field(ge=1)
    kind: str = Field(min_length=1, max_length=96)
    graph_sha256: str = Field(pattern=SHA256_PATTERN)
    topology_sha256: str = Field(pattern=SHA256_PATTERN)
    duration_ms: int = Field(ge=0)
    critical_path: tuple[str, ...]
    operation_counts: dict[str, int]
    estimated_cost_low_usd: float = Field(ge=0.0)
    estimated_cost_high_usd: float = Field(ge=0.0)
    spans: tuple[ProjectedSpan, ...]


def project_schedule(graph: Graph) -> Projection:
    """Project one deterministic resource-aware schedule without calling a provider."""

    spans: dict[str, ProjectedSpan] = {}
    resource_spans: dict[str, list[ProjectedSpan]] = {
        resource.resource_id: [] for resource in graph.resources
    }
    resources = {resource.resource_id: resource for resource in graph.resources}
    blockers: dict[str, str | None] = {}

    for node_id in topological_node_ids(graph.nodes):
        node = graph.node(node_id)
        dependency: ProjectedSpan | None = None
        if node.depends_on:
            dependency = max(
                (spans[dependency_id] for dependency_id in node.depends_on),
                key=lambda span: span.ended_offset_ms,
            )
        candidate = dependency.ended_offset_ms if dependency is not None else 0
        blocking_node_id = dependency.node_id if dependency is not None else None
        blocking_reason: Literal["dependency", "rate_limit", "concurrency"] | None = (
            "dependency" if dependency is not None else None
        )
        resource = resources[node.resource_id]
        scheduled = resource_spans[node.resource_id]
        if resource.requests_per_minute is not None and scheduled:
            minimum_interval = 60_000 / resource.requests_per_minute
            rate_candidate = round(scheduled[-1].started_offset_ms + minimum_interval)
            if rate_candidate > candidate:
                candidate = rate_candidate
                blocking_node_id = scheduled[-1].node_id
                blocking_reason = "rate_limit"
        while resource.max_in_flight is not None:
            active = [
                span
                for span in scheduled
                if span.started_offset_ms <= candidate < span.ended_offset_ms
            ]
            if len(active) < resource.max_in_flight:
                break
            earliest = min(active, key=lambda span: span.ended_offset_ms)
            candidate = earliest.ended_offset_ms
            blocking_node_id = earliest.node_id
            blocking_reason = "concurrency"
            if resource.requests_per_minute is not None and scheduled:
                minimum_interval = 60_000 / resource.requests_per_minute
                rate_candidate = round(scheduled[-1].started_offset_ms + minimum_interval)
                if rate_candidate > candidate:
                    candidate = rate_candidate
                    blocking_node_id = scheduled[-1].node_id
                    blocking_reason = "rate_limit"
        duration_ms = round(node.estimated_duration_seconds * 1_000)
        span = ProjectedSpan(
            node_id=node.node_id,
            operation=node.operation,
            resource_id=node.resource_id,
            started_offset_ms=candidate,
            ended_offset_ms=candidate + duration_ms,
            duration_ms=duration_ms,
            blocked_by_node_id=blocking_node_id,
            blocked_by_reason=blocking_reason,
        )
        spans[node.node_id] = span
        scheduled.append(span)
        blockers[node.node_id] = blocking_node_id

    terminal = spans[graph.terminal_node_id]
    critical_path_reversed: list[str] = []
    cursor: str | None = terminal.node_id
    while cursor is not None:
        critical_path_reversed.append(cursor)
        cursor = blockers[cursor]
    ordered_spans = tuple(spans[node.node_id] for node in graph.nodes)
    return Projection(
        schema_version=graph.schema_version,
        kind=graph.PROJECTION_KIND,
        graph_sha256=graph.graph_sha256,
        topology_sha256=graph.topology_sha256,
        duration_ms=terminal.ended_offset_ms,
        critical_path=tuple(reversed(critical_path_reversed)),
        operation_counts=graph.operation_counts(),
        estimated_cost_low_usd=round(sum(node.estimated_cost_low_usd for node in graph.nodes), 6),
        estimated_cost_high_usd=round(sum(node.estimated_cost_high_usd for node in graph.nodes), 6),
        spans=ordered_spans,
    )


class Scheduler:
    """Run ready DAG nodes concurrently; provider retry loops stay inside components."""

    def __init__(
        self,
        resources: Sequence[Resource],
        *,
        node_timeout_seconds: float = 1_800.0,
        secrets: Sequence[str] = (),
    ) -> None:
        if node_timeout_seconds <= 0:
            raise ValueError("node timeout must be positive")
        self._resources = {resource.resource_id: resource for resource in resources}
        self._semaphores = {
            resource.resource_id: (
                asyncio.Semaphore(resource.max_in_flight)
                if resource.max_in_flight is not None
                else None
            )
            for resource in resources
        }
        self._node_timeout_seconds = node_timeout_seconds
        self._secrets = tuple(secret for secret in secrets if secret)

    async def run(
        self,
        graph: Graph,
        handler: NodeHandler,
        *,
        invocation_id: str,
        trace_sink: TraceSink | None = None,
        target_node_ids: Sequence[str] | None = None,
    ) -> RunSummary:
        if tuple(self._resources) != tuple(resource.resource_id for resource in graph.resources):
            raise ValueError("executor resources must exactly match the execution graph")
        selected_nodes = node_closure(graph, target_node_ids)
        selected_ids = {node.node_id for node in selected_nodes}
        targets = (
            (graph.terminal_node_id,)
            if target_node_ids is None
            else tuple(dict.fromkeys(target_node_ids))
        )
        sink = trace_sink or MemoryTraceSink()
        started = time.perf_counter()
        sink.emit(run_event("run_started", invocation_id, graph, offset_ms=0))
        pending = set(selected_ids)
        results: dict[str, NodeExecutionResult] = {}
        traces: dict[str, NodeTrace] = {}
        running: dict[asyncio.Task[tuple[NodeTrace, NodeExecutionResult | None]], str] = {}
        ready_at: dict[str, int] = {node.node_id: 0 for node in selected_nodes}

        while pending or running:
            changed = True
            while changed:
                changed = False
                for node in selected_nodes:
                    node_id = node.node_id
                    if node_id not in pending:
                        continue
                    terminal_dependencies = {
                        dependency for dependency in node.depends_on if dependency in traces
                    }
                    if len(terminal_dependencies) != len(node.depends_on):
                        continue
                    blocked_by = tuple(
                        dependency
                        for dependency in node.depends_on
                        if traces[dependency].status is not NodeStatus.SUCCEEDED
                    )
                    if blocked_by:
                        now = elapsed_ms(started)
                        trace = NodeTrace(
                            node_id=node_id,
                            status=NodeStatus.SKIPPED,
                            ready_offset_ms=now,
                            ended_offset_ms=now,
                            queue_ms=0,
                            duration_ms=0,
                            attempts=0,
                            provider_operations=0,
                            blocked_by=blocked_by,
                        )
                        traces[node_id] = trace
                        pending.remove(node_id)
                        sink.emit(node_event("node_skipped", invocation_id, graph, trace))
                        changed = True
                        continue
                    ready = max(
                        (traces[dependency].ended_offset_ms for dependency in node.depends_on),
                        default=0,
                    )
                    ready_at[node_id] = ready
                    task = asyncio.create_task(
                        self._run_node(
                            graph,
                            node,
                            handler,
                            invocation_id=invocation_id,
                            dependency_results={
                                dependency: results[dependency] for dependency in node.depends_on
                            },
                            started=started,
                            ready_offset_ms=ready,
                            sink=sink,
                        ),
                        name=f"gnode:{node_id}",
                    )
                    running[task] = node_id
                    pending.remove(node_id)
                    changed = True

            if not running:
                if pending:
                    raise RuntimeError("execution scheduler reached an impossible pending state")
                break
            try:
                completed, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
            except BaseException:
                # An interrupt reaches the scheduler here, where the trace sink is
                # still open. Record that the run was cancelled so its records say
                # so outright, instead of leaving a reader to infer it from a trace
                # that simply stops. Then let the interrupt finish arriving.
                for task in running:
                    task.cancel()
                sink.emit(
                    {
                        **run_event(
                            "run_canceled", invocation_id, graph, offset_ms=elapsed_ms(started)
                        ),
                        "started_node_ids": sorted(running.values()),
                    }
                )
                raise
            for task in completed:
                node_id = running.pop(task)
                trace, result = task.result()
                traces[node_id] = trace
                if trace.status is NodeStatus.SUCCEEDED:
                    if result is None:
                        raise RuntimeError("successful execution task did not retain its result")
                    results[node_id] = result

        ordered = tuple(traces[node.node_id] for node in selected_nodes)
        duration_ms = elapsed_ms(started)
        provider_counts = {
            operation: sum(
                trace.provider_operations
                for node, trace in zip(selected_nodes, ordered, strict=True)
                if node.operation == operation
            )
            for operation in graph.provider_operation_vocabulary()
        }
        costs = [trace.known_cost_usd for trace in ordered if trace.known_cost_usd is not None]
        summary = RunSummary(
            schema_version=graph.schema_version,
            kind=graph.RUN_SUMMARY_KIND,
            invocation_id=invocation_id,
            graph_sha256=graph.graph_sha256,
            ok=all(traces[node_id].status is NodeStatus.SUCCEEDED for node_id in targets),
            duration_ms=duration_ms,
            nodes=ordered,
            provider_operation_counts=provider_counts,
            known_cost_usd=round(sum(costs), 6) if costs else None,
        )
        sink.emit(
            {
                **run_event("run_finished", invocation_id, graph, offset_ms=duration_ms),
                "ok": summary.ok,
                "provider_operation_counts": provider_counts,
            }
        )
        return summary

    async def _run_node(
        self,
        graph: Graph,
        node: Node,
        handler: NodeHandler,
        *,
        invocation_id: str,
        dependency_results: Mapping[str, NodeExecutionResult],
        started: float,
        ready_offset_ms: int,
        sink: TraceSink,
    ) -> tuple[NodeTrace, NodeExecutionResult | None]:
        semaphore = self._semaphores[node.resource_id]
        async with AsyncExitStack() as stack:
            if semaphore is not None:
                await stack.enter_async_context(semaphore)
            node_started = elapsed_ms(started)
            sink.emit(
                {
                    **run_event("node_started", invocation_id, graph, offset_ms=node_started),
                    "node_id": node.node_id,
                    "operation": node.operation,
                    "resource_id": node.resource_id,
                    "cache_key": node.cache_key,
                }
            )
            try:
                async with asyncio.timeout(self._node_timeout_seconds):
                    result = await handler(
                        node,
                        NodeExecutionContext(
                            invocation_id=invocation_id,
                            graph_sha256=graph.graph_sha256,
                            dependency_results=dependency_results,
                        ),
                    )
                if result.attempts > node.max_attempts:
                    raise ValueError("node handler exceeded its declared attempt limit")
                if node.is_local and result.provider_operations != 0:
                    raise ValueError("local execution nodes must report zero provider operations")
                ended = elapsed_ms(started)
                trace = NodeTrace(
                    node_id=node.node_id,
                    status=NodeStatus.SUCCEEDED,
                    ready_offset_ms=ready_offset_ms,
                    started_offset_ms=node_started,
                    ended_offset_ms=ended,
                    queue_ms=max(0, node_started - ready_offset_ms),
                    duration_ms=max(0, ended - node_started),
                    cache=result.cache,
                    attempts=result.attempts,
                    provider_operations=result.provider_operations,
                    known_cost_usd=result.known_cost_usd,
                    artifacts=result.artifacts,
                )
                sink.emit(node_event("node_finished", invocation_id, graph, trace))
                return trace, result
            except Exception as error:
                ended = elapsed_ms(started)
                attempts = error.attempts if isinstance(error, NodeExecutionError) else 1
                provider_operations = (
                    error.provider_operations if isinstance(error, NodeExecutionError) else 0
                )
                known_cost = error.known_cost_usd if isinstance(error, NodeExecutionError) else None
                message = redact_secrets(str(error).strip() or type(error).__name__, self._secrets)
                message = message.replace("\x00", "[NUL]")[:2_000]
                trace = NodeTrace(
                    node_id=node.node_id,
                    status=NodeStatus.FAILED,
                    ready_offset_ms=ready_offset_ms,
                    started_offset_ms=node_started,
                    ended_offset_ms=ended,
                    queue_ms=max(0, node_started - ready_offset_ms),
                    duration_ms=max(0, ended - node_started),
                    attempts=min(max(attempts, 1), node.max_attempts),
                    provider_operations=max(0, provider_operations),
                    known_cost_usd=known_cost,
                    error=message,
                )
                sink.emit(node_event("node_failed", invocation_id, graph, trace))
                return trace, None
