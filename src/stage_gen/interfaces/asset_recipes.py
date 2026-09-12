"""Thin CLI adapters for optional asset recipes, independent of maintained game consumers."""

from __future__ import annotations

import argparse
import asyncio
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from stage_gen.application import UsageError as CliUsageError
from stage_gen.application import resolve_cache_dir, resolve_output_path, run_report, write_report
from stage_gen.config import StageGenConfig, load_config


def main(argv: Sequence[str], *, stdout: TextIO, stderr: TextIO) -> int:
    parser = argparse.ArgumentParser(prog="stage-gen " + argv[0])
    actions = parser.add_subparsers(dest="phase", required=True)
    for phase in ("semantic", "gallery") if argv[0] == "universe" else ("generate",):
        action = actions.add_parser(phase)
        action.add_argument("--input", required=True, dest="input_path")
        action.add_argument("--output", required=True, dest="output_path")
        action.add_argument("--cache-dir", required=True)
        mode = action.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--live", action="store_true")
        action.add_argument("--invocation-id")
        action.add_argument("--failure-node")
        action.add_argument("--reroll", action="append", default=[], dest="rerolls")
        if argv[0] == "universe" and phase == "gallery":
            action.add_argument("--semantic-run", required=True)
            action.add_argument("--sample-ledger")
        if argv[0] == "storefront":
            action.add_argument("--draw-ledger")
    args = parser.parse_args(list(argv[1:]))
    args.universe_command = args.phase
    config = load_config()
    if argv[0] == "universe":
        return asyncio.run(_dispatch_universe(args, config=config, stdout=stdout))
    return asyncio.run(_dispatch_storefront(args, config=config, stdout=stdout))


async def _dispatch_universe(
    args: argparse.Namespace,
    *,
    config: StageGenConfig,
    stdout: TextIO,
) -> int:
    from stage_gen.recipes.universe.universe_executor import UniverseExecutor

    executor = UniverseExecutor(config)
    input_path = Path(args.input_path)
    output_path = resolve_output_path(args.output_path)
    cache_dir = resolve_cache_dir(args.cache_dir, config)
    phase = str(args.universe_command)
    invocation_id = args.invocation_id or f"universe-{phase}-{uuid.uuid4().hex}"
    if not args.dry_run and args.failure_node is not None:
        raise CliUsageError("--failure-node is available only with --dry-run")
    if phase == "semantic":
        if args.dry_run:
            run = await executor.dry_run_semantic(
                input_path,
                run_dir=output_path,
                cache_dir=cache_dir,
                invocation_id=invocation_id,
                failure_node_id=args.failure_node,
            )
        else:
            run = await executor.run_semantic(
                input_path,
                run_dir=output_path,
                cache_dir=cache_dir,
                invocation_id=invocation_id,
            )
    else:
        semantic_run = Path(args.semantic_run)
        rerolls = tuple(args.rerolls or ())
        sample_ledger = Path(args.sample_ledger) if args.sample_ledger else None
        if args.dry_run:
            run = await executor.dry_run_gallery(
                input_path,
                semantic_run=semantic_run,
                run_dir=output_path,
                cache_dir=cache_dir,
                invocation_id=invocation_id,
                rerolls=rerolls,
                sample_ledger=sample_ledger,
                failure_node_id=args.failure_node,
            )
        else:
            run = await executor.run_gallery(
                input_path,
                semantic_run=semantic_run,
                run_dir=output_path,
                cache_dir=cache_dir,
                invocation_id=invocation_id,
                rerolls=rerolls,
                sample_ledger=sample_ledger,
            )
    report = run_report(
        run,
        run_dir=output_path,
        recipe="universe",
        phase=phase,
        universe_id=run.plan.resolved.universe_id,
    )
    if run.manifest is not None:
        report["counts"] = run.manifest["counts"]
    return write_report(stdout, report)


async def _dispatch_storefront(
    args: argparse.Namespace,
    *,
    config: StageGenConfig,
    stdout: TextIO,
) -> int:
    from stage_gen.recipes.storefront.storefront_executor import StorefrontExecutor
    from stage_gen.recipes.storefront.storefront_request import (
        apply_rerolls,
        empty_ledger,
        read_draw_ledger,
        read_storefront_document,
        resolve_storefront,
    )

    input_path = Path(args.input_path)
    output_path = resolve_output_path(args.output_path)
    cache_dir = resolve_cache_dir(args.cache_dir, config)
    invocation_id = args.invocation_id or f"storefront-{uuid.uuid4().hex}"
    if not args.dry_run and args.failure_node is not None:
        raise CliUsageError("--failure-node is available only with --dry-run")
    # The ledger is resolved before the executor so a reroll of a surface the
    # package does not declare is refused here, by name, rather than after the
    # run directory has already been opened.
    source = resolve_storefront(read_storefront_document(input_path), root=input_path)
    ledger = (
        read_draw_ledger(Path(args.draw_ledger))
        if args.draw_ledger
        else empty_ledger(source.storefront_id)
    )
    draws = apply_rerolls(ledger, tuple(args.rerolls or ()))
    executor = StorefrontExecutor(config, draws=draws)
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
