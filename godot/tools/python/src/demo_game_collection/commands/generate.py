"""Private collection adapter for generate."""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path
from typing import TextIO, cast

from bellweather_pipeline.prepared_content import (
    content_review_target_node_ids,
    content_target_node_ids,
    soundtrack_target_node_ids,
)
from bellweather_pipeline.prepared_world import (
    world_review_target_node_ids,
    world_target_node_ids,
)
from demo_game_collection.executors import PreparedPackageExecutor, SideviewRunnerExecutor
from demo_game_collection.game_package import resolve_prepared_package
from demo_game_tools.application import resolve_genre
from stage_gen.application import (
    UsageError as CliUsageError,
)
from stage_gen.application import (
    resolve_cache_dir,
    resolve_output_path,
    run_report,
    write_report,
)
from stage_gen.application.runs import ReportableRun
from stage_gen.config import (
    StageGenConfig,
)


async def dispatch(args: argparse.Namespace, *, config: StageGenConfig, stdout: TextIO) -> int:
    if args.output_path is None:
        raise CliUsageError("generate requires --output")
    generate_package = resolve_prepared_package(Path(args.input_path))
    declared_genres = [entry.genre for entry in generate_package.game.genres]
    genre = resolve_genre(declared_genres, getattr(args, "genre", None))
    output_path = resolve_output_path(args.output_path)
    # The genre dispatch point: each genre member executes through its own
    # recipe executor. The runner runs single-shot; the platformer keeps its
    # bounded checkpoints below.
    if genre == "runner":
        runner_cache = resolve_cache_dir(args.cache_dir, config)
        if args.checkpoint is not None:
            raise CliUsageError(
                "the runner genre runs single-shot; --checkpoint is platformer-only"
            )
        if args.artifact_roots or args.replace_output:
            raise ValueError("--artifact-root/--replace-output are platformer integration flags")
        runner_executor = SideviewRunnerExecutor(config)
        if args.dry_run:
            runner_invocation = args.invocation_id or f"dry-run-{uuid.uuid4().hex}"
            runner_result = await runner_executor.dry_run(
                Path(args.input_path),
                run_dir=output_path,
                cache_dir=runner_cache,
                invocation_id=runner_invocation,
                failure_node_id=args.failure_node,
            )
        else:
            if args.failure_node is not None:
                raise CliUsageError("--failure-node is available only with --dry-run")
            runner_invocation = args.invocation_id or f"runner-{uuid.uuid4().hex}"
            runner_result = await runner_executor.run(
                Path(args.input_path),
                run_dir=output_path,
                cache_dir=runner_cache,
                invocation_id=runner_invocation,
            )
        return write_report(
            stdout,
            run_report(
                runner_result,
                run_dir=output_path,
                genre=genre,
                invocation_id=runner_invocation,
            ),
        )
    if genre != "platformer":
        raise CliUsageError(f"no recipe is registered for genre {genre!r}")
    cache_dir = resolve_cache_dir(args.cache_dir, config)
    if not args.dry_run:
        if args.checkpoint not in {
            "world",
            "content",
            "soundtrack",
            "world-review",
            "content-review",
            "integration",
        }:
            raise CliUsageError(
                "prepared-package execution requires --checkpoint "
                "world, content, soundtrack, world-review, content-review, or integration"
            )
        if args.failure_node is not None:
            raise CliUsageError("--failure-node is available only with --dry-run")
        checkpoint = cast("str", args.checkpoint)
        invocation_id = args.invocation_id or f"{checkpoint}-{uuid.uuid4().hex}"
        prepared_executor = PreparedPackageExecutor(config)
        if checkpoint == "integration":
            # The published closure is `--output`; the graph's own record of how it
            # was restored sits beside it, dot-prefixed, one directory per invocation.
            integration_run_dir = output_path.parent / (
                f".{output_path.name}.integration-{invocation_id}"
            )
            integration_result = await prepared_executor.run_integration(
                Path(args.input_path),
                run_dir=integration_run_dir,
                output_dir=output_path,
                cache_dir=cache_dir,
                invocation_id=invocation_id,
                artifact_roots=tuple(Path(path) for path in args.artifact_roots),
                replace_output=bool(args.replace_output),
            )
            published = integration_result.result
            return write_report(
                stdout,
                run_report(
                    integration_result,
                    run_dir=integration_run_dir,
                    ok=integration_result.summary.ok and published is not None,
                    genre=genre,
                    checkpoint=checkpoint,
                    invocation_id=invocation_id,
                    executed_node_count=len(integration_result.summary.nodes),
                    artifact_count=None if published is None else published.artifact_count,
                    adopted_from_roots=list(integration_result.adopted_node_ids),
                    package_sha256=integration_result.plan.resolved.package_sha256,
                    output_dir=str(output_path),
                    disposition=None if published is None else published.disposition,
                    replaced_manifest_sha256=(
                        None if published is None else published.replaced_manifest_sha256
                    ),
                ),
            )
        if args.artifact_roots:
            raise CliUsageError("--artifact-root is available only with --checkpoint integration")
        if args.replace_output:
            raise CliUsageError("--replace-output is available only with --checkpoint integration")
        if checkpoint in {"world", "world-review"}:
            live_result = await prepared_executor.run_world(
                Path(args.input_path),
                run_dir=output_path,
                cache_dir=cache_dir,
                invocation_id=invocation_id,
                targets=(
                    world_review_target_node_ids
                    if checkpoint == "world-review"
                    else world_target_node_ids
                ),
            )
            live_run: ReportableRun = live_result
        else:
            # `soundtrack` is `content` narrowed to the tracks. A track's cache
            # identity is its own authored entry, so a rewritten brief re-bills one
            # track -- but the full content closure also drags in every actor, catalog
            # and interface terminal, and regenerates any whose contract has moved
            # since the last accepted run. Rewriting a creative brief should not
            # replace reviewed art.
            content_result = await prepared_executor.run_content(
                Path(args.input_path),
                targets=(
                    soundtrack_target_node_ids
                    if checkpoint == "soundtrack"
                    else content_review_target_node_ids
                    if checkpoint == "content-review"
                    else content_target_node_ids
                ),
                run_dir=output_path,
                cache_dir=cache_dir,
                invocation_id=invocation_id,
            )
            live_run = content_result
        return write_report(
            stdout,
            run_report(
                live_run,
                run_dir=output_path,
                genre=genre,
                checkpoint=checkpoint,
                invocation_id=invocation_id,
                executed_node_count=len(live_run.summary.nodes),
            ),
        )
    if args.replace_output:
        raise CliUsageError("--replace-output is available only with --checkpoint integration")
    invocation_id = args.invocation_id or f"dry-run-{uuid.uuid4().hex}"
    dry_run_result = await PreparedPackageExecutor(config).dry_run(
        Path(args.input_path),
        run_dir=output_path,
        cache_dir=cache_dir,
        invocation_id=invocation_id,
        failure_node_id=args.failure_node,
    )
    return write_report(
        stdout,
        run_report(dry_run_result, run_dir=output_path, genre=genre, invocation_id=invocation_id),
    )
