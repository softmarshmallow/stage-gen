#!/usr/bin/env python3
"""Copy a game source project with a real, closed private addon payload.

The checkout uses development links to one maintained demo_support source tree.
This command assembles ordinary source files for copying outside the repository;
it does not export a binary, generate media, or embed an existing asset run.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

GAMES = Path(__file__).resolve().parents[1] / "games"
GAME_NAMES = ("bellweather", "iron_petal_unit", "ember_hollow", "the_grain")
PAYLOAD = GAMES / "_shared" / "runtime" / "addons" / "demo_support"


def package_project(name: str, destination: Path) -> Path:
    if name not in GAME_NAMES:
        raise ValueError(f"unknown game: {name}")
    source = GAMES / name
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"destination already exists: {destination}")
    if destination.resolve().is_relative_to(GAMES.resolve()):
        raise ValueError("destination must be outside the maintained game sources")
    addon = source / "addons" / "demo_support"
    if addon.resolve() != PAYLOAD.resolve():
        raise ValueError("the game's addon does not resolve to its declared private payload")
    entries = [
        source / part
        for part in ("project.godot", "main.gd", "main.gd.uid", "main.tscn", "gameplay", "scenes")
    ]
    for entry in [*entries, PAYLOAD]:
        candidates = [entry, *entry.rglob("*")] if entry.is_dir() else [entry]
        if any(path.is_symlink() for path in candidates):
            raise ValueError(f"source contains an undeclared development link: {entry}")
        if not entry.exists():
            raise ValueError(f"game source is incomplete: {entry}")
    destination.mkdir(parents=True)
    try:
        for entry in entries:
            target = destination / entry.name
            if entry.is_dir():
                shutil.copytree(entry, target)
            else:
                shutil.copy2(entry, target)
        shutil.copytree(
            PAYLOAD,
            destination / "addons" / "demo_support",
            ignore=shutil.ignore_patterns("testing"),
        )
    except Exception:
        shutil.rmtree(destination)
        raise
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, choices=GAME_NAMES)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        made = package_project(args.project, args.destination)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"package_game_project: {exc}\n")
    print(f"Game source project written to {made}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
