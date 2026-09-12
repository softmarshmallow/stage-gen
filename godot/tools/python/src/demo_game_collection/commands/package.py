"""Private collection adapter for package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TextIO

from bellweather_pipeline.package_graph import (
    CONTENT_CACHE_NAMESPACE,
    WORLD_CACHE_NAMESPACE,
)
from demo_game_collection.executors import PreparedPackageExecutor, SideviewRunnerExecutor
from demo_game_collection.game_package import resolve_prepared_package
from demo_game_tools.application import resolve_genre
from iron_petal_unit_pipeline.runner_graph import RUNNER_CACHE_NAMESPACE
from stage_gen.application import (
    UsageError as CliUsageError,
)
from stage_gen.config import (
    load_config,
)
from stage_gen.recipes.cache_report import cache_report


def dispatch(args: argparse.Namespace, *, stdout: TextIO) -> int:
    resolved_package = resolve_prepared_package(Path(args.input_path))
    if args.package_command == "digest":
        stdout.write(f"{resolved_package.closure_sha256}\n")
    elif args.package_command == "plan":
        declared_genres = [entry.genre for entry in resolved_package.game.genres]
        genre = resolve_genre(declared_genres, getattr(args, "genre", None))
        # The genre dispatch point: each genre member plans through its own
        # recipe executor.
        if genre == "runner":
            runner_plan = SideviewRunnerExecutor(load_config()).plan(Path(args.input_path))
            plan_report = {
                "genre": genre,
                "graph": runner_plan.graph.model_dump(mode="json"),
                "projection": runner_plan.projection.model_dump(mode="json"),
            }
            if args.cache_dir:
                plan_report["cache"] = cache_report(
                    runner_plan.graph, Path(args.cache_dir), (RUNNER_CACHE_NAMESPACE,)
                )
            stdout.write(f"{json.dumps(plan_report, sort_keys=True, separators=(',', ':'))}\n")
            return 0
        if genre != "platformer":
            raise CliUsageError(f"no recipe is registered for genre {genre!r}")
        plan = PreparedPackageExecutor(load_config()).plan(Path(args.input_path))
        plan_report = {
            "genre": genre,
            "graph": plan.graph.model_dump(mode="json"),
            "projection": plan.projection.model_dump(mode="json"),
        }
        if args.cache_dir:
            plan_report["cache"] = cache_report(
                plan.graph,
                Path(args.cache_dir),
                (WORLD_CACHE_NAMESPACE, CONTENT_CACHE_NAMESPACE),
            )
        stdout.write(f"{json.dumps(plan_report, sort_keys=True, separators=(',', ':'))}\n")
    else:
        package_report = {"valid": True, **resolved_package.identity()}
        stdout.write(f"{json.dumps(package_report, sort_keys=True, separators=(',', ':'))}\n")
    return 0
