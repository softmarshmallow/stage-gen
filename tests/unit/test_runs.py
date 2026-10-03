"""Run discovery and derived views: what the viewer and ``inspect --write-view`` read.

Every run here is synthetic and built under ``tmp_path``. A derived view must land in the
cache only; each test that derives one checks that the run folder is byte-for-byte as it
was written.
"""

from __future__ import annotations

import json
import os
import runpy
import shutil
from io import StringIO
from pathlib import Path

import pytest

from stage_gen import runs
from stage_gen.interfaces.cli import main

PARALLAX_INPUTS = (
    Path(__file__).resolve().parents[2]
    / "src/stage_gen/workflows/looping_parallax/inputs/supplied_layers/make_inputs.py"
)


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


@pytest.fixture(scope="module")
def parallax_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real, free looping-parallax run: an installed workflow owns it."""
    from gnode import run as gnode_run

    base = tmp_path_factory.mktemp("parallax")
    inputs = runpy.run_path(str(PARALLAX_INPUTS))["write_inputs"](base / "inputs")
    project = base / "project"
    project.mkdir()
    (project / "gnode.yaml").write_text("gnode: project/v1\n", encoding="utf-8")
    completed = gnode_run("looping-parallax", input_files=[inputs], cwd=project)
    assert completed.ok, completed.failed
    return completed.run_dir


def _owned_run(parallax_run: Path, run_dir: Path) -> Path:
    shutil.copytree(parallax_run, run_dir)
    return run_dir


def _workflow_run(run_dir: Path) -> Path:
    """A gnode workflow run as it starts: its plan, and the events it appends."""
    _write(run_dir / "plan.json", {"gnode": "plan/v1"})
    _write(run_dir / "events.jsonl", "")
    return run_dir


# ---------------------------------------------------------------- discovery


def test_discovery_finds_every_run_shape_under_several_roots(tmp_path: Path) -> None:
    out, spikes = tmp_path / "out", tmp_path / "spikes"
    _write(out / "sdk-run/execution-plan.json", {"kind": "pipeline-execution-graph-v1"})
    _write(out / "game-run/manifest.json", {"kind": "prepared-game-runtime-v12"})
    _write(out / "view-only/execution-view.json", {"kind": "x"})
    _workflow_run(spikes / "canary-01/wren-01")
    _workflow_run(spikes / "review/facial-4k/yuzu/run-01")
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
    _workflow_run(root / "run-01")
    _write(root / "a/b/c/d/e/execution-plan.json", {"kind": "x"})
    _write(root / "graph-only/graph.json", {"kind": "x"})

    assert [run.relative for run in runs.discover([root])] == ["run-01"]
    assert [run.relative for run in runs.discover([root], depth=5)] == ["a/b/c/d/e", "run-01"]
    assert runs.discover([tmp_path / "missing"]) == []


# ---------------------------------------------------------------- derived views


def test_a_workflow_run_is_projected_into_a_view_in_the_cache_only(
    tmp_path: Path, parallax_run: Path
) -> None:
    run_dir = _owned_run(parallax_run, tmp_path / "runs/parallax-01")
    cache = tmp_path / "cache"
    before = _snapshot(run_dir)

    assert runs.needs_view(run_dir, cache)
    written = runs.derive_view(run_dir, cache)

    assert written == cache / runs.view_key(run_dir) / runs.VIEW_FILE
    assert _snapshot(run_dir) == before
    view = json.loads(written.read_text(encoding="utf-8"))
    assert view["kind"] == "gnode-run-view-v1" and view["schema_version"] == 3
    assert view["run_state"] == "succeeded"
    assert {node["state"] for node in view["nodes"]} == {"succeeded"}
    assert all(node["title"] for node in view["nodes"])
    assert not runs.needs_view(run_dir, cache)


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


def test_a_started_workflow_run_is_listed_and_its_events_are_a_source(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runs/run-01"
    plan = _write(run_dir / "plan.json", {"gnode": "plan/v1"})
    os.utime(plan, (1000, 1000))
    # A plan alone is not yet a run.
    assert runs.discover((tmp_path / "runs",)) == []

    events = _write(run_dir / "events.jsonl", "")
    os.utime(events, (2000, 2000))
    assert [found.run_dir for found in runs.discover((tmp_path / "runs",))] == [run_dir.resolve()]
    assert runs.source_mtime(run_dir) == 2000.0


def test_a_fresh_persisted_view_needs_no_derivation(tmp_path: Path) -> None:
    run_dir = _workflow_run(tmp_path / "runs/run-01")
    view = _write(run_dir / runs.VIEW_FILE, {"kind": "gnode-run-view-v1"})
    trace = run_dir / "events.jsonl"
    os.utime(view, (trace.stat().st_mtime + 5, trace.stat().st_mtime + 5))
    assert not runs.needs_view(run_dir, tmp_path / "cache")
    os.utime(trace, (view.stat().st_mtime + 5, view.stat().st_mtime + 5))
    assert runs.needs_view(run_dir, tmp_path / "cache")


def test_the_refresher_derives_once_per_change_and_keeps_going_past_a_broken_run(
    tmp_path: Path, parallax_run: Path
) -> None:
    root = tmp_path / "runs"
    good = _owned_run(parallax_run, root / "good")
    # Owned by looping-parallax, but its plan has lost every instance: no view can be built.
    broken = _owned_run(parallax_run, root / "broken")
    plan = json.loads((broken / "plan.json").read_text(encoding="utf-8"))
    (broken / "plan.json").write_text(
        json.dumps({**plan, "instances": "not a list"}), encoding="utf-8"
    )
    refresher = runs.ViewRefresher((root,), tmp_path / "cache")

    assert refresher.refresh() == [runs.cached_view(good, tmp_path / "cache")]
    assert set(refresher.failures) == {broken.resolve()}
    assert refresher.refresh() == []

    trace = good / "events.jsonl"
    later = trace.stat().st_mtime + 10
    os.utime(trace, (later, later))
    assert refresher.refresh() == [runs.cached_view(good, tmp_path / "cache")]


def test_inspect_writes_a_view_only_where_it_is_asked(tmp_path: Path, parallax_run: Path) -> None:
    run_dir = _owned_run(parallax_run, tmp_path / "runs/parallax-01")
    before = _snapshot(run_dir)
    out, errors = StringIO(), StringIO()

    status = main(
        ["inspect", str(run_dir), "--write-view", str(tmp_path / "view"), "--json"],
        stdout=out,
        stderr=errors,
    )

    assert status == 0, errors.getvalue()
    record = json.loads(out.getvalue())
    assert record["workflow"] == "looping-parallax"
    assert record["written_view"] == str(tmp_path / "view" / runs.VIEW_FILE)
    assert _snapshot(run_dir) == before
