"""Command-line adapter for preparing, running and verifying portrait motion."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from stage_gen.components.portrait_motion import PortraitMotionSpec
from stage_gen.config import load_config
from stage_gen.orchestration.portrait_motion import (
    RuntimeProfile,
    prepare_run,
    run_pipeline,
    verify_run,
)


def entrypoint() -> None:
    parser = argparse.ArgumentParser(description="Bounded fixed-portrait blink and mouth animation")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Plan offline and import an original source")
    prepare.add_argument("--source", type=Path, required=True)
    prepare.add_argument("--spec", type=Path, required=True)
    prepare.add_argument("--profile", type=Path)
    prepare.add_argument("--run", type=Path, required=True)
    prepare.add_argument(
        "--face-crop",
        action="store_true",
        help="Locate a face, animate its crop, and restore patches to the original canvas",
    )
    run = commands.add_parser("run", help="Execute the prepared graph or reuse validated artifacts")
    run.add_argument("--run", type=Path, required=True)
    run.add_argument(
        "--live", action="store_true", help="Explicitly authorize configured provider calls"
    )
    run.add_argument("--dotenv", type=Path, help="Optional allowlisted local credential file")
    verify = commands.add_parser(
        "verify", help="Require every stage and verify content plus lineage"
    )
    verify.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        spec = PortraitMotionSpec.model_validate_json(args.spec.read_bytes())
        profile = (
            RuntimeProfile.model_validate_json(args.profile.read_bytes()) if args.profile else None
        )
        result = prepare_run(
            args.source,
            args.run,
            spec,
            profile,
            config=load_config(),
            face_crop=args.face_crop,
        )
    elif args.command == "run":
        result = asyncio.run(run_pipeline(args.run, live=args.live, dotenv=args.dotenv))
    else:
        result = verify_run(args.run)
    print(json.dumps(result, indent=2, allow_nan=False))
    if result["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    entrypoint()
