"""Private collection adapter for package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TextIO

from demo_game_collection.game_package import resolve_prepared_package


def dispatch(args: argparse.Namespace, *, stdout: TextIO) -> int:
    resolved_package = resolve_prepared_package(Path(args.input_path))
    if args.package_command == "digest":
        stdout.write(f"{resolved_package.closure_sha256}\n")
    else:
        package_report = {"valid": True, **resolved_package.identity()}
        stdout.write(f"{json.dumps(package_report, sort_keys=True, separators=(',', ':'))}\n")
    return 0
