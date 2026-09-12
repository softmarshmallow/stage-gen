"""Price a plan against a cache before anything is spent.

The projection prices a cold run: every provider node, every time. What an
author needs before a contract bump or an authoring edit is the warm number -
which nodes would restore from the cache and which would bill - and until now
nothing computed it, which is how eleven layer images were redrawn for a
change that touched no prompt.

The walk is static and conservative. A node restores when a record with its
current cache key exists and that record's lineage names the current cache
key of every non-barrier dependency. A provider node that cannot restore is
dirty, and dirt flows down every non-barrier edge: a redrawn image is new
bytes, and every consumer of those bytes re-runs even if its own record
exists. A local node that cannot restore is not dirty on its own, because a
deterministic local step reproduces the bytes its dependents recorded. The
result is an upper bound on spend, which is the honest direction to err.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from gnode import Graph, Node, topological_node_ids


def _record(cache_dir: Path, namespaces: Sequence[str], node: Node) -> dict[str, Any] | None:
    for namespace in namespaces:
        path = cache_dir / namespace / node.cache_key[:2] / node.cache_key / "record.json"
        if path.is_symlink() or not path.is_file():
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if (
            isinstance(record, dict)
            and record.get("cache_key") == node.cache_key
            and record.get("node_id") == node.node_id
        ):
            return record
    return None


def _lineage_matches(record: dict[str, Any], node: Node, graph: Graph) -> bool:
    lineage = record.get("lineage")
    if not isinstance(lineage, list):
        return False
    recorded = {
        entry.get("node_id"): entry.get("cache_key") for entry in lineage if isinstance(entry, dict)
    }
    barriers = set(node.barrier_only)
    expected = {
        dependency: graph.node(dependency).cache_key
        for dependency in node.depends_on
        if dependency not in barriers
    }
    return recorded == expected


def cache_report(graph: Graph, cache_dir: Path, namespaces: Sequence[str]) -> dict[str, Any]:
    """Which provider operations a run of ``graph`` would bill against ``cache_dir``."""

    dirty: set[str] = set()
    restored: list[Node] = []
    billed: list[Node] = []
    for node_id in topological_node_ids(graph.nodes):
        node = graph.node(node_id)
        barriers = set(node.barrier_only)
        upstream_dirty = any(
            dependency in dirty for dependency in node.depends_on if dependency not in barriers
        )
        record = None if upstream_dirty else _record(cache_dir, namespaces, node)
        restores = record is not None and _lineage_matches(record, node, graph)
        if node.provider is None:
            if upstream_dirty:
                dirty.add(node_id)
            continue
        if restores:
            restored.append(node)
        else:
            billed.append(node)
            dirty.add(node_id)
    counts: dict[str, int] = {}
    for node in billed:
        counts[node.operation] = counts.get(node.operation, 0) + 1
    return {
        "cache_dir": str(cache_dir),
        "namespaces": list(namespaces),
        "restored_provider_nodes": len(restored),
        "billed_provider_nodes": len(billed),
        "billed_operation_counts": dict(sorted(counts.items())),
        "estimated_cost_low_usd": round(sum(node.estimated_cost_low_usd for node in billed), 6),
        "estimated_cost_high_usd": round(sum(node.estimated_cost_high_usd for node in billed), 6),
        "billed": [
            {
                "node_id": node.node_id,
                "type_id": node.type_id,
                "operation": node.operation,
                "provider": node.provider,
                "model": node.model,
            }
            for node in billed
        ],
    }


__all__ = ["cache_report"]
