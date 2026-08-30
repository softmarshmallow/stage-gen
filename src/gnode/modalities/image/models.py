from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Literal, Protocol

from gnode.modalities._types import (
    ArtifactValidator,
    ProviderResponseMetadata,
    validate_optional_timeout,
)
from gnode.reliability import CancellationToken

ImageQuality = Literal["auto", "low", "medium", "high"]
ImageBackground = Literal["auto", "opaque", "transparent"]
ImageOutputFormat = Literal["png", "jpeg", "webp"]
ImageModeration = Literal["auto", "low"]
ImageResolution = Literal["512", "1K", "2K", "4K"]

_REFERENCE_RE = re.compile(r"^(?:https?://|data:image/[^;,]+;base64,)", re.IGNORECASE)
_ASPECT_RE = re.compile(r"^[1-9]\d*:[1-9]\d*$")
_SIZE_RE = re.compile(r"^[1-9]\d*x[1-9]\d*$")


@dataclass(frozen=True, slots=True)
class ImageReference:
    url: str
    provenance_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("image reference url must be non-empty")
        if not _REFERENCE_RE.match(self.url):
            raise ValueError("image references must be HTTP(S) URLs or base64 image data URLs")


@dataclass(frozen=True, slots=True)
class PromptAnchor:
    """One exact clause appended to a prompt idempotently and recorded verbatim.

    The engine knows nothing about what the clause means - an application
    compiles its own vocabulary (a style anchor, a house rule) into the
    rendered ``clause``, a ``marker`` substring that identifies the clause
    family inside a prompt, and the ``provenance`` block recorded under
    ``provenance_key`` in the artifact's params. Key order in ``provenance``
    is preserved into the persisted bytes.
    """

    clause: str
    marker: str
    provenance_key: str
    provenance: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.clause.strip():
            raise ValueError("prompt anchor clause must be non-empty")
        if not self.marker.strip() or self.marker not in self.clause:
            raise ValueError("prompt anchor marker must be a substring of its clause")
        if not self.provenance_key.strip():
            raise ValueError("prompt anchor provenance_key must be non-empty")


def append_prompt_anchor_once(prompt: str, anchor: PromptAnchor) -> str:
    """Append the anchor clause idempotently and reject conflicting pre-anchors."""

    occurrences = prompt.count(anchor.marker)
    if occurrences == 0:
        return f"{prompt.rstrip()}\n\n{anchor.clause}"
    if occurrences == 1 and anchor.clause in prompt:
        return prompt
    raise ValueError("prompt already contains a different or malformed anchor")


@dataclass(frozen=True, slots=True)
class ImageGenerationRequest:
    prompt: str
    artifact_path: str | Path
    input_references: tuple[ImageReference, ...] = ()
    #: Optional inpainting mask. Transparent areas mark the editable region. Providers without a
    #: real masked-edit route must reject it rather than silently ignoring it.
    mask_reference: ImageReference | None = None
    aspect_ratio: str | None = None
    quality: ImageQuality | None = None
    background: ImageBackground | None = None
    output_format: ImageOutputFormat | None = None
    output_compression: int | None = None
    moderation: ImageModeration | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    timeout_seconds: float | None = None
    cancellation: CancellationToken | None = None
    validate: ArtifactValidator | None = None
    provenance_schema_version: Literal[2] = 2
    prompt_anchor: PromptAnchor | None = None
    resolution: ImageResolution | None = None
    size: str | None = None

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("image prompt must be non-empty")
        if not str(self.artifact_path).strip():
            raise ValueError("artifact_path must be non-empty")
        if self.aspect_ratio not in {None, "auto"} and not _ASPECT_RE.fullmatch(
            self.aspect_ratio or ""
        ):
            raise ValueError(
                "aspect_ratio must be auto or two positive integers separated by a colon"
            )
        if self.output_compression is not None and (
            isinstance(self.output_compression, bool)
            or not isinstance(self.output_compression, int)
            or not 0 <= self.output_compression <= 100
        ):
            raise ValueError("output_compression must be an integer from 0 to 100")
        if self.resolution not in (None, "512", "1K", "2K", "4K"):
            raise ValueError("resolution must be 512, 1K, 2K, or 4K")
        if self.quality not in {None, "auto", "low", "medium", "high"}:
            raise ValueError("quality must be auto, low, medium, or high")
        if self.background not in {None, "auto", "opaque", "transparent"}:
            raise ValueError("background must be auto, opaque, or transparent")
        if self.output_format not in {None, "png", "jpeg", "webp"}:
            raise ValueError("output_format must be png, jpeg, or webp")
        if self.background == "transparent" and self.output_format not in {None, "png", "webp"}:
            raise ValueError("transparent background requires png or webp output")
        if self.size not in {None, "auto"} and not _SIZE_RE.fullmatch(self.size or ""):
            raise ValueError("size must be auto or WIDTHxHEIGHT with positive integer edges")
        if self.moderation not in {None, "auto", "low"}:
            raise ValueError("moderation must be auto or low")
        validate_optional_timeout(self.timeout_seconds)
        if self.provenance_schema_version != 2:
            raise ValueError("provenance_schema_version must be 2")


@dataclass(frozen=True, slots=True)
class ProviderImage:
    data: bytes
    media_type: str
    response_metadata: ProviderResponseMetadata
    applied_params: Mapping[str, object] | None = None


class ImageModelV1(Protocol):
    """The v1 image model spec: one attempt, no loop, injected credentials."""

    spec_version: ClassVar[Literal[1]]
    provider: str
    model: str
    secrets: tuple[str, ...]
    supports_native_alpha: bool

    async def generate_once(self, request: ImageGenerationRequest) -> ProviderImage: ...

    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ImageGenerationResult:
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
