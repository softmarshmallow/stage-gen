from __future__ import annotations

import inspect
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from stage_gen.components._types import (
    BinaryArtifact,
    JsonObject,
    ProviderResponseMetadata,
    validate_optional_timeout,
)
from stage_gen.reliability.cancellation import CancellationToken

BackgroundModelVariant = Literal[
    "General Use (Light)",
    "General Use (Light 2K)",
    "General Use (Heavy)",
    "Matting",
    "Portrait",
    "General Use (Dynamic)",
]
BackgroundOperatingResolution = Literal["1024x1024", "2048x2048", "2304x2304"]
BackgroundOutputFormat = Literal["png", "webp", "gif"]

_REFERENCE_RE = re.compile(r"^(?:https?://|data:image/[^;,]+;base64,)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class BackgroundMaskMetadata:
    url: str
    media_type: str | None = None
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True, slots=True)
class BackgroundMaskArtifact:
    url: str
    data: bytes
    media_type: str
    width: int | None = None
    height: int | None = None

    @property
    def bytes(self) -> bytes:
        return self.data


type BackgroundValidator = Callable[
    [BinaryArtifact, BackgroundMaskArtifact | None],
    Mapping[str, object] | Awaitable[Mapping[str, object] | None] | None,
]


@dataclass(frozen=True, slots=True)
class BackgroundRemovalRequest:
    image_url: str
    artifact_path: str | Path
    model_variant: BackgroundModelVariant = "General Use (Light)"
    operating_resolution: BackgroundOperatingResolution = "1024x1024"
    output_mask: bool = False
    refine_foreground: bool = True
    output_format: BackgroundOutputFormat = "png"
    mask_only: bool = False
    sync_mode: bool = True
    metadata: Mapping[str, object] = field(default_factory=dict)
    timeout_seconds: float | None = None
    cancellation: CancellationToken | None = None
    validate: BackgroundValidator | None = None
    provenance_schema_version: Literal[1, 2] = 1

    def __post_init__(self) -> None:
        if not self.image_url.strip():
            raise ValueError("background removal image_url must be non-empty")
        if not _REFERENCE_RE.match(self.image_url):
            raise ValueError("image_url must be an HTTP(S) URL or base64 image data URL")
        if not str(self.artifact_path).strip():
            raise ValueError("artifact_path must be non-empty")
        if (
            self.operating_resolution == "2304x2304"
            and self.model_variant != "General Use (Dynamic)"
        ):
            raise ValueError("2304x2304 requires the General Use (Dynamic) model variant")
        if self.model_variant not in {
            "General Use (Light)",
            "General Use (Light 2K)",
            "General Use (Heavy)",
            "Matting",
            "Portrait",
            "General Use (Dynamic)",
        }:
            raise ValueError("unsupported background removal model_variant")
        if self.operating_resolution not in {"1024x1024", "2048x2048", "2304x2304"}:
            raise ValueError("unsupported background removal operating_resolution")
        if self.output_format not in {"png", "webp", "gif"}:
            raise ValueError("output_format must be png, webp, or gif")
        for label, value in {
            "output_mask": self.output_mask,
            "refine_foreground": self.refine_foreground,
            "mask_only": self.mask_only,
            "sync_mode": self.sync_mode,
        }.items():
            if not isinstance(value, bool):
                raise ValueError(f"{label} must be a boolean")
        validate_optional_timeout(self.timeout_seconds)
        if self.provenance_schema_version not in {1, 2}:
            raise ValueError("provenance_schema_version must be 1 or 2")


@dataclass(frozen=True, slots=True)
class ProviderBackgroundRemoval:
    data: bytes
    media_type: str
    source_url: str
    source_kind: str
    response_metadata: ProviderResponseMetadata
    width: int | None = None
    height: int | None = None
    mask_image: BackgroundMaskMetadata | None = None
    mask: BackgroundMaskArtifact | None = None


class BackgroundRemovalBackend(Protocol):
    provider: str
    model: str
    secrets: tuple[str, ...]

    async def remove_once(self, request: BackgroundRemovalRequest) -> ProviderBackgroundRemoval: ...

    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class BackgroundRemovalResult:
    data: bytes
    media_type: str
    source_url: str
    provider: str
    model: str
    attempts: int
    provenance_path: str
    response_metadata: ProviderResponseMetadata
    width: int | None = None
    height: int | None = None
    mask_image: BackgroundMaskMetadata | None = None
    mask: BackgroundMaskArtifact | None = None

    @property
    def bytes(self) -> bytes:
        return self.data


async def run_background_validator(
    validator: BackgroundValidator | None,
    artifact: BinaryArtifact,
    mask: BackgroundMaskArtifact | None,
) -> JsonObject:
    if validator is None:
        return {}
    result = validator(artifact, mask)
    if inspect.isawaitable(result):
        result = await result
    if result is None:
        return {}
    if not isinstance(result, Mapping):
        raise ValueError("background validator must return a mapping or None")
    return dict(result)
