"""``stage-gen plan|run storefront``: every declared store surface and the listing.

``plan`` prints the planned graph without opening a run. A reroll is resolved against the
draw ledger before anything opens, so a surface the package does not declare is refused by
name. Everything heavier than argparse is imported inside the handlers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from stage_gen.workflows.storefront.models import DrawLedger


def _input_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--input",
        required=True,
        dest="input_path",
        help="authored storefront package directory (storefront.toml plus references/)",
    )
    parser.add_argument(
        "--reroll",
        action="append",
        default=[],
        dest="rerolls",
        metavar="SURFACE_ID",
        help="redraw one surface; repeatable, everything else stays a cache hit",
    )
    parser.add_argument(
        "--draw-ledger",
        help="carry a prior run's draw-ledger.json forward before applying --reroll",
    )


def register_plan(parser: argparse.ArgumentParser) -> None:
    _input_arguments(parser)
    parser.set_defaults(handler=_plan)


def register_run(parser: argparse.ArgumentParser) -> None:
    _input_arguments(parser)
    parser.add_argument("--output", required=True, dest="output_path", help="run folder to write")
    parser.add_argument("--cache-dir", required=True, help="content-addressed cache folder")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run", action="store_true", help="write node stubs without calling a provider"
    )
    mode.add_argument(
        "--live", action="store_true", help="explicitly authorize the paid provider calls"
    )
    parser.add_argument("--invocation-id", help="name of this invocation's trace (default: random)")
    parser.add_argument("--failure-node", help="inject one dry-run node failure")
    parser.set_defaults(handler=_run)


def _draws(args: argparse.Namespace) -> DrawLedger:
    from stage_gen.workflows.storefront.storefront_request import (
        apply_rerolls,
        empty_ledger,
        read_draw_ledger,
        read_storefront_document,
        resolve_storefront,
    )

    input_path = Path(args.input_path)
    source = resolve_storefront(read_storefront_document(input_path), root=input_path)
    ledger = (
        read_draw_ledger(Path(args.draw_ledger))
        if args.draw_ledger
        else empty_ledger(source.storefront_id)
    )
    return apply_rerolls(ledger, tuple(args.rerolls))


def _plan(args: argparse.Namespace, stdout: TextIO) -> int:
    from stage_gen.config import load_config
    from stage_gen.workflows.storefront.storefront_executor import StorefrontExecutor

    planned = StorefrontExecutor(load_config(), draws=_draws(args)).plan(Path(args.input_path))
    stdout.write(
        json.dumps(
            {
                "graph": planned.graph.model_dump(mode="json"),
                "projection": planned.projection.model_dump(mode="json"),
            },
            indent=2,
        )
        + "\n"
    )
    return 0


def _run(args: argparse.Namespace, stdout: TextIO) -> int:
    import asyncio

    return asyncio.run(_execute(args, stdout))


async def _execute(args: argparse.Namespace, stdout: TextIO) -> int:
    import uuid

    from stage_gen.application import (
        UsageError,
        resolve_cache_dir,
        resolve_output_path,
        run_report,
        write_report,
    )
    from stage_gen.config import load_config
    from stage_gen.workflows.storefront.storefront_executor import StorefrontExecutor

    config = load_config()
    input_path = Path(args.input_path)
    output_path = resolve_output_path(args.output_path)
    cache_dir = resolve_cache_dir(args.cache_dir, config)
    invocation_id = args.invocation_id or f"storefront-{uuid.uuid4().hex}"
    if not args.dry_run and args.failure_node is not None:
        raise UsageError("--failure-node is available only with --dry-run")
    # The ledger is resolved before the executor so a reroll of a surface the
    # package does not declare is refused here, by name, rather than after the
    # run directory has already been opened.
    executor = StorefrontExecutor(config, draws=_draws(args))
    if args.dry_run:
        run = await executor.dry_run(
            input_path,
            run_dir=output_path,
            cache_dir=cache_dir,
            invocation_id=invocation_id,
            failure_node_id=args.failure_node,
        )
    else:
        run = await executor.run(
            input_path,
            run_dir=output_path,
            cache_dir=cache_dir,
            invocation_id=invocation_id,
        )
    report = run_report(
        run,
        run_dir=output_path,
        recipe="storefront",
        storefront_id=run.plan.resolved.storefront_id,
        surfaces=run.plan.graph.surface_count,
    )
    return write_report(stdout, report)
