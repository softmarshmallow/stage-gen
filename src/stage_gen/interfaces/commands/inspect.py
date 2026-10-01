"""``stage-gen inspect RUN``: read one run folder without services.

The workflow that owns the run reads it: each workflow's ``CODE.owns_run`` is asked in
turn (``stage_gen.runs.owner_of``). A run no workflow owns is read as an SDK run, whose
plan and trace gnode joins into a run view; any other folder, such as a game run, is
refused. ``--verify`` recomputes what the run recorded; ``--write-view DIR`` writes the
derived ``execution-view.json`` into ``DIR``, which is a run folder only when it names one.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, TextIO


def register(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("run_dir", type=Path, help="the run folder to read")
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


def run(args: argparse.Namespace, stdout: TextIO) -> int:
    from stage_gen.runs import is_sdk_run, owner_of, write_view

    owner = owner_of(args.run_dir)
    if owner.workflow is None and not is_sdk_run(args.run_dir):
        raise ValueError(
            f"{args.run_dir} is not a workflow or SDK run; "
            "a game run is read by its game (demo-games export-view)"
        )
    record: dict[str, Any] = {"workflow": owner.workflow, "run_dir": str(args.run_dir)}
    if args.write_view is not None:
        written = write_view(args.run_dir, args.write_view)
        if written is None:
            raise ValueError(
                f"{args.run_dir} has no view to write yet; inspect reads its own records"
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
