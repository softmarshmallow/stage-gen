"""Console mechanics shared by game-owned preparation entry points.

Games supply their own executor and live operation. This module has no game roster,
input selection or gameplay configuration.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from gnode import Graph, RunSummary
from stage_gen.recipes.executor import Identified, RecipeExecutor


def preparation_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--input", type=Path, dest="input_path", help="override this game's local inputs"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="inspect the plan offline (default)")
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="exercise the graph with deterministic fake operations",
    )
    mode.add_argument(
        "--live", action="store_true", help="generate through configured paid providers"
    )
    parser.add_argument("--output", type=Path, help="new execution directory; required for a run")
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/stage-gen"))
    return parser


def validate_run_options(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if (args.live or args.dry_run) and args.output is None:
        parser.error("--output is required for --dry-run or --live")


def execute_preparation[R: Identified, G: Graph](
    executor: RecipeExecutor[R, G],
    input_path: Path,
    args: argparse.Namespace,
    *,
    live_run: Callable[[str], Awaitable[RunSummary]] | None = None,
) -> int:
    if not args.dry_run and not args.live:
        plan = executor.plan(input_path)
        print(
            json.dumps(
                {
                    "identity": dict(plan.resolved.identity()),
                    "graph": plan.graph.model_dump(mode="json"),
                    "projection": plan.projection.model_dump(mode="json"),
                },
                indent=2,
            )
        )
        return 0
    invocation_id = str(uuid.uuid4())
    if args.live:
        if live_run is None:
            raise ValueError("this preparation entry point has no live operation")

        async def invoke_live() -> RunSummary:
            assert live_run is not None
            return await live_run(invocation_id)

        summary = asyncio.run(invoke_live())
    else:
        run = asyncio.run(
            executor.dry_run(
                input_path,
                run_dir=args.output,
                cache_dir=args.cache_dir,
                invocation_id=invocation_id,
            )
        )
        summary = run.summary
    print(json.dumps(summary.model_dump(mode="json"), indent=2))
    return 0 if summary.ok else 1
