"""The richer Way In preserves its story and owns its presentation admission."""

from __future__ import annotations

import copy
import importlib.util
import json
import tomllib
from pathlib import Path
from typing import Any

import pytest

from scenario_authoring import ScenarioError, compile_scenario
from scenario_authoring.compatibility.v2 import RawIf, parse_scenario

GAME = Path(__file__).resolve().parents[2]
NARRATIVE = GAME / "narrative"


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _compile(catalog: dict[str, Any] | None = None) -> Any:
    return compile_scenario(
        (NARRATIVE / "e1_way_in.scenario").read_text(encoding="utf-8"),
        catalog=catalog if catalog is not None else _json(NARRATIVE / "catalog.json"),
        capabilities=_json(GAME / "presentation/scenario_capabilities.json"),
        source_name="e1_way_in.scenario",
    )


def _original_trace() -> tuple[list[dict[str, Any]], str, dict[str, bool]]:
    """Follow original jump edges; compare fact state at each spoken/narrated line."""
    source = (GAME / "inputs/scenarios/e1_way_in.scenario").read_text(encoding="utf-8")
    declarations = tomllib.loads(
        (GAME / "inputs/scenarios/e1_way_in.toml").read_text(encoding="utf-8")
    )
    blocks = {block.label: block for block in parse_scenario(source)}
    flags = {flag["flag_id"]: False for flag in declarations["flags"]}
    label = declarations["entry"]
    trace: list[dict[str, Any]] = []
    stage = ""
    cast: dict[str, dict[str, str]] = {}
    visited = set()
    while label not in visited:
        visited.add(label)
        for index, instruction in enumerate(blocks[label].statements):
            assert not isinstance(instruction, RawIf), "The original Way In has no branching"
            statement = instruction.model_dump()
            kind = statement["kind"]
            if kind == "stage":
                stage = statement["stage"]
            elif kind == "show":
                actor = statement["actor"]
                cast[actor] = {
                    "actor_id": actor,
                    "expression": statement["expression"],
                    "slot": statement["slot"],
                }
            elif kind == "hide":
                cast.pop(statement["actor"])
            elif kind == "line":
                speaker = statement["speaker"]
                if statement["expression"] is not None:
                    cast[speaker]["expression"] = statement["expression"]
                trace.append(
                    {
                        "statement_id": f"{label}#{index}",
                        "speaker": speaker or "",
                        "text": statement["text"],
                        "facts": flags.copy(),
                        "stage": stage,
                        "cast": copy.deepcopy(list(cast.values())),
                    }
                )
            elif kind == "set":
                flags[statement["flag"]] = statement["value"]
            elif kind == "jump":
                label = statement["target"]
                break
            elif kind == "end":
                return trace, statement["outcome"], flags
            else:
                raise AssertionError(f"The parity fixture gained an unsupported {kind}")
        else:
            raise AssertionError("The original block has no terminal instruction")
    raise AssertionError("The original Way In should have a finite, unbranched trace")


def _authored_trace() -> tuple[list[dict[str, Any]], str, dict[str, bool]]:
    program = _compile().program
    nodes = {node["id"]: node for node in program["nodes"]}
    catalog = _json(NARRATIVE / "catalog.json")["definitions"]
    facts = {name: declaration["default"] for name, declaration in program["facts"].items()}
    trace: list[dict[str, Any]] = []
    visited = set()
    node_id = program["entry"]
    while node_id not in visited:
        visited.add(node_id)
        node = nodes[node_id]
        if node["kind"] == "line":
            frame = catalog[node["cues"][0]["effect"]["preset"]]["parameters"]["to_frame"]
            trace.append(
                {
                    "statement_id": node["presentation"]["legacy_statement_id"],
                    "speaker": node.get("speaker", ""),
                    "text": node["text"],
                    "facts": facts.copy(),
                    "stage": frame["stage"],
                    "cast": frame["cast"],
                }
            )
        elif node["kind"] == "set":
            facts.update(node["values"])
        elif node["kind"] == "end":
            assert visited == set(nodes), "Every authored node must be exercised by the story"
            return trace, node["outcome"], facts
        else:
            raise AssertionError(f"Unexpected story instruction: {node['kind']}")
        node_id = node["next"]
    raise AssertionError("The authored Way In should have a finite, unbranched trace")


def test_every_line_speaker_cast_and_fact_timing_preserves_the_original_story() -> None:
    expected = _original_trace()
    assert len(expected[0]) == 47
    assert expected[1:] == (
        "first_bell",
        {"place_card_moved_twice": True, "suitcase_unopened": True},
    )
    assert _authored_trace() == expected


def test_compiled_narrative_and_source_map_are_current() -> None:
    path = GAME / "tools/compile_narrative.py"
    spec = importlib.util.spec_from_file_location("the_grain_compile_narrative", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.compile_narrative(check=True)


def test_every_frame_reference_belongs_to_existing_authored_assets() -> None:
    declarations = tomllib.loads(
        (GAME / "inputs/scenarios/e1_way_in.toml").read_text(encoding="utf-8")
    )
    stages = {entry["stage_id"] for entry in declarations["stages"]}
    cast = {entry["actor_id"]: entry for entry in declarations["cast"]}
    program = _compile().program
    assert program["speakers"] == [
        {"id": actor["actor_id"], "display_name": actor["display_name"]}
        for actor in declarations["cast"]
    ]
    assert program["required_capabilities"] == {"grain_frame": 1}
    catalog = _json(NARRATIVE / "catalog.json")["definitions"]
    used_presets = {
        cue["effect"]["preset"] for node in program["nodes"] for cue in node.get("cues", [])
    }
    assert used_presets == set(catalog), "The catalog should contain only this sequence's frames"
    assert len(catalog) < 47, "Repeated views should reuse named presets"
    for definition in catalog.values():
        assert definition["type"] == "grain_frame"
        for field in ("from_frame", "to_frame"):
            frame = definition["parameters"][field]
            assert frame["stage"] in stages
            actors = {actor["actor_id"] for actor in frame["cast"]}
            assert "henry" not in actors, "Henry remains an off-stage speaker"
            assert frame["focus"] == "" or frame["focus"] in actors
            for actor in frame["cast"]:
                assert actor["expression"] in cast[actor["actor_id"]]["expressions"]


def test_transition_clocks_gates_and_complete_frames_support_exact_continuation() -> None:
    program = _compile().program
    catalog = _json(NARRATIVE / "catalog.json")["definitions"]
    previous: dict[str, Any] | None = None
    frames: dict[str, Any] = {}
    for node in program["nodes"]:
        if node["kind"] != "line":
            continue
        assert node["presentation"]["chars_per_second"] == 42
        assert node["presentation"]["channel"] == "dialogue"
        assert node["presentation"]["profile"] == "bottom"
        assert node["gates"] == [
            {"event": "operation_completed:frame", "finish_on_advance": True},
            {"event": "text_revealed", "finish_on_advance": True},
        ]
        assert len(node["cues"]) == 1
        cue = node["cues"][0]
        assert cue["at"] == 0
        assert cue["scope"] == "node"
        assert cue["instance_id"] == "frame"
        assert cue["target"] == "stage"
        assert "duration" not in cue, "The binding reports completion after its actual transition"
        parameters = catalog[cue["effect"]["preset"]]["parameters"]
        if previous is not None:
            assert parameters["from_frame"] == previous
        else:
            assert parameters["from_frame"] == parameters["to_frame"]
        previous = parameters["to_frame"]
        frames[node["id"]] = parameters

    assert frames["the_service_door_09"]["seconds"] == 0.45
    assert frames["the_dark_floor_03"]["seconds"] == 0.6
    assert frames["the_service_lift_03"]["seconds"] == 0.6
    assert frames["the_winter_room_03"]["seconds"] == 0.8
    assert frames["the_winter_room_03"]["to_frame"]["zoom"] == 1.06
    assert frames["the_winter_room_10"]["to_frame"]["focus"] == "lydia"
    assert frames["the_winter_room_10"]["to_frame"]["zoom"] == 1.1
    assert frames["the_winter_room_11"]["to_frame"]["focus"] == ""
    assert frames["the_winter_room_11"]["to_frame"]["zoom"] == 1
    assert frames["the_green_ink_03"]["to_frame"]["focus"] == ""


@pytest.mark.parametrize(
    ("field", "value"),
    [("zoom", 1.3), ("zoom", True), ("undeclared_camera_hook", "call_game")],
)
def test_installed_frame_contract_refuses_unsupported_content(field: str, value: Any) -> None:
    catalog = _json(NARRATIVE / "catalog.json")
    first = next(iter(catalog["definitions"].values()))
    first["parameters"]["to_frame"][field] = value
    with pytest.raises(ScenarioError):
        _compile(catalog)
