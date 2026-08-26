"""Deterministic provider-free node handler for execution-graph verification."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from stage_gen.orchestration.execution_graph import (
    CacheDisposition,
    ExecutionGraph,
    ExecutionNode,
    NodeArtifact,
    NodeExecutionContext,
    NodeExecutionError,
    NodeExecutionResult,
    OperationKind,
)
from stage_gen.reliability import atomic_write_bytes, atomic_write_json

FAKE_CACHE_SCHEMA_VERSION = 1


class FakeNodeHandler:
    """Exercise scheduling, failure, trace, and cache behavior without provider access."""

    def __init__(
        self,
        graph: ExecutionGraph,
        *,
        run_dir: Path,
        cache_dir: Path,
        failure_node_id: str | None = None,
        time_scale: float = 0.0001,
    ) -> None:
        if time_scale < 0:
            raise ValueError("fake execution time_scale must be non-negative")
        if failure_node_id is not None:
            graph.node(failure_node_id)
        self._graph = graph
        self._run_dir = run_dir
        self._cache_dir = cache_dir
        self._failure_node_id = failure_node_id
        self._time_scale = time_scale

    async def __call__(
        self, node: ExecutionNode, context: NodeExecutionContext
    ) -> NodeExecutionResult:
        if context.graph_sha256 != self._graph.graph_sha256:
            raise ValueError("fake execution context graph identity changed")
        dependency_cache_keys = tuple(
            self._graph.node(dependency).cache_key for dependency in node.depends_on
        )
        dependency_lineage_values: list[dict[str, object]] = []
        for dependency in node.depends_on:
            dependency_lineage_values.append(
                {
                    "node_id": dependency,
                    "artifact_sha256": [
                        artifact.sha256
                        for artifact in context.dependency_results[dependency].artifacts
                    ],
                }
            )
        dependency_lineage = tuple(dependency_lineage_values)
        cached = self._read_cache(node, dependency_cache_keys, dependency_lineage)
        if cached is not None:
            artifact_bytes, artifact_sha256 = cached
            artifact_ref = _fake_artifact_ref(node)
            atomic_write_bytes(self._run_dir / artifact_ref, artifact_bytes)
            return NodeExecutionResult(
                cache=CacheDisposition.HIT,
                attempts=1,
                provider_operations=0,
                artifacts=(
                    NodeArtifact(
                        artifact_ref=artifact_ref,
                        sha256=artifact_sha256,
                        bytes=len(artifact_bytes),
                    ),
                ),
                known_cost_usd=0.0,
            )

        await asyncio.sleep(node.estimated_duration_seconds * self._time_scale)
        if node.node_id == self._failure_node_id:
            external = node.operation is not OperationKind.LOCAL
            raise NodeExecutionError(
                "injected fake-provider failure",
                attempts=node.max_attempts,
                provider_operations=node.max_attempts if external else 0,
                known_cost_usd=0.0,
            )

        artifact_bytes = _fake_artifact_bytes(node, dependency_cache_keys, dependency_lineage)
        artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
        artifact_ref = _fake_artifact_ref(node)
        atomic_write_bytes(self._run_dir / artifact_ref, artifact_bytes)
        self._write_cache(
            node,
            dependency_cache_keys,
            dependency_lineage,
            artifact_bytes,
            artifact_sha256,
        )
        external = node.operation is not OperationKind.LOCAL
        return NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=1,
            provider_operations=1 if external else 0,
            artifacts=(
                NodeArtifact(
                    artifact_ref=artifact_ref,
                    sha256=artifact_sha256,
                    bytes=len(artifact_bytes),
                ),
            ),
            known_cost_usd=0.0,
        )

    def _read_cache(
        self,
        node: ExecutionNode,
        dependency_cache_keys: tuple[str, ...],
        dependency_lineage: tuple[dict[str, object], ...],
    ) -> tuple[bytes, str] | None:
        record_path, artifact_path = self._cache_paths(node)
        try:
            record_value = json.loads(record_path.read_text(encoding="utf-8"))
            artifact_bytes = artifact_path.read_bytes()
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(record_value, dict):
            return None
        artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
        expected = {
            "schema_version": FAKE_CACHE_SCHEMA_VERSION,
            "kind": "fake-execution-node-cache-v1",
            "node_id": node.node_id,
            "cache_key": node.cache_key,
            "operation": node.operation.value,
            "dependency_cache_keys": list(dependency_cache_keys),
            "dependency_lineage": list(dependency_lineage),
            "artifact_file": artifact_path.name,
            "artifact_sha256": artifact_sha256,
            "artifact_bytes": len(artifact_bytes),
        }
        if record_value != expected:
            return None
        return artifact_bytes, artifact_sha256

    def _write_cache(
        self,
        node: ExecutionNode,
        dependency_cache_keys: tuple[str, ...],
        dependency_lineage: tuple[dict[str, object], ...],
        artifact_bytes: bytes,
        artifact_sha256: str,
    ) -> None:
        record_path, artifact_path = self._cache_paths(node)
        atomic_write_bytes(artifact_path, artifact_bytes)
        atomic_write_json(
            record_path,
            {
                "schema_version": FAKE_CACHE_SCHEMA_VERSION,
                "kind": "fake-execution-node-cache-v1",
                "node_id": node.node_id,
                "cache_key": node.cache_key,
                "operation": node.operation.value,
                "dependency_cache_keys": list(dependency_cache_keys),
                "dependency_lineage": list(dependency_lineage),
                "artifact_file": artifact_path.name,
                "artifact_sha256": artifact_sha256,
                "artifact_bytes": len(artifact_bytes),
            },
        )

    def _cache_paths(self, node: ExecutionNode) -> tuple[Path, Path]:
        bucket = self._cache_dir / node.cache_key[:2]
        return bucket / f"{node.cache_key}.json", bucket / f"{node.cache_key}.artifact.json"


def _fake_artifact_ref(node: ExecutionNode) -> str:
    return f"dry-run/{node.node_id}.json"


def _fake_artifact_bytes(
    node: ExecutionNode,
    dependency_cache_keys: tuple[str, ...],
    dependency_lineage: tuple[dict[str, object], ...],
) -> bytes:
    value = {
        "schema_version": 1,
        "kind": "fake-execution-artifact-v1",
        "node_id": node.node_id,
        "cache_key": node.cache_key,
        "operation": node.operation.value,
        "dependency_cache_keys": list(dependency_cache_keys),
        "dependency_lineage": list(dependency_lineage),
        "declared_outputs": list(node.outputs),
    }
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


__all__ = ["FAKE_CACHE_SCHEMA_VERSION", "FakeNodeHandler"]
