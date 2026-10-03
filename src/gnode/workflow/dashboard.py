"""``gnode view``: the run views a dashboard reads, kept fresh while it serves them.

gnode derives what a dashboard shows and ships no dashboard of its own: a plugin installs
one (``Plugin.dashboard``). While it runs, each workflow run under the given roots has its
run view (``execution-view.json``) and its view contexts (``view-contexts.json``) written
into the user cache, under a key made from the run's real path, and written again whenever
the run's plan or record changes. Nothing is ever written into a run.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import TextIO

from gnode.reliability.atomic import atomic_write_json
from gnode.workflow.plugins import load_plugins
from gnode.workflow.run import EVENTS_FILE, PLAN_FILE
from gnode.workflow.runview import project_run, read_plan, view_contexts

VIEW_FILE = "execution-view.json"
VIEW_CONTEXTS_FILE = "view-contexts.json"
VIEW_CONTEXTS_KIND = "gnode-view-contexts-v1"
VIEW_KEY_LENGTH = 16
#: How many folders below a root a run may sit (``out/runs/<workflow>/<run>`` is three).
SEARCH_DEPTH = 4
REFRESH_SECONDS = 3.0


@dataclass(frozen=True, slots=True)
class Dashboard:
    """What ``gnode view`` hands the installed dashboard: the run roots it shows, the cache
    the run views are kept in, and where it listens. The launcher blocks until the dashboard
    ends and returns its exit status."""

    roots: tuple[Path, ...]
    view_cache: Path
    port: int
    open_browser: bool


DashboardLauncher = Callable[[Dashboard], int]


def cache_home(env: Mapping[str, str]) -> Path:
    """``$XDG_CACHE_HOME/gnode`` when that is an absolute path, else ``~/.cache/gnode``."""

    configured = env.get("XDG_CACHE_HOME", "")
    base = Path(configured) if configured and Path(configured).is_absolute() else None
    return (base or Path.home() / ".cache") / "gnode"


def view_key(run_dir: Path) -> str:
    """The cache folder name of a run: its real path, hashed."""

    return sha256(str(run_dir.resolve()).encode()).hexdigest()[:VIEW_KEY_LENGTH]


def _file_names(directory: Path) -> set[str]:
    try:
        with os.scandir(directory) as entries:
            return {entry.name for entry in entries if entry.is_file()}
    except OSError:
        return set()


def is_run(directory: Path) -> bool:
    """A workflow run keeps its plan beside its record, from the moment it starts."""

    names = _file_names(directory)
    return PLAN_FILE in names and EVENTS_FILE in names


def discover(roots: Iterable[Path], *, depth: int = SEARCH_DEPTH) -> list[Path]:
    """Every workflow run under each root, at most ``depth`` folders down, in root then path
    order. A run's own folders are not searched; hidden folders, ``node_modules`` and
    symlinked folders (which could lead outside the root) are skipped."""

    found: list[Path] = []
    for given in roots:
        root = given.resolve()
        runs: list[Path] = []
        pending: list[tuple[Path, int]] = [(root, 0)]
        while pending:
            directory, level = pending.pop()
            if level and is_run(directory):
                runs.append(directory)
                continue
            if level == depth:
                continue
            try:
                with os.scandir(directory) as entries:
                    children = [
                        Path(entry.path)
                        for entry in entries
                        if not entry.name.startswith(".")
                        and entry.name != "node_modules"
                        and entry.is_dir(follow_symlinks=False)
                    ]
            except OSError:
                continue
            pending.extend((child, level + 1) for child in children)
        found.extend(sorted(runs, key=lambda run: run.relative_to(root).as_posix()))
    return found


def write_view(run_dir: Path, out_dir: Path) -> Path:
    """Write the run's view and its view contexts into ``out_dir``; returns the view."""

    atomic_write_json(
        out_dir / VIEW_CONTEXTS_FILE,
        {
            "kind": VIEW_CONTEXTS_KIND,
            "view_origins": list(read_plan(run_dir).get("view_origins", [])),
            "views": view_contexts(run_dir, facts_reader=load_plugins().facts_reader),
        },
    )
    path = out_dir / VIEW_FILE
    atomic_write_json(path, project_run(run_dir).model_dump(mode="json"))
    return path


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def source_mtime(run_dir: Path) -> float | None:
    """When the run's plan or record last changed; None when it has neither."""

    stamps = [_mtime(run_dir / name) for name in (PLAN_FILE, EVENTS_FILE)]
    present = [stamp for stamp in stamps if stamp is not None]
    return max(present) if present else None


@dataclass(slots=True)
class ViewRefresher:
    """Writes the views of runs whose plan or record changed, once per change.

    A run whose view cannot be written is tried again only after it changes, and the reason
    is kept in ``failures``.
    """

    roots: tuple[Path, ...]
    cache_dir: Path
    attempted: dict[Path, float] = field(default_factory=dict)
    failures: dict[Path, str] = field(default_factory=dict)

    def refresh(self) -> list[Path]:
        written: list[Path] = []
        for run_dir in discover(self.roots):
            source = source_mtime(run_dir)
            if source is None or self.attempted.get(run_dir) == source:
                continue
            out_dir = self.cache_dir / view_key(run_dir)
            view = _mtime(out_dir / VIEW_FILE)
            self.attempted[run_dir] = source
            if view is not None and view >= source:
                continue
            try:
                written.append(write_view(run_dir, out_dir))
            except Exception as error:  # a broken run must not stop the others
                self.failures[run_dir] = f"{type(error).__name__}: {error}"
                continue
            self.failures.pop(run_dir, None)
        return written


def keep_fresh(refresher: ViewRefresher, stop: threading.Event, errors: TextIO) -> None:
    """Refresh until ``stop`` is set, reporting each run whose view could not be written once."""

    reported: set[Path] = set()
    while True:
        try:
            refresher.refresh()
        except OSError as error:
            errors.write(f"gnode view: could not refresh the run views: {error}\n")
        for run_dir, failure in refresher.failures.items():
            if run_dir not in reported:
                reported.add(run_dir)
                errors.write(f"gnode view: no view for {run_dir}: {failure}\n")
        if stop.wait(REFRESH_SECONDS):
            return


__all__ = [
    "SEARCH_DEPTH",
    "VIEW_CONTEXTS_FILE",
    "VIEW_FILE",
    "Dashboard",
    "DashboardLauncher",
    "ViewRefresher",
    "cache_home",
    "discover",
    "is_run",
    "keep_fresh",
    "source_mtime",
    "view_key",
    "write_view",
]
