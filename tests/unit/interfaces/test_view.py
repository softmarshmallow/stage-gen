"""``stage-gen view``: the launcher's checkout, environment and command, offline.

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

from stage_gen.interfaces.cli import main, parse
from stage_gen.interfaces.commands import view

REPOSITORY = Path(__file__).resolve().parents[3]
SLEEP = shutil.which("sleep") or "/bin/sleep"
# Runs the real launcher in its own process, as a terminal would start it: the stop signals
# at their defaults, and the catalog export skipped since these tests are about processes.
LAUNCHER = """
import signal, sys
signal.signal(signal.SIGTERM, signal.SIG_DFL)
signal.signal(signal.SIGHUP, signal.SIG_DFL)
signal.signal(signal.SIGINT, signal.default_int_handler)
from stage_gen.interfaces.commands import view
view.export_catalog = lambda path: []
from stage_gen.interfaces.cli import main
raise SystemExit(main(["view", "--runs", sys.argv[1], "--no-open"]))
"""


def _stage_gen(*arguments: str) -> tuple[int, str, str]:
    output, errors = StringIO(), StringIO()
    status = main(list(arguments), stdout=output, stderr=errors)
    return status, output.getvalue(), errors.getvalue()


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


def test_print_command_shows_the_environment_and_command_without_starting(
    fake_bun: Path, tmp_path: Path
) -> None:
    first, second = tmp_path / "out", tmp_path / "spikes"
    first.mkdir()
    second.mkdir()

    status, output, errors = _stage_gen(
        "view", "--runs", str(first), "--runs", str(second), "--port", "3100", "--print-command"
    )

    assert status == 0, errors
    shown = json.loads(output)
    assert shown["command"] == [
        str(fake_bun),
        "run",
        "--cwd",
        "web/viewer",
        "dev",
        "--port",
        "3100",
        "--hostname",
        "127.0.0.1",
    ]
    assert shown["cwd"] == str(REPOSITORY)
    cache = tmp_path / "cache" / "stage-gen"
    assert shown["env"] == {
        "STAGE_GEN_RUN_ROOTS": os.pathsep.join((str(first.resolve()), str(second.resolve()))),
        "STAGE_GEN_CATALOG": str(cache / "catalog" / "catalog.json"),
        "STAGE_GEN_VIEW_CACHE": str(cache / "views"),
        "STAGE_GEN_REPO_ROOT": str(REPOSITORY),
    }
    assert shown["url"] == "http://127.0.0.1:3100/"
    catalog = json.loads((cache / "catalog" / "catalog.json").read_text(encoding="utf-8"))
    assert catalog["kind"] == "stage-gen-catalog-v1"
    assert {workflow["id"] for workflow in catalog["workflows"]} >= {"movie-sprite", "universe"}
    assert not (tmp_path / "bun-called.json").exists()


def test_the_default_root_is_out_of_the_checkout(fake_bun: Path) -> None:
    launch = view.prepare(parse(["view"]), os.environ)
    assert launch.roots == ((REPOSITORY / "out").resolve(),)
    assert launch.env["STAGE_GEN_RUN_ROOTS"] == str((REPOSITORY / "out").resolve())


def test_provider_keys_never_reach_the_viewer(fake_bun: Path) -> None:
    environment = {**os.environ, "OPENAI_API_KEY": "not-a-key", "FAL_KEY": "not-a-key"}
    launch = view.prepare(parse(["view"]), environment)
    assert "OPENAI_API_KEY" not in launch.env and "FAL_KEY" not in launch.env
    assert launch.env["PATH"] == environment["PATH"]


def test_the_launcher_runs_bun_in_the_checkout_and_returns_its_status(
    fake_bun: Path, tmp_path: Path
) -> None:
    root = tmp_path / "runs"
    root.mkdir()

    status, output, errors = _stage_gen("view", "--runs", str(root), "--no-open")

    assert status == 0, errors
    assert "http://127.0.0.1:3000/" in output
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
    status, _, errors = _stage_gen("view", "--print-command")
    assert status == 2
    assert view.REFUSAL in errors


def test_outside_a_checkout_it_refuses(fake_bun: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(view, "find_checkout", lambda starts: None)
    status, _, errors = _stage_gen("view", "--print-command")
    assert status == 2
    assert "needs a source checkout and Bun; see docs/viewer.md" in errors


def test_a_checkout_is_a_stage_gen_project_that_holds_the_viewer(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    nested = checkout / "src" / "stage_gen"
    nested.mkdir(parents=True)
    (checkout / "pyproject.toml").write_text('[project]\nname = "stage-gen"\n', encoding="utf-8")
    # An installed wheel's project file, without the viewer beside it, is not a checkout.
    assert view.find_checkout((nested,)) is None
    (checkout / "web" / "viewer").mkdir(parents=True)
    (checkout / "web" / "viewer" / "package.json").write_text("{}", encoding="utf-8")
    assert view.find_checkout((nested,)) == checkout
    (checkout / "pyproject.toml").write_text('[project]\nname = "other"\n', encoding="utf-8")
    assert view.find_checkout((nested,)) is None


def test_a_missing_run_folder_or_port_is_refused(fake_bun: Path, tmp_path: Path) -> None:
    status, _, errors = _stage_gen("view", "--runs", str(tmp_path / "absent"), "--print-command")
    assert status == 2 and "no run folder at" in errors
    status, _, errors = _stage_gen("view", "--port", "0", "--print-command")
    assert status == 2 and "--port" in errors


def test_the_cache_follows_an_absolute_xdg_cache_home_only(tmp_path: Path) -> None:
    assert view.cache_home({"XDG_CACHE_HOME": str(tmp_path)}) == tmp_path / "stage-gen"
    assert view.cache_home({"XDG_CACHE_HOME": "relative"}) == Path.home() / ".cache/stage-gen"
    assert view.cache_home({}) == Path.home() / ".cache/stage-gen"


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
    monkeypatch.setattr(view, "export_catalog", lambda path: [])
    root = tmp_path / "runs"
    root.mkdir()
    before = {number: signal.getsignal(number) for number in view.STOP_SIGNALS}

    status, _, errors = _stage_gen("view", "--runs", str(root), "--no-open")

    assert status == 0, errors
    _, server = (int(field) for field in server_pids.read_text(encoding="utf-8").split())
    assert _gone(server), "a process the viewer started outlived the launcher"
    assert {number: signal.getsignal(number) for number in view.STOP_SIGNALS} == before


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

        view._stop(child, grace=0.3)

        assert child.returncode == -signal.SIGKILL
        assert _gone(server)
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()


def test_a_signal_the_launcher_was_started_ignoring_stays_ignored() -> None:
    previous = signal.signal(signal.SIGHUP, signal.SIG_IGN)
    try:
        replaced = view._trap_stop_signals()
        try:
            assert signal.SIGHUP not in replaced
            assert signal.getsignal(signal.SIGHUP) is signal.SIG_IGN
            assert set(replaced) == {signal.SIGTERM, signal.SIGINT}
        finally:
            view._restore_signals(replaced)
    finally:
        signal.signal(signal.SIGHUP, previous)
