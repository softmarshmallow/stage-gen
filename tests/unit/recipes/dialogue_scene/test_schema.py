from __future__ import annotations

import re
from collections.abc import Mapping

from stage_gen.recipes.dialogue_scene.models import DialogueScenePlanDraft
from stage_gen.recipes.dialogue_scene.schema import (
    JSON_SCHEMA_STANDARD_KEYS,
    dialogue_plan_json_schema,
)

_SNAKE_CASE = re.compile(r"^[a-z][a-z0-9_]*$")


def test_definition_names_and_refs_are_canonical_lower_snake_case() -> None:
    schema = dialogue_plan_json_schema()
    definitions = schema["$defs"]
    assert isinstance(definitions, dict)
    assert set(definitions) == {
        "expression_directions",
        "shared_locks",
    }
    refs = _values_for_key(schema, "$ref")
    assert refs
    targets: set[str] = set()
    for ref in refs:
        assert isinstance(ref, str)
        targets.add(ref.removeprefix("#/$defs/"))
    assert targets <= set(definitions)


def test_standard_keywords_remain_exact_and_application_properties_are_snake_case() -> None:
    raw = DialogueScenePlanDraft.model_json_schema()
    normalized = dialogue_plan_json_schema()
    seen_keywords: set[str] = set()
    _assert_schema_keys(normalized, seen_keywords)
    assert seen_keywords <= JSON_SCHEMA_STANDARD_KEYS
    assert {"$defs", "$ref", "additionalProperties"} <= seen_keywords
    assert _values_for_key(normalized, "additionalProperties")
    for keyword in ("maxLength", "minLength"):
        assert _values_for_key(raw, keyword)
        assert not _values_for_key(normalized, keyword)
    assert not _values_for_key(normalized, "pattern")
    assert not _values_for_key(normalized, "default")
    _assert_all_properties_required(normalized)


def _assert_schema_keys(value: object, seen_keywords: set[str]) -> None:
    if isinstance(value, list):
        for item in value:
            _assert_schema_keys(item, seen_keywords)
        return
    if not isinstance(value, Mapping):
        return
    for key, item in value.items():
        seen_keywords.add(key)
        if key in {"$defs", "properties"}:
            assert isinstance(item, Mapping)
            for application_key, definition in item.items():
                assert _SNAKE_CASE.fullmatch(application_key)
                _assert_schema_keys(definition, seen_keywords)
        else:
            assert key in JSON_SCHEMA_STANDARD_KEYS
            _assert_schema_keys(item, seen_keywords)


def _values_for_key(value: object, target: str) -> list[object]:
    result: list[object] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == target:
                result.append(item)
            result.extend(_values_for_key(item, target))
    elif isinstance(value, list):
        for item in value:
            result.extend(_values_for_key(item, target))
    return result


def _assert_all_properties_required(value: object) -> None:
    if isinstance(value, Mapping):
        properties = value.get("properties")
        if isinstance(properties, Mapping):
            assert value.get("required") == list(properties)
        for item in value.values():
            _assert_all_properties_required(item)
    elif isinstance(value, list):
        for item in value:
            _assert_all_properties_required(item)
