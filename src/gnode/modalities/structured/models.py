from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Literal, Protocol

from gnode.modalities._types import (
    ProviderResponseMetadata,
    validate_optional_number,
    validate_optional_timeout,
)
from gnode.reliability import CancellationToken

_REFERENCE_RE = re.compile(r"^(?:https?://|data:image/[^;,]+;base64,)", re.IGNORECASE)

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


@dataclass(frozen=True, slots=True)
class StructuredReference:
    url: str
    provenance_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("structured reference url must be non-empty")
        if not _REFERENCE_RE.match(self.url):
            raise ValueError("structured references must be HTTP(S) URLs or base64 image data URLs")


@dataclass(frozen=True, slots=True)
class StructuredOutputSchema:
    name: str
    json_schema: Mapping[str, object]
    description: str | None = None
    strict: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("schema name must be non-empty")
        if not isinstance(self.json_schema, Mapping):
            raise ValueError("json_schema must be an object")
        if not isinstance(self.strict, bool):
            raise ValueError("schema strict must be a boolean")
        if self.strict:
            object.__setattr__(
                self,
                "json_schema",
                canonicalize_strict_json_schema(self.json_schema),
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
class StructuredGenerationRequest[T]:
    prompt: str
    artifact_path: str | Path
    schema: StructuredOutputSchema
    parse: Callable[[object], T]
    system: str | None = None
    references: tuple[StructuredReference, ...] = ()
    temperature: float | None = None
    max_tokens: int | None = None
    seed: int | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    timeout_seconds: float | None = None
    cancellation: CancellationToken | None = None
    artifact_value: Callable[[T], object] | None = None
    validate: Callable[[T], Mapping[str, object] | None] | None = None
    provenance_schema_version: Literal[2] = 2

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("structured prompt must be non-empty")
        if not str(self.artifact_path).strip():
            raise ValueError("artifact_path must be non-empty")
        if not callable(self.parse):
            raise ValueError("parse must be callable")
        if self.artifact_value is not None and not callable(self.artifact_value):
            raise ValueError("artifact_value must be callable")
        if self.validate is not None and not callable(self.validate):
            raise ValueError("validate must be callable")
        validate_optional_number(
            self.temperature,
            "temperature",
            minimum=0,
            maximum=2,
            message="temperature must be between 0 and 2",
        )
        if self.max_tokens is not None and (
            isinstance(self.max_tokens, bool)
            or not isinstance(self.max_tokens, int)
            or self.max_tokens < 1
        ):
            raise ValueError("max_tokens must be a positive integer")
        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
        ):
            raise ValueError("seed must be an integer")
        validate_optional_timeout(self.timeout_seconds)
        if self.provenance_schema_version != 2:
            raise ValueError("provenance_schema_version must be 2")


@dataclass(frozen=True, slots=True)
class ProviderStructuredOutput:
    decoded: object
    raw_text: str
    response_metadata: ProviderResponseMetadata


class StructuredModelV1(Protocol):
    """The v1 structured model spec: one attempt, no loop, injected credentials."""

    spec_version: ClassVar[Literal[1]]
    provider: str
    model: str
    secrets: tuple[str, ...]

    async def generate_once(
        self, request: StructuredGenerationRequest[object]
    ) -> ProviderStructuredOutput: ...

    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class StructuredGenerationResult[T]:
    value: T
    raw_text: str
    provider: str
    model: str
    attempts: int
    provenance_path: str
    response_metadata: ProviderResponseMetadata
