"""The dry run rehearses through the real node cache, and its placeholders are not artifacts."""

from __future__ import annotations

from pathlib import Path

import pytest

from ember_hollow_pipeline.survival_executor import ObliqueSurvivalExecutor
from stage_gen.config import StageGenConfig
from stage_gen.pipeline.dry_run import DRY_RUN_CACHE_NAMESPACE, is_placeholder

PACKAGE = Path(__file__).resolve().parents[3] / "godot/games/ember_hollow/inputs"


@pytest.mark.asyncio
async def test_a_second_rehearsal_restores_every_node_from_the_one_cache(tmp_path: Path) -> None:
    executor = ObliqueSurvivalExecutor(StageGenConfig(), scope="minimal")
    cache_dir = tmp_path / "cache"
    first = await executor.dry_run(
        PACKAGE, run_dir=tmp_path / "first", cache_dir=cache_dir, invocation_id="first"
    )
    assert first.summary.ok
    assert {trace.cache.value for trace in first.summary.nodes if trace.cache} == {"miss"}
    # One namespace under the cache root, the same layout a live run writes.
    assert [child.name for child in cache_dir.iterdir()] == [DRY_RUN_CACHE_NAMESPACE]
    # Every declared port carries a placeholder the run's readers can tell apart.
    for node in first.plan.graph.nodes:
        for port in node.ports:
            path = tmp_path / "first" / port.artifact_ref
            assert path.is_file(), port.artifact_ref
            assert is_placeholder(path), port.artifact_ref
    assert not is_placeholder(tmp_path / "first" / "execution-plan.json")
    assert not is_placeholder(tmp_path / "nowhere.png")

    second = await executor.dry_run(
        PACKAGE, run_dir=tmp_path / "second", cache_dir=cache_dir, invocation_id="second"
    )
    assert second.summary.ok
    assert {trace.cache.value for trace in second.summary.nodes if trace.cache} == {"hit"}
    assert all(count == 0 for count in second.summary.provider_operation_counts.values())
