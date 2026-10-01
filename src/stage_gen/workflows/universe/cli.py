"""``stage-gen plan|run universe --phase semantic|gallery``.

The semantic phase proposes and admits one storyworld as text; the gallery phase draws one
concept image per admitted entity from an admitted semantic run. ``plan`` prints the planned
graph without opening a run. Everything heavier than argparse is imported in the handlers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from stage_gen.workflows.universe.universe_executor import UniverseExecutor, UniversePlan

PHASES = ("semantic", "gallery")


def _input_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--phase",
        choices=PHASES,
        required=True,
        help="semantic writes the entities; gallery draws their concept images",
    )
    parser.add_argument(
        "--input",
        required=True,
        dest="input_path",
        help="authored universe package directory (universe.toml plus references/)",
    )
    parser.add_argument(
        "--semantic-run",
        help="gallery: an admitted semantic run directory planned from the same package",
    )
    parser.add_argument(
        "--reroll",
        action="append",
        default=[],
        dest="rerolls",
        metavar="ENTITY_ID",
        help="gallery: redraw one entity's concept image; repeatable",
    )
    parser.add_argument(
        "--sample-ledger",
        help="gallery: carry a prior run's sample-ledger.json forward before any --reroll",
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


def _check_phase(args: argparse.Namespace) -> None:
    if args.phase == "gallery" and args.semantic_run is None:
        raise ValueError("--phase gallery needs --semantic-run")
    if args.phase == "semantic" and (args.semantic_run or args.sample_ledger or args.rerolls):
        raise ValueError("--semantic-run, --sample-ledger and --reroll belong to --phase gallery")


def _plan_phase(executor: UniverseExecutor, args: argparse.Namespace) -> UniversePlan:
    input_path = Path(args.input_path)
    if args.phase == "semantic":
        return executor.plan_semantic(input_path)
    return executor.plan_gallery(
        input_path,
        semantic_run=Path(args.semantic_run),
        rerolls=tuple(args.rerolls),
        sample_ledger=Path(args.sample_ledger) if args.sample_ledger else None,
    )


def _plan(args: argparse.Namespace, stdout: TextIO) -> int:
    from stage_gen.config import load_config
    from stage_gen.workflows.universe.universe_executor import UniverseExecutor

    _check_phase(args)
    planned = _plan_phase(UniverseExecutor(load_config()), args)
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

    _check_phase(args)
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
    from stage_gen.workflows.universe.universe_executor import UniverseExecutor

    config = load_config()
    executor = UniverseExecutor(config)
    input_path = Path(args.input_path)
    output_path = resolve_output_path(args.output_path)
    cache_dir = resolve_cache_dir(args.cache_dir, config)
    phase = str(args.phase)
    invocation_id = args.invocation_id or f"universe-{phase}-{uuid.uuid4().hex}"
    if not args.dry_run and args.failure_node is not None:
        raise UsageError("--failure-node is available only with --dry-run")
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
        rerolls = tuple(args.rerolls)
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
