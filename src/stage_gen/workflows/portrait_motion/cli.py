"""``stage-gen plan|run portrait-motion``: prepare a run offline, then execute it.

``plan`` imports the source and writes the prepared run folder; ``run`` executes it or
reuses its validated artifacts. Verification is ``stage-gen inspect RUN --verify``.
Everything heavier than argparse is imported inside the handlers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, TextIO


def register_plan(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", type=Path, required=True, help="the portrait image to animate")
    parser.add_argument(
        "--spec", type=Path, required=True, help="PortraitMotionSpec JSON: the motion to make"
    )
    parser.add_argument("--profile", type=Path, help="optional RuntimeProfile JSON")
    parser.add_argument("--run", type=Path, required=True, help="the prepared run folder to write")
    parser.add_argument(
        "--face-crop",
        action="store_true",
        help="Locate a face, animate its crop, and restore patches to the original canvas",
    )
    parser.set_defaults(handler=_plan)


def register_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--run", type=Path, required=True, help="a run folder `plan portrait-motion` prepared"
    )
    parser.add_argument(
        "--live", action="store_true", help="Explicitly authorize configured provider calls"
    )
    parser.add_argument("--dotenv", type=Path, help="Optional allowlisted local credential file")
    parser.set_defaults(handler=_run)


def _plan(args: argparse.Namespace, stdout: TextIO) -> int:
    from stage_gen.components.portrait_motion import PortraitMotionSpec
    from stage_gen.config import load_config
    from stage_gen.workflows.portrait_motion.pipeline import RuntimeProfile, prepare_run

    spec = PortraitMotionSpec.model_validate_json(args.spec.read_bytes())
    profile = (
        RuntimeProfile.model_validate_json(args.profile.read_bytes()) if args.profile else None
    )
    return _report(
        stdout,
        prepare_run(
            args.source, args.run, spec, profile, config=load_config(), face_crop=args.face_crop
        ),
    )


def _run(args: argparse.Namespace, stdout: TextIO) -> int:
    import asyncio

    from stage_gen.orchestration.portrait_services import ConfiguredPortraitServices
    from stage_gen.workflows.portrait_motion.pipeline import run_pipeline

    return _report(
        stdout,
        asyncio.run(
            run_pipeline(
                args.run,
                live=args.live,
                dotenv=args.dotenv,
                service_factory=ConfiguredPortraitServices() if args.live else None,
            )
        ),
    )


def _report(stdout: TextIO, result: dict[str, Any]) -> int:
    stdout.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return 1 if result["status"] == "failed" else 0
