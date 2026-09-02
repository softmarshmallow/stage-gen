from __future__ import annotations

import inspect
import math
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from gnode.contracts import BinaryArtifact as BinaryArtifact

type JsonObject = dict[str, Any]
type ValidationResult = Mapping[str, Any] | None
type ArtifactValidator = Callable[
    ["BinaryArtifact"], ValidationResult | Awaitable[ValidationResult]
]

# A model-facing reference is a fetchable URL or an inline base64 image.
REFERENCE_URL_RE = re.compile(r"^(?:https?://|data:image/[^;,]+;base64,)", re.IGNORECASE)

# OpenAI-compatible strict structured-output transports accept a deliberately
# small JSON Schema subset. Caller validation remains authoritative for these
# assertion keywords after decoding.
_UNSUPPORTED_STRICT_ASSERTIONS = frozenset(
    {
        "contains",
        "format",
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
        "pattern",
        "patternProperties",
        "propertyNames",
        "unevaluatedItems",
        "unevaluatedProperties",
        "uniqueItems",
    }
)


def canonicalize_strict_json_schema(value: Mapping[str, object]) -> dict[str, object]:
    """Canonicalize the common strict-output subset before transport/provenance."""

    normalized = _canonicalize_schema_value(value)
    if not isinstance(normalized, dict):
        raise TypeError("strict json_schema must normalize to an object")
    return normalized


def _canonicalize_schema_value(value: object) -> object:
    if isinstance(value, list):
        return [_canonicalize_schema_value(item) for item in value]
    if not isinstance(value, Mapping):
        return value
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError("JSON Schema keys must be strings")
        if key == "default" or key in _UNSUPPORTED_STRICT_ASSERTIONS:
            continue
        result[key] = _canonicalize_schema_value(item)
    properties = result.get("properties")
    if isinstance(properties, Mapping):
        result["required"] = list(properties)
        result["additionalProperties"] = False
    return result


@dataclass(frozen=True, slots=True)
class ProviderResponseMetadata:
    request_id: str | None = None
    created: int | float | None = None
    usage: JsonObject | None = None


async def run_validator(
    validator: ArtifactValidator | None,
    artifact: BinaryArtifact,
) -> JsonObject:
    if validator is None:
        return {}
    result = validator(artifact)
    if inspect.isawaitable(result):
        result = await result
    if result is None:
        return {}
    if not isinstance(result, Mapping):
        raise ValueError("artifact validator must return a mapping or None")
    return dict(result)


def validate_optional_timeout(value: object, label: str = "timeout_seconds") -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be a positive finite number")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be a positive finite number")


def validate_optional_number(
    value: object,
    label: str,
    *,
    minimum: float,
    maximum: float,
    minimum_inclusive: bool = True,
    message: str | None = None,
) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(message or f"{label} must be finite")
    below = value < minimum if minimum_inclusive else value <= minimum
    if below or value > maximum:
        lower = "at least" if minimum_inclusive else "greater than"
        raise ValueError(message or f"{label} must be {lower} {minimum:g} and at most {maximum:g}")
