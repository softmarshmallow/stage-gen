"""The viewer, the dashboard ``gnode view`` starts: a local read-only client over run folders.

Stage Gen installs it as a gnode plugin of its own (``viewer`` in ``gnode.plugins``), apart
from the one that composes its routes and providers, because it reads the workflow catalog.

The viewer is the Next app in ``web/viewer``, so it needs a source checkout and Bun; from an
installed wheel it refuses. gnode keeps the run views fresh in its cache; this exports the
catalog the viewer groups runs by into the user cache and starts the viewer's dev server
with the run roots, the catalog and the view cache in its environment, provider keys left
out. Nothing it starts can start a run: the viewer only reads. However it ends, by the
server exiting, Ctrl-C, SIGTERM or a hangup, it first ends the server and every process the
server started.
"""

from __future__ import annotations

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
from typing import Any

from gnode import Dashboard, Plugin

REFUSAL = "the viewer needs a source checkout of Stage Gen and Bun; see docs/viewer.md"
VIEWER = Path("web/viewer")
HOST = "127.0.0.1"
# The signals that end the launcher; each one ends the viewer first.
STOP_SIGNALS = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)
# How long the viewer's process group has to leave after SIGTERM before it gets SIGKILL.
STOP_GRACE_SECONDS = 10.0

SignalHandler = Callable[[int, FrameType | None], Any] | int | signal.Handlers | None


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


def prepare(request: Dashboard, env: Mapping[str, str]) -> Launch:
    """Everything the viewer starts with, checked before anything is written or started."""
    import stage_gen
    from stage_gen.provider_env import PROVIDER_ENV_KEYS

    checkout = find_checkout((Path(stage_gen.__file__).resolve().parent, Path.cwd().resolve()))
    bun = shutil.which("bun", path=env.get("PATH"))
    if checkout is None or bun is None:
        raise ValueError(REFUSAL)
    catalog = cache_home(env) / "catalog" / "catalog.json"
    child_env = {name: value for name, value in env.items() if name not in PROVIDER_ENV_KEYS}
    child_env.update(
        {
            "STAGE_GEN_RUN_ROOTS": os.pathsep.join(str(root) for root in request.roots),
            "STAGE_GEN_CATALOG": str(catalog),
            "STAGE_GEN_VIEW_CACHE": str(request.view_cache),
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
        str(request.port),
        "--hostname",
        HOST,
    )
    return Launch(
        checkout, request.roots, catalog, request.view_cache, request.port, command, child_env
    )


def export_catalog(path: Path) -> list[str]:
    """Write the catalog the viewer groups runs by and draws plans from; the drift problems
    a full export would refuse on are returned, not raised, since the viewer only reads."""
    from gnode import atomic_write_bytes
    from stage_gen.workflows._catalog import build

    catalog, problems = build(examples_dir=None, allow_missing_examples=True)
    payload = json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"
    atomic_write_bytes(path, payload.encode(), mode=0o644)
    return problems


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


def launch(request: Dashboard) -> int:
    """Serve the viewer over ``request.roots`` until it ends; its exit status."""
    launched = prepare(request, os.environ)
    problems = export_catalog(launched.catalog)
    roots = ", ".join(str(root) for root in launched.roots)
    sys.stdout.write(f"gnode view: {launched.url} over {roots}\n")
    if problems:
        sys.stdout.write(f"gnode view: the catalog has {len(problems)} drift problem(s)\n")
    sys.stdout.flush()
    stop = threading.Event()
    replaced = _trap_stop_signals()
    child: subprocess.Popen[bytes] | None = None
    stop_child: Callable[[], None] | None = None
    status = 0
    try:
        child = subprocess.Popen(
            launched.command, cwd=launched.checkout, env=launched.env, start_new_session=True
        )
        # Also stopped at interpreter exit, should this frame never unwind.
        stop_child = functools.partial(_stop, child)
        atexit.register(stop_child)
        if request.open_browser:
            threading.Thread(
                target=_open_when_listening, args=(launched.url, launched.port, stop), daemon=True
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


def plugin() -> Plugin:
    """The ``gnode.plugins`` entry point: the viewer is the dashboard ``gnode view`` starts."""
    return Plugin(name="viewer", dashboard=launch)


__all__ = ["REFUSAL", "Launch", "export_catalog", "find_checkout", "launch", "plugin", "prepare"]
