"""Run discovery and derived views: what the viewer and ``inspect --write-view`` read.

Every run here is synthetic and built under ``tmp_path``. A derived view must land in the
cache only; each test that derives one checks that the run folder is byte-for-byte as it
was written.
"""

from __future__ import annotations

import json
import os
from io import StringIO
from pathlib import Path

from gnode import LOCAL_OPERATION, Graph, Node, Resource, RetryOwner, seal_graph
from stage_gen import runs
from stage_gen.interfaces.cli import main
from stage_gen.workflows.portrait_motion.workflow import ADMISSION, GUIDE

CHARACTER_KIND = "contained-character-parts-to-rig-v1"


def _write(path: Path, document: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = document if isinstance(document, str) else json.dumps(document)
    path.write_text(text, encoding="utf-8")
    return path


def _snapshot(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def _node(node_id: str, type_id: str, depends_on: tuple[str, ...] = ()) -> Node:
    return Node(
        node_id=node_id,
        type_id=type_id,
        domain="character",
        description=f"the {node_id} step",
        depends_on=depends_on,
        operation=LOCAL_OPERATION,
        resource_id="local",
        retry_owner=RetryOwner.NONE,
        max_attempts=1,
        cache_key="0" * 64,
        estimated_duration_seconds=0.0,
        estimated_cost_low_usd=0.0,
        estimated_cost_high_usd=0.0,
    )


def _graph(kind: str, *nodes: Node, schema_version: int = 1) -> Graph:
    return seal_graph(
        Graph,
        resources=(Resource(resource_id="local", rate_limit_owner="none"),),
        nodes=nodes,
        terminal_node_id=nodes[-1].node_id,
        schema_version=schema_version,
        kind=kind,
    )


def _events(graph: Graph, *finished: tuple[str, str]) -> str:
    """A gnode trace: the run starts, each node finishes with its one artifact, it ends."""
    lines: list[dict[str, object]] = [
        {"event": "run_started", "graph_sha256": graph.graph_sha256, "invocation_id": "one"}
    ]
    for node_id, artifact_ref in finished:
        lines.append(
            {
                "event": "node_finished",
                "graph_sha256": graph.graph_sha256,
                "node_id": node_id,
                "status": "succeeded",
                "artifacts": [{"artifact_ref": artifact_ref, "sha256": "a" * 64, "bytes": 2}],
            }
        )
    lines.append({"event": "run_finished", "graph_sha256": graph.graph_sha256, "ok": True})
    return "".join(json.dumps(line) + "\n" for line in lines)


def _character_run(run_dir: Path) -> Path:
    graph = _graph(
        CHARACTER_KIND,
        _node("runtime_admit", "3d/character/runtime_admit"),
        _node("rig_admit", "3d/character/rig_admit", ("runtime_admit",)),
    )
    _write(run_dir / "graph.json", graph.model_dump(mode="json"))
    _write(
        run_dir / "trace.jsonl",
        _events(graph, ("runtime_admit", "nodes/runtime_admit.json"), ("rig_admit", "x.json")),
    )
    _write(run_dir / "summary.json", {"kind": "gnode-run-summary-v1", "ok": True})
    _write(run_dir / "nodes/runtime_admit.json", "{}")
    return run_dir


def _portrait_run(run_dir: Path, *, traced: bool = True) -> Path:
    _write(run_dir / "plan.json", {"schema_version": 1, "kind": "portrait-face-motion-plan-v1"})
    _write(run_dir / "execution.json", {"status": "complete", "portrait_run_ref": "portrait"})
    graph = _graph(
        "portrait-motion-v2",
        _node("admission", ADMISSION.type_id),
        _node("guide", GUIDE.type_id, ("admission",)),
        schema_version=2,
    )
    _write(run_dir / "portrait/graph.json", graph.model_dump(mode="json"))
    if traced:
        _write(
            run_dir / "portrait/trace/one.jsonl",
            _events(graph, ("admission", "admission/result.json"), ("guide", "guide/sheet.png")),
        )
    _write(run_dir / "portrait/admission/result.json", "{}")
    return run_dir


# ---------------------------------------------------------------- discovery


def test_discovery_finds_every_run_shape_under_several_roots(tmp_path: Path) -> None:
    out, spikes = tmp_path / "out", tmp_path / "spikes"
    _write(out / "sdk-run/execution-plan.json", {"kind": "pipeline-execution-graph-v1"})
    _write(out / "game-run/manifest.json", {"kind": "prepared-game-runtime-v12"})
    _write(out / "view-only/execution-view.json", {"kind": "x"})
    _character_run(spikes / "canary-01/wren-01")
    _portrait_run(spikes / "review/facial-4k/yuzu/run-01")
    _write(spikes / "scratch/notes.txt", "not a run")

    found = runs.discover([out, spikes])

    assert [(run.root.name, run.relative) for run in found] == [
        ("out", "game-run"),
        ("out", "sdk-run"),
        ("out", "view-only"),
        ("spikes", "canary-01/wren-01"),
        ("spikes", "review/facial-4k/yuzu/run-01"),
    ]


def test_discovery_skips_the_example_store_hidden_folders_and_links_out(tmp_path: Path) -> None:
    out, elsewhere = tmp_path / "out", tmp_path / "elsewhere"
    _write(out / "examples/movie-sprite/yuzu-idle/manifest.json", {"kind": "x"})
    _write(out / ".cache/run/execution-plan.json", {"kind": "x"})
    _write(out / "node_modules/pkg/manifest.json", {"kind": "x"})
    _write(elsewhere / "outside/execution-plan.json", {"kind": "x"})
    (out / "linked").symlink_to(elsewhere, target_is_directory=True)
    # Only the store at the top of a root is skipped; a run may be named examples deeper.
    _write(out / "batch/examples/execution-plan.json", {"kind": "x"})

    assert [run.relative for run in runs.discover([out])] == ["batch/examples"]


def test_a_run_is_not_searched_again_and_depth_is_bounded(tmp_path: Path) -> None:
    root = tmp_path / "runs"
    _portrait_run(root / "run-01")
    _write(root / "a/b/c/d/e/execution-plan.json", {"kind": "x"})
    _write(root / "graph-only/graph.json", {"kind": "x"})

    assert [run.relative for run in runs.discover([root])] == ["run-01"]
    assert [run.relative for run in runs.discover([root], depth=5)] == ["a/b/c/d/e", "run-01"]
    assert runs.discover([tmp_path / "missing"]) == []


# ---------------------------------------------------------------- derived views


def test_a_character_run_is_joined_into_a_view_in_the_cache_only(tmp_path: Path) -> None:
    run_dir = _character_run(tmp_path / "runs/tavi-01")
    cache = tmp_path / "cache"
    before = _snapshot(run_dir)

    assert runs.needs_view(run_dir, cache)
    written = runs.derive_view(run_dir, cache)

    assert written == cache / runs.view_key(run_dir) / runs.VIEW_FILE
    assert _snapshot(run_dir) == before
    view = json.loads(written.read_text(encoding="utf-8"))
    assert view["kind"] == "gnode-run-view-v1" and view["schema_version"] == 3
    assert view["graph_kind"] == CHARACTER_KIND
    assert view["run_state"] == "succeeded"
    assert view["state_counts"]["succeeded"] == 2
    nodes = {node["node_id"]: node for node in view["nodes"]}
    # Titles come from workflow.toml, since the frozen implementation builds the types.
    assert nodes["runtime_admit"]["title"] == "Probe Blender"
    assert view["gaps"] == []
    assert nodes["runtime_admit"]["artifacts"][0]["present"] is True
    assert nodes["rig_admit"]["artifacts"][0]["present"] is False
    assert view["trace_modified_at"].endswith("Z")
    assert not runs.needs_view(run_dir, cache)


def test_a_portrait_run_is_joined_from_its_sub_run_with_run_relative_artifacts(
    tmp_path: Path,
) -> None:
    run_dir = _portrait_run(tmp_path / "runs/run-01")
    cache = tmp_path / "cache"
    before = _snapshot(run_dir)

    written = runs.derive_view(run_dir, cache)

    assert written is not None and _snapshot(run_dir) == before
    view = json.loads(written.read_text(encoding="utf-8"))
    assert view["graph_kind"] == "portrait-motion-v2"
    admission = next(node for node in view["nodes"] if node["node_id"] == "admission")
    assert admission["artifacts"][0]["artifact_ref"] == "portrait/admission/result.json"
    assert admission["artifacts"][0]["present"] is True
    assert admission["title"]


def test_a_portrait_run_without_a_trace_has_no_view_and_writes_nothing(tmp_path: Path) -> None:
    run_dir = _portrait_run(tmp_path / "runs/run-01", traced=False)
    cache = tmp_path / "cache"

    assert runs.derive_view(run_dir, cache) is None
    assert not (cache / runs.view_key(run_dir) / runs.VIEW_FILE).exists()


def test_a_game_run_is_never_derived(tmp_path: Path) -> None:
    run_dir = tmp_path / "out/bellweather-m21"
    _write(run_dir / "execution-plan.json", {"kind": "sideview-platformer-execution-graph-v2"})
    cache = tmp_path / "cache"

    # No workflow owns it, and it is not an SDK run, so nothing guesses at its view.
    assert runs.owner_of(run_dir).workflow is None
    assert not runs.is_sdk_run(run_dir)
    assert runs.derive_view(run_dir, cache) is None
    assert not cache.exists() or not any(cache.rglob(runs.VIEW_FILE))


def test_inspect_refuses_a_game_run_by_name(tmp_path: Path) -> None:
    run_dir = tmp_path / "out/bellweather-m21"
    _write(run_dir / "execution-plan.json", {"kind": "sideview-platformer-execution-graph-v2"})

    for extra in ([], ["--write-view", str(tmp_path / "view")]):
        errors = StringIO()
        assert main(["inspect", str(run_dir), *extra], stdout=StringIO(), stderr=errors) == 2
        assert "is not a workflow or SDK run" in errors.getvalue()
        assert "node-types.json" not in errors.getvalue()
    assert not (tmp_path / "view").exists()


def test_a_started_plain_portrait_run_is_listed_and_its_own_trace_is_a_source(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runs/run-01"
    plan = _write(run_dir / "plan.json", {"schema_version": 1, "kind": "portrait-motion-plan"})
    graph = _write(run_dir / "graph.json", {"kind": "portrait-motion-v2"})
    os.utime(plan, (1000, 1000))
    os.utime(graph, (1000, 1000))

    # Prepared, with no execution.json yet: listed, and its sources are the plan and graph.
    assert [found.run_dir for found in runs.discover((tmp_path / "runs",))] == [run_dir.resolve()]
    assert runs.source_mtime(run_dir) == 1000.0

    trace = _write(run_dir / "trace/a.jsonl", "")
    os.utime(trace, (2000, 2000))
    assert runs.source_mtime(run_dir) == 2000.0


def test_a_fresh_persisted_view_needs_no_derivation(tmp_path: Path) -> None:
    run_dir = _character_run(tmp_path / "runs/tavi-01")
    view = _write(run_dir / runs.VIEW_FILE, {"kind": "gnode-run-view-v1"})
    trace = run_dir / "trace.jsonl"
    os.utime(view, (trace.stat().st_mtime + 5, trace.stat().st_mtime + 5))
    assert not runs.needs_view(run_dir, tmp_path / "cache")
    os.utime(trace, (view.stat().st_mtime + 5, view.stat().st_mtime + 5))
    assert runs.needs_view(run_dir, tmp_path / "cache")


def test_the_refresher_derives_once_per_change_and_keeps_going_past_a_broken_run(
    tmp_path: Path,
) -> None:
    root = tmp_path / "runs"
    good = _character_run(root / "good")
    broken = root / "broken"
    _write(broken / "graph.json", {"kind": CHARACTER_KIND, "nodes": "not a graph"})
    _write(broken / "trace.jsonl", "")
    refresher = runs.ViewRefresher((root,), tmp_path / "cache")

    assert refresher.refresh() == [runs.cached_view(good, tmp_path / "cache")]
    assert set(refresher.failures) == {broken.resolve()}
    assert refresher.refresh() == []

    trace = good / "trace.jsonl"
    later = trace.stat().st_mtime + 10
    os.utime(trace, (later, later))
    assert refresher.refresh() == [runs.cached_view(good, tmp_path / "cache")]


def test_inspect_writes_a_character_view_only_where_it_is_asked(tmp_path: Path) -> None:
    run_dir = _character_run(tmp_path / "runs/tavi-01")
    before = _snapshot(run_dir)
    out, errors = StringIO(), StringIO()

    status = main(
        ["inspect", str(run_dir), "--write-view", str(tmp_path / "view"), "--json"],
        stdout=out,
        stderr=errors,
    )

    assert status == 0, errors.getvalue()
    record = json.loads(out.getvalue())
    assert record["workflow"] == "character-3d"
    assert record["written_view"] == str(tmp_path / "view" / runs.VIEW_FILE)
    assert _snapshot(run_dir) == before
