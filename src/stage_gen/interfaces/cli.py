"""``stage-gen``: one verb set over the installed workflows.

``list``, ``show``, ``plan``, ``run``, ``inspect`` and ``view`` work on workflows and runs;
``example``, ``catalog``, ``capability``, ``models`` and ``env`` are the tools around them.
``plan`` and ``run`` take a workflow id, discovered from the installed ``workflow.toml``
manifests, or ``file`` for a definition written with the SDK. Each workflow's ``cli`` module
registers its own flags and imports nothing heavier than argparse until it runs, so building
this parser loads no engine, media library or workflow implementation.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Never, TextIO

from stage_gen.interfaces.commands import capability, examples, sdk, view, workflows
from stage_gen.interfaces.commands import inspect as inspect_command


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ValueError(message)


def _workflow_verbs(commands: argparse._SubParsersAction[_Parser]) -> None:
    from stage_gen.workflows._registry import discover

    found = discover()
    for verb, summary in (
        ("plan", "plan a workflow offline, before any spend"),
        ("run", "run a workflow; provider calls need its explicit opt-in"),
    ):
        command = commands.add_parser(verb, help=summary, description=summary)
        targets = command.add_subparsers(dest="workflow", required=True, metavar="WORKFLOW")
        for workflow in found:
            module = importlib.import_module(f"{workflow.package}.cli")
            forwards = verb == "run" and getattr(module, "FORWARDS_RUN_ARGUMENTS", False)
            parser = targets.add_parser(
                workflow.id,
                help=workflow.manifest.promise,
                description=f"{workflow.manifest.title}: {workflow.manifest.promise}",
                add_help=not forwards,
            )
            getattr(module, f"register_{verb}")(parser)
            if forwards:
                parser.set_defaults(forward=True)
        sdk_parser = targets.add_parser(
            sdk.FILE_COMMAND,
            help="a pipeline definition written with the SDK (module:attribute or file.py:attr)",
        )
        (sdk.register_plan if verb == "plan" else sdk.register_run)(sdk_parser)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="stage-gen",
        description="Plan, run and inspect asset workflows and your own SDK pipelines",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    workflows.register_list(commands.add_parser("list", help="list the installed workflows"))
    workflows.register_show(
        commands.add_parser("show", help="one workflow: steps, sample plan, examples")
    )
    _workflow_verbs(commands)
    inspect_command.register(
        commands.add_parser("inspect", help="read, verify or write the view of one run folder")
    )
    view.register(commands.add_parser("view", help="open the local viewer over run folders"))
    examples.register_example(
        commands.add_parser("example", help="verify or promote pinned examples")
    )
    examples.register_catalog(
        commands.add_parser(
            "catalog", help="export the catalog of installed workflows and their examples"
        )
    )
    capability.register(
        commands.add_parser("capability", help="one provider or media call outside any graph")
    )
    models = commands.add_parser("models", help="inspect the application-owned route catalog")
    models.add_argument("action", nargs="?", choices=("routes",), default="routes")
    models.set_defaults(handler=_models)
    env = commands.add_parser("env", help="import provider keys into a local dotenv file")
    env_actions = env.add_subparsers(dest="action", required=True)
    env_import = env_actions.add_parser(
        "import", help="copy allowlisted provider keys from one dotenv file into another"
    )
    env_import.add_argument("--source", required=True)
    env_import.add_argument("--destination", required=True)
    env_import.set_defaults(handler=_env_import)
    return parser


CLI_REFERENCE_KIND = "stage-gen-cli-v1"
CLI_REFERENCE_FILE = "cli.json"
_USAGE_WIDTH = 88  # fixed, so the reference does not depend on the terminal that wrote it


def _usage(parser: argparse.ArgumentParser) -> str:
    formatter = argparse.HelpFormatter(parser.prog, width=_USAGE_WIDTH)
    formatter.add_usage(parser.usage, parser._actions, parser._mutually_exclusive_groups, prefix="")
    return formatter.format_help().strip()


def _default(action: argparse.Action) -> str | None:
    """The default worth printing: a set value, never a flag's False or an empty list."""
    value: object = action.default
    if value is None or value is False or value == argparse.SUPPRESS or action.nargs == 0:
        return None
    if isinstance(value, list | tuple):
        return ", ".join(str(item) for item in value) if value else None
    if isinstance(value, Path):
        if value.is_absolute():
            raise ValueError(f"{action.dest} defaults to an absolute path; the reference is public")
        return value.as_posix()
    if isinstance(value, str | int | float):
        return str(value)
    raise ValueError(f"{action.dest} has a default the reference cannot print: {value!r}")


def _argument(action: argparse.Action, parser: argparse.ArgumentParser) -> dict[str, Any]:
    formatter = argparse.HelpFormatter(parser.prog, width=_USAGE_WIDTH)
    positional = not action.option_strings
    if positional:
        metavar: str | None = formatter._format_args(
            action, formatter._get_default_metavar_for_positional(action)
        )
    elif action.nargs == 0:
        metavar = None
    else:
        metavar = formatter._format_args(
            action, formatter._get_default_metavar_for_optional(action)
        )
    repeatable = isinstance(action, argparse._AppendAction | argparse._CountAction)
    return {
        "names": list(action.option_strings) if not positional else [metavar or action.dest],
        "positional": positional,
        "metavar": metavar,
        "help": formatter._expand_help(action) if action.help else None,
        "required": bool(action.required),
        "repeatable": repeatable or action.nargs in ("*", "+"),
        "choices": None if action.choices is None else [str(c) for c in action.choices],
        "default": _default(action),
    }


def _command(parser: argparse.ArgumentParser, name: str, summary: str | None) -> dict[str, Any]:
    arguments: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction) or action.help == argparse.SUPPRESS:
            continue
        if isinstance(action, argparse._SubParsersAction):
            # One entry per command name, in the order they were added; aliases are not repeated.
            for choice in action._choices_actions:
                commands.append(_command(action.choices[choice.dest], choice.dest, choice.help))
            continue
        arguments.append(_argument(action, parser))
    return {
        "name": name,
        "prog": parser.prog,
        "summary": summary,
        "description": parser.description,
        "usage": _usage(parser),
        "forwards": bool(parser.get_default("forward")),
        "arguments": arguments,
        "commands": commands,
    }


def command_reference(parser: argparse.ArgumentParser | None = None) -> dict[str, Any]:
    """The ``stage-gen`` argparse tree as data, which the site's CLI reference is written from.

    Every command, with its usage, its arguments and its subcommands, in the order the parser
    declares them. ``stage-gen catalog export`` writes it beside the catalog as ``cli.json``.
    """
    root = parser or build_parser()
    return {"kind": CLI_REFERENCE_KIND, **_command(root, root.prog, None)}


def parse(
    arguments: Sequence[str], parser: argparse.ArgumentParser | None = None
) -> argparse.Namespace:
    """Parse one ``stage-gen`` command line, as the console script does.

    A workflow whose run parser forwards its arguments (character-3d) receives everything
    after its id, verbatim, as ``forwarded``; anywhere else an unknown argument is an error.
    """
    parser = parser or build_parser()
    args, extra = parser.parse_known_args(list(arguments))
    if getattr(args, "forward", False):
        args.forwarded = extra
    elif extra:
        parser.error(f"unrecognized arguments: {' '.join(extra)}")
    return args


def _models(args: argparse.Namespace, stdout: TextIO) -> int:
    import json

    from stage_gen.model_policy_maintenance import (
        load_active_model_policy_snapshot,
        model_route_report,
    )

    del args
    stdout.write(
        json.dumps(model_route_report(load_active_model_policy_snapshot()), indent=2) + "\n"
    )
    return 0


def _env_import(args: argparse.Namespace, stdout: TextIO) -> int:
    """Copies only allowlisted provider keys and prints their names, never their values.
    It writes a new file: an existing destination (a local ``.env`` above all) is refused."""
    import json
    import os

    from stage_gen.orchestration.env_import import import_provider_env

    if os.path.lexists(args.destination):
        raise ValueError(f"{args.destination} already exists; import into a new file")
    imported = import_provider_env(args.source, args.destination)
    stdout.write(f"{json.dumps(imported, separators=(',', ':'))}\n")
    return 0


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
    try:
        parser = build_parser()
        if not arguments or arguments[0] in {"help", "-h", "--help"}:
            parser.print_help(output)
            return 0
        args = parse(arguments, parser)
        return int(args.handler(args, output))
    except (ValueError, OSError) as error:
        errors.write(f"stage-gen: {error}\n")
        return 2
    except KeyboardInterrupt:
        return 130


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
