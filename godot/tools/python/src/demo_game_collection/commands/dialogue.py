"""Private collection adapter for dialogue."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import TextIO

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
from the_grain_pipeline.dialogue_scene.review import transition_dialogue_review
from the_grain_pipeline.dialogue_scene.scene_executor import DialogueSceneExecutor


async def _dispatch_dialogue_scene(
    args: argparse.Namespace,
    *,
    config: StageGenConfig,
    stdout: TextIO,
) -> int:
    if args.dialogue_command == "review":
        review_result = await transition_dialogue_review(
            {
                "bundle_path": args.bundle_path,
                "review_path": args.review_path,
                "acceptance_spec_path": args.acceptance_spec_path,
                "usage": args.usage,
            }
        )
        stdout.write(f"{json.dumps(review_result, separators=(',', ':'))}\n")
        return 0
    executor = DialogueSceneExecutor(config)
    output_path = resolve_output_path(args.output_path)
    cache_dir = resolve_cache_dir(args.cache_dir, config)
    invocation_id = args.invocation_id or f"dialogue-{uuid.uuid4().hex}"
    if args.dry_run:
        run = await executor.dry_run(
            Path(args.input_path),
            run_dir=output_path,
            cache_dir=cache_dir,
            invocation_id=invocation_id,
            failure_node_id=args.failure_node,
        )
    else:
        if args.failure_node is not None:
            raise CliUsageError("--failure-node is available only with --dry-run")
        run = await executor.run(
            Path(args.input_path),
            run_dir=output_path,
            cache_dir=cache_dir,
            invocation_id=invocation_id,
        )
    return write_report(
        stdout,
        run_report(
            run,
            run_dir=output_path,
            recipe="dialogue-scene",
            scene_id=run.plan.resolved.scene_id,
        ),
    )
