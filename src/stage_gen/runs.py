"""Run folders: where they are, who owns them, and the views a reader renders them from.

A run is a folder an executor wrote. ``discover`` finds runs under any number of roots by
the documents they publish, without importing a workflow. The workflow that owns a run
writes its run view on request: SDK and graph-document runs join their own plan and trace,
a character run and a joinable portrait run are joined from the plan and trace they keep
under their own names, and a game run is never derived here, because its game exports its
own view. ``derive_view`` writes into a user cache keyed by the run's real path, never into
the run; ``stage-gen view`` keeps those views fresh while runs are live, and
``stage-gen inspect RUN --write-view DIR`` writes one where it is asked to.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

from gnode import UNREGISTERED_TYPE_GAP_ID, Graph, NodeType, RunView, build_run_view

#: A folder holding one of these is a run.
RUN_DOCUMENTS = (
    "execution-plan.json",
    "execution-view.json",
    "manifest.json",
    "bundle.json",
    "case.json",
)
#: A folder holding the first of a pair and any one of its partners is a run: a character
#: run keeps ``graph.json`` beside its trace and summary, a portrait run ``plan.json``
#: beside ``graph.json`` from the moment it is prepared and ``execution.json`` once it ends,
#: and a gnode workflow run ``plan.json`` beside its ``events.jsonl``, so a run is listed
#: (without a view until it has a trace) while it runs.
RUN_DOCUMENT_PAIRS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("graph.json", ("summary.json", "trace.jsonl")),
    ("plan.json", ("execution.json", "graph.json", "events.jsonl")),
)
#: The example store sits at the top of a run root (``out/examples``); it holds exports, not
#: runs.
EXAMPLE_STORE = "examples"
#: How many folders below a root a run may sit: a portrait review run sits four deep
#: (``review/<set>/<character>/run-01``).
SEARCH_DEPTH = 4
VIEW_FILE = "execution-view.json"
#: The files whose change can make a run's view stale: plans, traces and the run's own
#: records. The run's own ``trace/*.jsonl`` counts too, as does a sub-run's
#: (``<child>/trace/*.jsonl``).
SOURCE_FILES = (
    "execution-plan.json",
    "execution-trace.jsonl",
    "graph.json",
    "trace.jsonl",
    "summary.json",
    "plan.json",
    "execution.json",
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
    stamps += [
        _mtime(trace)
        for trace in (*run_dir.glob("trace/*.jsonl"), *run_dir.glob("*/trace/*.jsonl"))
    ]
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


# ---------------------------------------------------------------- joined views


class JoinedGraph(Graph):
    """Any gnode graph document, read for its view; the view keeps the graph's own kind."""

    def view_header(self) -> dict[str, object]:
        return {"graph_kind": self.kind}


class JoinedRunView(RunView):
    graph_kind: str


def _present(run_dir: Path, artifact_ref: str) -> bool:
    if artifact_ref.startswith(("/", "\\")) or ".." in artifact_ref.split("/"):
        return False
    candidate = (run_dir / artifact_ref).resolve()
    return candidate.is_relative_to(run_dir.resolve()) and candidate.is_file()


def join_run_view(
    run_dir: Path,
    *,
    plan: Path,
    traces: Sequence[Path],
    types: Mapping[str, NodeType] | None = None,
    labels: Mapping[str, str] | None = None,
) -> JoinedRunView:
    """The run view of a run that keeps a gnode plan and trace under names of its own.

    ``plan`` is a gnode graph document inside ``run_dir`` (perhaps in a sub-run), and
    ``traces`` its append-only traces in the order they were written. They are staged in a
    temporary folder under gnode's names and joined there, so nothing is written into the
    run. Artifact references are made relative to ``run_dir`` and their presence checked
    there, so the view reads like any other run's. ``labels`` titles node types the
    registry cannot build; a label wins over a registry title, as in the catalog.
    """
    base = plan.parent.resolve()
    prefix = base.relative_to(run_dir.resolve()).as_posix()

    def relocated(ref: str) -> str:
        return ref if prefix == "." else f"{prefix}/{ref}"

    with tempfile.TemporaryDirectory(prefix="stage-gen-view-") as scratch:
        staged = Path(scratch)
        (staged / "execution-plan.json").symlink_to(plan.resolve())
        if len(traces) == 1:
            (staged / "execution-trace.jsonl").symlink_to(traces[0].resolve())
        elif traces:
            with (staged / "execution-trace.jsonl").open("wb") as joined:
                for trace in traces:
                    joined.write(trace.read_bytes().rstrip(b"\n") + b"\n")
        view = build_run_view(staged, graph_type=JoinedGraph, view_type=JoinedRunView, types=types)
    titles = labels or {}
    nodes = tuple(
        node.model_copy(
            update={
                "title": titles.get(node.type_id, node.title),
                "ports": tuple(
                    port.model_copy(
                        update={
                            "artifact_ref": relocated(port.artifact_ref),
                            "sidecar_ref": None
                            if port.sidecar_ref is None
                            else relocated(port.sidecar_ref),
                        }
                    )
                    for port in node.ports
                ),
                "artifacts": tuple(
                    artifact.model_copy(
                        update={
                            "artifact_ref": relocated(artifact.artifact_ref),
                            "present": _present(run_dir, relocated(artifact.artifact_ref)),
                        }
                    )
                    for artifact in node.artifacts
                ),
            }
        )
        for node in view.nodes
    )
    titled = all(node.title for node in nodes)
    stamps = [stamp for stamp in (_mtime(trace) for trace in traces) if stamp is not None]
    return view.model_copy(
        update={
            "nodes": nodes,
            "gaps": tuple(
                gap for gap in view.gaps if not (titled and gap.gap_id == UNREGISTERED_TYPE_GAP_ID)
            ),
            "trace_modified_at": _utc(max(stamps)) if stamps else None,
        }
    )


def _utc(stamp: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stamp))


# ---------------------------------------------------------------- refreshing


@dataclass(slots=True)
class ViewRefresher:
    """Derives the views of stale runs into a cache, once per change of their sources.

    A run whose owner cannot derive a view (a game run, a portrait run whose trace cannot
    be joined) is tried again only after its sources change.
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
    "JoinedGraph",
    "JoinedRunView",
    "RunOwner",
    "ViewRefresher",
    "cached_view",
    "derive_view",
    "discover",
    "is_run",
    "is_sdk_run",
    "join_run_view",
    "needs_view",
    "owner_of",
    "source_mtime",
    "view_key",
    "write_view",
]
