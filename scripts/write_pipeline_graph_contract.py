#!/usr/bin/env python3
"""Check or rewrite the executable graph-contract block in the generation-pipeline document.

`docs/spec/game/generation-pipeline.md` carries a JSON snapshot of the Bellweather platformer
execution graph, `docs/spec/game/runner.md` snapshots the Iron Petal Unit structural-ground
runner graph, and `docs/spec/universe/generation-v1.md` snapshots both phases of the Lantern
Ferry universe. `tests/contract/test_generation_pipeline_docs.py` asserts every document matches
the graphs the code actually builds. Any change to recipe stages, asset fan-out, or scheduling
invalidates the relevant snapshot.

A document may carry more than one block when a recipe plans more than one graph. Universe does:
the size of its gallery is a result of its semantic phase, so the two graphs are sealed
separately and each carries its own labelled block.

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
from stage_gen.recipes.sideview_platformer.package_graph import (
    build_package_execution_graph,
    package_graph_profile,
)
from stage_gen.recipes.sideview_runner.runner_graph import (
    build_runner_execution_graph,
    runner_graph_profile,
)
from stage_gen.recipes.sideview_runner.runner_request import resolve_runner_package
from stage_gen.recipes.universe.universe_graph import (
    build_universe_gallery_graph,
    build_universe_semantic_graph,
    universe_graph_profile,
)
from stage_gen.recipes.universe.universe_request import (
    admitted_universe_from_document,
    read_universe_document,
    resolve_sample_ledger,
    resolve_universe_source,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_DOCUMENT = REPOSITORY_ROOT / "docs/spec/game/generation-pipeline.md"
CONTRACT_START = "<!-- pipeline-graph-contract:start -->"
CONTRACT_END = "<!-- pipeline-graph-contract:end -->"
CONTRACT_KIND = "prepared-game-execution-graph-contract-v1"
FIXTURE_REF = "library/games/bellweather"
RUNNER_FIXTURE_REF = "library/games/iron-petal-unit"
RUNNER_PIPELINE_DOCUMENT = REPOSITORY_ROOT / "docs/spec/game/runner.md"
RUNNER_CONTRACT_KIND = "sideview-runner-execution-graph-contract-v1"
UNIVERSE_DOCUMENT = REPOSITORY_ROOT / "docs/spec/universe/generation-v1.md"
UNIVERSE_FIXTURE_REF = "library/games/lantern_ferry"
UNIVERSE_ADMITTED_REF = "tests/contract/fixtures/universe/lantern_ferry.admitted-universe.json"
UNIVERSE_SEMANTIC_CONTRACT_KIND = "universe-semantic-execution-graph-contract-v1"
UNIVERSE_GALLERY_CONTRACT_KIND = "universe-gallery-execution-graph-contract-v1"


def contract_markers(label: str | None) -> tuple[str, str, re.Pattern[str]]:
    """Delimiters for one block. A label lets one document carry several."""

    start = CONTRACT_START if label is None else f"<!-- pipeline-graph-contract:{label}:start -->"
    end = CONTRACT_END if label is None else f"<!-- pipeline-graph-contract:{label}:end -->"
    pattern = re.compile(
        rf"{re.escape(start)}\s*```json\s*(.*?)\s*```\s*{re.escape(end)}",
        re.DOTALL,
    )
    return start, end, pattern


CONTRACT_PATTERN = contract_markers(None)[2]


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


def build_runner_graph_contract(repo: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Derive the runner member's contract from the graph the code builds."""

    resolved = resolve_runner_package(repo / RUNNER_FIXTURE_REF)
    graph = build_runner_execution_graph(resolved, profile=runner_graph_profile(StageGenConfig()))
    return {
        "kind": RUNNER_CONTRACT_KIND,
        "fixture_ref": RUNNER_FIXTURE_REF,
        "graph_schema_version": graph.schema_version,
        "topology_sha256": graph.topology_sha256,
        "node_count": len(graph.nodes),
        "terminal_node_id": graph.terminal_node_id,
        "operation_counts": graph.operation_counts(),
        "resources": [resource.model_dump(mode="json") for resource in graph.resources],
    }


def _universe_inputs(repo: Path) -> tuple[Any, Any]:
    """The fixture package and the admitted universe committed beside it.

    Planning the gallery offline needs an admission, and an admission is what
    the semantic phase costs money to produce. The committed fixture stands in
    for that run so the second graph has a checked identity too.
    """

    root = repo / UNIVERSE_FIXTURE_REF
    resolved = resolve_universe_source(read_universe_document(root), root=root)
    admitted = admitted_universe_from_document(
        repo / UNIVERSE_ADMITTED_REF, poster_sha256=resolved.poster_sha256
    )
    return resolved, admitted


def build_universe_semantic_graph_contract(repo: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    resolved, _admitted = _universe_inputs(repo)
    graph = build_universe_semantic_graph(
        resolved, profile=universe_graph_profile(StageGenConfig(), images=False)
    )
    return {
        "kind": UNIVERSE_SEMANTIC_CONTRACT_KIND,
        "fixture_ref": UNIVERSE_FIXTURE_REF,
        "phase": graph.phase,
        "graph_schema_version": graph.schema_version,
        "topology_sha256": graph.topology_sha256,
        "node_count": len(graph.nodes),
        "terminal_node_id": graph.terminal_node_id,
        "operation_counts": graph.operation_counts(),
        "resources": [resource.model_dump(mode="json") for resource in graph.resources],
    }


def build_universe_gallery_graph_contract(repo: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    resolved, admitted = _universe_inputs(repo)
    samples = resolve_sample_ledger(
        universe_id=admitted.universe_id, entity_ids=admitted.entity_ids()
    )
    graph = build_universe_gallery_graph(
        resolved,
        admitted,
        samples=samples,
        profile=universe_graph_profile(StageGenConfig(), images=True),
    )
    return {
        "kind": UNIVERSE_GALLERY_CONTRACT_KIND,
        "fixture_ref": UNIVERSE_FIXTURE_REF,
        "admitted_ref": UNIVERSE_ADMITTED_REF,
        "phase": graph.phase,
        "entity_count": graph.entity_count,
        "graph_schema_version": graph.schema_version,
        "topology_sha256": graph.topology_sha256,
        "node_count": len(graph.nodes),
        "terminal_node_id": graph.terminal_node_id,
        "operation_counts": graph.operation_counts(),
        "resources": [resource.model_dump(mode="json") for resource in graph.resources],
    }


def document_contract(
    document: Path = PIPELINE_DOCUMENT, *, label: str | None = None
) -> dict[str, Any]:
    """Read the snapshot currently written into the document."""

    start, end, pattern = contract_markers(label)
    source = document.read_text(encoding="utf-8")
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError(f"the document must carry exactly one {label or 'graph'}-contract block")
    matches = pattern.findall(source)
    if len(matches) != 1:
        raise ValueError("the graph-contract block is malformed")
    value = json.loads(matches[0])
    if not isinstance(value, dict):
        raise ValueError("the graph-contract block must be a JSON object")
    return value


def render(contract: dict[str, Any], *, label: str | None = None) -> str:
    start, end, _ = contract_markers(label)
    return f"{start}\n```json\n{json.dumps(contract, indent=2)}\n```\n{end}"


def write_contract(
    contract: dict[str, Any], document: Path = PIPELINE_DOCUMENT, *, label: str | None = None
) -> bool:
    """Replace the block in place. Returns True when the document changed."""

    start, end, pattern = contract_markers(label)
    source = document.read_text(encoding="utf-8")
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError(f"the document must carry exactly one {label or 'graph'}-contract block")
    updated = pattern.sub(lambda _: render(contract, label=label), source, count=1)
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

    contracts: tuple[tuple[str, Path, Any, str | None], ...] = (
        ("platformer", PIPELINE_DOCUMENT, build_graph_contract, None),
        ("runner", RUNNER_PIPELINE_DOCUMENT, build_runner_graph_contract, None),
        (
            "universe-semantic",
            UNIVERSE_DOCUMENT,
            build_universe_semantic_graph_contract,
            "semantic",
        ),
        (
            "universe-gallery",
            UNIVERSE_DOCUMENT,
            build_universe_gallery_graph_contract,
            "gallery",
        ),
    )
    status = 0
    for label, document, build, marker in contracts:
        built = build()
        current = document_contract(document, label=marker)
        if built == current:
            print(
                f"{label} graph contract is current: {built['node_count']} nodes, "
                f"{built['topology_sha256']}"
            )
            continue
        differing = sorted(
            key for key in set(built) | set(current) if built.get(key) != current.get(key)
        )
        if not args.write:
            print(f"{label} graph contract is STALE. Differing keys: " + ", ".join(differing))
            print(f"  built topology_sha256:    {built.get('topology_sha256')}")
            print(f"  document topology_sha256: {current.get('topology_sha256')}")
            print("Run with --write to regenerate.")
            status = 1
            continue
        write_contract(built, document, label=marker)
        print(f"{label} graph contract rewritten. Differing keys were: " + ", ".join(differing))
        print(f"  node_count {current.get('node_count')} -> {built['node_count']}")
        print(f"  topology_sha256 {current.get('topology_sha256')} -> {built['topology_sha256']}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
