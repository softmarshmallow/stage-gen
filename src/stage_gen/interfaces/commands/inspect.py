"""``stage-gen inspect RUN``: read one run folder without services.

The workflow that owns the run reads it: each workflow's ``CODE.owns_run`` is asked in
turn. A run no workflow owns is read as an SDK run, whose plan and trace gnode joins into a
run view. ``--verify`` recomputes what the run recorded; ``--write-view DIR`` writes the
derived ``execution-view.json`` into ``DIR``, which is a run folder only when it names one.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO


def register(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--verify", action="store_true", help="recompute every recorded artifact and stage"
    )
    parser.add_argument(
        "--write-view",
        type=Path,
        metavar="DIR",
        help="write the derived execution-view.json into DIR",
    )
    parser.add_argument("--json", action="store_true", help="print the whole record as JSON")
    parser.set_defaults(handler=run)


@dataclass(frozen=True, slots=True)
class RunOwner:
    """The workflow that owns a run, or None for an SDK run, and its readers for it."""

    workflow: str | None
    inspect: Callable[[Path, bool], dict[str, object]]
    write_view: Callable[[Path, Path], Path | None]


def owner_of(run_dir: Path) -> RunOwner:
    from stage_gen import pipeline
    from stage_gen.workflows._registry import ViewRuns, discover, load_code

    for found in discover():
        code = load_code(found.id)
        if code.owns_run(run_dir):
            return RunOwner(found.id, code.inspect, code.write_view)
    runs = ViewRuns(kinds=frozenset(), build_view=pipeline.inspect)
    return RunOwner(None, runs.inspect, runs.write_view)


def run(args: argparse.Namespace, stdout: TextIO) -> int:
    owner = owner_of(args.run_dir)
    record: dict[str, Any] = {"workflow": owner.workflow, "run_dir": str(args.run_dir)}
    if args.write_view is not None:
        written = owner.write_view(args.run_dir, args.write_view)
        if written is None:
            raise ValueError(
                f"{owner.workflow} runs persist no run view to write; "
                "inspect reads their own records"
            )
        record["written_view"] = str(written)
    record.update(owner.inspect(args.run_dir, args.verify))
    stdout.write(json.dumps(record, indent=2) + "\n" if args.json else _summary(record))
    return 1 if args.verify and not _verified(record.get("verification")) else 0


def _verified(verification: object) -> bool:
    if not isinstance(verification, dict):
        return False
    return verification.get("verified") is not False and verification.get("status") != "failed"


def _state(record: dict[str, Any]) -> str | None:
    for key in ("view", "execution", "summary", "outcome"):
        document = record.get(key)
        if isinstance(document, dict):
            for field in ("run_state", "status", "state"):
                if isinstance(document.get(field), str):
                    return str(document[field])
    return None


def _summary(record: dict[str, Any]) -> str:
    rows = [
        ("run", record["run_dir"]),
        ("workflow", record["workflow"] or "none (an SDK run)"),
        ("state", _state(record) or "not recorded"),
    ]
    view = record.get("view")
    if isinstance(view, dict):
        counts = ", ".join(f"{state} {n}" for state, n in sorted(view["state_counts"].items()))
        rows.append(("nodes", f"{len(view['nodes'])} ({counts})"))
    if "verification" in record:
        verification = record["verification"]
        problems = verification.get("problems", []) if isinstance(verification, dict) else []
        rows.append(
            (
                "verified",
                "yes" if _verified(verification) else f"no: {len(problems)} problem(s)",
            )
        )
    if "written_view" in record:
        rows.append(("view", record["written_view"]))
    width = max(len(label) for label, _ in rows)
    return "".join(f"{label:<{width}}  {value}\n" for label, value in rows)
