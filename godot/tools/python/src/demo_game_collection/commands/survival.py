"""Private collection adapter for survival."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import TextIO

from ember_hollow_pipeline.survival_executor import ObliqueSurvivalExecutor
from ember_hollow_pipeline.survival_graph import (
    OBLIQUE_SURVIVAL_CACHE_NAMESPACE,
)
from stage_gen.application import (
    UsageError as CliUsageError,
)
from stage_gen.application import (
    resolve_cache_dir,
    resolve_output_path,
    run_report,
    write_report,
)
from stage_gen.config import (
    StageGenConfig,
)
from stage_gen.recipes.cache_report import cache_report


async def _dispatch_oblique_survival(
    args: argparse.Namespace,
    *,
    config: StageGenConfig,
    stdout: TextIO,
) -> int:
    subcommand = str(args.oblique_survival_command)
    if subcommand == "plan":
        executor = ObliqueSurvivalExecutor(config, scope=str(args.scope))
        plan = executor.plan(Path(args.input_path))
        plan_report: dict[str, object] = {
            "recipe": "oblique-survival",
            "scope": plan.scope,
            "package_id": plan.resolved.package_id,
            "graph": plan.graph.model_dump(mode="json"),
            "projection": plan.projection.model_dump(mode="json"),
        }
        if args.cache_dir:
            # What the warm run would actually cost, read statically and for free.
            plan_report["cache"] = cache_report(
                plan.graph, Path(args.cache_dir), (OBLIQUE_SURVIVAL_CACHE_NAMESPACE,)
            )
        stdout.write(f"{json.dumps(plan_report, sort_keys=True, separators=(',', ':'))}\n")
        return 0
    if subcommand == "import-run":
        executor = ObliqueSurvivalExecutor(config, scope=str(args.scope))
        transfer = executor.import_run(
            Path(args.run_dir),
            input_path=Path(args.input_path),
            cache_dir=resolve_cache_dir(args.cache_dir, config),
        )
        return write_report(stdout, {"ok": True, **transfer.document()})
    if subcommand == "finalize":
        executor = ObliqueSurvivalExecutor(config)
        run_dir = Path(args.run_dir)
        manifest = executor.finalize(run_dir, input_path=Path(args.input_path))
        return write_report(
            stdout,
            {
                "ok": True,
                "recipe": "oblique-survival",
                "run_dir": str(run_dir),
                "status": manifest["status"],
            },
        )

    executor = ObliqueSurvivalExecutor(config, scope=str(args.scope))
    input_path = Path(args.input_path)
    output_path = resolve_output_path(args.output_path)
    cache_dir = resolve_cache_dir(args.cache_dir, config)
    invocation_id = args.invocation_id or f"oblique-survival-{uuid.uuid4().hex}"
    if not args.dry_run and args.failure_node is not None:
        raise CliUsageError("--failure-node is available only with --dry-run")
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
        recipe="oblique-survival",
        scope=run.plan.scope,
        package_id=run.plan.resolved.package_id,
    )
    if run.manifest is not None:
        report["status"] = run.manifest.get("status")
    return write_report(stdout, report)
