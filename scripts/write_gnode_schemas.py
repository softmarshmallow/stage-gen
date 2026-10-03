#!/usr/bin/env python3
"""Check or write gnode's published JSON Schemas in src/gnode/schemas/.

uv run python scripts/write_gnode_schemas.py --check
uv run python scripts/write_gnode_schemas.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gnode import document_schemas

FOLDER = Path(__file__).resolve().parents[1] / "src/gnode/schemas"


def render(schema: dict[str, object]) -> str:
    return json.dumps(schema, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare without writing")
    args = parser.parse_args(argv)
    schemas = {name: render(schema) for name, schema in document_schemas().items()}
    present = {path.name for path in FOLDER.glob("*.schema.json")} if FOLDER.is_dir() else set()
    stale = sorted(
        name
        for name, text in schemas.items()
        if not (FOLDER / name).is_file() or (FOLDER / name).read_text(encoding="utf-8") != text
    )
    extra = sorted(present - set(schemas))
    if args.check:
        for name in stale:
            print(f"stale   {name}")
        for name in extra:
            print(f"extra   {name}")
        if stale or extra:
            print("run scripts/write_gnode_schemas.py to rewrite them")
            return 1
        print(f"gnode schemas are current: {len(schemas)}")
        return 0
    FOLDER.mkdir(parents=True, exist_ok=True)
    for name, text in schemas.items():
        (FOLDER / name).write_text(text, encoding="utf-8")
    for name in extra:
        (FOLDER / name).unlink()
    print(f"wrote {len(schemas)} schemas to src/gnode/schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
