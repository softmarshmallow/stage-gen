"""Asset-graph topology: typed nodes, declared resources, and content identity."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol, cast

from pydantic import Field, field_validator, model_validator

from gnode.contracts.artifacts import SHA256_PATTERN, PersistedContractModel
from gnode.reliability import atomic_write_json

NODE_ID_PATTERN = r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$"
OPERATION_PATTERN = r"^[a-z0-9]+(?:_[a-z0-9]+)*$"
LOCAL_OPERATION = "local"


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


class Resource(PersistedContractModel):
    resource_id: str = Field(pattern=NODE_ID_PATTERN, max_length=96)
    max_in_flight: int | None = Field(default=None, ge=1, le=1_024)
    requests_per_minute: int | None = Field(default=None, ge=1)
    rate_limit_owner: Literal["scheduler", "provider_adapter", "none"]

    @model_validator(mode="after")
    def validate_rate_owner(self) -> Resource:
        if self.requests_per_minute is None and self.rate_limit_owner != "none":
            raise ValueError("rate-limited resources require requests_per_minute")
        if self.requests_per_minute is not None and self.rate_limit_owner == "none":
            raise ValueError("requests_per_minute requires a rate-limit owner")
        return self


class Node(PersistedContractModel):
    node_id: str = Field(pattern=NODE_ID_PATTERN, max_length=192)
    domain: str = Field(pattern=NODE_ID_PATTERN, max_length=96)
    description: str = Field(min_length=1, max_length=512)
    depends_on: tuple[str, ...] = ()
    operation: str = Field(pattern=OPERATION_PATTERN, max_length=64)
    resource_id: str = Field(pattern=NODE_ID_PATTERN, max_length=96)
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

    @property
    def is_local(self) -> bool:
        """A node is local when its operation runs without a provider route."""

        return self.operation == LOCAL_OPERATION

    @model_validator(mode="after")
    def validate_operation_ownership(self) -> Node:
        if self.is_local:
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


class Graph(PersistedContractModel):
    """One sealed asset graph.

    A consumer subclasses this to add its own header fields and to pin ``kind``;
    everything below the header is the engine's. The document kinds stamped on
    derived records are class attributes so a consumer keeps its own vocabulary
    without the engine knowing anything about it.
    """

    TRACE_SCHEMA_VERSION: ClassVar[int] = 1
    TRACE_EVENT_KIND: ClassVar[str] = "gnode-node-event-v1"
    RUN_SUMMARY_KIND: ClassVar[str] = "gnode-run-summary-v1"
    PROJECTION_KIND: ClassVar[str] = "gnode-projection-v1"
    VIEW_KIND: ClassVar[str] = "gnode-run-view-v1"
    VIEW_SCHEMA_VERSION: ClassVar[int] = 2

    schema_version: int = Field(ge=1)
    kind: str = Field(min_length=1, max_length=96)
    resources: tuple[Resource, ...]
    nodes: tuple[Node, ...]
    terminal_node_id: str
    topology_sha256: str = Field(pattern=SHA256_PATTERN)
    graph_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_graph(self) -> Graph:
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
        topological_node_ids(self.nodes)
        descendants = dependency_ancestors(self.terminal_node_id, self.nodes)
        orphaned = sorted(known - descendants - {self.terminal_node_id})
        if orphaned:
            raise ValueError(
                "execution graph contains nodes outside terminal closure: " + ", ".join(orphaned)
            )
        if self.topology_sha256 != topology_sha256(self):
            raise ValueError("execution graph topology_sha256 is stale")
        if self.graph_sha256 != graph_sha256_of(self):
            raise ValueError("execution graph graph_sha256 is stale")
        return self

    def node(self, node_id: str) -> Node:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        raise KeyError(node_id)

    def identity_header(self) -> dict[str, object]:
        """Header fields that participate in topology identity.

        A consumer overrides this to add its own; the values must be JSON
        scalars so the digest stays stable across processes.
        """

        return {"schema_version": self.schema_version, "kind": self.kind}

    def annotator_key(self) -> str:
        """Which artifact-annotator family this graph's nodes belong to."""

        return self.kind

    def view_header(self) -> dict[str, object]:
        """Consumer header fields copied onto this graph's derived run view."""

        return {}

    def operation_vocabulary(self) -> tuple[str, ...]:
        """Operations reported in counts, including those with no node.

        The default reports exactly what the graph contains. A consumer with a
        closed vocabulary overrides this so a zero count stays visible.
        """

        return tuple(sorted({node.operation for node in self.nodes}))

    def operation_counts(self) -> dict[str, int]:
        return {
            operation: sum(node.operation == operation for node in self.nodes)
            for operation in self.operation_vocabulary()
        }

    def provider_operation_vocabulary(self) -> tuple[str, ...]:
        return tuple(
            operation for operation in self.operation_vocabulary() if operation != LOCAL_OPERATION
        )


def topology_sha256(graph: Graph) -> str:
    identity = {
        **graph.identity_header(),
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
                "operation": node.operation,
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


def graph_sha256_of(graph: Graph) -> str:
    value = graph.model_dump(mode="json", exclude={"graph_sha256", "topology_sha256"})
    return _sha256_json(value)


def seal_graph[GraphT: Graph](
    graph_type: type[GraphT],
    *,
    resources: Sequence[Resource],
    nodes: Sequence[Node],
    terminal_node_id: str,
    **header: object,
) -> GraphT:
    """Compute both digests and return one validated graph.

    Topology identity is sealed first so a moved node stays distinguishable
    from a changed input; content identity then covers the whole document.
    """

    payload: dict[str, Any] = {
        "resources": tuple(resources),
        "nodes": tuple(nodes),
        "terminal_node_id": terminal_node_id,
        "topology_sha256": "0" * 64,
        "graph_sha256": "0" * 64,
        **header,
    }
    incomplete = cast(GraphT, graph_type.model_construct(**payload))
    with_topology = incomplete.model_copy(update={"topology_sha256": topology_sha256(incomplete)})
    sealed = with_topology.model_copy(update={"graph_sha256": graph_sha256_of(with_topology)})
    return graph_type.model_validate(sealed.model_dump())


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
    async def __call__(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult: ...


def dependency_ancestors(node_id: str, nodes: Sequence[Node]) -> set[str]:
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


def node_closure(
    graph: Graph,
    target_node_ids: Sequence[str] | None,
) -> tuple[Node, ...]:
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
        selected.update(dependency_ancestors(target, graph.nodes))
    return tuple(node for node in graph.nodes if node.node_id in selected)


def topological_node_ids(nodes: Sequence[Node]) -> tuple[str, ...]:
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


def build_node_cache_key(
    *,
    node_id: str,
    operation: str,
    provider: str | None,
    model: str | None,
    input_sha256: Sequence[str],
    dependency_cache_keys: Sequence[str],
    contract_version: str,
) -> str:
    return _sha256_json(
        {
            "node_id": node_id,
            "operation": str(operation),
            "provider": provider,
            "model": model,
            "input_sha256": sorted(input_sha256),
            "dependency_cache_keys": list(dependency_cache_keys),
            "contract_version": contract_version,
        }
    )


def write_graph(path: Path, graph: Graph) -> None:
    """Persist one sealed graph as this run's plan of record."""

    atomic_write_json(path, graph.model_dump(mode="json"))
