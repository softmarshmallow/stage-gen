"""Private collection adapter for cli."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from stage_gen.application import (
    UsageError as CliUsageError,
)

if TYPE_CHECKING:
    from stage_gen.capabilities import HeadlessRuntime
from demo_game_collection.parser import build_parser as build_parser
from stage_gen.config import (
    ConfigError,
    StageGenConfig,
    TransparencyMode,
)


def main(
    argv: Sequence[str] | None = None,
    *,
    runtime: HeadlessRuntime | None = None,
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
        return _dispatch(namespace, runtime=runtime, stdout=output)
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


def create_doctor_report(
    config: StageGenConfig, requested_mode: TransparencyMode | None = None
) -> dict[str, object]:
    """Compatibility entry point for callers of the collection readiness report."""
    from demo_game_collection.commands.doctor import create_doctor_report as report

    return report(config, requested_mode)


def _dispatch(args: argparse.Namespace, *, runtime: HeadlessRuntime | None, stdout: TextIO) -> int:
    command: str = args.command
    if command == "models":
        from demo_game_collection.commands.models import dispatch

        return dispatch(args, stdout=stdout)
    if command == "package":
        from demo_game_collection.commands.package import dispatch

        return dispatch(args, stdout=stdout)
    if command == "character-profile":
        from demo_game_collection.commands.bindings import dispatch_character_profile

        return dispatch_character_profile(args, stdout=stdout)
    if command == "soundtrack":
        from demo_game_collection.commands.bindings import dispatch_soundtrack

        return dispatch_soundtrack(args, stdout=stdout)
    if command == "doctor":
        from demo_game_collection.commands.doctor import dispatch

        return dispatch(args, stdout=stdout)
    if command == "export-view":
        from demo_game_collection.commands.views import dispatch

        return dispatch(args, stdout=stdout)
    if command == "universe" and args.universe_command == "page":
        from stage_gen.recipes.universe import gallery_page

        page_path = gallery_page.render(Path(args.run_dir))
        stdout.write(f"{json.dumps({'page': page_path}, sort_keys=True, separators=(',', ':'))}\n")
        return 0
    if command == "import-env":
        from stage_gen.orchestration.env_import import import_provider_env

        imported = import_provider_env(args.source, args.destination)
        stdout.write(f"{json.dumps(imported, separators=(',', ':'))}\n")
        return 0
    if command == "scenario":
        from demo_game_collection.commands.scenario import _dispatch_scenario

        return _dispatch_scenario(args, stdout=stdout)
    if command == "case":
        from demo_game_collection.commands.case import _dispatch_case

        return _dispatch_case(args, stdout=stdout)
    return asyncio.run(_dispatch_async(args, runtime=runtime, stdout=stdout))


async def _dispatch_async(
    args: argparse.Namespace, *, runtime: HeadlessRuntime | None, stdout: TextIO
) -> int:
    from stage_gen.config import load_config

    config = load_config()
    if args.command == "dialogue-scene":
        from demo_game_collection.commands.dialogue import _dispatch_dialogue_scene

        return await _dispatch_dialogue_scene(args, config=config, stdout=stdout)
    if args.command == "pointclick-room":
        from demo_game_collection.commands.room import _dispatch_pointclick_room

        return await _dispatch_pointclick_room(args, config=config, stdout=stdout)
    if args.command == "universe":
        from stage_gen.interfaces.asset_recipes import _dispatch_universe

        return await _dispatch_universe(args, config=config, stdout=stdout)
    if args.command == "storefront":
        from stage_gen.interfaces.asset_recipes import _dispatch_storefront

        return await _dispatch_storefront(args, config=config, stdout=stdout)
    if args.command == "oblique-survival":
        from demo_game_collection.commands.survival import _dispatch_oblique_survival

        return await _dispatch_oblique_survival(args, config=config, stdout=stdout)
    if args.command == "generate":
        from demo_game_collection.commands.generate import dispatch

        return await dispatch(args, config=config, stdout=stdout)
    from demo_game_collection.commands.capabilities import dispatch as capability_dispatch

    return await capability_dispatch(args, config=config, runtime=runtime, stdout=stdout)
