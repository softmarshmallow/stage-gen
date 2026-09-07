from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Literal, Protocol

from gnode.contracts import ArtifactRights
from gnode.modalities._types import (
    REFERENCE_URL_RE,
    ArtifactValidator,
    ProviderResponseMetadata,
    validate_optional_number,
    validate_optional_timeout,
)
from gnode.reliability import CancellationToken

VideoOutputFormat = Literal["mp4"]

#: The broadcast ladder, not any one vendor's enum. A route declares which
#: rungs it serves through its binding; asking for one it does not serve is the
#: provider's refusal, not this modality's.
VideoResolution = Literal["360p", "720p", "1080p", "4k"]

_ASPECT_RATIO = ("16:9", "9:16", "1:1", "4:3", "3:4", "21:9")


@dataclass(frozen=True, slots=True)
class VideoReference:
    """One picture a video route is shown before it draws.

    A typed wrapper rather than a bare URL because the provenance writer
    redacts an inline data URI to ``data:image/png;base64,[REDACTED]``: without
    ``provenance_ref`` every reference in a run would land in the sidecar under
    the same anonymous name, and which plates a clip was drawn from is exactly
    what the record exists to say.
    """

    url: str
    provenance_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("video reference url must be non-empty")
        if not REFERENCE_URL_RE.match(self.url):
            raise ValueError("video references must be HTTP(S) URLs or base64 image data URLs")


@dataclass(frozen=True, slots=True)
class VideoGenerationRequest:
    """One video-generation request.

    ``references`` are the pictures the route is shown, in the order it is shown
    them - order is part of the ask, because a route reads the first as the
    art direction the rest are judged against.

    There is no seed. The routes this modality is written for accept none, and
    per the speech precedent a control that cannot make a draw repeatable must
    not be exposed as though it could: two identical requests are independent
    draws, and a second one is bought deliberately.

    There is also **no clip-length ceiling here**. How long a clip a route will
    make is a fact about that route, not about video, so it is declared on the
    route's binding as a limit and refused while planning. Putting a number
    here would be one model's cap wearing the modality's clothes, and every
    other route would inherit it.
    """

    prompt: str
    artifact_path: str | Path
    references: tuple[VideoReference, ...] = ()
    duration_seconds: float | None = None
    resolution: VideoResolution | None = None
    aspect_ratio: str | None = None
    output_format: VideoOutputFormat = "mp4"
    metadata: Mapping[str, object] = field(default_factory=dict)
    rights: ArtifactRights | None = None
    timeout_seconds: float | None = None
    cancellation: CancellationToken | None = None
    validate: ArtifactValidator | None = None

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("video prompt must be non-empty")
        if not str(self.artifact_path).strip():
            raise ValueError("artifact_path must be non-empty")
        if self.output_format != "mp4":
            raise ValueError("output_format must be mp4")
        validate_optional_number(
            self.duration_seconds,
            "duration_seconds",
            minimum=0,
            maximum=float("inf"),
            minimum_inclusive=False,
            message="duration_seconds must be a positive finite number of seconds",
        )
        if self.aspect_ratio is not None and self.aspect_ratio not in _ASPECT_RATIO:
            raise ValueError(f"aspect_ratio must be one of {', '.join(_ASPECT_RATIO)}")
        validate_optional_timeout(self.timeout_seconds)


@dataclass(frozen=True, slots=True)
class ProviderVideo:
    data: bytes
    media_type: str
    source_shape: str
    response_metadata: ProviderResponseMetadata


class VideoModelV1(Protocol):
    """The v1 video model spec: one attempt, no loop, injected credentials."""

    spec_version: ClassVar[Literal[1]]
    provider: str
    model: str
    secrets: tuple[str, ...]

    async def generate_once(self, request: VideoGenerationRequest) -> ProviderVideo: ...

    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class VideoGenerationResult:
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
