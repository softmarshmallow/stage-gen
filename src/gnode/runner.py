"""Run one sealed plan: the engine's one runner, whoever calls it.

A run is a directory that holds its plan and one append-only event log. ``run_graph``
takes the run's lock, reads back what earlier invocations recorded, and dispatches the
plan under the scheduler with the run's ceiling, its wall-clock limit and the process's
interrupt signals. Starting the same plan again in the same directory continues that
run: the log grows, the ceiling counts what was already spent, and the node cache
answers what already succeeded. A directory that holds a different plan is refused.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import json
import os
import signal
import threading
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gnode.graph import Graph, NodeHandler
from gnode.schedule import Scheduler
from gnode.trace import JsonlTraceSink, RunSummary, write_run_summary

PLAN_FILE = "execution-plan.json"
LOG_FILE = "execution-trace.jsonl"
SUMMARY_FILE = "execution-summary.json"
LOCK_FILE = "run.lock"

CancelReason = Literal["signal", "wall_timeout"]


class RunLocked(RuntimeError):
    """Another invocation holds this run."""


class RunCanceled(RuntimeError):
    """The run stopped before it finished; its log says which nodes were in flight."""

    def __init__(self, reason: CancelReason) -> None:
        message = {
            "signal": "the run was interrupted",
            "wall_timeout": "the run reached its wall-clock limit",
        }[reason]
        super().__init__(message)
        self.reason = reason


def read_run_events(run_dir: Path) -> list[dict[str, object]]:
    """Every event the run's log holds, oldest first, without the crash-cut tail."""

    path = run_dir / LOG_FILE
    if not path.is_file():
        return []
    events: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            decoded = json.loads(stripped)
        except json.JSONDecodeError:
            break
        if isinstance(decoded, dict):
            events.append(decoded)
    return events


@contextlib.contextmanager
def run_lock(run_dir: Path) -> Iterator[None]:
    """Hold the run's exclusive lock, or refuse at once when someone else does."""

    with (run_dir / LOCK_FILE).open("a+b") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RunLocked(f"another invocation is running {run_dir.name}") from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _cut_crashed_tail(path: Path) -> None:
    """Drop a final line a crash left half-written, so appended events stay readable."""

    if not path.is_file():
        return
    data = path.read_bytes()
    if not data or data.endswith(b"\n"):
        return
    with path.open("r+b") as handle:
        handle.truncate(data.rfind(b"\n") + 1)
        handle.flush()
        os.fsync(handle.fileno())


def _admit_plan(run_dir: Path, graph: Graph, prior: Sequence[Mapping[str, object]]) -> None:
    plan_path = run_dir / PLAN_FILE
    if not plan_path.is_file():
        raise ValueError(f"{run_dir.name} holds no {PLAN_FILE}; write the plan first")
    recorded = json.loads(plan_path.read_text(encoding="utf-8")).get("graph_sha256")
    if recorded != graph.graph_sha256:
        raise ValueError(f"{run_dir.name} holds a different plan")
    if any(event.get("graph_sha256") not in {None, graph.graph_sha256} for event in prior):
        raise ValueError(f"{run_dir.name} records events of a different plan")


async def run_graph(
    graph: Graph,
    handler: NodeHandler,
    *,
    run_dir: Path,
    invocation_id: str,
    targets: Sequence[str] | None = None,
    ceiling_usd: float | None = None,
    node_timeout_seconds: float = 1_800.0,
    wall_timeout_seconds: float | None = None,
    secrets: Sequence[str] = (),
    handle_signals: bool = True,
) -> RunSummary:
    """Dispatch ``graph`` in ``run_dir`` and write its summary.

    ``ceiling_usd`` bounds every invocation of the run together; ``None`` keeps the
    accounts without refusing. ``wall_timeout_seconds`` bounds this invocation. With
    ``handle_signals``, SIGINT and SIGTERM cancel the run cleanly from the main thread.
    A canceled run raises ``RunCanceled`` after every in-flight node has finished its
    cleanup; a caller's own cancellation propagates unchanged.
    """

    if wall_timeout_seconds is not None and wall_timeout_seconds <= 0:
        raise ValueError("a wall-clock limit must be positive")
    with run_lock(run_dir):
        log_path = run_dir / LOG_FILE
        _cut_crashed_tail(log_path)
        prior = read_run_events(run_dir)
        _admit_plan(run_dir, graph, prior)
        scheduler = Scheduler(
            graph.resources, node_timeout_seconds=node_timeout_seconds, secrets=secrets
        )
        sink = JsonlTraceSink(log_path, append=True)
        loop = asyncio.get_running_loop()
        task = asyncio.current_task()
        assert task is not None
        reason: list[CancelReason] = []

        def cancel(why: CancelReason) -> None:
            if not reason:
                reason.append(why)
                task.cancel()

        timer = (
            loop.call_later(wall_timeout_seconds, cancel, "wall_timeout")
            if wall_timeout_seconds is not None
            else None
        )
        installed: list[signal.Signals] = []
        if handle_signals and threading.current_thread() is threading.main_thread():
            for number in (signal.SIGINT, signal.SIGTERM):
                with contextlib.suppress(NotImplementedError, RuntimeError):
                    loop.add_signal_handler(number, cancel, "signal")
                    installed.append(number)
        try:
            summary = await scheduler.run(
                graph,
                handler,
                invocation_id=invocation_id,
                trace_sink=sink,
                target_node_ids=targets,
                ceiling_usd=ceiling_usd,
                prior_events=prior,
                cancel_reason=lambda: reason[0] if reason else None,
            )
        except asyncio.CancelledError:
            if not reason:
                raise
            task.uncancel()
            raise RunCanceled(reason[0]) from None
        finally:
            if timer is not None:
                timer.cancel()
            for number in installed:
                loop.remove_signal_handler(number)
            sink.close()
        write_run_summary(run_dir / SUMMARY_FILE, summary)
        return summary


@dataclass(frozen=True, slots=True)
class ResumeCheck:
    """What an existing run directory says about starting a plan in it."""

    exists: bool
    same_plan: bool


def resume_check(run_dir: Path, graph: Graph) -> ResumeCheck:
    """Whether ``run_dir`` is new, holds this very plan, or holds something else."""

    if not run_dir.exists():
        return ResumeCheck(exists=False, same_plan=False)
    plan_path = run_dir / PLAN_FILE
    if not plan_path.is_file():
        return ResumeCheck(exists=True, same_plan=False)
    try:
        recorded = json.loads(plan_path.read_text(encoding="utf-8")).get("graph_sha256")
    except (OSError, ValueError, AttributeError):
        return ResumeCheck(exists=True, same_plan=False)
    return ResumeCheck(exists=True, same_plan=recorded == graph.graph_sha256)


__all__ = [
    "LOCK_FILE",
    "LOG_FILE",
    "PLAN_FILE",
    "SUMMARY_FILE",
    "ResumeCheck",
    "RunCanceled",
    "RunLocked",
    "read_run_events",
    "resume_check",
    "run_graph",
    "run_lock",
]
