from __future__ import annotations

import inspect
import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from gnode.contracts import BinaryArtifact as BinaryArtifact

type JsonObject = dict[str, Any]
type ValidationResult = Mapping[str, Any] | None
type ArtifactValidator = Callable[
    ["BinaryArtifact"], ValidationResult | Awaitable[ValidationResult]
]


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
