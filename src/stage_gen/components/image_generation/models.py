from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from stage_gen.components._types import (
    ArtifactValidator,
    ProviderResponseMetadata,
    validate_optional_timeout,
)
from stage_gen.reliability.cancellation import CancellationToken

from .style import CanonicalStyleAnchor, ImageAssetKind

ImageQuality = Literal["auto", "low", "medium", "high"]
ImageBackground = Literal["auto", "opaque"]
ImageModeration = Literal["auto", "low"]
ImageResolution = Literal["512", "1K", "2K", "4K"]

_REFERENCE_RE = re.compile(r"^(?:https?://|data:image/[^;,]+;base64,)", re.IGNORECASE)
_ASPECT_RE = re.compile(r"^[1-9]\d*:[1-9]\d*$")


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
class ImageGenerationRequest:
    prompt: str
    artifact_path: str | Path
    input_references: tuple[ImageReference, ...] = ()
    aspect_ratio: str | None = None
    quality: ImageQuality | None = None
    background: ImageBackground | None = None
    output_compression: int | None = None
    moderation: ImageModeration | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    timeout_seconds: float | None = None
    cancellation: CancellationToken | None = None
    validate: ArtifactValidator | None = None
    provenance_schema_version: Literal[1, 2] = 1
    style_anchor: CanonicalStyleAnchor | None = None
    asset_kind: ImageAssetKind | None = None
    resolution: ImageResolution | None = None

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
        if self.background not in {None, "auto", "opaque"}:
            raise ValueError("background must be auto or opaque")
        if self.moderation not in {None, "auto", "low"}:
            raise ValueError("moderation must be auto or low")
        validate_optional_timeout(self.timeout_seconds)
        if self.provenance_schema_version not in {1, 2}:
            raise ValueError("provenance_schema_version must be 1 or 2")
        if (self.style_anchor is None) != (self.asset_kind is None):
            raise ValueError("style_anchor and asset_kind must be provided together")


@dataclass(frozen=True, slots=True)
class ProviderImage:
    data: bytes
    media_type: str
    response_metadata: ProviderResponseMetadata


class ImageGenerationBackend(Protocol):
    provider: str
    model: str
    secrets: tuple[str, ...]

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
