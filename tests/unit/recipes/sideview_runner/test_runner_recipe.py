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
    # 1 ground + 1 layer + 1 concept + 4 motion strips (the declared duck
    # profile obligates a slide) + 2 catalog assets = 9 images; the two rebase
    # judges are the only structured calls; no design node exists - segments
    # are authored. The canonical fixture declares two BGM tracks.
    assert operations == {
        "local": 13,
        "image_generation": 9,
        "structured_generation": 2,
        "music_generation": 2,
    }
    # The package node is a barrier: provider roots order behind it without
    # carrying it in cache lineage.
    for node in graph.nodes:
        if node.operation == "image_generation" and "package-resolve" in node.depends_on:
            assert "package-resolve" in node.barrier_only


def test_the_motion_vocabulary_is_declared_exactly_once() -> None:
    """The states that validate, the tuple that fans out nodes, and the plate
    band order are all one declaration; editing one without the others emits
    strips no contract admits, or refuses avatars no node serves."""

    from stage_gen.components.runner_content import (
        RUNNER_AVATAR_BASE_MOTION_STATES,
        RUNNER_AVATAR_MOTION_STATES,
        RUNNER_MOTION_ORDER,
    )
    from stage_gen.recipes.sideview_runner.runner_graph import RUNNER_MOTION_STATES

    assert RUNNER_MOTION_STATES is RUNNER_MOTION_ORDER
    assert frozenset(RUNNER_MOTION_ORDER) == RUNNER_AVATAR_MOTION_STATES
    assert RUNNER_AVATAR_BASE_MOTION_STATES < RUNNER_AVATAR_MOTION_STATES
    # The runtime's copy (web/lib/sideview-runner/contract.ts) pins the same
    # order in its own suite; a drift there fails the web gate.
    assert RUNNER_MOTION_ORDER == ("run", "jump", "slide", "death")


def test_a_slide_free_avatar_fans_out_no_slide_nodes(tmp_path: Path) -> None:
    """The node census is a function of what the member declares."""

    from ..._runner_fixture import (
        RUNNER_AVATAR_NO_SLIDE,
        RUNNER_GAMEPLAY_NO_DUCK,
        WIDE_FLAT_ROWS,
        chunk_toml,
    )

    package = two_genre_package(
        tmp_path,
        chunks=chunk_toml("warmup_flat", WIDE_FLAT_ROWS),
        gameplay=RUNNER_GAMEPLAY_NO_DUCK,
        avatar=RUNNER_AVATAR_NO_SLIDE,
    )
    plan = _executor().plan(package)
    node_ids = {node.node_id for node in plan.graph.nodes}
    assert "avatar-run-generate" in node_ids
    assert "avatar-slide-generate" not in node_ids
    assert "avatar-slide-validate" not in node_ids


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
