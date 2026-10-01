"""``stage-gen plan|run looping-parallax``: supplied layers in, repeating layers out.

The input folder holds the layer pictures and a ``ParallaxSpec`` as JSON (``parallax.json``
unless ``--spec`` names another input-relative file). The reports have the shape of
``stage-gen plan|run file``. Everything heavier than argparse is imported in the handlers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from stage_gen.pipeline import PipelineDefinition

SPEC_FILE = "parallax.json"


def _input_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        dest="input_root",
        help="folder the input layers resolve in",
    )
    parser.add_argument(
        "--spec",
        default=SPEC_FILE,
        help=f"input-relative ParallaxSpec JSON (default: {SPEC_FILE})",
    )
    parser.add_argument(
        "--target",
        action="append",
        default=None,
        dest="targets",
        help="stop at this node id; repeatable (default: every node)",
    )


def register_plan(parser: argparse.ArgumentParser) -> None:
    _input_arguments(parser)
    parser.add_argument("--output", type=Path, dest="output_root", help="write the plan here")
    parser.set_defaults(handler=_plan)


def register_run(parser: argparse.ArgumentParser) -> None:
    _input_arguments(parser)
    parser.add_argument(
        "--output", type=Path, required=True, dest="output_root", help="run folder to write"
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        required=True,
        dest="cache_root",
        help="content-addressed cache folder",
    )
    parser.add_argument("--invocation-id", help="name of this invocation's trace (default: random)")
    parser.add_argument(
        "--live",
        action="store_true",
        help="allow the provider edit a seam_repaint layer needs when it does not already loop",
    )
    parser.set_defaults(handler=_run)


def build_definition(args: argparse.Namespace) -> PipelineDefinition:
    from stage_gen.workflows.looping_parallax import ParallaxSpec, create_pipeline

    spec = ParallaxSpec.model_validate_json((args.input_root / args.spec).read_bytes())
    return create_pipeline(spec)


def _plan(args: argparse.Namespace, stdout: TextIO) -> int:
    from stage_gen.pipeline import plan, write_plan

    planned = plan(build_definition(args), input_root=args.input_root, targets=args.targets)
    if args.output_root is not None:
        write_plan(planned, args.output_root)
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

    from stage_gen.pipeline import plan, run

    definition = build_definition(args)
    planned = plan(definition, input_root=args.input_root, targets=args.targets)
    completed = asyncio.run(
        run(
            planned,
            output_root=args.output_root,
            cache_root=args.cache_root,
            invocation_id=args.invocation_id,
            allow_provider_calls=args.live,
        )
    )
    stdout.write(
        json.dumps(
            {
                "ok": completed.summary.ok,
                "pipeline_id": definition.pipeline_id,
                "run_dir": str(completed.run_dir),
                "summary": completed.summary.model_dump(mode="json"),
            },
            indent=2,
        )
        + "\n"
    )
    return 0 if completed.summary.ok else 1
