"""Command adapters for user-authored asset pipelines and optional consumers."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Never, TextIO


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ValueError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="stage-gen", description="Author, run and inspect your own asset pipelines"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    pipeline = commands.add_parser("pipeline", help="run a Python-authored asset pipeline")
    actions = pipeline.add_subparsers(dest="action", required=True)
    for action in ("plan", "run"):
        command = actions.add_parser(action)
        command.add_argument(
            "definition", help="module:attribute or file.py:attribute (default: pipeline)"
        )
        command.add_argument("--input", type=Path, required=True, dest="input_root")
        command.add_argument("--output", type=Path, required=action == "run", dest="output_root")
        command.add_argument("--target", action="append", default=None, dest="targets")
        if action == "run":
            command.add_argument("--cache-dir", type=Path, required=True, dest="cache_root")
            command.add_argument("--invocation-id")
            command.add_argument(
                "--live",
                action="store_true",
                help="explicitly allow provider nodes configured by the pipeline author",
            )
    inspect_parser = actions.add_parser("inspect")
    inspect_parser.add_argument("run_dir", type=Path)
    commands.add_parser("universe", help="optional storyworld asset recipe; use universe --help")
    commands.add_parser(
        "storefront", help="optional promotional asset recipe; use storefront --help"
    )
    commands.add_parser("models", help="inspect the application-owned route catalog")
    commands.add_parser(
        "legacy", help="optional legacy game tools; install the legacy workspace group"
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output, errors = stdout or sys.stdout, stderr or sys.stderr
    arguments = list(sys.argv[1:] if argv is None else argv)
    while arguments and arguments[0] == "--":
        arguments.pop(0)
    parser = build_parser()
    if not arguments or arguments[0] in {"help", "-h", "--help"}:
        parser.print_help(output)
        return 0
    try:
        if arguments[0] == "legacy":
            try:
                adapter = importlib.import_module("stage_gen_legacy.interfaces.cli")
            except ModuleNotFoundError as error:
                if error.name != "stage_gen_legacy":
                    raise
                raise ValueError(
                    "legacy tools are optional; install stage-gen-legacy or uv sync --group legacy"
                ) from error
            return int(adapter.main(arguments[1:], stdout=output, stderr=errors))
        if arguments[0] in {"universe", "storefront"}:
            from stage_gen.interfaces.asset_recipes import main as recipe_main

            return recipe_main(arguments, stdout=output, stderr=errors)
        if arguments[0] == "models":
            from stage_gen.model_policy_maintenance import (
                load_active_model_policy_snapshot,
                model_route_report,
            )

            if arguments[1:] not in ([], ["routes"]):
                raise ValueError(
                    "use stage-gen models routes; legacy fixture projections belong to "
                    "stage-gen legacy models"
                )
            output.write(
                json.dumps(model_route_report(load_active_model_policy_snapshot()), indent=2) + "\n"
            )
            return 0
        args = parser.parse_args(arguments)
        from stage_gen.pipeline import inspect, load_definition, plan, run, write_plan

        if args.action == "inspect":
            result = inspect(args.run_dir)
            output.write(result.model_dump_json(indent=2) + "\n")
            return 0
        try:
            definition = load_definition(args.definition)
        except (ImportError, AttributeError, TypeError, SyntaxError) as error:
            raise ValueError(f"cannot load pipeline definition: {error}") from error
        planned = plan(definition, input_root=args.input_root, targets=args.targets)
        if args.action == "plan":
            if args.output_root is not None:
                write_plan(planned, args.output_root)
            output.write(
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
        completed = asyncio.run(
            run(
                planned,
                output_root=args.output_root,
                cache_root=args.cache_root,
                invocation_id=args.invocation_id,
                allow_provider_calls=args.live,
            )
        )
        output.write(
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
    except (ValueError, FileNotFoundError, FileExistsError) as error:
        errors.write(f"stage-gen: {error}\n")
        return 2
    except KeyboardInterrupt:
        return 130


def entrypoint() -> None:
    raise SystemExit(main())
