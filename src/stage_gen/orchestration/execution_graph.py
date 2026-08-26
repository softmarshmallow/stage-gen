"""Provider-neutral executable DAG scheduling and sanitized trace contracts."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections.abc import Mapping, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

from pydantic import Field, field_validator, model_validator

from stage_gen.components._game_input import SHA256_PATTERN
from stage_gen.contracts.artifacts import PersistedContractModel
from stage_gen.reliability import atomic_write_json, redact_secrets

EXECUTION_GRAPH_SCHEMA_VERSION = 1
EXECUTION_TRACE_SCHEMA_VERSION = 1
_NODE_ID_PATTERN = r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$"


class OperationKind(StrEnum):
    LOCAL = "local"
    IMAGE_GENERATION = "image_generation"
    STRUCTURED_GENERATION = "structured_generation"
    MUSIC_GENERATION = "music_generation"


class RetryOwner(StrEnum):
    NONE = "none"
    COMPONENT = "component"


class CacheDisposition(StrEnum):
    HIT = "hit"
    MISS = "miss"
    BYPASS = "bypass"


class NodeStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExecutionResource(PersistedContractModel):
    resource_id: str = Field(pattern=_NODE_ID_PATTERN, max_length=96)
    max_in_flight: int | None = Field(default=None, ge=1, le=1_024)
    requests_per_minute: int | None = Field(default=None, ge=1)
    rate_limit_owner: Literal["scheduler", "provider_adapter", "none"]

    @model_validator(mode="after")
    def validate_rate_owner(self) -> ExecutionResource:
        if self.requests_per_minute is None and self.rate_limit_owner != "none":
            raise ValueError("rate-limited resources require requests_per_minute")
        if self.requests_per_minute is not None and self.rate_limit_owner == "none":
            raise ValueError("requests_per_minute requires a rate-limit owner")
        return self


class ExecutionNode(PersistedContractModel):
    node_id: str = Field(pattern=_NODE_ID_PATTERN, max_length=192)
    domain: str = Field(pattern=_NODE_ID_PATTERN, max_length=96)
    description: str = Field(min_length=1, max_length=512)
    depends_on: tuple[str, ...] = ()
    operation: OperationKind
    resource_id: str = Field(pattern=_NODE_ID_PATTERN, max_length=96)
    provider: str | None = Field(default=None, max_length=96)
    model: str | None = Field(default=None, max_length=192)
    retry_owner: RetryOwner
    max_attempts: int = Field(ge=1, le=6)
    input_sha256: tuple[str, ...] = ()
    cache_key: str = Field(pattern=SHA256_PATTERN)
    outputs: tuple[str, ...] = ()
    estimated_duration_seconds: float = Field(ge=0.0)
    estimated_cost_low_usd: float = Field(ge=0.0)
    estimated_cost_high_usd: float = Field(ge=0.0)

    @field_validator("depends_on")
    @classmethod
    def validate_dependencies(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("execution node dependencies must be unique")
        return value

    @field_validator("input_sha256")
    @classmethod
    def validate_input_digests(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("execution node input digests must be unique")
        for digest in value:
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError("execution node input digests must be SHA-256 values")
        return value

    @model_validator(mode="after")
    def validate_operation_ownership(self) -> ExecutionNode:
        is_local = self.operation is OperationKind.LOCAL
        if is_local:
            if self.provider is not None or self.model is not None:
                raise ValueError("local execution nodes must not declare provider models")
            if self.retry_owner is not RetryOwner.NONE or self.max_attempts != 1:
                raise ValueError("local execution nodes must not own provider retries")
        else:
            if not self.provider or not self.model:
                raise ValueError("provider execution nodes require provider and model")
            if self.retry_owner is not RetryOwner.COMPONENT:
                raise ValueError("provider retries must be owned by the component")
        if self.estimated_cost_high_usd < self.estimated_cost_low_usd:
            raise ValueError("estimated high cost must not be below estimated low cost")
        return self


class ExecutionGraph(PersistedContractModel):
    schema_version: Literal[1]
    kind: Literal["prepared-game-execution-graph-v1"]
    recipe: Literal["scrolling-preview"]
    game_id: str
    package_sha256: str = Field(pattern=SHA256_PATTERN)
    resources: tuple[ExecutionResource, ...]
    nodes: tuple[ExecutionNode, ...]
    terminal_node_id: str
    topology_sha256: str = Field(pattern=SHA256_PATTERN)
    graph_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_graph(self) -> ExecutionGraph:
        resource_ids = [resource.resource_id for resource in self.resources]
        if len(resource_ids) != len(set(resource_ids)):
            raise ValueError("execution graph resources must be unique")
        node_ids = [node.node_id for node in self.nodes]
        if not node_ids or len(node_ids) != len(set(node_ids)):
            raise ValueError("execution graph nodes must be non-empty and unique")
        known = set(node_ids)
        if self.terminal_node_id not in known:
            raise ValueError("execution graph terminal node is undeclared")
        for node in self.nodes:
            if node.node_id in node.depends_on:
                raise ValueError("execution graph nodes must not depend on themselves")
            unknown = sorted(set(node.depends_on) - known)
            if unknown:
                raise ValueError(
                    f"execution node {node.node_id} has undeclared dependencies: "
                    + ", ".join(unknown)
                )
            if node.resource_id not in resource_ids:
                raise ValueError(f"execution node {node.node_id} uses an undeclared resource")
        _topological_node_ids(self.nodes)
        descendants = _dependency_ancestors(self.terminal_node_id, self.nodes)
        orphaned = sorted(known - descendants - {self.terminal_node_id})
        if orphaned:
            raise ValueError(
                "execution graph contains nodes outside terminal closure: " + ", ".join(orphaned)
            )
        if self.topology_sha256 != execution_topology_sha256(self):
            raise ValueError("execution graph topology_sha256 is stale")
        if self.graph_sha256 != execution_graph_sha256(self):
            raise ValueError("execution graph graph_sha256 is stale")
        return self

    def node(self, node_id: str) -> ExecutionNode:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        raise KeyError(node_id)

    def operation_counts(self) -> dict[str, int]:
        return {
            operation.value: sum(node.operation is operation for node in self.nodes)
            for operation in OperationKind
        }


def execution_topology_sha256(graph: ExecutionGraph) -> str:
    identity = {
        "schema_version": graph.schema_version,
        "kind": graph.kind,
        "recipe": graph.recipe,
        "resources": [
            {
                "resource_id": resource.resource_id,
                "max_in_flight": resource.max_in_flight,
                "requests_per_minute": resource.requests_per_minute,
                "rate_limit_owner": resource.rate_limit_owner,
            }
            for resource in graph.resources
        ],
        "nodes": [
            {
                "node_id": node.node_id,
                "domain": node.domain,
                "depends_on": list(node.depends_on),
                "operation": node.operation.value,
                "resource_id": node.resource_id,
                "retry_owner": node.retry_owner.value,
                "max_attempts": node.max_attempts,
                "outputs": list(node.outputs),
            }
            for node in graph.nodes
        ],
        "terminal_node_id": graph.terminal_node_id,
    }
    return _sha256_json(identity)


def execution_graph_sha256(graph: ExecutionGraph) -> str:
    value = graph.model_dump(mode="json", exclude={"graph_sha256", "topology_sha256"})
    return _sha256_json(value)


def finalize_execution_graph(
    *,
    game_id: str,
    package_sha256: str,
    resources: Sequence[ExecutionResource],
    nodes: Sequence[ExecutionNode],
    terminal_node_id: str,
) -> ExecutionGraph:
    incomplete = ExecutionGraph.model_construct(
        schema_version=1,
        kind="prepared-game-execution-graph-v1",
        recipe="scrolling-preview",
        game_id=game_id,
        package_sha256=package_sha256,
        resources=tuple(resources),
        nodes=tuple(nodes),
        terminal_node_id=terminal_node_id,
        topology_sha256="0" * 64,
        graph_sha256="0" * 64,
    )
    topology_sha256 = execution_topology_sha256(incomplete)
    with_topology = incomplete.model_copy(update={"topology_sha256": topology_sha256})
    graph_sha256 = execution_graph_sha256(with_topology)
    return ExecutionGraph.model_validate(
        with_topology.model_copy(update={"graph_sha256": graph_sha256}).model_dump()
    )


class NodeArtifact(PersistedContractModel):
    artifact_ref: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    bytes: int = Field(ge=0)


@dataclass(frozen=True, slots=True)
class NodeExecutionResult:
    cache: CacheDisposition
    attempts: int
    provider_operations: int
    artifacts: tuple[NodeArtifact, ...] = ()
    known_cost_usd: float | None = None

    def __post_init__(self) -> None:
        if self.attempts < 1 or self.attempts > 6:
            raise ValueError("node execution attempts must be between one and six")
        if self.provider_operations < 0:
            raise ValueError("node provider operation count must be non-negative")
        if self.known_cost_usd is not None and self.known_cost_usd < 0:
            raise ValueError("known node cost must be non-negative")


class NodeExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        attempts: int = 1,
        provider_operations: int = 0,
        known_cost_usd: float | None = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.provider_operations = provider_operations
        self.known_cost_usd = known_cost_usd


@dataclass(frozen=True, slots=True)
class NodeExecutionContext:
    invocation_id: str
    graph_sha256: str
    dependency_results: Mapping[str, NodeExecutionResult]


class NodeHandler(Protocol):
    async def __call__(
        self, node: ExecutionNode, context: NodeExecutionContext
    ) -> NodeExecutionResult: ...


class TraceSink(Protocol):
    def emit(self, event: Mapping[str, object]) -> None: ...


class MemoryTraceSink:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def emit(self, event: Mapping[str, object]) -> None:
        self.events.append(dict(event))


class JsonlTraceSink:
    """Create one immutable JSONL trace without persisting absolute paths or secrets."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self._stream = os.fdopen(descriptor, "w", encoding="utf-8")

    def emit(self, event: Mapping[str, object]) -> None:
        self._stream.write(json.dumps(dict(event), sort_keys=True, separators=(",", ":")))
        self._stream.write("\n")
        self._stream.flush()

    def close(self) -> None:
        self._stream.close()


class NodeTrace(PersistedContractModel):
    node_id: str
    status: NodeStatus
    ready_offset_ms: int = Field(ge=0)
    started_offset_ms: int | None = Field(default=None, ge=0)
    ended_offset_ms: int = Field(ge=0)
    queue_ms: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    cache: CacheDisposition | None = None
    attempts: int = Field(ge=0, le=6)
    provider_operations: int = Field(ge=0)
    known_cost_usd: float | None = Field(default=None, ge=0.0)
    artifacts: tuple[NodeArtifact, ...] = ()
    blocked_by: tuple[str, ...] = ()
    error: str | None = None


class ExecutionSummary(PersistedContractModel):
    schema_version: Literal[1]
    kind: Literal["prepared-game-execution-summary-v1"]
    invocation_id: str
    graph_sha256: str = Field(pattern=SHA256_PATTERN)
    ok: bool
    duration_ms: int = Field(ge=0)
    nodes: tuple[NodeTrace, ...]
    provider_operation_counts: dict[str, int]
    known_cost_usd: float | None = Field(default=None, ge=0.0)


class ProjectedNodeSpan(PersistedContractModel):
    node_id: str
    operation: OperationKind
    resource_id: str
    started_offset_ms: int = Field(ge=0)
    ended_offset_ms: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    blocked_by_node_id: str | None = None
    blocked_by_reason: Literal["dependency", "rate_limit", "concurrency"] | None = None


class ExecutionProjection(PersistedContractModel):
    schema_version: Literal[1]
    kind: Literal["prepared-game-execution-projection-v1"]
    graph_sha256: str = Field(pattern=SHA256_PATTERN)
    topology_sha256: str = Field(pattern=SHA256_PATTERN)
    duration_ms: int = Field(ge=0)
    critical_path: tuple[str, ...]
    operation_counts: dict[str, int]
    estimated_cost_low_usd: float = Field(ge=0.0)
    estimated_cost_high_usd: float = Field(ge=0.0)
    spans: tuple[ProjectedNodeSpan, ...]


def project_execution(graph: ExecutionGraph) -> ExecutionProjection:
    """Project one deterministic resource-aware schedule without calling a provider."""

    spans: dict[str, ProjectedNodeSpan] = {}
    resource_spans: dict[str, list[ProjectedNodeSpan]] = {
        resource.resource_id: [] for resource in graph.resources
    }
    resources = {resource.resource_id: resource for resource in graph.resources}
    blockers: dict[str, str | None] = {}

    for node_id in _topological_node_ids(graph.nodes):
        node = graph.node(node_id)
        dependency: ProjectedNodeSpan | None = None
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
        span = ProjectedNodeSpan(
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
    return ExecutionProjection(
        schema_version=1,
        kind="prepared-game-execution-projection-v1",
        graph_sha256=graph.graph_sha256,
        topology_sha256=graph.topology_sha256,
        duration_ms=terminal.ended_offset_ms,
        critical_path=tuple(reversed(critical_path_reversed)),
        operation_counts=graph.operation_counts(),
        estimated_cost_low_usd=round(sum(node.estimated_cost_low_usd for node in graph.nodes), 6),
        estimated_cost_high_usd=round(sum(node.estimated_cost_high_usd for node in graph.nodes), 6),
        spans=ordered_spans,
    )


class DependencyExecutor:
    """Run ready DAG nodes concurrently; provider retry loops stay inside components."""

    def __init__(
        self,
        resources: Sequence[ExecutionResource],
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
        graph: ExecutionGraph,
        handler: NodeHandler,
        *,
        invocation_id: str,
        trace_sink: TraceSink | None = None,
        target_node_ids: Sequence[str] | None = None,
    ) -> ExecutionSummary:
        if tuple(self._resources) != tuple(resource.resource_id for resource in graph.resources):
            raise ValueError("executor resources must exactly match the execution graph")
        selected_nodes = _execution_node_closure(graph, target_node_ids)
        selected_ids = {node.node_id for node in selected_nodes}
        targets = (
            (graph.terminal_node_id,)
            if target_node_ids is None
            else tuple(dict.fromkeys(target_node_ids))
        )
        sink = trace_sink or MemoryTraceSink()
        started = time.perf_counter()
        sink.emit(_event("run_started", invocation_id, graph, offset_ms=0))
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
                        now = _elapsed_ms(started)
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
                        sink.emit(_node_event("node_skipped", invocation_id, graph, trace))
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
                        name=f"stage-gen:{node_id}",
                    )
                    running[task] = node_id
                    pending.remove(node_id)
                    changed = True

            if not running:
                if pending:
                    raise RuntimeError("execution scheduler reached an impossible pending state")
                break
            completed, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
            for task in completed:
                node_id = running.pop(task)
                trace, result = task.result()
                traces[node_id] = trace
                if trace.status is NodeStatus.SUCCEEDED:
                    if result is None:
                        raise RuntimeError("successful execution task did not retain its result")
                    results[node_id] = result

        ordered = tuple(traces[node.node_id] for node in selected_nodes)
        duration_ms = _elapsed_ms(started)
        provider_counts = {
            operation.value: sum(
                trace.provider_operations
                for node, trace in zip(selected_nodes, ordered, strict=True)
                if node.operation is operation
            )
            for operation in OperationKind
            if operation is not OperationKind.LOCAL
        }
        costs = [trace.known_cost_usd for trace in ordered if trace.known_cost_usd is not None]
        summary = ExecutionSummary(
            schema_version=1,
            kind="prepared-game-execution-summary-v1",
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
                **_event("run_finished", invocation_id, graph, offset_ms=duration_ms),
                "ok": summary.ok,
                "provider_operation_counts": provider_counts,
            }
        )
        return summary

    async def _run_node(
        self,
        graph: ExecutionGraph,
        node: ExecutionNode,
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
            node_started = _elapsed_ms(started)
            sink.emit(
                {
                    **_event("node_started", invocation_id, graph, offset_ms=node_started),
                    "node_id": node.node_id,
                    "operation": node.operation.value,
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
                if node.operation is OperationKind.LOCAL and result.provider_operations != 0:
                    raise ValueError("local execution nodes must report zero provider operations")
                ended = _elapsed_ms(started)
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
                sink.emit(_node_event("node_finished", invocation_id, graph, trace))
                return trace, result
            except Exception as error:
                ended = _elapsed_ms(started)
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
                sink.emit(_node_event("node_failed", invocation_id, graph, trace))
                return trace, None


def write_execution_plan(path: Path, graph: ExecutionGraph) -> None:
    atomic_write_json(path, graph.model_dump(mode="json"))


def write_execution_summary(path: Path, summary: ExecutionSummary) -> None:
    atomic_write_json(path, summary.model_dump(mode="json"))


def _dependency_ancestors(node_id: str, nodes: Sequence[ExecutionNode]) -> set[str]:
    dependencies = {node.node_id: set(node.depends_on) for node in nodes}
    ancestors: set[str] = set()
    frontier = list(dependencies[node_id])
    while frontier:
        dependency = frontier.pop()
        if dependency in ancestors:
            continue
        ancestors.add(dependency)
        frontier.extend(dependencies[dependency])
    return ancestors


def _execution_node_closure(
    graph: ExecutionGraph,
    target_node_ids: Sequence[str] | None,
) -> tuple[ExecutionNode, ...]:
    if target_node_ids is None:
        return graph.nodes
    targets = tuple(dict.fromkeys(target_node_ids))
    if not targets:
        raise ValueError("target_node_ids must not be empty")
    known = {node.node_id for node in graph.nodes}
    unknown = sorted(set(targets) - known)
    if unknown:
        raise ValueError("execution targets are undeclared: " + ", ".join(unknown))
    selected = set(targets)
    for target in targets:
        selected.update(_dependency_ancestors(target, graph.nodes))
    return tuple(node for node in graph.nodes if node.node_id in selected)


def _topological_node_ids(nodes: Sequence[ExecutionNode]) -> tuple[str, ...]:
    dependencies = {node.node_id: set(node.depends_on) for node in nodes}
    unresolved = set(dependencies)
    resolved: list[str] = []
    while unresolved:
        resolved_set = set(resolved)
        ready = [
            node.node_id
            for node in nodes
            if node.node_id in unresolved and dependencies[node.node_id] <= resolved_set
        ]
        if not ready:
            raise ValueError("execution graph dependencies contain a cycle")
        resolved.extend(ready)
        unresolved.difference_update(ready)
    return tuple(resolved)


def _sha256_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1_000)


def _event(
    event: str,
    invocation_id: str,
    graph: ExecutionGraph,
    *,
    offset_ms: int,
) -> dict[str, object]:
    return {
        "schema_version": EXECUTION_TRACE_SCHEMA_VERSION,
        "kind": "prepared-game-execution-event-v1",
        "event": event,
        "invocation_id": invocation_id,
        "graph_sha256": graph.graph_sha256,
        "offset_ms": offset_ms,
    }


def _node_event(
    event: str,
    invocation_id: str,
    graph: ExecutionGraph,
    trace: NodeTrace,
) -> dict[str, object]:
    return {
        **_event(event, invocation_id, graph, offset_ms=trace.ended_offset_ms),
        **trace.model_dump(mode="json", exclude_none=True),
    }


def build_node_cache_key(
    *,
    node_id: str,
    operation: OperationKind,
    provider: str | None,
    model: str | None,
    input_sha256: Sequence[str],
    dependency_cache_keys: Sequence[str],
    contract_version: str,
) -> str:
    return _sha256_json(
        {
            "node_id": node_id,
            "operation": operation.value,
            "provider": provider,
            "model": model,
            "input_sha256": sorted(input_sha256),
            "dependency_cache_keys": list(dependency_cache_keys),
            "contract_version": contract_version,
        }
    )


__all__ = [
    "EXECUTION_GRAPH_SCHEMA_VERSION",
    "EXECUTION_TRACE_SCHEMA_VERSION",
    "CacheDisposition",
    "DependencyExecutor",
    "ExecutionGraph",
    "ExecutionNode",
    "ExecutionProjection",
    "ExecutionResource",
    "ExecutionSummary",
    "JsonlTraceSink",
    "MemoryTraceSink",
    "NodeArtifact",
    "NodeExecutionContext",
    "NodeExecutionError",
    "NodeExecutionResult",
    "NodeHandler",
    "NodeStatus",
    "NodeTrace",
    "OperationKind",
    "ProjectedNodeSpan",
    "RetryOwner",
    "build_node_cache_key",
    "execution_graph_sha256",
    "execution_topology_sha256",
    "finalize_execution_graph",
    "project_execution",
    "write_execution_plan",
    "write_execution_summary",
]
