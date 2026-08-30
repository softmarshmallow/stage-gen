"""Content-and-lineage validated reuse of one node's artifacts.

The engine owns cache *keys*; what a key is allowed to restore is the application's
business. A record is honoured only when the key matches, the recorded lineage still
matches what the dependencies actually produced this run, every restored byte hashes
to what was recorded, and the recipe's own admission check passes. Path existence is
never sufficient - a stale directory must not be able to publish itself as a hit.
"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import TYPE_CHECKING

from gnode import (
    CacheDisposition,
    NodeArtifact,
    NodeExecutionResult,
    atomic_write_bytes,
    atomic_write_json,
    resolve_writable_path_within_root,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from gnode import Graph, Node, NodeExecutionContext

NODE_CACHE_SCHEMA_VERSION = 2


class NodeArtifactCache:
    """One recipe's cache tier over a run directory and a cache directory."""

    def __init__(
        self,
        graph: Graph,
        *,
        run_dir: Path,
        cache_dir: Path,
        namespace: str,
        record_kind: str,
        admit: Callable[[Node, tuple[bytes, ...]], bool] | None = None,
    ) -> None:
        self._graph = graph
        self._run_dir = run_dir
        self._cache_dir = cache_dir
        self._namespace = namespace
        self._record_kind = record_kind
        self._admit = admit

    def read(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult | None:
        record_path, artifacts_dir = self._paths(node)
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if (
            not isinstance(record, dict)
            or record.get("cache_key") != node.cache_key
            or record.get("lineage") != self.lineage(node, context)
        ):
            return None
        outputs = record.get("artifacts")
        if not isinstance(outputs, list):
            return None
        restored: list[NodeArtifact] = []
        payloads: list[bytes] = []
        for index, value in enumerate(outputs):
            if not isinstance(value, dict) or not isinstance(value.get("artifact_ref"), str):
                return None
            try:
                data = (artifacts_dir / f"{index}.bin").read_bytes()
            except OSError:
                return None
            if sha256(data).hexdigest() != value.get("sha256") or len(data) != value.get("bytes"):
                return None
            payloads.append(data)
            restored.append(NodeArtifact.model_validate(value))
        if self._admit is not None and not self._admit(node, tuple(payloads)):
            return None
        for artifact, data in zip(restored, payloads, strict=True):
            # A cache record is data, not authority: its refs must stay inside
            # the run directory even if the record was corrupted or crafted.
            try:
                target = resolve_writable_path_within_root(
                    self._run_dir, artifact.artifact_ref, "cached artifact path"
                )
            except ValueError:
                return None
            atomic_write_bytes(target, data)
        return NodeExecutionResult(
            cache=CacheDisposition.HIT,
            attempts=1,
            provider_operations=0,
            artifacts=tuple(restored),
            known_cost_usd=0.0,
        )

    def write(self, node: Node, context: NodeExecutionContext, result: NodeExecutionResult) -> None:
        record_path, artifacts_dir = self._paths(node)
        for index, artifact in enumerate(result.artifacts):
            atomic_write_bytes(
                artifacts_dir / f"{index}.bin",
                (self._run_dir / artifact.artifact_ref).read_bytes(),
            )
        atomic_write_json(
            record_path,
            {
                "schema_version": NODE_CACHE_SCHEMA_VERSION,
                "kind": self._record_kind,
                "cache_key": node.cache_key,
                "node_id": node.node_id,
                "lineage": self.lineage(node, context),
                "artifacts": [item.model_dump(mode="json") for item in result.artifacts],
            },
        )

    def lineage(self, node: Node, context: NodeExecutionContext) -> list[dict[str, object]]:
        """Lineage covers exactly the dependencies the cache key covers.

        A barrier edge orders execution without contributing identity; binding
        its artifact digests here would re-bill every provider node whenever
        anything upstream of the barrier changed, which is precisely what the
        barrier declaration promises not to do.
        """

        barriers = set(node.barrier_only)
        return [
            {
                "node_id": dependency,
                "cache_key": self._graph.node(dependency).cache_key,
                "artifact_sha256": [
                    artifact.sha256 for artifact in context.dependency_results[dependency].artifacts
                ],
            }
            for dependency in node.depends_on
            if dependency not in barriers
        ]

    def _paths(self, node: Node) -> tuple[Path, Path]:
        root = self._cache_dir / self._namespace / node.cache_key[:2] / node.cache_key
        return root / "record.json", root / "artifacts"


__all__ = ["NODE_CACHE_SCHEMA_VERSION", "NodeArtifactCache"]
