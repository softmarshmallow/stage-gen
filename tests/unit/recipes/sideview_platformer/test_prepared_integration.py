"""The terminal node is real: integration restores, adopts, or refuses; it never spends."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from gnode import Scheduler
from stage_gen.config import StageGenConfig
from stage_gen.recipes.sideview_platformer.package_executor import PreparedPackageExecutor
from stage_gen.recipes.sideview_platformer.package_types import MANIFEST_ASSEMBLE
from stage_gen.recipes.sideview_platformer.prepared_content import (
    PreparedContentNodeHandler,
    content_target_node_ids,
)
from stage_gen.recipes.sideview_platformer.prepared_integration import (
    PROVIDER_FREE_REASON,
    PreparedIntegrationNodeHandler,
)
from stage_gen.resources import (
    terrain_atlas_template_path,
    terrain_atlas_topology_reference_path,
)
from tests.unit.recipes.sideview_platformer.test_prepared_content import (
    BELLWEATHER,
    _FakeImageService,
    _FakeMusicService,
    _FakeStructuredService,
)


async def _content_run(tmp_path: Path) -> tuple[Path, Path]:
    """One fake content run into a cache: what a paid checkpoint leaves behind."""

    prepared = PreparedPackageExecutor(StageGenConfig()).plan(BELLWEATHER)
    run_dir = tmp_path / "content-run"
    run_dir.mkdir()
    cache_dir = tmp_path / "cache"
    handler = PreparedContentNodeHandler(
        prepared.graph,
        prepared.resolved,
        run_dir=run_dir,
        cache_dir=cache_dir,
        image_service=_FakeImageService(),  # type: ignore[arg-type]
        structured_service=_FakeStructuredService(),  # type: ignore[arg-type]
        music_service=_FakeMusicService(),  # type: ignore[arg-type]
    )
    summary = await Scheduler(prepared.graph.resources, node_timeout_seconds=120).run(
        prepared.graph,
        handler,
        invocation_id="content",
        target_node_ids=content_target_node_ids(prepared.graph),
    )
    assert summary.ok is True
    return run_dir, cache_dir


@dataclass(frozen=True, slots=True)
class _Run:
    ok: bool
    nodes: dict[str, dict[str, object]]
    ops: dict[str, int]


async def _integrate(
    tmp_path: Path, *, cache_dir: Path, artifact_roots: tuple[Path, ...] = ()
) -> tuple[PreparedIntegrationNodeHandler, _Run]:
    prepared = PreparedPackageExecutor(StageGenConfig()).plan(BELLWEATHER)
    run_dir = tmp_path / "integration-run"
    run_dir.mkdir()
    handler = PreparedIntegrationNodeHandler(
        prepared.graph,
        prepared.resolved,
        run_dir=run_dir,
        cache_dir=cache_dir,
        output_dir=tmp_path / "published",
        terrain_template_path=terrain_atlas_template_path(),
        terrain_topology_reference_path=terrain_atlas_topology_reference_path(),
        artifact_roots=artifact_roots,
    )
    summary = await Scheduler(prepared.graph.resources, node_timeout_seconds=120).run(
        prepared.graph,
        handler,
        invocation_id="integration",
        target_node_ids=(prepared.graph.terminal_node_id,),
    )
    nodes = {record.node_id: record.model_dump(mode="json") for record in summary.nodes}
    return handler, _Run(summary.ok, nodes, dict(summary.provider_operation_counts))


async def test_integration_restores_the_cache_and_refuses_what_it_lacks(tmp_path: Path) -> None:
    """The content cache is restored whole; the world was never run, so integration stops
    at the first world image with the provider-free reason, having spent nothing."""

    _, cache_dir = await _content_run(tmp_path)
    handler, run = await _integrate(tmp_path, cache_dir=cache_dir)
    assert run.ok is False
    assert handler.result is None
    assert handler.adopted_node_ids == []
    assert run.ops == {
        "image_generation": 0,
        "music_generation": 0,
        "structured_generation": 0,
    }
    failed = {
        node_id: record
        for node_id, record in run.nodes.items()
        if isinstance(record, dict) and record.get("status") == "failed"
    }
    assert failed, "a world node the cache lacks must fail rather than generate"
    for record in failed.values():
        assert PROVIDER_FREE_REASON in str(record.get("error"))
    # What refused is exactly paid work the cache lacks: the world's images and the
    # content reviews, which left the default content closure with the review checkpoints.
    prepared = PreparedPackageExecutor(StageGenConfig()).plan(BELLWEATHER)
    paid = {node.node_id for node in prepared.graph.nodes if not node.is_local}
    assert set(failed) <= paid, sorted(set(failed) - paid)
    assert any(node_id.startswith("map-") for node_id in failed)
    assert any(node_id.endswith("-review") for node_id in failed)
    assert not (tmp_path / "published").exists()


async def test_integration_adopts_from_a_root_only_what_the_cache_lacks(tmp_path: Path) -> None:
    """With an empty cache and the content run as a root, every paid content node is adopted
    from the root - and the cache still lacks it, so the price stays visible."""

    content_run, _ = await _content_run(tmp_path)
    handler, run = await _integrate(
        tmp_path, cache_dir=tmp_path / "empty-cache", artifact_roots=(content_run,)
    )
    assert run.ok is False  # the world is still missing; adoption is not generation
    assert run.ops["image_generation"] == 0 and run.ops["structured_generation"] == 0
    assert handler.adopted_node_ids
    assert all(not node_id.startswith("map-") for node_id in handler.adopted_node_ids)
    assert all(not node_id.endswith("-review") for node_id in handler.adopted_node_ids)
    # Local nodes cache as they re-derive; an adopted paid node never does.
    cached_node_ids = {
        json.loads(path.read_text(encoding="utf-8"))["node_id"]
        for path in (tmp_path / "empty-cache").rglob("record.json")
    }
    assert cached_node_ids.isdisjoint(handler.adopted_node_ids)


def test_the_manifest_node_is_registered_by_the_integration_handler() -> None:
    """Every type the graph declares has a handler: the manifest type is integration's."""

    prepared = PreparedPackageExecutor(StageGenConfig()).plan(BELLWEATHER)
    handler = PreparedIntegrationNodeHandler(
        prepared.graph,
        prepared.resolved,
        run_dir=Path("/nonexistent"),
        cache_dir=Path("/nonexistent"),
        output_dir=Path("/nonexistent"),
        terrain_template_path=terrain_atlas_template_path(),
        terrain_topology_reference_path=terrain_atlas_topology_reference_path(),
    )
    owned = handler._world.registered_type_ids | handler._content.registered_type_ids
    declared = {node.type_id for node in prepared.graph.nodes}
    assert declared - owned == {MANIFEST_ASSEMBLE.type_id}
