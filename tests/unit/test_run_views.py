"""``gnode view``: the workflow runs it finds, and the run views it keeps fresh in the cache.

Every run here is built under ``tmp_path`` and every dashboard is a stand-in that waits for
what the test expects and returns. A view must land in the cache only; each test that has
one written checks that the run folder is byte-for-byte as it was written.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import re
import runpy
import shutil
import time
from collections.abc import Callable
from io import StringIO
from pathlib import Path

import pytest

from gnode import Dashboard, Plugin, cli, view_key
from gnode import run as gnode_run

PARALLAX_INPUTS = (
    Path(__file__).resolve().parents[2]
    / "src/stage_gen/workflows/looping_parallax/inputs/supplied_layers/make_inputs.py"
)
WAIT_SECONDS = 30.0


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


def _started_run(run_dir: Path) -> Path:
    """A workflow run as it starts: its plan (here, one no view can be built from) and the
    record it appends to."""
    _write(run_dir / "plan.json", {"gnode": "graph/v2"})
    _write(run_dir / "events.jsonl", "")
    return run_dir


@pytest.fixture(scope="module")
def parallax_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real, free looping-parallax run."""
    base = tmp_path_factory.mktemp("parallax")
    inputs = runpy.run_path(str(PARALLAX_INPUTS))["write_inputs"](base / "inputs")
    project = base / "project"
    project.mkdir()
    (project / "gnode.yaml").write_text("gnode: project/v1\n", encoding="utf-8")
    completed = gnode_run("looping-parallax", input_files=[inputs], cwd=project)
    assert completed.ok, completed.failed
    return completed.run_dir


class _Board:
    """A dashboard that waits until ``ready`` holds (or a deadline passes), then returns."""

    def __init__(self, ready: Callable[[Dashboard], bool]) -> None:
        self.ready = ready
        self.requests: list[Dashboard] = []

    def __call__(self, request: Dashboard) -> int:
        self.requests.append(request)
        deadline = time.monotonic() + WAIT_SECONDS
        while not self.ready(request):
            if time.monotonic() > deadline:
                return 1
            time.sleep(0.05)
        return 0


@pytest.fixture(autouse=True)
def _cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


class _Entry:
    """A ``gnode.plugins`` entry point that returns a plugin made here."""

    def __init__(self, plugin: Plugin) -> None:
        self.name = plugin.name
        self.plugin = plugin

    def load(self) -> Plugin:
        return self.plugin


def _install(monkeypatch: pytest.MonkeyPatch, *installed: Plugin) -> None:
    """The standard node types' plugin and ``installed``, and no other: Stage Gen's own
    plugin installs the real viewer, which these stand-ins replace."""
    std = [e for e in importlib.metadata.entry_points(group="gnode.plugins") if e.name == "std"]
    entries = [*std, *(_Entry(plugin) for plugin in installed)]
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda **_: entries)


def _view(cwd: Path, *arguments: str, errors: StringIO | None = None) -> int:
    return cli.main(["view", *arguments], stdout=StringIO(), stderr=errors or StringIO(), cwd=cwd)


def _view_of(request: Dashboard, run_dir: Path) -> Path:
    return request.view_cache / view_key(run_dir) / "execution-view.json"


# ---------------------------------------------------------------- the runs it finds


def test_it_finds_workflow_runs_under_each_root_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, spikes, elsewhere = tmp_path / "out", tmp_path / "spikes", tmp_path / "elsewhere"
    expected = [
        _started_run(out / "runs/universe/2026-10-03-1"),
        _started_run(spikes / "review/facial-4k/yuzu/run-01"),
    ]
    _write(out / "ember-hollow/manifest.json", {"kind": "a delivered package"})
    _write(spikes / "plan-only/plan.json", {"gnode": "graph/v2"})
    _started_run(out / ".cache/run")
    _started_run(out / "node_modules/pkg")
    _started_run(out / "runs/universe/2026-10-03-1/files/inner")
    _started_run(out / "a/b/c/d/too-deep")
    _started_run(elsewhere / "outside")
    (out / "linked").symlink_to(elsewhere, target_is_directory=True)
    board = _Board(lambda request: all(_view_of(request, run).is_file() for run in expected))
    _install(monkeypatch, Plugin(name="board", dashboard=board))

    assert _view(tmp_path, str(out), str(spikes)) == 0
    time.sleep(0.2)  # one pass writes every view it finds
    kept = {path.name for path in board.requests[0].view_cache.iterdir()}
    assert kept == {view_key(run) for run in expected}


# ---------------------------------------------------------------- the views it keeps


def _reported(errors: StringIO) -> set[str]:
    return set(re.findall(r"no view for (\S+):", errors.getvalue()))


def test_a_run_s_view_and_contexts_are_written_into_the_cache_only(
    tmp_path: Path, parallax_run: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = shutil.copytree(parallax_run, tmp_path / "runs/parallax-01")
    before = _snapshot(run_dir)
    board = _Board(lambda request: _view_of(request, run_dir).is_file())
    _install(monkeypatch, Plugin(name="board", dashboard=board))

    assert _view(tmp_path, str(tmp_path / "runs")) == 0

    [request] = board.requests
    assert request.view_cache == tmp_path / "cache/gnode/views"
    written = _view_of(request, run_dir)
    assert _snapshot(run_dir) == before
    view = json.loads(written.read_text(encoding="utf-8"))
    assert view["kind"] == "gnode-run-view-v1" and view["schema_version"] == 3
    assert view["run_state"] == "succeeded"
    assert {node["state"] for node in view["nodes"]} == {"succeeded"}
    contexts = json.loads((written.parent / "view-contexts.json").read_text(encoding="utf-8"))
    assert contexts["kind"] == "gnode-view-contexts-v1" and contexts["views"]


def test_a_view_is_written_again_only_when_its_run_changes(
    tmp_path: Path, parallax_run: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "runs"
    good = shutil.copytree(parallax_run, root / "good")
    # Its plan has lost every instance: no view can be built from it, and the good run's
    # view is written all the same.
    broken = shutil.copytree(parallax_run, root / "broken")
    plan = json.loads((broken / "plan.json").read_text(encoding="utf-8"))
    (broken / "plan.json").write_text(
        json.dumps({**plan, "instances": "not a list"}), encoding="utf-8"
    )
    errors = StringIO()
    board = _Board(lambda request: _view_of(request, good).is_file() and bool(_reported(errors)))
    _install(monkeypatch, Plugin(name="board", dashboard=board))
    assert _view(tmp_path, str(root), errors=errors) == 0
    assert _reported(errors) == {str(broken.resolve())}
    view = _view_of(board.requests[0], good)
    written = view.stat().st_mtime_ns

    # Nothing changed: the next view leaves it as it was.
    still = _Board(lambda request: True)
    _install(monkeypatch, Plugin(name="board", dashboard=still))
    assert _view(tmp_path, str(root)) == 0
    time.sleep(0.5)
    assert view.stat().st_mtime_ns == written

    # The run's record changed: it is written again.
    events = good / "events.jsonl"
    later = time.time() + 10
    os.utime(events, (later, later))
    again = _Board(lambda request: view.stat().st_mtime_ns > written)
    _install(monkeypatch, Plugin(name="board", dashboard=again))
    assert _view(tmp_path, str(root)) == 0


def test_the_view_key_is_the_real_path_hashed(tmp_path: Path) -> None:
    run_dir = _started_run(tmp_path / "runs/run-01")
    (tmp_path / "alias").symlink_to(tmp_path / "runs", target_is_directory=True)
    assert view_key(tmp_path / "alias/run-01") == view_key(run_dir)
    assert re.fullmatch(r"[0-9a-f]{16}", view_key(run_dir))


# ---------------------------------------------------------------- the verb


def test_without_a_dashboard_it_says_so_and_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, Plugin(name="bare"))
    errors = StringIO()
    assert _view(tmp_path, str(tmp_path), errors=errors) == 2
    assert "no dashboard is installed" in errors.getvalue()


def test_two_dashboards_are_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        Plugin(name="one", dashboard=lambda request: 0),
        Plugin(name="two", dashboard=lambda request: 0),
    )
    errors = StringIO()
    assert _view(tmp_path, str(tmp_path), errors=errors) == 2
    assert "two plugins install a dashboard: one, two" in errors.getvalue()


def test_the_dashboard_gets_the_roots_the_cache_and_the_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Dashboard] = []

    def launch(request: Dashboard) -> int:
        seen.append(request)
        return 7

    _install(monkeypatch, Plugin(name="board", dashboard=launch))
    (tmp_path / "project/out/runs").mkdir(parents=True)
    (tmp_path / "project/gnode.yaml").write_text(
        "gnode: project/v1\nruns: out/runs\n", encoding="utf-8"
    )

    assert _view(tmp_path / "project", "--port", "3100", "--no-open") == 7
    assert seen == [
        Dashboard(
            roots=((tmp_path / "project/out/runs").resolve(),),
            view_cache=tmp_path / "cache/gnode/views",
            port=3100,
            open_browser=False,
        )
    ]


def test_a_missing_run_folder_or_a_bad_port_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, Plugin(name="board", dashboard=lambda request: 0))
    errors = StringIO()
    assert _view(tmp_path, str(tmp_path / "absent"), errors=errors) == 2
    assert "no run folder at" in errors.getvalue()
    errors = StringIO()
    assert _view(tmp_path, str(tmp_path), "--port", "0", errors=errors) == 2
    assert "--port" in errors.getvalue()
