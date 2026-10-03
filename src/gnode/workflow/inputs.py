"""A workflow's ``inputs:``: the shorthand, the JSON Schema it compiles to, and loading.

The shorthand types are ``string``, ``integer``, ``number``, ``boolean``, ``file`` (with
``kind``), ``files``, ``list`` (``items``), ``map`` (``values``) and nested objects (a
mapping of fields with no ``type``). Keywords are snake_case and become their JSON Schema
spelling. ``$ref`` reuses another workflow's input. One declaration feeds the command
line flags, ``--inputs`` files, the agent tool schema and validation.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

import jsonschema

from gnode.workflow.values import FileValue

_SCALARS = {"string", "integer", "number", "boolean"}
_KEYWORDS = {
    "description": "description",
    "default": "default",
    "enum": "enum",
    "minimum": "minimum",
    "maximum": "maximum",
    "exclusive_minimum": "exclusiveMinimum",
    "exclusive_maximum": "exclusiveMaximum",
    "multiple_of": "multipleOf",
    "min_length": "minLength",
    "max_length": "maxLength",
    "pattern": "pattern",
    "min_items": "minItems",
    "max_items": "maxItems",
    "unique_items": "uniqueItems",
    "format": "format",
    "examples": "examples",
}
_SHORTHAND = {"type", "kind", "items", "values", "glob", "optional"}

#: Marks a schema node that holds a file path, with the file's kind.
FILE_TAG = "x-gnode-file"

RefResolver = Callable[[str], Any]


class InputError(ValueError):
    """Inputs that do not match the workflow's declaration; says which and why."""


def _is_field(declared: Any) -> bool:
    return isinstance(declared, Mapping) and ("type" in declared or "$ref" in declared)


def _required(declared: Any) -> bool:
    if not isinstance(declared, Mapping):
        return True
    if not _is_field(declared):
        return any(_required(field) for field in declared.values())
    return "default" not in declared and not declared.get("optional", False)


def compile_input(
    declared: Any, *, where: str, resolve_ref: RefResolver | None = None
) -> dict[str, Any]:
    """One input declaration as JSON Schema."""

    if not isinstance(declared, Mapping):
        raise InputError(f"{where}: an input is a mapping")
    if "$ref" in declared:
        if resolve_ref is None:
            raise InputError(f"{where}: $ref needs the referenced workflow")
        return compile_input(
            resolve_ref(str(declared["$ref"])), where=where, resolve_ref=resolve_ref
        )
    if "type" not in declared:
        properties = {
            name: compile_input(field, where=f"{where}.{name}", resolve_ref=resolve_ref)
            for name, field in declared.items()
        }
        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        required = [name for name, field in declared.items() if _required(field)]
        if required:
            schema["required"] = required
        return schema
    kind = declared["type"]
    unknown = set(declared) - set(_KEYWORDS) - _SHORTHAND
    if unknown:
        raise InputError(f"{where}: unknown keyword {', '.join(sorted(unknown))}")
    schema = {_KEYWORDS[key]: value for key, value in declared.items() if key in _KEYWORDS}
    if kind in _SCALARS:
        schema["type"] = kind
    elif kind == "file":
        schema.update({"type": "string", FILE_TAG: {"kind": declared.get("kind", "file")}})
    elif kind == "files":
        schema.update(
            {
                "type": "array",
                "items": {"type": "string"},
                FILE_TAG: {
                    "kind": declared.get("kind", "file"),
                    "many": True,
                    "glob": bool(declared.get("glob", False)),
                },
            }
        )
    elif kind == "list":
        items = declared.get("items")
        if not isinstance(items, Mapping):
            raise InputError(f"{where}: a list declares its items")
        schema.update(
            {
                "type": "array",
                "items": compile_input(items, where=f"{where}[]", resolve_ref=resolve_ref),
            }
        )
    elif kind == "map":
        values = declared.get("values")
        if not isinstance(values, Mapping):
            raise InputError(f"{where}: a map declares its values")
        schema.update(
            {
                "type": "object",
                "additionalProperties": compile_input(
                    values, where=f"{where}{{}}", resolve_ref=resolve_ref
                ),
            }
        )
    else:
        raise InputError(f"{where}: unknown type {kind!r}")
    if declared.get("optional") and "default" not in schema:
        schema["default"] = None
        schema["type"] = [schema["type"], "null"]
    return schema


def compile_inputs(
    inputs: Mapping[str, Any], *, resolve_ref: RefResolver | None = None
) -> dict[str, Any]:
    """The whole ``inputs:`` block as one JSON Schema object."""

    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            name: compile_input(field, where=f"inputs.{name}", resolve_ref=resolve_ref)
            for name, field in inputs.items()
        },
        "additionalProperties": False,
    }
    required = [name for name, field in inputs.items() if _required(field)]
    if required:
        schema["required"] = required
    return schema


def flag_name(name: str) -> str:
    """The command line flag of an input: ``max_entities`` is ``--max-entities``."""

    return "--" + name.replace("_", "-")


# --------------------------------------------------------------------------- loading


def _anchor(schema: Mapping[str, Any], value: Any, base: Path) -> Any:
    """Make every file path absolute against ``base`` (where it was written)."""

    tag = schema.get(FILE_TAG)
    if tag is not None:
        if value is None:
            return None
        if tag.get("many"):
            paths: list[str] = []
            for pattern in value if isinstance(value, list) else [value]:
                if tag.get("glob") and any(mark in str(pattern) for mark in "*?["):
                    paths.extend(
                        str(path.resolve())
                        for path in sorted(base.glob(str(pattern)))
                        if path.is_file()
                    )
                else:
                    paths.append(str((base / str(pattern)).resolve()))
            return paths
        return str((base / str(value)).resolve())
    kinds = schema.get("type")
    if kinds == "object" and isinstance(value, Mapping):
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties")
        return {
            name: _anchor(
                properties.get(name, extra if isinstance(extra, Mapping) else {}), item, base
            )
            for name, item in value.items()
        }
    if kinds == "array" and isinstance(value, list):
        return [_anchor(schema.get("items", {}), item, base) for item in value]
    return value


def _with_defaults(schema: Mapping[str, Any], value: Any) -> Any:
    if schema.get("type") == "object" and isinstance(value, Mapping):
        out = dict(value)
        for name, field in schema.get("properties", {}).items():
            if name not in out and "default" in field:
                out[name] = field["default"]
            elif name in out:
                out[name] = _with_defaults(field, out[name])
        return out
    if schema.get("type") == "array" and isinstance(value, list):
        return [_with_defaults(schema.get("items", {}), item) for item in value]
    return value


def validate(schema: Mapping[str, Any], given: Mapping[str, Any]) -> dict[str, Any]:
    """Apply defaults, then validate; the error names the input and the rule it broke."""

    value = _with_defaults(schema, dict(given))
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(value), key=lambda error: list(error.absolute_path))
    if errors:
        lines = []
        for error in errors[:8]:
            location = "inputs" + "".join(
                f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path
            )
            lines.append(f"{location}: {error.message}")
        raise InputError("; ".join(lines))
    return dict(value)


def _bind(schema: Mapping[str, Any], value: Any, read: Callable[[Path, str], FileValue]) -> Any:
    tag = schema.get(FILE_TAG)
    if tag is not None:
        if value is None:
            return None
        if tag.get("many"):
            return [read(Path(path), tag["kind"]).with_key(Path(path).stem) for path in value]
        return read(Path(value), tag["kind"])
    if schema.get("type") == "object" and isinstance(value, Mapping):
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties")
        return {
            name: _bind(
                properties.get(name, extra if isinstance(extra, Mapping) else {}), item, read
            )
            for name, item in value.items()
        }
    if schema.get("type") == "array" and isinstance(value, list):
        return [_bind(schema.get("items", {}), item, read) for item in value]
    return value


def load_inputs(
    schema: Mapping[str, Any],
    *,
    sources: Iterable[tuple[Path, Mapping[str, Any]]] = (),
    flags: Mapping[str, Any] | None = None,
    flags_base: Path,
    read: Callable[[Path, str], FileValue],
) -> dict[str, Any]:
    """Merge ``--inputs`` files in order, then flags; validate; read every file by content.

    Paths inside an inputs file are relative to that file; paths given as flags are
    relative to ``flags_base`` (the working directory).
    """

    merged: dict[str, Any] = {}
    properties = schema.get("properties", {})
    for base, document in sources:
        for name, value in document.items():
            merged[name] = _anchor(properties.get(name, {}), value, base)
    for name, value in (flags or {}).items():
        merged[name] = _anchor(properties.get(name, {}), value, flags_base)
    unknown = sorted(set(merged) - set(properties))
    if unknown:
        raise InputError(f"no input named {', '.join(unknown)}")
    checked = validate(schema, merged)
    bound = _bind(schema, checked, read)
    assert isinstance(bound, dict)
    return bound


def bind_given(
    schema: Mapping[str, Any],
    given: Mapping[str, Any],
    *,
    read: Callable[[str, str], FileValue],
    is_open: Callable[[Any], bool],
) -> tuple[dict[str, Any], list[str]]:
    """The inputs one workflow gives another it uses as a step, as the inner one sees them.

    Defaults apply at every depth, paths in file inputs are read as files, and the result
    is validated once nothing in it is still open (``is_open``: a value only a run makes).
    """

    value = _with_defaults(schema, dict(given))
    bound = _bind_open(schema, value, read, is_open)
    problems: list[str] = []
    if not is_open(bound):
        try:
            validate(schema, _as_checked(bound))
        except InputError as error:
            problems.append(str(error))
    assert isinstance(bound, dict)
    return bound, problems


def _bind_open(
    schema: Mapping[str, Any],
    value: Any,
    read: Callable[[str, str], FileValue],
    is_open: Callable[[Any], bool],
) -> Any:
    tag = schema.get(FILE_TAG)
    if tag is not None:
        if value is None or isinstance(value, FileValue) or is_open(value):
            return value
        if tag.get("many") and isinstance(value, list):
            return [
                item
                if isinstance(item, FileValue) or is_open(item)
                else read(str(item), tag["kind"])
                for item in value
            ]
        return read(str(value), tag["kind"])
    if schema.get("type") == "object" and isinstance(value, Mapping):
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties")
        return {
            name: _bind_open(
                properties.get(name, extra if isinstance(extra, Mapping) else {}),
                item,
                read,
                is_open,
            )
            for name, item in value.items()
        }
    if schema.get("type") == "array" and isinstance(value, list):
        return [_bind_open(schema.get("items", {}), item, read, is_open) for item in value]
    return value


def _as_checked(value: Any) -> Any:
    """What validation sees: a file as its name (the schema checks that a path was given)."""

    if isinstance(value, FileValue):
        return value.name
    if isinstance(value, Mapping):
        return {key: _as_checked(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_as_checked(item) for item in value]
    return value


__all__ = [
    "bind_given",
    "FILE_TAG",
    "InputError",
    "compile_input",
    "compile_inputs",
    "flag_name",
    "load_inputs",
    "validate",
]
