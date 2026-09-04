"""One assertion shared by every shipped game's identity test.

A golden file of ``node_id -> cache_key`` is the whole regression guard for
provider spend: a key that moved is a node that would re-bill. The assertion
names the moved nodes and prices them, so a failure reads as a decision -
"these eleven layer images will be redrawn, because ..." - rather than as
"expected X got Y". Re-pin by rewriting the file and reading the diff.
"""

from __future__ import annotations

import json
from pathlib import Path

from gnode import Graph


def assert_cache_keys_match_golden(graph: Graph, golden: Path) -> None:
    expected = json.loads(golden.read_text(encoding="utf-8"))
    assert isinstance(expected, dict)
    actual = {node.node_id: node.cache_key for node in graph.nodes}
    if actual == expected:
        return
    nodes = {node.node_id: node for node in graph.nodes}
    added = sorted(set(actual) - set(expected))
    removed = sorted(set(expected) - set(actual))
    moved = sorted(
        node_id for node_id in set(actual) & set(expected) if actual[node_id] != expected[node_id]
    )
    billed = [nodes[node_id] for node_id in moved + added if nodes[node_id].provider is not None]
    low = sum(node.estimated_cost_low_usd for node in billed)
    high = sum(node.estimated_cost_high_usd for node in billed)
    lines = [f"cache keys moved against {golden.name}:"]
    lines.extend(f"  moved   {node_id}  ({nodes[node_id].type_id})" for node_id in moved)
    lines.extend(f"  added   {node_id}  ({nodes[node_id].type_id})" for node_id in added)
    lines.extend(f"  removed {node_id}" for node_id in removed)
    lines.append(
        f"  {len(billed)} provider operation(s) would re-bill, "
        f"estimated USD {low:.2f}-{high:.2f}; rewrite the golden if that is the intent"
    )
    raise AssertionError("\n".join(lines))


def write_cache_key_golden(graph: Graph, golden: Path) -> None:
    """Rewrite a golden from a plan; the diff is the review."""

    keys = {node.node_id: node.cache_key for node in graph.nodes}
    golden.write_text(json.dumps(keys, indent=1, sort_keys=True) + "\n", encoding="utf-8")


__all__ = ["assert_cache_keys_match_golden", "write_cache_key_golden"]
