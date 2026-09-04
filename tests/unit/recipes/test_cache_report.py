"""The warm price of a plan: what a cache would restore and what it would bill."""

from __future__ import annotations

import json
from pathlib import Path

from gnode import Graph
from stage_gen.config import StageGenConfig
from stage_gen.recipes.cache_report import cache_report
from stage_gen.recipes.sideview_runner.runner_executor import SideviewRunnerExecutor
from stage_gen.recipes.sideview_runner.runner_graph import RUNNER_CACHE_NAMESPACE

IRON_PETAL = Path(__file__).parents[3] / "library/games/iron-petal-unit"


def _graph() -> Graph:
    return SideviewRunnerExecutor(StageGenConfig()).plan(IRON_PETAL).graph


def _seed(cache_dir: Path, graph: Graph, *, skip: frozenset[str] = frozenset()) -> None:
    """Write a record for every node as the real cache would, minus ``skip``."""

    for node in graph.nodes:
        if node.node_id in skip:
            continue
        barriers = set(node.barrier_only)
        root = cache_dir / RUNNER_CACHE_NAMESPACE / node.cache_key[:2] / node.cache_key
        root.mkdir(parents=True)
        (root / "record.json").write_text(
            json.dumps(
                {
                    "cache_key": node.cache_key,
                    "node_id": node.node_id,
                    "lineage": [
                        {"node_id": dep, "cache_key": graph.node(dep).cache_key}
                        for dep in node.depends_on
                        if dep not in barriers
                    ],
                }
            ),
            encoding="utf-8",
        )


def _provider_descendants(graph: Graph, root_id: str) -> set[str]:
    """Provider nodes reachable from ``root_id`` through non-barrier edges."""

    reached = {root_id}
    changed = True
    while changed:
        changed = False
        for node in graph.nodes:
            if node.node_id in reached:
                continue
            barriers = set(node.barrier_only)
            if any(dep in reached for dep in node.depends_on if dep not in barriers):
                reached.add(node.node_id)
                changed = True
    return {node_id for node_id in reached if graph.node(node_id).provider is not None}


def test_an_empty_cache_bills_every_provider_operation(tmp_path: Path) -> None:
    graph = _graph()
    provider_count = sum(1 for node in graph.nodes if node.provider is not None)

    report = cache_report(graph, tmp_path, (RUNNER_CACHE_NAMESPACE,))

    assert report["billed_provider_nodes"] == provider_count
    assert report["restored_provider_nodes"] == 0
    assert report["estimated_cost_high_usd"] > 0
    assert sum(report["billed_operation_counts"].values()) == provider_count


def test_a_complete_cache_bills_nothing(tmp_path: Path) -> None:
    graph = _graph()
    _seed(tmp_path, graph)

    report = cache_report(graph, tmp_path, (RUNNER_CACHE_NAMESPACE,))

    assert report["billed_provider_nodes"] == 0
    assert report["estimated_cost_high_usd"] == 0
    assert report["restored_provider_nodes"] == sum(
        1 for node in graph.nodes if node.provider is not None
    )


def test_one_missing_provider_record_dirties_its_provider_descendants(tmp_path: Path) -> None:
    graph = _graph()
    missing = next(node for node in graph.nodes if node.provider is not None)
    _seed(tmp_path, graph, skip=frozenset({missing.node_id}))

    report = cache_report(graph, tmp_path, (RUNNER_CACHE_NAMESPACE,))

    assert {entry["node_id"] for entry in report["billed"]} == _provider_descendants(
        graph, missing.node_id
    )


def test_a_stale_lineage_is_a_miss_even_with_a_matching_key(tmp_path: Path) -> None:
    graph = _graph()
    _seed(tmp_path, graph)
    victim = next(node for node in graph.nodes if node.provider is not None and node.depends_on)
    root = tmp_path / RUNNER_CACHE_NAMESPACE / victim.cache_key[:2] / victim.cache_key
    record = json.loads((root / "record.json").read_text(encoding="utf-8"))
    record["lineage"] = []
    (root / "record.json").write_text(json.dumps(record), encoding="utf-8")

    report = cache_report(graph, tmp_path, (RUNNER_CACHE_NAMESPACE,))

    assert victim.node_id in {entry["node_id"] for entry in report["billed"]}
