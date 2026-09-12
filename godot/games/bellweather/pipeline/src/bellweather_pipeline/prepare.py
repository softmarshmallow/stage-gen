"""Bellweather owns its variants and world/content preparation checkpoints."""

from collections.abc import Sequence
from pathlib import Path

from bellweather_pipeline.package_executor import PreparedPackageExecutor
from demo_game_tools.preparation import (
    execute_preparation,
    preparation_parser,
    validate_run_options,
)
from gnode import RunSummary
from stage_gen.config import load_config


def main(default_input: Path, argv: Sequence[str] | None = None) -> int:
    parser = preparation_parser("Prepare Bellweather assets")
    parser.add_argument("--variant", choices=("default", "waves"), default="default")
    parser.add_argument("--checkpoint", choices=("world", "content", "integration"))
    parser.add_argument(
        "--assets-output", type=Path, help="manifest/assets destination for integration"
    )
    args = parser.parse_args(argv)
    validate_run_options(parser, args)
    if args.live and args.checkpoint is None:
        parser.error("--live requires --checkpoint world or content")
    if args.checkpoint == "integration" and (args.assets_output is None or args.output is None):
        parser.error("integration requires --output and --assets-output")
    if args.checkpoint == "integration" and (args.live or args.dry_run):
        parser.error("integration restores the cache offline; omit --live and --dry-run")
    input_path = args.input_path or default_input / args.variant
    executor = PreparedPackageExecutor(load_config())

    async def live_run(invocation_id: str) -> RunSummary:
        operation = executor.run_world if args.checkpoint == "world" else executor.run_content
        run = await operation(
            input_path, run_dir=args.output, cache_dir=args.cache_dir, invocation_id=invocation_id
        )
        return run.summary

    if args.checkpoint == "integration":
        import asyncio
        import json
        import uuid

        run = asyncio.run(
            executor.run_integration(
                input_path,
                run_dir=args.output,
                output_dir=args.assets_output,
                cache_dir=args.cache_dir,
                invocation_id=str(uuid.uuid4()),
            )
        )
        print(json.dumps(run.summary.model_dump(mode="json"), indent=2))
        return 0 if run.summary.ok else 1
    return execute_preparation(executor, input_path, args, live_run=live_run)
