#!/usr/bin/env python3
"""Check or rewrite maintained game graph snapshots.

These executable contracts belong to the game-owned builders. New asset
pipelines do not inherit their gameplay stages or fixture requirements.

    python godot/tools/write_game_graph_contract.py
    python godot/tools/write_game_graph_contract.py --write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from bellweather_pipeline.package_graph import (
    build_package_execution_graph,
    package_graph_profile,
)
from demo_game_collection.game_package import resolve_game_package
from ember_hollow_pipeline.survival_graph import (
    build_graph as build_oblique_survival_graph,
)
from ember_hollow_pipeline.survival_request import resolve_survival_source
from iron_petal_unit_pipeline.runner_graph import (
    build_runner_execution_graph,
    runner_graph_profile,
)
from iron_petal_unit_pipeline.runner_request import resolve_runner_package
from scripts.write_pipeline_graph_contract import document_contract, write_contract
from stage_gen.config import StageGenConfig
from stage_gen.recipes.storefront.storefront_graph import (
    build_storefront_graph,
    storefront_graph_profile,
)
from stage_gen.recipes.storefront.storefront_request import (
    read_storefront_document,
    resolve_storefront,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DOCUMENT = REPOSITORY_ROOT / "godot/games/bellweather/docs/generation-pipeline.md"
CONTRACT_KIND = "prepared-game-execution-graph-contract-v1"
FIXTURE_REF = "godot/games/bellweather/inputs/default"
RUNNER_FIXTURE_REF = "godot/games/iron_petal_unit/inputs"
RUNNER_PIPELINE_DOCUMENT = REPOSITORY_ROOT / "godot/games/iron_petal_unit/docs/runner.md"
RUNNER_CONTRACT_KIND = "sideview-runner-execution-graph-contract-v1"
OBLIQUE_SURVIVAL_DOCUMENT = REPOSITORY_ROOT / "godot/games/ember_hollow/docs/generation-v1.md"
OBLIQUE_SURVIVAL_FIXTURE_REF = "godot/games/ember_hollow/inputs"
OBLIQUE_SURVIVAL_CONTRACT_KIND = "oblique-survival-execution-graph-contract-v1"
OBLIQUE_SURVIVAL_SCOPE = "full"


STOREFRONT_DOCUMENT = REPOSITORY_ROOT / "docs/spec/storefront/generation-v1.md"
STOREFRONT_FIXTURE_REF = "godot/games/ember_hollow/inputs"
STOREFRONT_CONTRACT_KIND = "storefront-execution-graph-contract-v1"


def build_graph_contract(repo: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Derive the contract from the graph the code builds. Key order is the document's order."""

    config = StageGenConfig()
    package = resolve_game_package(repo / FIXTURE_REF)
    graph = build_package_execution_graph(
        package,
        profile=package_graph_profile(config),
        config=config,
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

    config = StageGenConfig()
    resolved = resolve_runner_package(repo / RUNNER_FIXTURE_REF)
    graph = build_runner_execution_graph(
        resolved,
        profile=runner_graph_profile(config),
        config=config,
    )
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


def build_oblique_survival_graph_contract(repo: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Derive the survival world's contract from the graph the code builds.

    The scope rides the payload because it is the one header field in this
    recipe's topology identity: it genuinely selects a subset of the nodes.
    """

    package = resolve_survival_source(repo / OBLIQUE_SURVIVAL_FIXTURE_REF)
    graph = build_oblique_survival_graph(StageGenConfig(), package, OBLIQUE_SURVIVAL_SCOPE)
    return {
        "kind": OBLIQUE_SURVIVAL_CONTRACT_KIND,
        "fixture_ref": OBLIQUE_SURVIVAL_FIXTURE_REF,
        "scope": graph.scope,
        "graph_schema_version": graph.schema_version,
        "topology_sha256": graph.topology_sha256,
        "node_count": len(graph.nodes),
        "terminal_node_id": graph.terminal_node_id,
        "operation_counts": graph.operation_counts(),
        "resources": [resource.model_dump(mode="json") for resource in graph.resources],
    }


def build_storefront_graph_contract(repo: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Derive the storefront's contract from the graph the code builds.

    Planned against an empty draw ledger, which is what a first run has: a reroll
    changes one image node's identity and nothing about the shape of the graph, so
    the snapshot would be identical and the ledger is left out of it.
    """

    config = StageGenConfig()
    root = repo / STOREFRONT_FIXTURE_REF
    resolved = resolve_storefront(read_storefront_document(root), root=root)
    graph = build_storefront_graph(
        resolved,
        profile=storefront_graph_profile(config),
        config=config,
    )
    return {
        "kind": STOREFRONT_CONTRACT_KIND,
        "fixture_ref": STOREFRONT_FIXTURE_REF,
        "surface_count": graph.surface_count,
        "graph_schema_version": graph.schema_version,
        "topology_sha256": graph.topology_sha256,
        "node_count": len(graph.nodes),
        "terminal_node_id": graph.terminal_node_id,
        "operation_counts": graph.operation_counts(),
        "resources": [resource.model_dump(mode="json") for resource in graph.resources],
    }


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
        ("storefront", STOREFRONT_DOCUMENT, build_storefront_graph_contract, None),
        (
            "oblique-survival",
            OBLIQUE_SURVIVAL_DOCUMENT,
            build_oblique_survival_graph_contract,
            None,
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
