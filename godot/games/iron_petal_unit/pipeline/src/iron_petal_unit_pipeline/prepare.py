"""Explicit asset preparation for Iron Petal Unit."""

from collections.abc import Sequence
from pathlib import Path

from demo_game_tools.preparation import (
    execute_preparation,
    preparation_parser,
    validate_run_options,
)
from gnode import RunSummary
from iron_petal_unit_pipeline.runner_executor import SideviewRunnerExecutor
from stage_gen.config import load_config


def main(default_input: Path, argv: Sequence[str] | None = None) -> int:
    parser = preparation_parser("Prepare Iron Petal Unit assets")
    args = parser.parse_args(argv)
    validate_run_options(parser, args)
    input_path = args.input_path or default_input
    executor = SideviewRunnerExecutor(load_config())

    async def live_run(invocation_id: str) -> RunSummary:
        run = await executor.run(
            input_path, run_dir=args.output, cache_dir=args.cache_dir, invocation_id=invocation_id
        )
        return run.summary

    return execute_preparation(executor, input_path, args, live_run=live_run)
