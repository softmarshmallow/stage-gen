"""The viewer ``gnode view`` starts: its checkout, environment and command, offline.

Bun is a fake script on ``PATH`` and the user cache is a temporary folder, so nothing here
starts the real viewer or writes outside ``tmp_path``. The stop tests give the fake Bun a
child of its own, standing in for the server ``next dev`` starts, and check that no process
of the viewer outlives the launcher.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import time
from collections.abc import Iterator
from io import StringIO
from pathlib import Path

import pytest

from gnode import Dashboard, cli
from stage_gen import viewer as dashboard

REPOSITORY = Path(__file__).resolve().parents[2]
SLEEP = shutil.which("sleep") or "/bin/sleep"
# Runs the real `gnode view` in its own process, as a terminal would start it: the stop
# signals at their defaults, and the catalog export skipped since these tests are about
# processes.
LAUNCHER = """
import signal, sys
signal.signal(signal.SIGTERM, signal.SIG_DFL)
signal.signal(signal.SIGHUP, signal.SIG_DFL)
signal.signal(signal.SIGINT, signal.default_int_handler)
from stage_gen import viewer as dashboard
dashboard.export_catalog = lambda path: []
from gnode import cli
raise SystemExit(cli.main(["view", sys.argv[1], "--no-open"]))
"""


def _gnode_view(*arguments: str) -> tuple[int, str, str]:
    output, errors = StringIO(), StringIO()
    status = cli.main(["view", *arguments], stdout=output, stderr=errors, cwd=REPOSITORY)
    return status, output.getvalue(), errors.getvalue()


def _request(*roots: Path, port: int = 3000) -> Dashboard:
    return Dashboard(
        roots=tuple(root.resolve() for root in roots) or ((REPOSITORY / "out/runs").resolve(),),
        view_cache=Path("/views"),
        port=port,
        open_browser=False,
    )


@pytest.fixture
def fake_bun(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A ``bun`` that records how it was called and exits, alone on ``PATH``."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    bun = bin_dir / "bun"
    record = tmp_path / "bun-called.json"
    bun.write_text(
        f'#!/bin/sh\nprintf \'%s\\n\' "$PWD" "$STAGE_GEN_RUN_ROOTS" "$@" > \'{record}\'\n',
        encoding="utf-8",
    )
    bun.chmod(bun.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return bun


def test_the_launch_carries_the_roots_catalog_and_view_cache(
    fake_bun: Path, tmp_path: Path
) -> None:
    first, second = tmp_path / "out", tmp_path / "spikes"

    launch = dashboard.prepare(_request(first, second, port=3100), os.environ)

    assert launch.command == (
        str(fake_bun),
        "run",
        "--cwd",
        "web/viewer",
        "dev",
        "--port",
        "3100",
        "--hostname",
        "127.0.0.1",
    )
    assert launch.checkout == REPOSITORY
    cache = tmp_path / "cache" / "stage-gen"
    assert {name: launch.env[name] for name in launch.env if name.startswith("STAGE_GEN_")} == {
        "STAGE_GEN_RUN_ROOTS": os.pathsep.join((str(first.resolve()), str(second.resolve()))),
        "STAGE_GEN_CATALOG": str(cache / "catalog" / "catalog.json"),
        "STAGE_GEN_VIEW_CACHE": "/views",
        "STAGE_GEN_REPO_ROOT": str(REPOSITORY),
    }
    assert launch.url == "http://127.0.0.1:3100/"


def test_the_catalog_export_lists_the_installed_workflows(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    assert dashboard.export_catalog(path) == []
    catalog = json.loads(path.read_text(encoding="utf-8"))
    assert catalog["kind"] == "stage-gen-catalog-v1"
    assert {workflow["id"] for workflow in catalog["workflows"]} >= {"movie-sprite", "universe"}


def test_provider_keys_never_reach_the_viewer(fake_bun: Path) -> None:
    environment = {**os.environ, "OPENAI_API_KEY": "not-a-key", "FAL_KEY": "not-a-key"}
    launch = dashboard.prepare(_request(), environment)
    assert "OPENAI_API_KEY" not in launch.env and "FAL_KEY" not in launch.env
    assert launch.env["PATH"] == environment["PATH"]


def test_gnode_view_runs_bun_in_the_checkout_and_returns_its_status(
    fake_bun: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dashboard, "export_catalog", lambda path: [])
    root = tmp_path / "runs"
    root.mkdir()

    status, _, errors = _gnode_view(str(root), "--no-open")

    assert status == 0, errors
    called = (tmp_path / "bun-called.json").read_text(encoding="utf-8").splitlines()
    assert called == [
        str(REPOSITORY),
        str(root.resolve()),
        "run",
        "--cwd",
        "web/viewer",
        "dev",
        "--port",
        "3000",
        "--hostname",
        "127.0.0.1",
    ]


def test_without_bun_it_refuses_and_points_at_the_guide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    status, _, errors = _gnode_view(str(tmp_path))
    assert status == 2
    assert dashboard.REFUSAL in errors


def test_outside_a_checkout_it_refuses(fake_bun: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dashboard, "find_checkout", lambda starts: None)
    with pytest.raises(ValueError, match="needs a source checkout of Stage Gen and Bun"):
        dashboard.prepare(_request(), os.environ)


def test_a_checkout_is_a_stage_gen_project_that_holds_the_viewer(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    nested = checkout / "src" / "stage_gen"
    nested.mkdir(parents=True)
    (checkout / "pyproject.toml").write_text('[project]\nname = "stage-gen"\n', encoding="utf-8")
    # An installed wheel's project file, without the viewer beside it, is not a checkout.
    assert dashboard.find_checkout((nested,)) is None
    (checkout / "web" / "viewer").mkdir(parents=True)
    (checkout / "web" / "viewer" / "package.json").write_text("{}", encoding="utf-8")
    assert dashboard.find_checkout((nested,)) == checkout
    (checkout / "pyproject.toml").write_text('[project]\nname = "other"\n', encoding="utf-8")
    assert dashboard.find_checkout((nested,)) is None


def test_the_catalog_cache_follows_an_absolute_xdg_cache_home_only(tmp_path: Path) -> None:
    assert dashboard.cache_home({"XDG_CACHE_HOME": str(tmp_path)}) == tmp_path / "stage-gen"
    assert dashboard.cache_home({"XDG_CACHE_HOME": "rel"}) == Path.home() / ".cache/stage-gen"
    assert dashboard.cache_home({}) == Path.home() / ".cache/stage-gen"


def _write_server_bun(bun: Path, pids: Path, *, then: str) -> None:
    """A ``bun`` that starts a long-lived child, records both process ids, then ``then``."""
    bun.write_text(
        f"#!/bin/sh\n{SLEEP} 300 &\nprintf '%s %s\\n' \"$$\" \"$!\" > '{pids}'\n{then}\n",
        encoding="utf-8",
    )


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _gone(pid: int, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while _alive(pid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)
    return True


def _started(pids: Path, launcher: subprocess.Popen[bytes], log: Path) -> tuple[int, int]:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        fields = pids.read_text(encoding="utf-8").split() if pids.exists() else []
        if len(fields) == 2:
            return int(fields[0]), int(fields[1])
        if launcher.poll() is not None:
            break
        time.sleep(0.05)
    raise AssertionError(f"the fake viewer never started: {log.read_text(encoding='utf-8')}")


@pytest.fixture
def server_pids(fake_bun: Path, tmp_path: Path) -> Iterator[Path]:
    """Where the fake Bun records its pid and its child's; both are killed if a test fails."""
    pids = tmp_path / "pids"
    yield pids
    if pids.exists():
        for pid in (int(field) for field in pids.read_text(encoding="utf-8").split()):
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)


@pytest.mark.parametrize(
    "sent", [signal.SIGTERM, signal.SIGHUP, signal.SIGINT], ids=["SIGTERM", "SIGHUP", "SIGINT"]
)
def test_a_stop_signal_ends_the_viewer_and_everything_it_started(
    sent: signal.Signals, fake_bun: Path, server_pids: Path, tmp_path: Path
) -> None:
    _write_server_bun(fake_bun, server_pids, then="wait")
    root = tmp_path / "runs"
    root.mkdir()
    # The launcher's output goes to a file: a pipe would stay open in any process that
    # outlived it, and reading it would then hang instead of failing.
    log = tmp_path / "launcher.log"
    with log.open("wb") as output:
        launcher = subprocess.Popen(
            [sys.executable, "-c", LAUNCHER, str(root)],
            cwd=REPOSITORY,
            env=dict(os.environ),
            stdout=output,
            stderr=subprocess.STDOUT,
        )
    try:
        bun, server = _started(server_pids, launcher, log)
        assert _alive(bun) and _alive(server)

        launcher.send_signal(sent)

        assert launcher.wait(timeout=30) == 128 + sent, log.read_text(encoding="utf-8")
        assert _gone(bun), "the viewer outlived the launcher"
        assert _gone(server), "a process the viewer started outlived the launcher"
    finally:
        if launcher.poll() is None:
            launcher.kill()
            launcher.wait()


def test_when_the_viewer_exits_what_it_started_is_ended_too(
    fake_bun: Path, server_pids: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_server_bun(fake_bun, server_pids, then="exit 0")
    monkeypatch.setattr(dashboard, "export_catalog", lambda path: [])
    root = tmp_path / "runs"
    root.mkdir()
    before = {number: signal.getsignal(number) for number in dashboard.STOP_SIGNALS}

    status, _, errors = _gnode_view(str(root), "--no-open")

    assert status == 0, errors
    _, server = (int(field) for field in server_pids.read_text(encoding="utf-8").split())
    assert _gone(server), "a process the viewer started outlived the launcher"
    assert {number: signal.getsignal(number) for number in dashboard.STOP_SIGNALS} == before


def test_a_viewer_that_ignores_sigterm_is_killed_after_the_grace(tmp_path: Path) -> None:
    pids = tmp_path / "pids"
    child = subprocess.Popen(
        ["/bin/sh", "-c", f"trap '' TERM; {SLEEP} 300 & echo $! > '{pids}'; wait"],
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not (pids.exists() and pids.read_text(encoding="utf-8").strip()):
            assert time.monotonic() < deadline, "the stubborn viewer never started"
            time.sleep(0.05)
        server = int(pids.read_text(encoding="utf-8"))

        dashboard._stop(child, grace=0.3)

        assert child.returncode == -signal.SIGKILL
        assert _gone(server)
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()


def test_a_signal_the_launcher_was_started_ignoring_stays_ignored() -> None:
    previous = signal.signal(signal.SIGHUP, signal.SIG_IGN)
    try:
        replaced = dashboard._trap_stop_signals()
        try:
            assert signal.SIGHUP not in replaced
            assert signal.getsignal(signal.SIGHUP) is signal.SIG_IGN
            assert set(replaced) == {signal.SIGTERM, signal.SIGINT}
        finally:
            dashboard._restore_signals(replaced)
    finally:
        signal.signal(signal.SIGHUP, previous)
