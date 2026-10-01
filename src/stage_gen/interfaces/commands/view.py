"""``stage-gen view``: open the viewer, the local read-only client, over run folders.

The viewer is the Next app in ``web/viewer``, so this command needs a source checkout and
Bun; from an installed wheel it refuses. It exports the catalog into the user cache, keeps
derived run views fresh in that cache while it runs, and starts the viewer's dev server
with the run roots, the catalog and the view cache in its environment. Nothing it starts
can start a run: the viewer only reads.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import tomllib
import webbrowser
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

REFUSAL = "stage-gen view needs a source checkout and Bun; see docs/viewer.md"
VIEWER = Path("web/viewer")
DEFAULT_PORT = 3000
REFRESH_SECONDS = 3.0
HOST = "127.0.0.1"


def register(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--runs",
        action="append",
        default=[],
        type=Path,
        metavar="DIR",
        help="a folder of runs to show; repeat it for several (default: out/ of the checkout)",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
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


def _stop(child: subprocess.Popen[bytes]) -> None:
    """End the dev server and everything it started: it leads its own process group."""
    for sent in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(child.pid, sent)
        except ProcessLookupError:
            return
        try:
            child.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            continue


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
    child = subprocess.Popen(
        launch.command, cwd=launch.checkout, env=launch.env, start_new_session=True
    )
    if not args.no_open:
        threading.Thread(
            target=_open_when_listening, args=(launch.url, launch.port, stop), daemon=True
        ).start()
    try:
        return child.wait()
    finally:
        stop.set()
        _stop(child)
