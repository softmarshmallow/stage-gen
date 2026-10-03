"""Private collection adapter for views."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TextIO

from gnode import RunView, write_run_view


def _build_run_view_for(run_dir: Path) -> RunView:
    """Pick the view document by the kind the run's own plan declares.

    Each recipe declares its own accepted graph kinds. Read that declaration before
    importing a builder so the selected adapter owns validation and unsupported
    kinds receive a clear refusal.
    """

    plan_path = run_dir / "execution-plan.json"
    if not plan_path.is_file():
        raise ValueError(f"run directory has no execution-plan.json: {run_dir.name}")
    declared = json.loads(plan_path.read_text(encoding="utf-8")).get("kind")
    if (
        declared == "oblique-survival-execution-graph-v2"
        or declared == "oblique-survival-execution-graph-v1"
    ):
        from ember_hollow_pipeline.survival_view import build_oblique_survival_view

        return build_oblique_survival_view(run_dir)
    raise ValueError(
        f"unsupported execution plan kind: {declared!r}; a product workflow writes its run "
        "view with `stage-gen inspect RUN_DIR --write-view DIR`, and an older game run is "
        "re-exported with a current stage-gen"
    )


def dispatch(args: argparse.Namespace, *, stdout: TextIO) -> int:
    run_dir = Path(args.run_dir)
    view = _build_run_view_for(run_dir)
    view_path = Path(args.output_path) if args.output_path else run_dir / "execution-view.json"
    write_run_view(view_path, view)
    view_report = {
        "gaps": len(view.gaps),
        "nodes": len(view.nodes),
        "run_state": view.run_state,
        "output": str(view_path),
        "states": view.state_counts,
    }
    stdout.write(f"{json.dumps(view_report, sort_keys=True, separators=(',', ':'))}\n")
    return 0
