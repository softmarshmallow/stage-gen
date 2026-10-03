"""Export the catalog the site and the viewer read, and the ``gnode`` command-line reference.

    uv run python scripts/catalog.py --out DIR [--examples DIR] [--allow-missing-examples]
    uv run python scripts/catalog.py --out DIR --check

Writes ``catalog.json`` (every installed workflow, its steps, identities, offline sample plan
and pinned examples) and ``cli.json`` (the ``gnode`` argparse tree) into ``--out``, unless
``--check`` asks only for the drift checks or something drifted. Prints a JSON summary and
exits 1 when any drift problem is found.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts/catalog.py", description="write catalog.json and cli.json, or check drift"
    )
    parser.add_argument(
        "--out", type=Path, required=True, dest="out_dir", help="folder to write them into"
    )
    parser.add_argument("--examples", type=Path, dest="examples_dir", help="the example store")
    parser.add_argument(
        "--allow-missing-examples",
        action="store_true",
        help="build without pinned store examples that are absent; a mismatch still fails",
    )
    parser.add_argument("--check", action="store_true", help="run the drift checks only")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    from stage_gen.workflows._catalog import default_examples_dir, export

    output = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    result = export(
        args.out_dir,
        examples_dir=args.examples_dir or default_examples_dir(),
        allow_missing_examples=args.allow_missing_examples,
        check=args.check,
    )
    output.write(
        json.dumps(
            {
                "workflows": result.workflows,
                "catalog": None if result.path is None else str(result.path),
                "cli": None if result.reference is None else str(result.reference),
                "problems": list(result.problems),
            },
            indent=2,
        )
        + "\n"
    )
    return 1 if result.problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
