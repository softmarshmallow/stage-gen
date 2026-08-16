from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from stage_gen.components._types import (
    ProviderResponseMetadata,
    validate_optional_number,
    validate_optional_timeout,
)
from stage_gen.reliability.cancellation import CancellationToken

_REFERENCE_RE = re.compile(r"^(?:https?://|data:image/[^;,]+;base64,)", re.IGNORECASE)


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

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("structured prompt must be non-empty")
        if not str(self.artifact_path).strip():
            raise ValueError("artifact_path must be non-empty")
        if not callable(self.parse):
            raise ValueError("parse must be callable")
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


@dataclass(frozen=True, slots=True)
class ProviderStructuredOutput:
    decoded: object
    raw_text: str
    response_metadata: ProviderResponseMetadata


class StructuredGenerationBackend(Protocol):
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
