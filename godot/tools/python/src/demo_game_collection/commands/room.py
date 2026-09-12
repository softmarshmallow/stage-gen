"""Private collection adapter for room."""

from __future__ import annotations

import argparse
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
from the_grain_pipeline.pointclick_room.room_executor import PointClickRoomExecutor


async def _dispatch_pointclick_room(
    args: argparse.Namespace,
    *,
    config: StageGenConfig,
    stdout: TextIO,
) -> int:
    executor = PointClickRoomExecutor(config)
    output_path = resolve_output_path(args.output_path)
    cache_dir = resolve_cache_dir(args.cache_dir, config)
    invocation_id = args.invocation_id or f"room-{uuid.uuid4().hex}"
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
            recipe="pointclick-room",
            room_id=run.plan.resolved.room.room_id,
        ),
    )
