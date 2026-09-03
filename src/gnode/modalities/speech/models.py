from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Literal, Protocol

from gnode.contracts import ArtifactRights
from gnode.modalities._types import (
    ArtifactValidator,
    ProviderResponseMetadata,
    validate_optional_number,
    validate_optional_timeout,
)
from gnode.reliability import CancellationToken

SpeechOutputFormat = Literal["mp3"]

#: The longest text a text-to-speech route accepts in one request; the modality
#: refuses more before any provider sees it.
MAX_SPEECH_TEXT_CHARACTERS = 5000


@dataclass(frozen=True, slots=True)
class SpeechGenerationRequest:
    """One text-to-speech request.

    The text is sent verbatim, delivery annotations included: this modality
    compiles nothing onto it. ``voice`` is the provider's own voice reference
    and is opaque here - which voice a game-owned name resolves to is the
    application's business. The controls are the ones a speech route honours:
    how literally the voice follows the text (``stability``) and, optionally,
    the language the text should be read in.

    There is no duration control - the model decides how long a line takes -
    and the seed such routes accept is deliberately not exposed: measured, it
    pins the length of a read without reproducing its waveform, so it cannot
    make a draw repeatable and must not pretend to. Two identical requests are
    independent draws.
    """

    text: str
    voice: str
    artifact_path: str | Path
    stability: float | None = None
    language_code: str | None = None
    output_format: SpeechOutputFormat = "mp3"
    metadata: Mapping[str, object] = field(default_factory=dict)
    rights: ArtifactRights | None = None
    timeout_seconds: float | None = None
    cancellation: CancellationToken | None = None
    validate: ArtifactValidator | None = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("speech text must be non-empty")
        if len(self.text) > MAX_SPEECH_TEXT_CHARACTERS:
            raise ValueError(f"speech text must be at most {MAX_SPEECH_TEXT_CHARACTERS} characters")
        if not self.voice.strip():
            raise ValueError("speech voice must be non-empty")
        if not str(self.artifact_path).strip():
            raise ValueError("artifact_path must be non-empty")
        if self.output_format != "mp3":
            raise ValueError("output_format must be mp3")
        validate_optional_number(
            self.stability,
            "stability",
            minimum=0,
            maximum=1,
            message="stability must be between 0 and 1",
        )
        if self.language_code is not None and not self.language_code.strip():
            raise ValueError("language_code must be non-empty when given")
        validate_optional_timeout(self.timeout_seconds)


@dataclass(frozen=True, slots=True)
class ProviderSpeech:
    data: bytes
    media_type: str
    source_shape: str
    response_metadata: ProviderResponseMetadata


class SpeechModelV1(Protocol):
    """The v1 speech model spec: one attempt, no loop, injected credentials."""

    spec_version: ClassVar[Literal[1]]
    provider: str
    model: str
    secrets: tuple[str, ...]

    async def generate_once(self, request: SpeechGenerationRequest) -> ProviderSpeech: ...

    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class SpeechGenerationResult:
    data: bytes
    media_type: str
    provider: str
    model: str
    attempts: int
    provenance_path: str
    response_metadata: ProviderResponseMetadata

    @property
    def bytes(self) -> bytes:
        return self.data
