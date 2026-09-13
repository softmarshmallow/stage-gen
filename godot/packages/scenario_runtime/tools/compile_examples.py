#!/usr/bin/env python3
"""Compile the package's procedural examples through its public authoring API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scenario_authoring import compile_scenario

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
OWNED = ("combat_dialogue", "world_bubbles", "catalog_effects")


def compile_examples(*, check: bool = False) -> None:
    capabilities = json.loads((EXAMPLES / "capabilities.json").read_text())
    for name in OWNED:
        folder = EXAMPLES / name
        source = folder / "dialogue.scenario"
        result = compile_scenario(
            source.read_text(),
            catalog=json.loads((folder / "catalog.json").read_text()),
            capabilities=capabilities,
            source_name=source.name,
        )
        for filename, value in (
            ("program.json", result.program),
            ("program.map.json", result.source_map),
        ):
            path = folder / filename
            if check:
                if not path.is_file() or json.loads(path.read_text()) != value:
                    raise ValueError(f"Stale procedural example: {name}/{filename}")
            else:
                path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    compile_examples(check=parser.parse_args().check)
    print("PASS procedural Scenario examples match authored source")


if __name__ == "__main__":
    main()
