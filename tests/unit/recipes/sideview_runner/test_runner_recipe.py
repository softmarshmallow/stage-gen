"""The runner recipe: plan shape, dry-run execution, and the exported view."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from stage_gen.config import StageGenConfig
from stage_gen.recipes.sideview_runner.runner_executor import SideviewRunnerExecutor
from stage_gen.recipes.sideview_runner.runner_view import build_sideview_runner_view

from ..._runner_fixture import two_genre_package


def _executor() -> SideviewRunnerExecutor:
    return SideviewRunnerExecutor(StageGenConfig())


def test_the_plan_states_the_exact_graph_the_member_implies(tmp_path: Path) -> None:
    plan = _executor().plan(two_genre_package(tmp_path))

    graph = plan.graph
    assert graph.kind == "sideview-runner-execution-graph-v1"
    assert graph.recipe == "sideview-runner"
    assert graph.track_id == "meadow-dash"
    assert graph.terminal_node_id == "manifest-assemble"
    operations = Counter(node.operation for node in graph.nodes)
    # 1 ground + 1 layer + 1 concept + 3 motion strips + 2 catalog assets = 8
    # images; the two rebase judges are the only structured calls; no design
    # node exists - segments are authored; no soundtrack member is declared.
    assert operations == {"local": 10, "image_generation": 8, "structured_generation": 2}
    # The package node is a barrier: provider roots order behind it without
    # carrying it in cache lineage.
    for node in graph.nodes:
        if node.operation == "image_generation" and "package-resolve" in node.depends_on:
            assert "package-resolve" in node.barrier_only


def test_every_generation_node_states_its_full_prompt_on_its_card(tmp_path: Path) -> None:
    plan = _executor().plan(two_genre_package(tmp_path))

    for node in plan.graph.nodes:
        if node.operation == "image_generation" and "loop" not in node.node_id:
            assert node.card is not None and node.card.prompt, node.node_id


@pytest.mark.asyncio
async def test_a_dry_run_executes_the_whole_graph_and_exports_a_view(tmp_path: Path) -> None:
    package = two_genre_package(tmp_path)
    run_dir = tmp_path / "run"
    result = await _executor().dry_run(
        package,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        invocation_id="dry-run-test",
    )

    assert result.summary.ok
    plan_document = json.loads((run_dir / "execution-plan.json").read_text(encoding="utf-8"))
    assert plan_document["kind"] == "sideview-runner-execution-graph-v1"
    view = build_sideview_runner_view(run_dir)
    assert view.recipe == "sideview-runner"
    assert view.track_id == "meadow-dash"
    assert len(view.nodes) == len(result.plan.graph.nodes)


@pytest.mark.asyncio
async def test_a_dry_run_failure_is_reported_rather_than_swallowed(tmp_path: Path) -> None:
    result = await _executor().dry_run(
        two_genre_package(tmp_path),
        run_dir=tmp_path / "run",
        cache_dir=tmp_path / "cache",
        invocation_id="dry-run-failure",
        failure_node_id="avatar-run-generate",
    )

    assert not result.summary.ok
