#!/usr/bin/env python3
"""Check or rewrite the executable graph-contract block in the generation-pipeline document.

`docs/spec/game/generation-pipeline.md` carries a JSON snapshot of the Bellweather execution
graph, and `tests/contract/test_generation_pipeline_docs.py` asserts the document matches the
graph the code actually builds. Any change to recipe stages, asset fan-out, or scheduling
invalidates that snapshot.

Regenerating it by hand means transcribing a sha256, a node count, an operation-count map, and
the full resource list out of a pytest assertion diff. This owns that instead, so the snapshot is
derived rather than typed.

    uv run python scripts/write_pipeline_graph_contract.py            # check, non-zero if stale
    uv run python scripts/write_pipeline_graph_contract.py --write    # rewrite the block
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stage_gen.config import StageGenConfig
from stage_gen.orchestration.game_package import resolve_game_package
from stage_gen.recipes.scrolling_preview.package_graph import (
    build_package_execution_graph,
    package_graph_profile,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_DOCUMENT = REPOSITORY_ROOT / "docs/spec/game/generation-pipeline.md"
CONTRACT_START = "<!-- pipeline-graph-contract:start -->"
CONTRACT_END = "<!-- pipeline-graph-contract:end -->"
CONTRACT_KIND = "prepared-game-execution-graph-contract-v1"
FIXTURE_REF = "library/games/bellweather"

CONTRACT_PATTERN = re.compile(
    rf"{re.escape(CONTRACT_START)}\s*```json\s*(.*?)\s*```\s*{re.escape(CONTRACT_END)}",
    re.DOTALL,
)


def build_graph_contract(repo: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Derive the contract from the graph the code builds. Key order is the document's order."""

    package = resolve_game_package(repo / FIXTURE_REF)
    graph = build_package_execution_graph(
        package,
        profile=package_graph_profile(StageGenConfig()),
    )
    return {
        "kind": CONTRACT_KIND,
        "fixture_ref": FIXTURE_REF,
        "graph_schema_version": graph.schema_version,
        "topology_sha256": graph.topology_sha256,
        "node_count": len(graph.nodes),
        "terminal_node_id": graph.terminal_node_id,
        "operation_counts": graph.operation_counts(),
        "resources": [resource.model_dump(mode="json") for resource in graph.resources],
    }


def document_contract(document: Path = PIPELINE_DOCUMENT) -> dict[str, Any]:
    """Read the snapshot currently written into the document."""

    source = document.read_text(encoding="utf-8")
    if source.count(CONTRACT_START) != 1 or source.count(CONTRACT_END) != 1:
        raise ValueError("the pipeline document must carry exactly one graph-contract block")
    matches = CONTRACT_PATTERN.findall(source)
    if len(matches) != 1:
        raise ValueError("the graph-contract block is malformed")
    value = json.loads(matches[0])
    if not isinstance(value, dict):
        raise ValueError("the graph-contract block must be a JSON object")
    return value


def render(contract: dict[str, Any]) -> str:
    return f"{CONTRACT_START}\n```json\n{json.dumps(contract, indent=2)}\n```\n{CONTRACT_END}"


def write_contract(contract: dict[str, Any], document: Path = PIPELINE_DOCUMENT) -> bool:
    """Replace the block in place. Returns True when the document changed."""

    source = document.read_text(encoding="utf-8")
    if source.count(CONTRACT_START) != 1 or source.count(CONTRACT_END) != 1:
        raise ValueError("the pipeline document must carry exactly one graph-contract block")
    updated = CONTRACT_PATTERN.sub(lambda _: render(contract), source, count=1)
    if updated == source:
        return False
    document.write_text(updated, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="rewrite the block instead of only reporting whether it is stale",
    )
    args = parser.parse_args(argv)

    built = build_graph_contract()
    current = document_contract()
    if built == current:
        print(f"graph contract is current: {built['node_count']} nodes, {built['topology_sha256']}")
        return 0

    differing = sorted(
        key for key in set(built) | set(current) if built.get(key) != current.get(key)
    )
    if not args.write:
        print("graph contract is STALE. Differing keys: " + ", ".join(differing))
        print(f"  built topology_sha256:    {built.get('topology_sha256')}")
        print(f"  document topology_sha256: {current.get('topology_sha256')}")
        print("Run with --write to regenerate.")
        return 1

    write_contract(built)
    print("graph contract rewritten. Differing keys were: " + ", ".join(differing))
    print(f"  node_count {current.get('node_count')} -> {built['node_count']}")
    print(f"  topology_sha256 {current.get('topology_sha256')} -> {built['topology_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
