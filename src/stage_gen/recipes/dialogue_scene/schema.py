"""Recipe-owned canonical JSON Schema serialization for dialogue planning."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from stage_gen.components.structured_generation import canonicalize_strict_json_schema
from stage_gen.recipes.dialogue_scene.models import DialogueScenePlanDraft

# These are JSON Schema vocabulary, not application-owned persisted keys. Their
# spelling is fixed by the standard and must never be snake_case-normalized.
JSON_SCHEMA_STANDARD_KEYS = frozenset(
    {
        "$anchor",
        "$comment",
        "$defs",
        "$dynamicAnchor",
        "$dynamicRef",
        "$id",
        "$ref",
        "$schema",
        "$vocabulary",
        "additionalProperties",
        "allOf",
        "anyOf",
        "const",
        "contains",
        "contentEncoding",
        "contentMediaType",
        "contentSchema",
        "default",
        "dependentRequired",
        "dependentSchemas",
        "deprecated",
        "description",
        "else",
        "enum",
        "examples",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "format",
        "if",
        "items",
        "maxContains",
        "maxItems",
        "maxLength",
        "maxProperties",
        "maximum",
        "minContains",
        "minItems",
        "minLength",
        "minProperties",
        "minimum",
        "multipleOf",
        "not",
        "oneOf",
        "pattern",
        "patternProperties",
        "prefixItems",
        "properties",
        "propertyNames",
        "readOnly",
        "required",
        "then",
        "title",
        "type",
        "unevaluatedItems",
        "unevaluatedProperties",
        "uniqueItems",
        "writeOnly",
    }
)

_FIRST_CAPITAL = re.compile(r"(.)([A-Z][a-z]+)")
_SECOND_CAPITAL = re.compile(r"([a-z0-9])([A-Z])")
_SNAKE_CASE = re.compile(r"^[a-z][a-z0-9_]*$")


def dialogue_plan_json_schema() -> dict[str, Any]:
    """Return the exact strict plan schema sent to and persisted for the service."""

    raw = DialogueScenePlanDraft.model_json_schema()
    definitions = raw.get("$defs", {})
    if not isinstance(definitions, Mapping):
        raise ValueError("dialogue plan $defs must be an object")
    names = {str(name): _lower_snake(str(name)) for name in definitions}
    if len(set(names.values())) != len(names):
        raise ValueError("dialogue plan definition names collide after normalization")
    normalized = _normalize_schema(raw, definition_names=names)
    if not isinstance(normalized, dict):
        raise TypeError("dialogue plan schema must normalize to an object")
    return canonicalize_strict_json_schema(normalized)


def _normalize_schema(value: object, *, definition_names: Mapping[str, str]) -> object:
    if isinstance(value, list):
        return [_normalize_schema(item, definition_names=definition_names) for item in value]
    if not isinstance(value, Mapping):
        return value

    result: dict[str, object] = {}
    for raw_key, item in value.items():
        key = str(raw_key)
        if key == "$defs":
            if not isinstance(item, Mapping):
                raise ValueError("dialogue plan $defs must be an object")
            result[key] = {
                definition_names[str(name)]: _normalize_schema(
                    definition, definition_names=definition_names
                )
                for name, definition in item.items()
            }
            continue
        if key == "properties":
            if not isinstance(item, Mapping):
                raise ValueError("dialogue plan properties must be an object")
            properties: dict[str, object] = {}
            for property_name, definition in item.items():
                name = str(property_name)
                if not _SNAKE_CASE.fullmatch(name):
                    raise ValueError(f"dialogue plan property is not lower_snake_case: {name}")
                properties[name] = _normalize_schema(definition, definition_names=definition_names)
            result[key] = properties
            continue
        if key not in JSON_SCHEMA_STANDARD_KEYS:
            raise ValueError(f"unsupported dialogue plan JSON Schema key: {key}")
        if key == "$ref" and isinstance(item, str):
            prefix = "#/$defs/"
            target = item.removeprefix(prefix)
            if item.startswith(prefix) and target in definition_names:
                item = f"{prefix}{definition_names[target]}"
        result[key] = _normalize_schema(item, definition_names=definition_names)
    return result


def _lower_snake(value: str) -> str:
    first = _FIRST_CAPITAL.sub(r"\1_\2", value)
    return _SECOND_CAPITAL.sub(r"\1_\2", first).lower()
