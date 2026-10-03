#!/usr/bin/env python3
"""Check or rewrite maintained game graph snapshots.

These executable contracts belong to the game-owned builders. New asset
pipelines do not inherit their gameplay stages or fixture requirements. A game
built with gnode pins the plan of its builder over its own package: every planned
step instance (later takes included) and what each reads.

    python godot/tools/write_game_graph_contract.py
    python godot/tools/write_game_graph_contract.py --write
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections import Counter
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
from gnode import plan_async
from scripts.graph_contracts import document_contract, write_contract
from stage_gen.config import StageGenConfig

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DOCUMENT = REPOSITORY_ROOT / "godot/games/bellweather/docs/generation-pipeline.md"
CONTRACT_KIND = "prepared-game-execution-graph-contract-v1"
FIXTURE_REF = "godot/games/bellweather/inputs/default"
RUNNER_GAME = "godot/games/iron_petal_unit"
RUNNER_BUILDER = "pipeline/workflow.py:build"
RUNNER_FIXTURE_REF = f"{RUNNER_GAME}/inputs"
RUNNER_PIPELINE_DOCUMENT = REPOSITORY_ROOT / RUNNER_GAME / "docs/runner.md"
RUNNER_CONTRACT_KIND = "sideview-runner-gnode-plan-contract-v1"
OBLIQUE_SURVIVAL_DOCUMENT = REPOSITORY_ROOT / "godot/games/ember_hollow/docs/generation-v1.md"
OBLIQUE_SURVIVAL_FIXTURE_REF = "godot/games/ember_hollow/inputs"
OBLIQUE_SURVIVAL_CONTRACT_KIND = "oblique-survival-execution-graph-contract-v1"
OBLIQUE_SURVIVAL_SCOPE = "full"


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
    """Derive the runner's contract from the plan its gnode builder makes of its package."""

    planned = asyncio.run(
        plan_async(RUNNER_BUILDER, cwd=repo / RUNNER_GAME, arguments={"package": "inputs"})
    )
    if not planned.ok:
        problems = "; ".join(f"{p.where}: {p.message}" for p in planned.problems)
        raise ValueError(f"the runner builder does not plan: {problems}")
    live = [instance for instance in planned.instances if instance.state != "absent"]
    ids = {instance.id for instance in live}
    topology = sorted(
        [instance.id, sorted(dep for dep in instance.inputs_from if dep in ids)]
        for instance in live
    )
    operations = Counter(
        ",".join(sorted(instance.routes)) or "local"
        for instance in live
        if not instance.take or instance.take == 1
    )
    return {
        "kind": RUNNER_CONTRACT_KIND,
        "fixture_ref": RUNNER_FIXTURE_REF,
        "builder": RUNNER_BUILDER,
        "workflow_id": planned.planner.workflow.id,
        "topology_sha256": hashlib.sha256(
            json.dumps(topology, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "node_count": len(live),
        "step_count": len({instance.step for instance in live}),
        "first_take_operation_counts": dict(sorted(operations.items())),
        "outputs": sorted(planned.planner.workflow.outputs),
        "type_ids": sorted({instance.uses for instance in live}),
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
