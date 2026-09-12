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
        declared == "dialogue-scene-execution-graph-v6"
        or declared == "dialogue-scene-execution-graph-v5"
    ):
        from the_grain_pipeline.dialogue_scene.scene_view import build_dialogue_scene_view

        return build_dialogue_scene_view(run_dir)
    if (
        declared == "pointclick-room-execution-graph-v2"
        or declared == "pointclick-room-execution-graph-v1"
    ):
        from the_grain_pipeline.pointclick_room.room_view import build_pointclick_room_view

        return build_pointclick_room_view(run_dir)
    if (
        declared == "sideview-platformer-execution-graph-v2"
        or declared == "sideview-platformer-execution-graph-v1"
    ):
        from bellweather_pipeline.execution_view import build_execution_view
        from bellweather_pipeline.view_annotations import annotate_sideview_platformer_artifact

        return build_execution_view(
            run_dir,
            annotators={"sideview-platformer": annotate_sideview_platformer_artifact},
        )
    if (
        declared == "sideview-runner-execution-graph-v2"
        or declared == "sideview-runner-execution-graph-v1"
    ):
        from iron_petal_unit_pipeline.runner_view import build_sideview_runner_view

        return build_sideview_runner_view(run_dir)
    if declared == "universe-execution-graph-v2" or declared == "universe-execution-graph-v1":
        from stage_gen.recipes.universe.universe_view import build_universe_view

        return build_universe_view(run_dir)
    if declared == "storefront-execution-graph-v2" or declared == "storefront-execution-graph-v1":
        from stage_gen.recipes.storefront.storefront_view import build_storefront_view

        return build_storefront_view(run_dir)
    if (
        declared == "oblique-survival-execution-graph-v2"
        or declared == "oblique-survival-execution-graph-v1"
    ):
        from ember_hollow_pipeline.survival_view import build_oblique_survival_view

        return build_oblique_survival_view(run_dir)
    raise ValueError(
        f"unsupported execution plan kind: {declared!r}; re-export this run with a current "
        "stage-gen"
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
