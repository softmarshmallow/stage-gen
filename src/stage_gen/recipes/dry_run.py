"""Deterministic provider-free node handler over the real cache.

A plan can always be rehearsed for free: every node writes a small fake document to
each port it declared, sleeps a scaled fraction of its estimate, and reports the
spend it would have made. It runs through the same ``NodeArtifactCache`` as a live
run - same record, same lineage rule, same admission - so a rehearsal exercises the
cache a live run will meet, rather than a second implementation with its own rules.
The engine once carried that second implementation; it wrote a flat, namespace-less
tree into whatever cache directory it was handed, which is how the gate polluted the
real cache the day ``.cache`` became the default root.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from gnode import (
    Graph,
    Node,
    NodeExecutionContext,
    NodeExecutionError,
    NodeExecutionResult,
    NodeType,
    atomic_write_bytes,
)
from stage_gen.recipes.node_handler import NodeMethod, RecipeNodeHandler

DRY_RUN_CACHE_NAMESPACE = "dry-run-nodes-v1"
DRY_RUN_CACHE_RECORD_KIND = "dry-run-node-cache-v1"
DRY_RUN_ARTIFACT_KIND = "dry-run-artifact-v1"
PLACEHOLDER_PREFIX = f'{{"kind":"{DRY_RUN_ARTIFACT_KIND}"'.encode()


class DryRunNodeHandler(RecipeNodeHandler):
    """Exercise scheduling, failure, trace and cache behaviour without provider access."""

    def __init__(
        self,
        graph: Graph,
        *,
        run_dir: Path,
        cache_dir: Path,
        failure_node_id: str | None = None,
        time_scale: float = 0.0001,
    ) -> None:
        if time_scale < 0:
            raise ValueError("dry-run time_scale must be non-negative")
        if failure_node_id is not None:
            graph.node(failure_node_id)
        self._failure_node_id = failure_node_id
        self._time_scale = time_scale
        super().__init__(
            graph,
            run_dir=run_dir,
            cache_dir=cache_dir,
            namespace=DRY_RUN_CACHE_NAMESPACE,
            record_kind=DRY_RUN_CACHE_RECORD_KIND,
        )

    def _handlers(self) -> tuple[tuple[NodeType, NodeMethod], ...]:
        return ()

    async def _dispatch(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        if context.graph_sha256 != self._graph.graph_sha256:
            raise ValueError("dry-run context graph identity changed")
        await asyncio.sleep(node.estimated_duration_seconds * self._time_scale)
        if node.node_id == self._failure_node_id:
            raise NodeExecutionError(
                "injected dry-run failure",
                attempts=node.max_attempts,
                provider_operations=0 if node.is_local else node.max_attempts,
                known_cost_usd=0.0,
            )
        for port in node.ports:
            for ref in (port.artifact_ref, port.sidecar_ref):
                if ref is not None:
                    atomic_write_bytes(self._path(ref), _fake_bytes(node, context, ref))
        return self._result(node, provider_operations=0 if node.is_local else 1, known_cost_usd=0.0)


def is_placeholder(path: Path) -> bool:
    """Whether the file at ``path`` is a dry-run placeholder rather than an artifact.

    A reader that treats a run file's presence as the artifact's presence - a manifest
    naming the bytes it publishes - asks this first, so a rehearsal never publishes a
    placeholder as if a provider had produced it.
    """

    try:
        with path.open("rb") as handle:
            head = handle.read(len(PLACEHOLDER_PREFIX))
    except OSError:
        return False
    return head == PLACEHOLDER_PREFIX


def _fake_bytes(node: Node, context: NodeExecutionContext, ref: str) -> bytes:
    # The kind leads, in insertion order, so a reader can recognise a placeholder from
    # its first bytes without parsing a document whose lineage may run long.
    value = {
        "kind": DRY_RUN_ARTIFACT_KIND,
        "schema_version": 1,
        "node_id": node.node_id,
        "cache_key": node.cache_key,
        "operation": node.operation,
        "artifact_ref": ref,
        "dependency_artifact_sha256": {
            dependency: [artifact.sha256 for artifact in result.artifacts]
            for dependency, result in sorted(context.dependency_results.items())
        },
    }
    encoded = (json.dumps(value, separators=(",", ":")) + "\n").encode("utf-8")
    assert encoded.startswith(PLACEHOLDER_PREFIX)
    return encoded


__all__ = [
    "DRY_RUN_ARTIFACT_KIND",
    "is_placeholder",
    "DRY_RUN_CACHE_NAMESPACE",
    "DRY_RUN_CACHE_RECORD_KIND",
    "DryRunNodeHandler",
]
