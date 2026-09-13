#!/usr/bin/env python3
"""Compile Command Link's authored mission, offline and without asset generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scenario_authoring import compile_scenario

NARRATIVE = Path(__file__).resolve().parents[1] / "narrative"


def compile_mission(*, check: bool = False, narrative: Path = NARRATIVE) -> None:
    source = narrative / "mission.scenario"
    compiled = compile_scenario(
        source.read_text(encoding="utf-8"),
        catalog=json.loads((narrative / "catalog.json").read_text()),
        capabilities=json.loads(
            (narrative.parent / "presentation/scenario_capabilities.json").read_text()
        ),
        source_name=source.name,
    )
    for name, value in (
        ("mission.json", compiled.program),
        ("mission.map.json", compiled.source_map),
    ):
        expected = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
        target = narrative / name
        if check:
            if not target.is_file() or target.read_text(encoding="utf-8") != expected:
                raise ValueError(f"Compiled mission is stale: {name}")
        else:
            target.write_text(expected, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    compile_mission(check=arguments.check)
    print("PASS Command Link authored mission matches its compiled program")


if __name__ == "__main__":
    main()
