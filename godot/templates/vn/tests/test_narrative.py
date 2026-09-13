"""The starter's shipped program and text are its authored content closure."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scenario_authoring import compile_scenario

TEMPLATE = Path(__file__).resolve().parents[1]


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_shipped_starter_program_and_source_map_match_authored_source() -> None:
    narrative = TEMPLATE / "narrative"
    result = compile_scenario(
        (narrative / "episode.scenario").read_text(encoding="utf-8"),
        catalog=_json(narrative / "catalog.json"),
        capabilities=_json(TEMPLATE / "bindings/capabilities.json"),
        source_name="episode.scenario",
    )
    assert result.program == _json(narrative / "episode.json")
    assert result.source_map == _json(narrative / "episode.map.json")
    assert result.program["required_capabilities"] == {"point_contact": 1, "radial_burst": 1}


def test_all_authored_text_and_choices_have_localized_content() -> None:
    program = _json(TEMPLATE / "narrative/episode.json")
    words = _json(TEMPLATE / "text/en.json")
    keys = {
        item["text_key"]
        for node in program["nodes"]
        for item in [node, *node.get("options", [])]
        if "text_key" in item
    }
    assert keys <= words.keys()
    assert {"reply_light", "reply_note", "contact", "ending"} <= keys
