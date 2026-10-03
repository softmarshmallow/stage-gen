"""Run folders: where they are, who owns them, and the views a reader renders them from.

A run is a folder an executor wrote. ``discover`` finds runs under any number of roots by
the documents they publish, without importing a workflow. The workflow that owns a run
writes its run view on request: SDK and graph-document runs join their own plan and trace,
a gnode workflow run its plan and events, and a game run is never derived here, because its
game exports its own view. ``derive_view`` writes into a user cache keyed by the run's real
path, never into the run; ``stage-gen view`` keeps those views fresh while runs are live, and
``stage-gen inspect RUN --write-view DIR`` writes one where it is asked to.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

#: A folder holding one of these is a run.
RUN_DOCUMENTS = (
    "execution-plan.json",
    "execution-view.json",
    "manifest.json",
    "bundle.json",
    "case.json",
)
#: A folder holding the first of a pair and any one of its partners is a run: a gnode
#: workflow run keeps ``plan.json`` beside its ``events.jsonl``, so a run is listed while it
#: runs.
RUN_DOCUMENT_PAIRS: tuple[tuple[str, tuple[str, ...]], ...] = (("plan.json", ("events.jsonl",)),)
#: The example store sits at the top of a run root (``out/examples``); it holds exports, not
#: runs.
EXAMPLE_STORE = "examples"
#: How many folders below a root a run may sit: a review run can sit four deep
#: (``review/<set>/<character>/run-01``).
SEARCH_DEPTH = 4
VIEW_FILE = "execution-view.json"
#: The files whose change can make a run's view stale: plans, traces and the run's own
#: records.
SOURCE_FILES = (
    "execution-plan.json",
    "execution-trace.jsonl",
    "plan.json",
    "events.jsonl",
)
VIEW_KEY_LENGTH = 16


# ---------------------------------------------------------------- discovery


@dataclass(frozen=True, slots=True)
class FoundRun:
    root: Path
    run_dir: Path

    @property
    def relative(self) -> str:
        return self.run_dir.relative_to(self.root).as_posix()


def _file_names(directory: Path) -> set[str]:
    try:
        with os.scandir(directory) as entries:
            return {entry.name for entry in entries if entry.is_file()}
    except OSError:
        return set()


def is_run(directory: Path) -> bool:
    names = _file_names(directory)
    return any(name in names for name in RUN_DOCUMENTS) or any(
        first in names and any(partner in names for partner in partners)
        for first, partners in RUN_DOCUMENT_PAIRS
    )


def discover(roots: Iterable[Path], *, depth: int = SEARCH_DEPTH) -> list[FoundRun]:
    """Every run under each root, at most ``depth`` folders down, in root then path order.

    A run's own folders are not searched again, so a sub-run is part of its run. Hidden
    folders, ``node_modules``, the example store at the top of a root and symlinked folders
    (which could lead outside the root) are skipped.
    """
    found: list[FoundRun] = []
    for given in roots:
        root = given.resolve()
        if not root.is_dir():
            continue
        runs: list[FoundRun] = []
        pending: list[tuple[Path, int]] = [(root, 0)]
        while pending:
            directory, level = pending.pop()
            if level and is_run(directory):
                runs.append(FoundRun(root, directory))
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
                        and not (level == 0 and entry.name == EXAMPLE_STORE)
                        and entry.is_dir(follow_symlinks=False)
                    ]
            except OSError:
                continue
            pending.extend((child, level + 1) for child in children)
        found.extend(sorted(runs, key=lambda run: run.relative))
    return found


# ---------------------------------------------------------------- freshness


def view_key(run_dir: Path) -> str:
    """The cache folder name of a run: its real path, hashed."""
    return sha256(str(run_dir.resolve()).encode()).hexdigest()[:VIEW_KEY_LENGTH]


def cached_view(run_dir: Path, cache_dir: Path) -> Path:
    return cache_dir / view_key(run_dir) / VIEW_FILE


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def source_mtime(run_dir: Path) -> float | None:
    """When the run's plan, trace or own records last changed; None when it has none."""
    stamps = [_mtime(run_dir / name) for name in SOURCE_FILES]
    present = [stamp for stamp in stamps if stamp is not None]
    return max(present) if present else None


def needs_view(run_dir: Path, cache_dir: Path) -> bool:
    """True when neither the run's own view nor its cached one is as new as its sources."""
    source = source_mtime(run_dir)
    if source is None:
        return False
    for view in (run_dir / VIEW_FILE, cached_view(run_dir, cache_dir)):
        written = _mtime(view)
        if written is not None and written >= source:
            return False
    return True


# ---------------------------------------------------------------- owners


@dataclass(frozen=True, slots=True)
class RunOwner:
    """The workflow that owns a run, or None for a run the SDK wrote, and its readers."""

    workflow: str | None
    inspect: Callable[[Path, bool], dict[str, object]]
    write_view: Callable[[Path, Path], Path | None]


def _document_kind(path: Path) -> str | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    kind = document.get("kind") if isinstance(document, dict) else None
    return kind if isinstance(kind, str) else None


def owner_of(run_dir: Path) -> RunOwner:
    """Each installed workflow is asked in turn; a run none owns is read as an SDK run, whose
    plan and trace the SDK joins (``stage-gen inspect`` has always read it so)."""
    from stage_gen.pipeline import inspect as inspect_sdk_run
    from stage_gen.workflows._registry import ViewRuns, discover, load_code

    for found in discover():
        code = load_code(found.id)
        if code.owns_run(run_dir):
            return RunOwner(found.id, code.inspect, code.write_view)
    runs = ViewRuns(kinds=frozenset(), build_view=inspect_sdk_run)
    return RunOwner(None, runs.inspect, runs.write_view)


def is_sdk_run(run_dir: Path) -> bool:
    """Whether the run's plan is the SDK's graph document."""
    from stage_gen.pipeline import PipelineGraph

    sdk_kind: str = PipelineGraph.model_fields["kind"].default
    return _document_kind(run_dir / "execution-plan.json") == sdk_kind


def write_view(run_dir: Path, out_dir: Path) -> Path | None:
    """Ask the run's owner to write its ``execution-view.json`` into ``out_dir``. None when
    no owner can derive one: a run no workflow owns is derived only when the SDK wrote it,
    so a game run or a run an older build wrote is never guessed at."""
    owner = owner_of(run_dir)
    if owner.workflow is None and not is_sdk_run(run_dir):
        return None
    return owner.write_view(run_dir, out_dir)


def derive_view(run_dir: Path, cache_dir: Path) -> Path | None:
    """Write the run's view into ``cache_dir/<view key>/``, never into the run."""
    return write_view(run_dir, cache_dir / view_key(run_dir))


# ---------------------------------------------------------------- refreshing


@dataclass(slots=True)
class ViewRefresher:
    """Derives the views of stale runs into a cache, once per change of their sources.

    A run whose owner cannot derive a view (a game run, a run with no trace yet) is tried
    again only after its sources change.
    """

    roots: tuple[Path, ...]
    cache_dir: Path
    attempted: dict[Path, float] = field(default_factory=dict)
    failures: dict[Path, str] = field(default_factory=dict)

    def refresh(self) -> list[Path]:
        derived: list[Path] = []
        for found in discover(self.roots):
            run_dir = found.run_dir
            source = source_mtime(run_dir)
            if source is None or self.attempted.get(run_dir) == source:
                continue
            if not needs_view(run_dir, self.cache_dir):
                continue
            self.attempted[run_dir] = source
            try:
                written = derive_view(run_dir, self.cache_dir)
            except Exception as error:  # a broken run must not stop the others
                self.failures[run_dir] = f"{type(error).__name__}: {error}"
                continue
            self.failures.pop(run_dir, None)
            if written is not None:
                derived.append(written)
        return derived


__all__ = [
    "EXAMPLE_STORE",
    "RUN_DOCUMENTS",
    "RUN_DOCUMENT_PAIRS",
    "SEARCH_DEPTH",
    "SOURCE_FILES",
    "VIEW_FILE",
    "FoundRun",
    "RunOwner",
    "ViewRefresher",
    "cached_view",
    "derive_view",
    "discover",
    "is_run",
    "is_sdk_run",
    "needs_view",
    "owner_of",
    "source_mtime",
    "view_key",
    "write_view",
]
