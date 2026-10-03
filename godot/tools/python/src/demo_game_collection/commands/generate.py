"""Private collection adapter for generate."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TextIO

from demo_game_collection.executors import gnode_build
from demo_game_collection.game_package import resolve_prepared_package
from demo_game_tools.application import resolve_genre
from stage_gen.application import UsageError as CliUsageError
from stage_gen.config import StageGenConfig


async def dispatch(args: argparse.Namespace, *, config: StageGenConfig, stdout: TextIO) -> int:
    """Every genre this command ran builds with gnode now; say how, or that none is known."""

    del config, stdout
    package = resolve_prepared_package(Path(args.input_path))
    genre = resolve_genre(
        [entry.genre for entry in package.game.genres], getattr(args, "genre", None)
    )
    notice = gnode_build(genre)
    raise CliUsageError(notice or f"no recipe is registered for genre {genre!r}")
