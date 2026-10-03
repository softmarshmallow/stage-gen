"""Private collection adapter for package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TextIO

from demo_game_collection.executors import gnode_build
from demo_game_collection.game_package import resolve_prepared_package
from demo_game_tools.application import resolve_genre
from stage_gen.application import (
    UsageError as CliUsageError,
)


def dispatch(args: argparse.Namespace, *, stdout: TextIO) -> int:
    resolved_package = resolve_prepared_package(Path(args.input_path))
    if args.package_command == "digest":
        stdout.write(f"{resolved_package.closure_sha256}\n")
    elif args.package_command == "plan":
        declared_genres = [entry.genre for entry in resolved_package.game.genres]
        genre = resolve_genre(declared_genres, getattr(args, "genre", None))
        raise CliUsageError(gnode_build(genre) or f"no recipe is registered for genre {genre!r}")
    else:
        package_report = {"valid": True, **resolved_package.identity()}
        stdout.write(f"{json.dumps(package_report, sort_keys=True, separators=(',', ':'))}\n")
    return 0
