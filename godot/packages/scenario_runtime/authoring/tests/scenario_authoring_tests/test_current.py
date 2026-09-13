"""Current source, catalog and wire conformance, with no game or provider dependencies."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest

from scenario_authoring import ScenarioError, compile_scenario, empty_catalog, read_catalog
from scenario_authoring.program import admit_program

CONFORMANCE = Path(__file__).resolve().parents[3] / "conformance/authoring"


def _json(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((CONFORMANCE / name).read_text(encoding="utf-8")))


def _compile(source: str | None = None) -> Any:
    return compile_scenario(
        source or (CONFORMANCE / "bridge.scenario").read_text(encoding="utf-8"),
        catalog=_json("catalog.json"),
        capabilities=_json("capabilities.json"),
        source_name="bridge.scenario",
    )


@pytest.mark.parametrize(
    "schema",
    [
        {},
        {"type": "uninstalled"},
        {"type": "json", "required": "yes"},
        {"type": "object", "additional_properties": 1},
        {"type": "number", "min": 5, "max": 2},
        {"type": "number", "min": True},
        {"type": "number", "max": float("inf")},
        {"type": "string", "enum": "closed"},
        {"type": "array", "items": {}},
        {"type": "object", "properties": {"unused": {"type": "unknown"}}},
        {"type": "string", "default": False},
        {"type": "json", "callback": "execute"},
    ],
)
def test_unused_installed_parameter_schemas_are_admitted_before_content(
    schema: dict[str, Any],
) -> None:
    capabilities = {"unused": {"version": 1, "parameters": {"value": schema}}}
    with pytest.raises(ScenarioError):
        read_catalog(empty_catalog(), capabilities)


def test_schema_nesting_has_the_same_native_depth_limit() -> None:
    schema: dict[str, Any] = {"type": "json"}
    for _ in range(64):
        schema = {"type": "array", "items": schema}
    read_catalog(empty_catalog(), {"unused": {"version": 1, "parameters": {"value": schema}}})
    schema = {"type": "array", "items": schema}
    with pytest.raises(ScenarioError, match="64 levels"):
        read_catalog(empty_catalog(), {"unused": {"version": 1, "parameters": {"value": schema}}})


def test_authored_source_matches_the_shipped_cross_language_program() -> None:
    compiled = _compile()
    assert compiled.program == _json("bridge.program.json")
    assert compiled.source_map == _json("bridge.map.json")
    assert compiled.program["required_capabilities"] == {"particle": 1}
    assert compiled.program_sha256 == _compile().program_sha256


def test_fixed_and_world_bound_dialogue_need_no_staging_contract() -> None:
    compiled = compile_scenario("""scenario warning
speaker scout "Scout"
@warning
scout "Incoming!" profile=bubble anchor=scout portrait=false
@done
end delivered
""")
    line = compiled.program["nodes"][0]
    assert line["presentation"] == {
        "channel": "dialogue",
        "profile": "bubble",
        "anchor": "scout",
        "portrait": False,
    }
    assert "stages" not in compiled.program
    assert "game_id" not in compiled.program


def test_named_and_inline_effects_share_typed_defaults_and_validation() -> None:
    catalog = read_catalog(_json("catalog.json"), _json("capabilities.json"))
    named = catalog.effect({"preset": "embers", "parameters": {"rate": 8}})
    inline = catalog.effect({"type": "particle", "parameters": {"sprite_id": "ember", "rate": 8}})
    assert named == inline
    assert named["parameters"]["tint"] == [1, 1, 1, 1]
    assert named["version"] == 1


def test_a_new_noun_needs_no_new_capability_or_compiler() -> None:
    document = _json("catalog.json")
    document["definitions"]["snow"] = {
        "type": "particle",
        "parameters": {"sprite_id": "snowflake", "rate": 3},
        "overrides": [],
    }
    catalog = read_catalog(document, _json("capabilities.json"))
    assert catalog.effect({"preset": "snow"})["parameters"]["sprite_id"] == "snowflake"
    source = (
        "scenario snow\n@fall\nstart snow as weather\n"
        '@watch\n"It is snowing."\n@end\nend complete\n'
    )
    compiled = compile_scenario(source, catalog=document, capabilities=_json("capabilities.json"))
    assert compiled.program["required_capabilities"] == {"particle": 1}


@pytest.mark.parametrize(
    ("reference", "message"),
    [
        ({"preset": "absent"}, "unknown preset"),
        ({"preset": "embers", "parameters": {"sprite_id": "other"}}, "does not expose"),
        (
            {"type": "particle", "parameters": {"sprite_id": "ember", "rate": True}},
            "expected number",
        ),
        ({"type": "particle", "parameters": {"sprite_id": "ember", "rate": -1}}, "minimum"),
        ({"type": "particle", "parameters": {"sprite_id": "ember", "rate": 201}}, "maximum"),
        ({"type": "particle", "parameters": {}}, "required parameter"),
        (
            {"type": "particle", "parameters": {"sprite_id": "ember", "code": "run"}},
            "unknown parameters",
        ),
        ({"type": "particle", "preset": "embers"}, "exactly one"),
    ],
)
def test_effect_refusals_happen_before_execution(reference: dict[str, Any], message: str) -> None:
    catalog = read_catalog(_json("catalog.json"), _json("capabilities.json"))
    with pytest.raises(ScenarioError, match=message):
        catalog.effect(reference)


def test_multiline_presentation_gates_and_completion_relative_cues() -> None:
    compiled = _compile("""scenario contact
speaker guide "Guide"
@contact
guide key contact_caption
    present {
        "profile":"front_view",
        "portrait":false,
        "camera":{"target":[0.2,0.5],"duration":1.5}
    }
    gate operation_completed:contact finish_on_advance=false
    advance_mode on_gates
    cue feedback on operation_completed:contact after 0.2 start embers as glow duration=0.1
@done
end complete
""")
    line = compiled.program["nodes"][0]
    assert line["advance_mode"] == "on_gates"
    assert line["presentation"]["camera"] == {"target": [0.2, 0.5], "duration": 1.5}
    assert line["gates"] == [{"event": "operation_completed:contact", "finish_on_advance": False}]
    assert line["cues"][0]["after"] == 0.2


def test_choice_prompt_keeps_cues_gates_and_finite_string_fact_assignments() -> None:
    compiled = _compile()
    choice = next(node for node in compiled.program["nodes"] if node["kind"] == "choice")
    choice["gates"] = [{"event": "text_revealed", "finish_on_advance": True}]
    choice["cues"] = [copy.deepcopy(compiled.program["nodes"][1]["cues"][0])]
    admit_program(compiled.program, read_catalog(_json("catalog.json"), _json("capabilities.json")))
    choice["options"][0]["set"]["reply"] = "undeclared"
    with pytest.raises(ScenarioError, match="enum"):
        admit_program(
            compiled.program, read_catalog(_json("catalog.json"), _json("capabilities.json"))
        )


def test_reusable_sequences_expand_stable_ids_and_operation_instances() -> None:
    compiled = _compile("""scenario repeat
speaker guide "Guide"
sequence flourish:
    @burst
    start particle({"sprite_id":"spark"}) as flash target=$actor
    @wait
    wait operation=flash
    @utterance
    say $actor "$words"
@first
use flourish with={"actor":"guide","words":"One."}
@second
use flourish with={"actor":"guide","words":"Two."}
@done
end complete
""")
    nodes = {node["id"]: node for node in compiled.program["nodes"]}
    assert nodes["first__burst"]["instance_id"] == "first__flash"
    assert nodes["first__wait"]["operation"] == "first__flash"
    assert nodes["first__utterance"]["text"] == "One."
    assert nodes["first__utterance"]["next"] == "second"
    assert nodes["second__utterance"]["text"] == "Two."
    assert compiled.source_map["second__utterance"]["sequence"] == "flourish"


def test_recursive_sequence_calls_are_refused() -> None:
    with pytest.raises(ScenarioError, match="recursive"):
        compile_scenario("""scenario recursion
sequence recurse:
    @again
    use recurse
@entry
use recurse
@done
end complete
""")


def test_dollar_text_is_literal_outside_explicit_template_parameters() -> None:
    compiled = compile_scenario('scenario prices\n@price\n"$100 is enough."\n@done\nend complete\n')
    assert compiled.program["nodes"][0]["text"] == "$100 is enough."


def test_source_line_diagnostics_and_stable_ids_are_not_derived_from_order() -> None:
    source = 'scenario stable\n@opening\n"Hello."\n@done\nend complete\n'
    before = compile_scenario(source, source_name="test.scenario")
    after = compile_scenario("# New comment\n" + source, source_name="test.scenario")
    assert before.program == after.program
    assert after.source_map["opening"]["line"] == before.source_map["opening"]["line"] + 1
    with pytest.raises(ScenarioError, match=r"test.scenario:3"):
        compile_scenario("scenario bad\n@opening\nwait nonsense\n", source_name="test.scenario")


def test_a_reachable_invisible_trap_is_refused_even_when_another_path_ends() -> None:
    with pytest.raises(ScenarioError, match="invisible instruction cycle"):
        compile_scenario("""scenario trap
@question
menu:
    finish "Finish." -> done
    trap "Wait forever." -> loop
@loop
jump loop
@done
end complete
""")


def test_required_capability_versions_are_exact() -> None:
    with pytest.raises(ScenarioError, match="required version 2"):
        compile_scenario(
            'scenario versions\nrequire particle 2\n@hello\n"Hello."\n@done\nend complete\n',
            catalog=_json("catalog.json"),
            capabilities=_json("capabilities.json"),
        )


def test_empty_malformed_catalog_is_not_silently_replaced() -> None:
    with pytest.raises(ScenarioError, match="catalog: fields"):
        compile_scenario("scenario simple\n@done\nend complete\n", catalog={})
    assert read_catalog(empty_catalog(), {}).document["revision"] == "1"


@pytest.mark.parametrize(
    "instruction", ["set ready=true", 'menu:\n    yes "Yes." -> done set={"ready":true}']
)
def test_external_facts_can_be_read_but_are_only_changed_by_the_game(instruction: str) -> None:
    source = (
        "scenario facts\nfact ready external = false\n@change\n"
        f"{instruction}\n@done\nend complete\n"
    )
    with pytest.raises(ScenarioError, match="game-owned and read-only"):
        compile_scenario(source)


def test_zero_duration_wait_is_not_an_escape_from_silent_cycle_admission() -> None:
    source = """scenario trap
@question
menu:
    finish "Finish." -> done
    trap "Wait." -> wait
@wait
wait duration=0 next=wait
@done
end complete
"""
    with pytest.raises(ScenarioError, match="invisible instruction cycle"):
        compile_scenario(source)


def test_automatic_line_requires_an_actual_gate() -> None:
    with pytest.raises(ScenarioError, match="requires at least one explicit gate"):
        compile_scenario(
            'scenario automatic\n@line\n"Hello." advance_mode=on_gates\n@done\nend complete\n'
        )
