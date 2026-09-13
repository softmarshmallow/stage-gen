#!/usr/bin/env python3
"""Compile Afterlight's episode against its installed presentation capabilities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scenario_authoring import compile_scenario

PROJECT = Path(__file__).resolve().parents[1]
NARRATIVE = PROJECT / "narrative"
CAPABILITIES = PROJECT.parents[1] / (
    "packages/scenario_runtime/addons/scenario_runtime/presentation/front_types.json"
)


def compile_narrative(*, check: bool = False) -> None:
    source = NARRATIVE / "episode.scenario"
    compiled = compile_scenario(
        source.read_text(encoding="utf-8"),
        catalog=json.loads((NARRATIVE / "catalog.json").read_text()),
        capabilities=json.loads(CAPABILITIES.read_text()),
        source_name=source.name,
    )
    for name, value in (
        ("program.json", compiled.program),
        ("program.map.json", compiled.source_map),
    ):
        target = NARRATIVE / name
        if check:
            if not target.is_file() or json.loads(target.read_text()) != value:
                raise ValueError(f"Compiled Afterlight episode is stale: {name}")
        else:
            target.write_text(
                json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    compile_narrative(check=arguments.check)
    print("PASS Afterlight authored episode matches its compiled program")


if __name__ == "__main__":
    main()
