"""Game-owned nouns resolve to typed installed capabilities before activation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .validation import (
    ScenarioError,
    json_value,
    logical_id,
    validate_capabilities,
    validate_parameters,
)


@dataclass(frozen=True)
class Catalog:
    document: dict[str, Any]
    capabilities: dict[str, Any]

    def effect(self, reference: Any, location: str = "effect") -> dict[str, Any]:
        if not isinstance(reference, dict) or set(reference) - {"type", "preset", "parameters"}:
            raise ScenarioError(f"{location}: expected type or preset with parameters")
        if ("type" in reference) == ("preset" in reference):
            raise ScenarioError(f"{location}: exactly one of type or preset is required")
        parameters = reference.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ScenarioError(f"{location}.parameters: expected an object")
        if "preset" in reference:
            name = logical_id(reference["preset"], f"{location}.preset")
            definition = self.document["definitions"].get(name)
            if definition is None:
                raise ScenarioError(f"{location}: unknown preset {name!r}")
            denied = set(parameters) - set(definition.get("overrides", []))
            if denied:
                raise ScenarioError(
                    f"{location}: preset does not expose {', '.join(sorted(denied))}"
                )
            parameters = {**definition.get("parameters", {}), **parameters}
            kind = definition["type"]
        else:
            kind = logical_id(reference["type"], f"{location}.type")
        if kind not in self.capabilities:
            raise ScenarioError(f"{location}: required capability {kind!r} is not installed")
        capability = self.capabilities[kind]
        return {
            "type": kind,
            "version": capability["version"],
            "parameters": validate_parameters(
                parameters, capability.get("parameters", {}), f"{location}.parameters"
            ),
        }


def read_catalog(document: Any, capabilities: Any) -> Catalog:
    installed = validate_capabilities(capabilities)
    data = json_value(document, "catalog")
    if not isinstance(data, dict):
        raise ScenarioError("catalog: expected an object")
    expected = {"kind", "schema_version", "catalog_id", "revision", "definitions"}
    if set(data) != expected:
        raise ScenarioError(f"catalog: fields must be {', '.join(sorted(expected))}")
    if (
        data["kind"] != "scenario-catalog"
        or type(data["schema_version"]) is not int
        or data["schema_version"] != 1
    ):
        raise ScenarioError("catalog: expected scenario-catalog schema_version 1")
    logical_id(data["catalog_id"], "catalog.catalog_id")
    revision = data["revision"]
    if not isinstance(revision, str) or not revision.strip() or revision != revision.strip():
        raise ScenarioError("catalog.revision: expected a nonempty immutable revision string")
    if not isinstance(data["definitions"], dict):
        raise ScenarioError("catalog.definitions: expected an object")
    result = Catalog(data, installed)
    for name, definition in data["definitions"].items():
        logical_id(name, "catalog definition name")
        if not isinstance(definition, dict) or set(definition) - {
            "type",
            "parameters",
            "overrides",
        }:
            raise ScenarioError(f"catalog.definitions.{name}: expected typed definition")
        overrides = definition.get("overrides", [])
        if not isinstance(overrides, list) or any(not isinstance(item, str) for item in overrides):
            raise ScenarioError(f"catalog.definitions.{name}.overrides: expected parameter names")
        if len(set(overrides)) != len(overrides):
            raise ScenarioError(f"catalog.definitions.{name}.overrides: duplicate parameter name")
        normalized = result.effect(
            {"type": definition.get("type"), "parameters": definition.get("parameters", {})},
            f"catalog.definitions.{name}",
        )
        unknown = set(overrides) - set(installed[normalized["type"]].get("parameters", {}))
        if unknown:
            raise ScenarioError(
                f"catalog.definitions.{name}: unknown override parameters {sorted(unknown)}"
            )
    return result


def empty_catalog() -> dict[str, Any]:
    return {
        "kind": "scenario-catalog",
        "schema_version": 1,
        "catalog_id": "empty",
        "revision": "1",
        "definitions": {},
    }
