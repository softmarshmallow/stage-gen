from __future__ import annotations

import json
from pathlib import Path

from gnode import DryRunNodeHandler, NodeStatus, Scheduler
from stage_gen.config import StageGenConfig
from stage_gen.recipes.sideview_platformer.package_executor import PreparedPackageExecutor
from stage_gen.recipes.sideview_platformer.prepared_content import content_target_node_ids
from stage_gen.recipes.sideview_platformer.prepared_world import world_target_node_ids

REPOSITORY_ROOT = Path(__file__).parents[3]
BELLWEATHER = REPOSITORY_ROOT / "library/games/bellweather"


async def test_full_fake_execution_proves_concurrency_cache_and_failure_isolation(
    tmp_path: Path,
) -> None:
    executor = PreparedPackageExecutor(StageGenConfig())
    cache_dir = tmp_path / "cache"

    first = await executor.dry_run(
        BELLWEATHER,
        run_dir=tmp_path / "first",
        cache_dir=cache_dir,
        invocation_id="first",
    )
    assert first.summary.ok is True
    assert first.summary.provider_operation_counts == {
        "image_generation": 93,
        "structured_generation": 21,
        "music_generation": 3,
    }
    by_id = {trace.node_id: trace for trace in first.summary.nodes}
    first_map = by_id["map-sunpetal-crossing-layer-clear_sky-generate"]
    independent_mob = by_id["mob-petal_puff-concept-generate"]
    assert first_map.started_offset_ms is not None
    assert independent_mob.started_offset_ms is not None
    assert first_map.started_offset_ms < independent_mob.ended_offset_ms
    assert independent_mob.started_offset_ms < first_map.ended_offset_ms
    for node in first.plan.graph.nodes:
        started = by_id[node.node_id].started_offset_ms
        assert started is not None
        assert all(by_id[dependency].ended_offset_ms <= started for dependency in node.depends_on)

    replay = await executor.dry_run(
        BELLWEATHER,
        run_dir=tmp_path / "replay",
        cache_dir=cache_dir,
        invocation_id="replay",
    )
    assert replay.summary.ok is True
    assert replay.summary.provider_operation_counts == {
        "image_generation": 0,
        "structured_generation": 0,
        "music_generation": 0,
    }
    assert all(
        trace.cache is not None and trace.cache.value == "hit" for trace in replay.summary.nodes
    )

    failure = await executor.dry_run(
        BELLWEATHER,
        run_dir=tmp_path / "failure",
        cache_dir=tmp_path / "failure-cache",
        invocation_id="failure",
        failure_node_id="mob-petal_puff-state-attack-generate",
    )
    failure_by_id = {trace.node_id: trace for trace in failure.summary.nodes}
    assert failure.summary.ok is False
    assert failure_by_id["mob-petal_puff-state-attack-generate"].status is NodeStatus.FAILED
    assert failure_by_id["mob-petal_puff-state-attack-validate"].status is NodeStatus.SKIPPED
    assert failure_by_id["mob-petal_puff-review"].status is NodeStatus.SKIPPED
    assert failure_by_id["mob-jewelwing_beetle-review"].status is NodeStatus.SUCCEEDED
    assert failure_by_id["map-sunpetal-crossing-review"].status is NodeStatus.SUCCEEDED
    assert failure_by_id["manifest-assemble"].status is NodeStatus.SKIPPED

    trace_text = (tmp_path / "first/execution-trace.jsonl").read_text(encoding="utf-8")
    assert str(BELLWEATHER) not in trace_text
    assert "OPENAI_API_KEY" not in trace_text
    events = [json.loads(line) for line in trace_text.splitlines()]
    assert events[0]["event"] == "run_started"
    assert events[-1]["event"] == "run_finished"


async def test_cache_replay_rejects_modified_content_and_lineage(tmp_path: Path) -> None:
    executor = PreparedPackageExecutor(StageGenConfig())
    cache_dir = tmp_path / "cache"
    first = await executor.dry_run(
        BELLWEATHER,
        run_dir=tmp_path / "first",
        cache_dir=cache_dir,
        invocation_id="first",
    )
    node = first.plan.graph.node("props-review")
    record_path = cache_dir / node.cache_key[:2] / f"{node.cache_key}.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["dependency_lineage"] = []
    record_path.write_text(json.dumps(record), encoding="utf-8")

    content_node = first.plan.graph.node("items-review")
    content_artifact = (
        cache_dir / content_node.cache_key[:2] / f"{content_node.cache_key}.artifact.json"
    )
    content_artifact.write_bytes(content_artifact.read_bytes() + b"corrupt")

    replay = await executor.dry_run(
        BELLWEATHER,
        run_dir=tmp_path / "replay",
        cache_dir=cache_dir,
        invocation_id="replay",
    )
    by_id = {trace.node_id: trace for trace in replay.summary.nodes}
    assert by_id["props-review"].cache is not None
    assert by_id["props-review"].cache.value == "miss"
    assert by_id["items-review"].cache is not None
    assert by_id["items-review"].cache.value == "miss"
    assert replay.summary.provider_operation_counts["structured_generation"] == 2


async def test_world_targets_execute_only_map_ancestors(tmp_path: Path) -> None:
    prepared = PreparedPackageExecutor(StageGenConfig()).plan(BELLWEATHER)
    targets = world_target_node_ids(prepared.graph)
    summary = await Scheduler(prepared.graph.resources).run(
        prepared.graph,
        DryRunNodeHandler(
            prepared.graph,
            run_dir=tmp_path / "run",
            cache_dir=tmp_path / "cache",
            time_scale=0,
        ),
        invocation_id="world-closure",
        target_node_ids=targets,
    )

    assert summary.ok is True
    assert len(summary.nodes) == 41
    # Thirteen asset images plus four Sunpetal loop nodes: that map declares `generated_bridge`,
    # so each of its layers may need one bridge image. Crowncrag declares `mirror_repeat` and its
    # loop nodes are local. This is the worst case; admission runs first and a layer that already
    # loops spends nothing.
    assert summary.provider_operation_counts == {
        "image_generation": 17,
        "structured_generation": 4,
        "music_generation": 0,
    }
    assert {trace.node_id for trace in summary.nodes}.isdisjoint(
        {"player-wayfarer-concept-generate", "soundtrack-title_theme-generate"}
    )


async def test_content_targets_execute_only_content_ancestors(tmp_path: Path) -> None:
    prepared = PreparedPackageExecutor(StageGenConfig()).plan(BELLWEATHER)
    targets = content_target_node_ids(prepared.graph)
    summary = await Scheduler(prepared.graph.resources).run(
        prepared.graph,
        DryRunNodeHandler(
            prepared.graph,
            run_dir=tmp_path / "run",
            cache_dir=tmp_path / "cache",
            time_scale=0,
        ),
        invocation_id="content-closure",
        target_node_ids=targets,
    )

    assert summary.ok is True
    assert len(summary.nodes) == 180
    assert summary.provider_operation_counts == {
        "image_generation": 76,
        "structured_generation": 17,
        "music_generation": 3,
    }
    node_ids = {trace.node_id for trace in summary.nodes}
    assert "gameplay-bindings-validate" in node_ids
    # The projectile is a content family like props and items, and its sprite is a required
    # runtime artifact. Absent from this closure, the content checkpoint produced everything
    # except that sprite and integration then failed on it.
    assert "projectiles-review" in node_ids
    assert "projectile-paperwing_dart-generate" in node_ids
    assert "manifest-assemble" not in node_ids
    assert not any(node_id.startswith("map-") for node_id in node_ids)
