"""``stage-gen view``: open the viewer, the local read-only client, over run folders.

The viewer is the Next app in ``web/viewer``, so this command needs a source checkout and
Bun; from an installed wheel it refuses. It exports the catalog into the user cache, keeps
derived run views fresh in that cache while it runs, and starts the viewer's dev server
with the run roots, the catalog and the view cache in its environment. Nothing it starts
can start a run: the viewer only reads. However the launcher ends, by the server exiting,
Ctrl-C, SIGTERM or a hangup, it first ends the server and every process the server started.
"""

from __future__ import annotations

import argparse
import atexit
import contextlib
import functools
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import tomllib
import webbrowser
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any, TextIO

REFUSAL = "stage-gen view needs a source checkout and Bun; see docs/viewer.md"
VIEWER = Path("web/viewer")
DEFAULT_PORT = 3000
REFRESH_SECONDS = 3.0
HOST = "127.0.0.1"
# The signals that end the launcher; each one ends the viewer first.
STOP_SIGNALS = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)
# How long the viewer's process group has to leave after SIGTERM before it gets SIGKILL.
STOP_GRACE_SECONDS = 10.0

SignalHandler = Callable[[int, FrameType | None], Any] | int | signal.Handlers | None


def register(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--runs",
        action="append",
        default=[],
        type=Path,
        metavar="DIR",
        help="a folder of runs to show; repeat it for several (default: out/ of the checkout)",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help="local port the viewer listens on"
    )
    parser.add_argument("--no-open", action="store_true", help="do not open a browser")
    # Test hook: print the command and environment the viewer would start with, and stop.
    parser.add_argument("--print-command", action="store_true", help=argparse.SUPPRESS)
    parser.set_defaults(handler=run)


def cache_home(env: Mapping[str, str]) -> Path:
    """``$XDG_CACHE_HOME/stage-gen`` when that is an absolute path, else ``~/.cache``."""
    configured = env.get("XDG_CACHE_HOME", "")
    base = Path(configured) if configured and Path(configured).is_absolute() else None
    return (base or Path.home() / ".cache") / "stage-gen"


def _names_stage_gen(pyproject: Path) -> bool:
    try:
        return bool(
            tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["name"] == "stage-gen"
        )
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError):
        return False


def find_checkout(starts: tuple[Path, ...]) -> Path | None:
    """The nearest folder at or above a start whose ``pyproject.toml`` names stage-gen and
    which holds the viewer; the installed package is asked first, then the working
    directory."""
    for start in starts:
        for candidate in (start, *start.parents):
            if (candidate / VIEWER / "package.json").is_file() and _names_stage_gen(
                candidate / "pyproject.toml"
            ):
                return candidate
    return None


@dataclass(frozen=True, slots=True)
class Launch:
    checkout: Path
    roots: tuple[Path, ...]
    catalog: Path
    view_cache: Path
    port: int
    command: tuple[str, ...]
    env: dict[str, str]

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}/"


def prepare(args: argparse.Namespace, env: Mapping[str, str]) -> Launch:
    """Everything the viewer starts with, checked before anything is written or started."""
    import stage_gen
    from stage_gen.provider_env import PROVIDER_ENV_KEYS

    checkout = find_checkout((Path(stage_gen.__file__).resolve().parent, Path.cwd().resolve()))
    bun = shutil.which("bun", path=env.get("PATH"))
    if checkout is None or bun is None:
        raise ValueError(REFUSAL)
    if not 0 < args.port < 65536:
        raise ValueError(f"--port must be between 1 and 65535, not {args.port}")
    roots = tuple(path.resolve() for path in args.runs) or ((checkout / "out").resolve(),)
    missing = [str(root) for root in args.runs if not root.is_dir()]
    if missing:
        raise ValueError(f"no run folder at {', '.join(missing)}")
    cache = cache_home(env)
    catalog = cache / "catalog" / "catalog.json"
    view_cache = cache / "views"
    child_env = {name: value for name, value in env.items() if name not in PROVIDER_ENV_KEYS}
    child_env.update(
        {
            "STAGE_GEN_RUN_ROOTS": os.pathsep.join(str(root) for root in roots),
            "STAGE_GEN_CATALOG": str(catalog),
            "STAGE_GEN_VIEW_CACHE": str(view_cache),
            "STAGE_GEN_REPO_ROOT": str(checkout),
        }
    )
    command = (
        bun,
        "run",
        "--cwd",
        str(VIEWER),
        "dev",
        "--port",
        str(args.port),
        "--hostname",
        HOST,
    )
    return Launch(checkout, roots, catalog, view_cache, args.port, command, child_env)


def export_catalog(path: Path) -> list[str]:
    """Write the catalog the viewer groups runs by and draws plans from; the drift problems
    a full export would refuse on are returned, not raised, since the viewer only reads."""
    from gnode import atomic_write_bytes
    from stage_gen.workflows._catalog import build

    catalog, problems = build(examples_dir=None, allow_missing_examples=True)
    payload = json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"
    atomic_write_bytes(path, payload.encode(), mode=0o644)
    return problems


def _refresh_views(launch: Launch, stop: threading.Event, errors: TextIO) -> None:
    from stage_gen.runs import ViewRefresher

    refresher = ViewRefresher(launch.roots, launch.view_cache)
    reported: set[Path] = set()
    while True:
        try:
            refresher.refresh()
        except OSError as error:
            errors.write(f"stage-gen view: could not refresh views: {error}\n")
        for run_dir, failure in refresher.failures.items():
            if run_dir not in reported:
                reported.add(run_dir)
                errors.write(f"stage-gen view: no view for {run_dir}: {failure}\n")
        if stop.wait(REFRESH_SECONDS):
            return


def _open_when_listening(url: str, port: int, stop: threading.Event) -> None:
    while not stop.wait(0.5):
        try:
            with socket.create_connection((HOST, port), timeout=0.5):
                webbrowser.open(url)
                return
        except OSError:
            continue


def _group_alive(group: int) -> bool:
    try:
        os.killpg(group, 0)
    except OSError:  # gone, or the id no longer names a group of ours
        return False
    return True


def _stop(child: subprocess.Popen[bytes], grace: float = STOP_GRACE_SECONDS) -> None:
    """End the dev server and everything it started.

    The server leads its own process group, so the group is signalled, not the child alone:
    ``next dev`` starts a server process of its own that would otherwise outlive it. A group
    still alive ``grace`` seconds after SIGTERM gets SIGKILL. The child is reaped as it
    exits, since on some systems an unreaped child keeps its group alive, and once more at
    the end so that it leaves no zombie behind.
    """
    try:
        for sent in (signal.SIGTERM, signal.SIGKILL):
            child.poll()
            if not _group_alive(child.pid):
                return
            try:
                os.killpg(child.pid, sent)
            except ProcessLookupError:
                return
            deadline = time.monotonic() + grace
            while time.monotonic() < deadline:
                child.poll()
                if not _group_alive(child.pid):
                    return
                time.sleep(0.05)
    finally:
        with contextlib.suppress(subprocess.TimeoutExpired):
            child.wait(timeout=grace)


class _Stopped(Exception):
    """A stop signal reached the launcher; it unwinds to the code that ends the viewer."""

    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum


def _raise_stopped(signum: int, frame: FrameType | None) -> None:
    raise _Stopped(signum)


def _trap_stop_signals() -> dict[int, SignalHandler]:
    """Make SIGTERM, SIGHUP and SIGINT unwind the launcher instead of ending it outright.

    The viewer leads its own session, so a terminal's hangup or interrupt never reaches it,
    and the default action of SIGTERM or SIGHUP would end the launcher alone and orphan the
    server. A signal the launcher was started ignoring, as under ``nohup``, stays ignored.
    Only the main thread may set handlers; elsewhere nothing is trapped. Returns the
    handlers replaced, for :func:`_restore_signals`.
    """
    if threading.current_thread() is not threading.main_thread():
        return {}
    replaced: dict[int, SignalHandler] = {}
    for number in STOP_SIGNALS:
        if signal.getsignal(number) is not signal.SIG_IGN:
            replaced[number] = signal.signal(number, _raise_stopped)
    return replaced


def _restore_signals(replaced: Mapping[int, SignalHandler]) -> None:
    for number, handler in replaced.items():
        signal.signal(number, handler)


def run(args: argparse.Namespace, stdout: TextIO) -> int:
    launch = prepare(args, os.environ)
    problems = export_catalog(launch.catalog)
    if args.print_command:
        shown = (
            "STAGE_GEN_RUN_ROOTS",
            "STAGE_GEN_CATALOG",
            "STAGE_GEN_VIEW_CACHE",
            "STAGE_GEN_REPO_ROOT",
        )
        stdout.write(
            json.dumps(
                {
                    "command": list(launch.command),
                    "cwd": str(launch.checkout),
                    "env": {name: launch.env[name] for name in shown},
                    "url": launch.url,
                    "catalog_problems": problems,
                },
                indent=2,
            )
            + "\n"
        )
        return 0
    roots = ", ".join(str(root) for root in launch.roots)
    stdout.write(f"stage-gen view: {launch.url} over {roots}\n")
    if problems:
        stdout.write(f"stage-gen view: the catalog has {len(problems)} drift problem(s)\n")
    stdout.flush()
    stop = threading.Event()
    threading.Thread(target=_refresh_views, args=(launch, stop, sys.stderr), daemon=True).start()
    replaced = _trap_stop_signals()
    child: subprocess.Popen[bytes] | None = None
    stop_child: Callable[[], None] | None = None
    status = 0
    try:
        child = subprocess.Popen(
            launch.command, cwd=launch.checkout, env=launch.env, start_new_session=True
        )
        # Also stopped at interpreter exit, should this frame never unwind.
        stop_child = functools.partial(_stop, child)
        atexit.register(stop_child)
        if not args.no_open:
            threading.Thread(
                target=_open_when_listening, args=(launch.url, launch.port, stop), daemon=True
            ).start()
        status = child.wait()
    except _Stopped as stopped:
        status = 128 + stopped.signum
    finally:
        # A second stop signal must not cut the stop short.
        for number in replaced:
            signal.signal(number, signal.SIG_IGN)
        stop.set()
        if child is not None:
            _stop(child)
        if stop_child is not None:
            atexit.unregister(stop_child)
        _restore_signals(replaced)
    return status
