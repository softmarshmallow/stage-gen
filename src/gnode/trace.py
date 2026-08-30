"""Append-only run trace: one immutable record of what the scheduler did."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from pydantic import Field

from gnode.contracts.artifacts import SHA256_PATTERN, PersistedContractModel
from gnode.graph import CacheDisposition, Graph, NodeArtifact, NodeStatus
from gnode.reliability import atomic_write_json


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


class RunSummary(PersistedContractModel):
    """One post-run reduce over the trace.

    ``kind`` and ``schema_version`` are stamped from the graph's declared
    document vocabulary, so a consumer keeps its own record names.
    """

    schema_version: int = Field(ge=1)
    kind: str = Field(min_length=1, max_length=96)
    invocation_id: str
    graph_sha256: str = Field(pattern=SHA256_PATTERN)
    ok: bool
    duration_ms: int = Field(ge=0)
    nodes: tuple[NodeTrace, ...]
    provider_operation_counts: dict[str, int]
    known_cost_usd: float | None = Field(default=None, ge=0.0)


def write_run_summary(path: Path, summary: RunSummary) -> None:
    atomic_write_json(path, summary.model_dump(mode="json"))


def elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1_000)


def run_event(
    event: str,
    invocation_id: str,
    graph: Graph,
    *,
    offset_ms: int,
) -> dict[str, object]:
    return {
        "schema_version": graph.TRACE_SCHEMA_VERSION,
        "kind": graph.TRACE_EVENT_KIND,
        "event": event,
        "invocation_id": invocation_id,
        "graph_sha256": graph.graph_sha256,
        "offset_ms": offset_ms,
    }


def node_event(
    event: str,
    invocation_id: str,
    graph: Graph,
    trace: NodeTrace,
) -> dict[str, object]:
    return {
        **run_event(event, invocation_id, graph, offset_ms=trace.ended_offset_ms),
        **trace.model_dump(mode="json", exclude_none=True),
    }
