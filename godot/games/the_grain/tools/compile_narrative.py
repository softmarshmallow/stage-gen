#!/usr/bin/env python3
"""Compile The Grain's authored presentation sequence without generating assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scenario_authoring import compile_scenario

NARRATIVE = Path(__file__).resolve().parents[1] / "narrative"


def compile_narrative(*, check: bool = False, narrative: Path = NARRATIVE) -> None:
    source = narrative / "e1_way_in.scenario"
    compiled = compile_scenario(
        source.read_text(encoding="utf-8"),
        catalog=json.loads((narrative / "catalog.json").read_text(encoding="utf-8")),
        capabilities=json.loads(
            (narrative.parent / "presentation/scenario_capabilities.json").read_text(
                encoding="utf-8"
            )
        ),
        source_name=source.name,
    )
    for name, value in (
        ("e1_way_in.json", compiled.program),
        ("e1_way_in.map.json", compiled.source_map),
    ):
        expected = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
        target = narrative / name
        if check:
            if not target.is_file() or target.read_text(encoding="utf-8") != expected:
                raise ValueError(f"Compiled Grain narrative is stale: {name}")
        else:
            target.write_text(expected, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    compile_narrative(check=arguments.check)
    print("PASS The Grain authored narrative matches its compiled program")


if __name__ == "__main__":
    main()
