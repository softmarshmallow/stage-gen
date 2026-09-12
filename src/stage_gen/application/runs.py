"""One run report, the usage error, and the resolutions every run command makes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, TextIO

from gnode import Graph, RunSummary
from stage_gen.config import StageGenConfig


class UsageError(ValueError):
    """A command was asked for something its flags cannot mean.

    Distinct from an internal failure so the process can say so with exit status 2,
    the way argparse does for a malformed command line.
    """


def resolve_output_path(raw: str) -> Path:
    """A run directory the user named, resolved through symlinks.

    The node cache refuses a symlink anywhere above a root it writes under, and on
    macOS every temporary directory sits under one (``/var`` -> ``/private/var``). The
    layout above the root the user chose is the operating system's; the rule guards
    what lies beneath it.
    """

    return Path(raw).resolve()


def resolve_cache_dir(explicit: str | None, config: StageGenConfig) -> Path:
    """The execution cache root: the flag, else the configured repo-anchored directory."""

    return (Path(explicit) if explicit else config.cache_dir).resolve()


class GraphPlan(Protocol):
    @property
    def graph(self) -> Graph: ...


class ReportableRun(Protocol):
    @property
    def plan(self) -> GraphPlan: ...

    @property
    def summary(self) -> RunSummary: ...


def run_report(
    run: ReportableRun,
    *,
    run_dir: Path,
    **fields: object,
) -> dict[str, object]:
    """The shape every run command reports, with the command's own fields on top.

    Every run says whether it succeeded, where it ran, which plan it executed and what
    it spent. A command adds what only it knows - its recipe, a checkpoint, an
    identity from the resolved input - and may override a base key when its meaning
    differs (a checkpoint reports the nodes it executed, not the plan's count).
    """

    graph = run.plan.graph
    return {
        "ok": run.summary.ok,
        "run_dir": str(run_dir),
        "graph_sha256": graph.graph_sha256,
        "topology_sha256": graph.topology_sha256,
        "node_count": len(graph.nodes),
        "provider_operation_counts": run.summary.provider_operation_counts,
        "duration_ms": run.summary.duration_ms,
        **fields,
    }


def write_report(stdout: TextIO, report: dict[str, object]) -> int:
    """Print one JSON report line; the exit status is the report's own verdict."""

    stdout.write(f"{json.dumps(report, sort_keys=True, separators=(',', ':'))}\n")
    return 0 if report.get("ok") else 1


__all__ = [
    "UsageError",
    "resolve_cache_dir",
    "resolve_output_path",
    "run_report",
    "write_report",
]
