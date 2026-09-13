"""Portable JSON values and installed capability schemas shared by authoring tools."""

from __future__ import annotations

import copy
import math
import re
from collections.abc import Mapping
from typing import Any

ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
FIELD_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
VALUE_TYPES = {"number", "integer", "string", "boolean", "array", "object", "json"}
SCHEMA_FIELDS = {
    "type",
    "required",
    "default",
    "enum",
    "min",
    "max",
    "items",
    "properties",
    "additional_properties",
}


class ScenarioError(ValueError):
    """An authored document or content package violates the public contract."""


def logical_id(value: object, location: str) -> str:
    if not isinstance(value, str) or len(value) > 128 or not ID_PATTERN.fullmatch(value):
        raise ScenarioError(f"{location}: expected a stable logical identifier")
    return value


def json_value(value: Any, location: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return copy.deepcopy(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ScenarioError(f"{location}: numbers must be finite")
        return value
    if isinstance(value, list):
        return [json_value(item, f"{location}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: json_value(item, f"{location}.{key}") for key, item in value.items()}
    raise ScenarioError(f"{location}: expected portable JSON data")


def validate_value(value: Any, schema: Mapping[str, Any], location: str) -> Any:
    kind = schema.get("type", "json")
    if not isinstance(kind, str) or kind not in VALUE_TYPES:
        raise ScenarioError(f"{location}: unsupported parameter type {kind!r}")
    matches = {
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "array": isinstance(value, list),
        "object": isinstance(value, dict),
        "json": True,
    }
    if not matches[kind]:
        raise ScenarioError(f"{location}: expected {kind}")
    result = json_value(value, location)
    if "enum" in schema and not any(
        type(value) is type(option) and value == option for option in schema["enum"]
    ):
        raise ScenarioError(f"{location}: value is outside the declared enum")
    if kind in {"number", "integer"}:
        if "min" in schema and value < schema["min"]:
            raise ScenarioError(f"{location}: value is below minimum {schema['min']}")
        if "max" in schema and value > schema["max"]:
            raise ScenarioError(f"{location}: value is above maximum {schema['max']}")
    elif kind == "array":
        result = [
            validate_value(item, schema.get("items", {"type": "json"}), f"{location}[{index}]")
            for index, item in enumerate(value)
        ]
    elif kind == "object":
        result = validate_parameters(
            value,
            schema.get("properties", {}),
            location,
            additional=bool(schema.get("additional_properties", False)),
        )
    return result


def validate_parameters(
    values: Mapping[str, Any],
    schemas: Mapping[str, Any],
    location: str,
    *,
    additional: bool = False,
) -> dict[str, Any]:
    unknown = set(values) - set(schemas)
    if unknown and not additional:
        raise ScenarioError(f"{location}: unknown parameters {', '.join(sorted(unknown))}")
    result = {name: json_value(values[name], f"{location}.{name}") for name in unknown}
    for name, schema in schemas.items():
        if name in values:
            result[name] = validate_value(values[name], schema, f"{location}.{name}")
        elif "default" in schema:
            result[name] = validate_value(schema["default"], schema, f"{location}.{name}")
        elif schema.get("required", False):
            raise ScenarioError(f"{location}.{name}: required parameter is missing")
    return result


def validate_capabilities(value: Any) -> dict[str, Any]:
    value = json_value(value, "capabilities")
    if not isinstance(value, dict):
        raise ScenarioError("capabilities: expected an object")
    for name, definition in value.items():
        logical_id(name, "capability name")
        if not isinstance(definition, dict):
            raise ScenarioError(f"capabilities.{name}: expected a definition")
        version = definition.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ScenarioError(f"capabilities.{name}: version must be a positive integer")
        schemas = definition.get("parameters", {})
        if not isinstance(schemas, dict):
            raise ScenarioError(f"capabilities.{name}.parameters: expected an object")
        _validate_schemas(schemas, f"capabilities.{name}.parameters")
        for flag in ("reconstructable", "finishable"):
            if flag in definition and not isinstance(definition[flag], bool):
                raise ScenarioError(f"capabilities.{name}.{flag}: expected boolean")
    return value


def _validate_schemas(schemas: dict[str, Any], location: str, depth: int = 0) -> None:
    if depth > 64:
        raise ScenarioError(f"{location}: parameter schema nesting exceeds 64 levels")
    for name, schema in schemas.items():
        if not FIELD_PATTERN.fullmatch(name) or not isinstance(schema, dict):
            raise ScenarioError(f"{location}.{name}: expected snake-case parameter schema")
        unknown = set(schema) - SCHEMA_FIELDS
        if unknown:
            raise ScenarioError(
                f"{location}.{name}: unknown parameter schema fields {', '.join(sorted(unknown))}"
            )
        if not isinstance(schema.get("type"), str) or schema.get("type") not in VALUE_TYPES:
            raise ScenarioError(f"{location}.{name}: schema needs an explicit supported type")
        for flag in ("required", "additional_properties"):
            if flag in schema and not isinstance(schema[flag], bool):
                raise ScenarioError(f"{location}.{name}.{flag}: expected boolean")
        if "properties" in schema:
            if not isinstance(schema["properties"], dict):
                raise ScenarioError(f"{location}.{name}.properties: expected object")
            _validate_schemas(schema["properties"], f"{location}.{name}.properties", depth + 1)
        if "items" in schema:
            _validate_schemas({"item": schema["items"]}, f"{location}.{name}.items", depth + 1)
        if "enum" in schema and not isinstance(schema["enum"], list):
            raise ScenarioError(f"{location}.{name}.enum: expected array")
        for bound in ("min", "max"):
            if bound in schema and (
                not isinstance(schema[bound], (int, float)) or isinstance(schema[bound], bool)
            ):
                raise ScenarioError(f"{location}.{name}.{bound}: expected number")
        if "min" in schema and "max" in schema and schema["min"] > schema["max"]:
            raise ScenarioError(f"{location}.{name}: minimum exceeds maximum")
        if "default" in schema:
            validate_value(schema["default"], schema, f"{location}.{name}.default")
