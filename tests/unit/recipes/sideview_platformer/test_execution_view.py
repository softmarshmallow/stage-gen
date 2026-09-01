from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from gnode import RunViewError, write_run_view
from stage_gen.config import StageGenConfig
from stage_gen.recipes.sideview_platformer.execution_view import ExecutionView, build_execution_view
from stage_gen.recipes.sideview_platformer.package_executor import PreparedPackageExecutor

REPOSITORY_ROOT = Path(__file__).parents[4]
BELLWEATHER = REPOSITORY_ROOT / "library/games/bellweather"


@pytest.fixture(scope="module")
def dry_run_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("execution-view")
    run_dir = root / "run"
    asyncio.run(
        PreparedPackageExecutor(StageGenConfig()).dry_run(
            BELLWEATHER,
            run_dir=run_dir,
            cache_dir=root / "cache",
            invocation_id="view-fixture",
        )
    )
    return run_dir


def test_view_joins_plan_and_trace_for_a_finished_run(dry_run_dir: Path) -> None:
    view = build_execution_view(dry_run_dir)

    plan = json.loads((dry_run_dir / "execution-plan.json").read_text(encoding="utf-8"))
    assert len(view.nodes) == len(plan["nodes"])
    assert view.run_state == "succeeded"
    assert view.trace_modified_at is not None
    assert view.invocation_id == "view-fixture"
    assert view.duration_ms is not None
    assert view.state_counts["succeeded"] == len(view.nodes)
    assert view.state_counts["pending"] == 0
    # Ports closed the edge-kind and path-convention gaps; nothing else is missing.
    assert view.gaps == ()

    by_id = {node.node_id: node for node in view.nodes}
    resolve = by_id["package-resolve"]
    assert resolve.state == "succeeded"
    assert resolve.cache is not None
    assert resolve.duration_ms is not None
    assert resolve.artifacts
    assert all(artifact.present for artifact in resolve.artifacts)
    # The display join: every node carries its registered type's title and archetype.
    assert resolve.type_id == "2d/sideview/platformer/package.resolve"
    assert resolve.title == "Package capture"
    assert resolve.archetype == "source"
    layer = by_id["map-crowncrag-road-layer-open_sky-generate"]
    assert layer.archetype == "image"
    assert layer.params == {"map_id": "crowncrag-road", "layer_id": "open_sky"}
    assert {port.port_id for port in layer.ports} == {"image"}
    assert by_id["map-crowncrag-road-ground-generate"].barrier_only == ("package-resolve",)

    view_path = dry_run_dir / "execution-view.json"
    write_run_view(view_path, view)
    text = view_path.read_text(encoding="utf-8")
    assert str(BELLWEATHER) not in text
    assert str(dry_run_dir) not in text
    assert "OPENAI_API_KEY" not in text
    assert ExecutionView.model_validate_json(text).graph_sha256 == view.graph_sha256


def test_view_reads_a_cut_trace_as_in_flight(dry_run_dir: Path, tmp_path: Path) -> None:
    running_node = "manifest-assemble"
    pending_node = "package-resolve"
    partial = tmp_path / "partial"
    partial.mkdir()
    (partial / "execution-plan.json").write_text(
        (dry_run_dir / "execution-plan.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    kept: list[str] = []
    for line in (dry_run_dir / "execution-trace.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event["event"] == "run_finished":
            continue
        if event.get("node_id") == running_node and event["event"] != "node_started":
            continue
        if event.get("node_id") == pending_node:
            continue
        kept.append(line)
    kept.append('{"event":"node_fini')  # a crash cuts the last line mid-write
    (partial / "execution-trace.jsonl").write_text("\n".join(kept) + "\n", encoding="utf-8")

    view = build_execution_view(partial)
    by_id = {node.node_id: node for node in view.nodes}
    # The records stop mid-stream. The document says exactly that and no more:
    # whether the run is still going is a liveness question its reader answers.
    assert view.run_state == "unfinished"
    assert view.trace_modified_at is not None
    assert view.duration_ms is None
    assert by_id[running_node].state == "running"
    assert by_id[running_node].started_offset_ms is not None
    assert by_id[pending_node].state == "pending"
    assert view.state_counts["running"] == 1
    assert view.state_counts["pending"] == 1
    assert view.state_counts["succeeded"] == len(view.nodes) - 2


def test_view_without_any_trace_reports_every_node_pending(
    dry_run_dir: Path, tmp_path: Path
) -> None:
    planned = tmp_path / "planned"
    planned.mkdir()
    (planned / "execution-plan.json").write_text(
        (dry_run_dir / "execution-plan.json").read_text(encoding="utf-8"), encoding="utf-8"
    )

    view = build_execution_view(planned)
    assert view.run_state == "planned"
    assert view.trace_modified_at is None
    assert view.invocation_id is None
    assert view.state_counts["pending"] == len(view.nodes)


def test_view_refuses_a_missing_or_unknown_plan(dry_run_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(RunViewError, match=r"no execution-plan\.json"):
        build_execution_view(tmp_path)

    plan = json.loads((dry_run_dir / "execution-plan.json").read_text(encoding="utf-8"))
    plan["schema_version"] = 99
    unknown = tmp_path / "unknown"
    unknown.mkdir()
    (unknown / "execution-plan.json").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(RunViewError, match="not a valid ExecutionGraph"):
        build_execution_view(unknown)


def test_a_canceled_run_says_so_rather_than_leaving_it_to_be_inferred(
    dry_run_dir: Path, tmp_path: Path
) -> None:
    """An interrupt reaches the scheduler while the sink is open, so it is recorded."""

    canceled = tmp_path / "canceled"
    canceled.mkdir()
    (canceled / "execution-plan.json").write_text(
        (dry_run_dir / "execution-plan.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    lines = (dry_run_dir / "execution-trace.jsonl").read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if '"event":"run_finished"' not in line][:20]
    started = json.loads(kept[0])
    kept.append(
        json.dumps(
            {
                "schema_version": started["schema_version"],
                "kind": started["kind"],
                "event": "run_canceled",
                "invocation_id": started["invocation_id"],
                "graph_sha256": started["graph_sha256"],
                "offset_ms": 4_200,
                "started_node_ids": [],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    (canceled / "execution-trace.jsonl").write_text("\n".join(kept) + "\n", encoding="utf-8")

    view = build_execution_view(canceled)

    assert view.run_state == "canceled"
    assert view.duration_ms == 4_200
