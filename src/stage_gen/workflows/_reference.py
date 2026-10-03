"""The ``gnode`` command line as data, which the site's CLI reference is written from.

Every command, with its usage, its arguments and its subcommands, in the order gnode's
parser declares them. ``scripts/catalog.py`` writes it beside the catalog as ``cli.json``.
The usage is formatted at a fixed width, so the reference does not depend on the terminal
that wrote it, and a default that is an absolute path is refused, since the reference is
public.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

CLI_REFERENCE_KIND = "gnode-cli-v1"
CLI_REFERENCE_FILE = "cli.json"
_USAGE_WIDTH = 88


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
        "arguments": arguments,
        "commands": commands,
    }


def command_reference(parser: argparse.ArgumentParser | None = None) -> dict[str, Any]:
    """The ``gnode`` argparse tree as data (``gnode-cli-v1``)."""
    from gnode import cli

    root = parser or cli.build_parser()
    return {"kind": CLI_REFERENCE_KIND, **_command(root, root.prog, None)}


__all__ = ["CLI_REFERENCE_FILE", "CLI_REFERENCE_KIND", "command_reference"]
