#!/usr/bin/env python3
"""Validate the canonical current-only game source package."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from stage_gen.orchestration.game_package import (
    MAIN_GAME_SELECTOR_REF,
    GamePackageValidationError,
    invalid_game_package_report,
    validate_game_package,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate one exact-current canonical game source closure without rewriting it."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="workspace root containing library/ and examples/ (default: current directory)",
    )
    parser.add_argument(
        "--selector",
        default=MAIN_GAME_SELECTOR_REF,
        help=f"selector path (must be {MAIN_GAME_SELECTOR_REF})",
    )
    parser.add_argument(
        "--require-tracked",
        action="store_true",
        help="also reject any closure source that is not Git-tracked",
    )
    parser.add_argument(
        "--require-committed",
        action="store_true",
        help="also require every validated closure byte to match Git HEAD",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = validate_game_package(
            args.root,
            selector_ref=args.selector,
            require_tracked=args.require_tracked,
            require_committed=args.require_committed,
        )
    except GamePackageValidationError as error:
        report = invalid_game_package_report(error)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
