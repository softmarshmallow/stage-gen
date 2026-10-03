"""Private collection adapter for cli."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from typing import TextIO

from demo_game_collection.parser import build_parser as build_parser
from stage_gen.application import (
    UsageError as CliUsageError,
)
from stage_gen.config import (
    ConfigError,
)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    args = list(sys.argv[1:] if argv is None else argv)
    while args and args[0] == "--":
        args.pop(0)
    parser = build_parser()
    if not args:
        parser.print_help(output)
        return 0
    if args[0] in {"help", "-h", "--help"}:
        parser.print_help(output)
        return 0
    try:
        namespace = parser.parse_args(args)
        return _dispatch(namespace, stdout=output)
    except CliUsageError as error:
        errors.write(f"demo-games: usage: {error}\n")
        return 2
    except ConfigError as error:
        errors.write(f"demo-games: configuration: {error}\n")
        return 2
    except Exception as error:
        errors.write(f"demo-games: error: {error}\n")
        return 1
    except KeyboardInterrupt:
        return 130


def entrypoint() -> None:
    raise SystemExit(main())


def _dispatch(args: argparse.Namespace, *, stdout: TextIO) -> int:
    command: str = args.command
    if command == "package":
        from demo_game_collection.commands.package import dispatch

        return dispatch(args, stdout=stdout)
    if command == "character-profile":
        from demo_game_collection.commands.bindings import dispatch_character_profile

        return dispatch_character_profile(args, stdout=stdout)
    if command == "soundtrack":
        from demo_game_collection.commands.bindings import dispatch_soundtrack

        return dispatch_soundtrack(args, stdout=stdout)
    if command == "example":
        from demo_game_collection.commands.examples import dispatch

        return dispatch(args, stdout=stdout)
    if command == "scenario":
        from demo_game_collection.commands.scenario import _dispatch_scenario

        return _dispatch_scenario(args, stdout=stdout)
    if command == "case":
        from demo_game_collection.commands.case import _dispatch_case

        return _dispatch_case(args, stdout=stdout)
    return asyncio.run(_dispatch_async(args, stdout=stdout))


async def _dispatch_async(args: argparse.Namespace, *, stdout: TextIO) -> int:
    from stage_gen.config import load_config

    config = load_config()
    if args.command == "dialogue-scene":
        from demo_game_collection.commands.dialogue import _dispatch_dialogue_scene

        return await _dispatch_dialogue_scene(args, config=config, stdout=stdout)
    raise CliUsageError(f"unknown command {args.command!r}")
