from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from gnode import ArtifactRights, CancellationToken
from stage_gen.components._types import (
    ArtifactValidator,
    ProviderResponseMetadata,
    validate_optional_number,
    validate_optional_timeout,
)

MusicOutputFormat = Literal["mp3", "wav"]
_REFERENCE_RE = re.compile(r"^(?:https?://|data:image/[^;,]+;base64,)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class MusicReference:
    url: str
    provenance_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("music reference url must be non-empty")
        if not _REFERENCE_RE.match(self.url):
            raise ValueError("music references must be HTTP(S) URLs or base64 image data URLs")


@dataclass(frozen=True, slots=True)
class MusicGenerationRequest:
    prompt: str
    artifact_path: str | Path
    references: tuple[MusicReference, ...] = ()
    output_format: MusicOutputFormat = "mp3"
    temperature: float | None = None
    top_p: float | None = None
    seed: int | None = None
    max_tokens: int | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    rights: ArtifactRights | None = None
    timeout_seconds: float | None = None
    cancellation: CancellationToken | None = None
    validate: ArtifactValidator | None = None

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("music prompt must be non-empty")
        if not str(self.artifact_path).strip():
            raise ValueError("artifact_path must be non-empty")
        if self.output_format not in {"mp3", "wav"}:
            raise ValueError("output_format must be mp3 or wav")
        validate_optional_number(
            self.temperature,
            "temperature",
            minimum=0,
            maximum=2,
            message="temperature must be between 0 and 2",
        )
        validate_optional_number(
            self.top_p,
            "top_p",
            minimum=0,
            maximum=1,
            minimum_inclusive=False,
            message="top_p must be greater than 0 and at most 1",
        )
        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
        ):
            raise ValueError("seed must be an integer")
        if self.max_tokens is not None and (
            isinstance(self.max_tokens, bool)
            or not isinstance(self.max_tokens, int)
            or self.max_tokens < 1
        ):
            raise ValueError("max_tokens must be a positive integer")
        validate_optional_timeout(self.timeout_seconds)


@dataclass(frozen=True, slots=True)
class ProviderMusic:
    data: bytes
    media_type: str
    source_shape: str
    response_metadata: ProviderResponseMetadata
    text: str | None = None


class MusicGenerationBackend(Protocol):
    provider: str
    model: str
    secrets: tuple[str, ...]

    async def generate_once(self, request: MusicGenerationRequest) -> ProviderMusic: ...

    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class MusicGenerationResult:
    data: bytes
    media_type: str
    provider: str
    model: str
    attempts: int
    provenance_path: str
    response_metadata: ProviderResponseMetadata
    text: str | None = None

    @property
    def bytes(self) -> bytes:
        return self.data
