"""``demo-games example export <game>``: publish the examples a game made into the store.

The game owns its examples: their declaration, prose, importers and pins. This command
only selects the game and reports what was written. The product reads the store and never
names a game.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TextIO


def dispatch(args: argparse.Namespace, *, stdout: TextIO) -> int:
    from bellweather_pipeline.examples import REPOSITORY_ROOT, export, read_manifest

    store = Path(args.store) if args.store else REPOSITORY_ROOT / "out" / "examples"
    exported = export(read_manifest(), store=store.resolve(), from_frozen=args.from_frozen)
    report = {
        "game": args.game,
        "store": str(store),
        "mode": "frozen" if args.from_frozen else "rederived",
        "examples": [
            {"id": item.example_id, "currency": item.currency, "directory": str(item.directory)}
            for item in exported
        ],
    }
    stdout.write(f"{json.dumps(report, sort_keys=True, separators=(',', ':'))}\n")
    return 0
