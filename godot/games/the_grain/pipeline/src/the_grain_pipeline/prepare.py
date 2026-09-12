"""The Grain owns its case proof, dialogue and room preparation."""

import json
from collections.abc import Sequence
from pathlib import Path

from demo_game_tools.preparation import (
    execute_preparation,
    preparation_parser,
    validate_run_options,
)
from gnode import RunSummary
from stage_gen.config import load_config
from the_grain_pipeline.case_binding import bind_case
from the_grain_pipeline.case_bundle import publish_case
from the_grain_pipeline.dialogue_scene.scene_executor import DialogueSceneExecutor
from the_grain_pipeline.pointclick_room.room_executor import PointClickRoomExecutor


def main(default_input: Path, argv: Sequence[str] | None = None) -> int:
    parser = preparation_parser("Prepare The Grain assets and case bindings")
    parser.add_argument("--mode", choices=("case", "dialogue", "room"), default="case")
    parser.add_argument("--case", default="episode_one", dest="case_id")
    parser.add_argument("--room", default="window", help="room directory within inputs/rooms")
    parser.add_argument(
        "--bundle", action="store_true", help="assemble a proven case from existing beat runs"
    )
    parser.add_argument("--beat-run", action="append", default=[], metavar="BEAT_ID=RUN_TAG")
    parser.add_argument("--runs-dir", type=Path)
    args = parser.parse_args(argv)
    validate_run_options(parser, args)
    input_path = args.input_path or default_input
    if args.mode == "case":
        if args.live or args.dry_run:
            parser.error(
                "case checks and bundling consume existing inputs and runs; omit --live/--dry-run"
            )
        bound = bind_case(input_path, args.case_id)
        if args.bundle:
            if args.output is None:
                parser.error("--bundle requires --output")
            beat_runs: dict[str, str] = {}
            for value in args.beat_run:
                beat_id, separator, run_tag = value.partition("=")
                if not separator or not beat_id or not run_tag or beat_id in beat_runs:
                    parser.error("--beat-run requires a unique BEAT_ID=RUN_TAG")
                beat_runs[beat_id] = run_tag
            report = publish_case(
                input_path,
                args.case_id,
                run_tags=beat_runs,
                output=args.output,
                runs_root=args.runs_dir or args.output.parent,
            )
            print(json.dumps(report.runtime.model_dump(mode="json"), indent=2))
        else:
            print(
                json.dumps(
                    {
                        "case_id": bound.resolved.case.case_id,
                        "valid": True,
                        "beats": [beat.beat_id for beat in bound.beats],
                    },
                    indent=2,
                )
            )
        return 0
    if args.bundle:
        parser.error("--bundle is only valid with --mode case")
    if args.mode == "room":
        if Path(args.room).name != args.room or args.room in ("", ".", ".."):
            parser.error("--room must be one directory name")
        room_input = input_path / "rooms" / args.room
        room_executor = PointClickRoomExecutor(load_config())

        async def room_run(invocation_id: str) -> RunSummary:
            run = await room_executor.run(
                room_input,
                run_dir=args.output,
                cache_dir=args.cache_dir,
                invocation_id=invocation_id,
            )
            return run.summary

        return execute_preparation(room_executor, room_input, args, live_run=room_run)
    scene_executor = DialogueSceneExecutor(load_config())

    async def scene_run(invocation_id: str) -> RunSummary:
        run = await scene_executor.run(
            input_path, run_dir=args.output, cache_dir=args.cache_dir, invocation_id=invocation_id
        )
        return run.summary

    return execute_preparation(scene_executor, input_path, args, live_run=scene_run)
