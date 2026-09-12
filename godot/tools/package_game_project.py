#!/usr/bin/env python3
"""Copy a game source project with a real, closed private addon payload.

The checkout uses development links to one maintained demo_support source tree.
This command assembles ordinary source files for copying outside the repository;
it does not export a binary, generate media, or embed an existing asset run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from _shared.source_assembly import (  # noqa: E402 - standalone tool path bootstrap
    copy_files,
    files,
    staged_destination,
)

GAMES = Path(__file__).resolve().parents[1] / "games"
GAME_NAMES = ("bellweather", "iron_petal_unit", "ember_hollow", "the_grain")
PAYLOAD = GAMES / "_shared" / "runtime" / "addons" / "demo_support"
PACKAGES = GAMES.parent / "packages"
GAME_ADDONS = {
    name: (
        "demo_support",
        "content_io",
        *(() if name not in {"bellweather", "the_grain"} else ("scenario_runtime",)),
        *(() if name not in {"bellweather", "iron_petal_unit"} else ("sideview_rendering",)),
    )
    for name in GAME_NAMES
}


def package_project(name: str, destination: Path) -> Path:
    if name not in GAME_NAMES:
        raise ValueError(f"unknown game: {name}")
    source = GAMES / name
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"destination already exists: {destination}")
    if destination.resolve().is_relative_to(GAMES.resolve()):
        raise ValueError("destination must be outside the maintained game sources")
    payloads = {
        addon: PAYLOAD if addon == "demo_support" else PACKAGES / addon / "addons" / addon
        for addon in GAME_ADDONS[name]
    }
    for addon, payload in payloads.items():
        if (source / "addons" / addon).resolve() != payload.resolve():
            raise ValueError(f"The game's addon does not resolve to its declared payload: {addon}")
        if destination.resolve().is_relative_to(payload.resolve()):
            raise ValueError("destination must be outside maintained addon sources")
    entries = [
        source / part
        for part in ("project.godot", "main.gd", "main.gd.uid", "main.tscn", "gameplay", "scenes")
    ]
    selected: list[Path] = []
    for entry in entries:
        if not entry.exists() or entry.is_symlink():
            raise ValueError(f"game source is incomplete or linked: {entry}")
        if entry.is_dir():
            selected.extend(entry.relative_to(source) / child for child in files(entry))
        else:
            selected.append(entry.relative_to(source))
    payload_files = {
        addon: files(payload, frozenset({Path("testing")})) for addon, payload in payloads.items()
    }
    with staged_destination(destination) as temporary:
        source_hashes = copy_files(source, temporary, selected)
        license_hashes = copy_files(GAMES.parent, temporary, [Path("LICENSE")])
        addons = {
            addon: copy_files(payload, temporary / "addons" / addon, payload_files[addon])
            for addon, payload in payloads.items()
        }
        report = {
            "schema_version": 1,
            "kind": "godot_game_source",
            "game": name,
            "source_files": {**source_hashes, **license_hashes},
            "addon_files": addons,
        }
        (temporary / "assembly.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
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
