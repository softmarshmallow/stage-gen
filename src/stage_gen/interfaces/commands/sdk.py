"""``stage-gen plan|run file``: a pipeline definition written with the SDK.

The definition is ``module:attribute`` or ``file.py:attribute`` (default attribute:
``pipeline``). ``run`` refuses provider nodes unless ``--live`` allows them.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from stage_gen.pipeline import PipelineDefinition

#: The reserved word after ``plan`` or ``run`` that names an SDK definition, not a workflow.
FILE_COMMAND = "file"


def _definition_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "definition", help="module:attribute or file.py:attribute (default: pipeline)"
    )
    parser.add_argument("--input", type=Path, required=True, dest="input_root")
    parser.add_argument("--target", action="append", default=None, dest="targets")


def register_plan(parser: argparse.ArgumentParser) -> None:
    _definition_arguments(parser)
    parser.add_argument("--output", type=Path, dest="output_root", help="write the plan here")
    parser.set_defaults(handler=_plan)


def register_run(parser: argparse.ArgumentParser) -> None:
    _definition_arguments(parser)
    parser.add_argument("--output", type=Path, required=True, dest="output_root")
    parser.add_argument("--cache-dir", type=Path, required=True, dest="cache_root")
    parser.add_argument("--invocation-id")
    parser.add_argument(
        "--live",
        action="store_true",
        help="explicitly allow provider nodes configured by the pipeline author",
    )
    parser.set_defaults(handler=_run)


def _load(reference: str) -> PipelineDefinition:
    from stage_gen.pipeline import load_definition

    try:
        return load_definition(reference)
    except (ImportError, AttributeError, TypeError, SyntaxError) as error:
        raise ValueError(f"cannot load pipeline definition: {error}") from error


def _plan(args: argparse.Namespace, stdout: TextIO) -> int:
    from stage_gen.pipeline import plan, write_plan

    planned = plan(_load(args.definition), input_root=args.input_root, targets=args.targets)
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

    definition = _load(args.definition)
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
