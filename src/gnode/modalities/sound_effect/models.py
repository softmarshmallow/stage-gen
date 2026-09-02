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

SoundEffectOutputFormat = Literal["mp3"]

#: The longest prompt a text-to-sound route accepts; the modality refuses more
#: before any provider sees it.
MAX_SOUND_EFFECT_PROMPT_CHARACTERS = 450
MIN_SOUND_EFFECT_DURATION_SECONDS = 0.5
MAX_SOUND_EFFECT_DURATION_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class SoundEffectGenerationRequest:
    """One text-to-sound-effect request.

    The prompt is sent verbatim: this modality compiles nothing onto it. The
    only controls are the ones a text-to-sound route actually honours - an
    exact duration, how literally the prompt is followed, and whether the clip
    should be a seamless loop. There is no seed and no reference input, so two
    identical requests are independent draws.
    """

    prompt: str
    artifact_path: str | Path
    duration_seconds: float | None = None
    prompt_influence: float | None = None
    loop: bool = False
    output_format: SoundEffectOutputFormat = "mp3"
    metadata: Mapping[str, object] = field(default_factory=dict)
    rights: ArtifactRights | None = None
    timeout_seconds: float | None = None
    cancellation: CancellationToken | None = None
    validate: ArtifactValidator | None = None

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("sound effect prompt must be non-empty")
        if len(self.prompt) > MAX_SOUND_EFFECT_PROMPT_CHARACTERS:
            limit = MAX_SOUND_EFFECT_PROMPT_CHARACTERS
            raise ValueError(f"sound effect prompt must be at most {limit} characters")
        if not str(self.artifact_path).strip():
            raise ValueError("artifact_path must be non-empty")
        if self.output_format != "mp3":
            raise ValueError("output_format must be mp3")
        validate_optional_number(
            self.duration_seconds,
            "duration_seconds",
            minimum=MIN_SOUND_EFFECT_DURATION_SECONDS,
            maximum=MAX_SOUND_EFFECT_DURATION_SECONDS,
            message="duration_seconds must be between 0.5 and 30",
        )
        validate_optional_number(
            self.prompt_influence,
            "prompt_influence",
            minimum=0,
            maximum=1,
            message="prompt_influence must be between 0 and 1",
        )
        if not isinstance(self.loop, bool):
            raise ValueError("loop must be a boolean")
        validate_optional_timeout(self.timeout_seconds)


@dataclass(frozen=True, slots=True)
class ProviderSoundEffect:
    data: bytes
    media_type: str
    source_shape: str
    response_metadata: ProviderResponseMetadata


class SoundEffectModelV1(Protocol):
    """The v1 sound-effect model spec: one attempt, no loop, injected credentials."""

    spec_version: ClassVar[Literal[1]]
    provider: str
    model: str
    secrets: tuple[str, ...]

    async def generate_once(self, request: SoundEffectGenerationRequest) -> ProviderSoundEffect: ...

    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class SoundEffectGenerationResult:
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
