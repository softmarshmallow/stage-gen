"""Provider-neutral contracts for endpoint-conditioned horizontal loop synthesis."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, Self

from pydantic import Field, field_validator, model_validator

from stage_gen.components._types import ProviderResponseMetadata, validate_optional_timeout
from stage_gen.contracts import ArtifactRights
from stage_gen.contracts.artifacts import PersistedContractModel
from stage_gen.contracts.provenance import RightsStatus
from stage_gen.reliability import assert_safe_path_segment, redact_secrets
from stage_gen.reliability.cancellation import CancellationToken

LOOP_SYNTHESIS_ALGORITHM = "endpoint-conditioned-bridge-v1"
MASKED_IMAGE_EDIT_CAPABILITY = "masked-image-edit"
MAX_LOOP_SOURCE_BYTES = 32 * 1024 * 1024
MAX_LOOP_PROVIDER_BYTES = 64 * 1024 * 1024
MAX_LOOP_DIMENSION = 8192
MAX_LOOP_PIXELS = 24_000_000
MAX_CONTEXT_BAND_PX = 1024
MAX_BRIDGE_WIDTH_PX = 4096
_BACKEND_LABEL_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,63})"
    r"(?:/[A-Za-z0-9](?:[A-Za-z0-9._-]{0,63}))*$"
)


@dataclass(frozen=True, slots=True)
class LoopContinuityThresholds:
    """Hard acceptance thresholds evaluated independently at both joins."""

    pixel_mae: float = 24.0
    pixel_p95: float = 40.0
    pixel_max: float = 96.0
    gradient_mae: float = 32.0
    gradient_p95: float = 56.0
    gradient_max: float = 128.0
    perceptual_delta_e: float = 18.0
    perceptual_delta_e_p95: float = 28.0
    perceptual_delta_e_max: float = 60.0

    def __post_init__(self) -> None:
        _bounded_finite(self.pixel_mae, "pixel_mae", maximum=255.0)
        _bounded_finite(self.pixel_p95, "pixel_p95", maximum=255.0)
        _bounded_finite(self.pixel_max, "pixel_max", maximum=255.0)
        _bounded_finite(self.gradient_mae, "gradient_mae", maximum=510.0)
        _bounded_finite(self.gradient_p95, "gradient_p95", maximum=510.0)
        _bounded_finite(self.gradient_max, "gradient_max", maximum=510.0)
        _bounded_finite(self.perceptual_delta_e, "perceptual_delta_e", maximum=200.0)
        _bounded_finite(
            self.perceptual_delta_e_p95,
            "perceptual_delta_e_p95",
            maximum=300.0,
        )
        _bounded_finite(
            self.perceptual_delta_e_max,
            "perceptual_delta_e_max",
            maximum=300.0,
        )
        for mean_name, percentile_name, maximum_name in (
            ("pixel_mae", "pixel_p95", "pixel_max"),
            ("gradient_mae", "gradient_p95", "gradient_max"),
            (
                "perceptual_delta_e",
                "perceptual_delta_e_p95",
                "perceptual_delta_e_max",
            ),
        ):
            mean = float(getattr(self, mean_name))
            percentile = float(getattr(self, percentile_name))
            maximum = float(getattr(self, maximum_name))
            if not mean <= percentile <= maximum:
                raise ValueError(
                    f"{mean_name}, {percentile_name}, and {maximum_name} must be ordered"
                )


@dataclass(frozen=True, slots=True)
class LoopSynthesisRequest:
    """A source strip and safe output names for one horizontal repeat unit."""

    source_path: str | Path
    output_dir: str | Path
    artifact_name: str
    manifest_name: str
    prompt: str
    source_provenance_path: str | Path | None = None
    source_ref: str | None = None
    context_band_px: int = 96
    bridge_width_px: int = 384
    thresholds: LoopContinuityThresholds = field(default_factory=LoopContinuityThresholds)
    output_rights: ArtifactRights | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    timeout_seconds: float | None = None
    cancellation: CancellationToken | None = None

    def __post_init__(self) -> None:
        if not str(self.source_path).strip():
            raise ValueError("source_path must be non-empty")
        if not str(self.output_dir).strip():
            raise ValueError("output_dir must be non-empty")
        assert_safe_path_segment(self.artifact_name, "artifact_name")
        assert_safe_path_segment(self.manifest_name, "manifest_name")
        assert_safe_path_segment(f"{self.artifact_name}.meta.json", "artifact provenance name")
        assert_safe_path_segment(f"{self.manifest_name}.meta.json", "manifest provenance name")
        if Path(self.artifact_name).suffix.lower() != ".png":
            raise ValueError("artifact_name must use a .png extension")
        if not self.manifest_name.endswith(".loop.json"):
            raise ValueError("manifest_name must use an exact .loop.json suffix")
        if self.artifact_name == self.manifest_name:
            raise ValueError("artifact_name and manifest_name must differ")
        prompt = self.prompt.strip()
        if not prompt:
            raise ValueError("loop synthesis prompt must be non-empty")
        if len(prompt) > 8192:
            raise ValueError("loop synthesis prompt must be at most 8192 characters")
        _bounded_integer(
            self.context_band_px,
            "context_band_px",
            minimum=2,
            maximum=MAX_CONTEXT_BAND_PX,
        )
        _bounded_integer(
            self.bridge_width_px,
            "bridge_width_px",
            minimum=2,
            maximum=MAX_BRIDGE_WIDTH_PX,
        )
        if self.source_ref is not None:
            assert_safe_path_segment(self.source_ref, "source_ref")
            assert_safe_path_segment(f"{self.source_ref}.meta.json", "source provenance ref")
        validate_optional_timeout(self.timeout_seconds)


@dataclass(frozen=True, slots=True)
class MaskedImageEditRequest:
    """The exact masked-edit boundary implemented by future provider adapters."""

    prompt: str
    conditioning_image: bytes
    mask_image: bytes
    width: int
    height: int
    context_band_px: int
    bridge_width_px: int
    metadata: Mapping[str, object]
    cancellation: CancellationToken | None = None


@dataclass(frozen=True, slots=True)
class ProviderLoopEdit:
    data: bytes
    media_type: str
    response_metadata: ProviderResponseMetadata = field(default_factory=ProviderResponseMetadata)


class MaskedImageEditBackend(Protocol):
    """Provider adapter capable of preserving context while editing a supplied mask."""

    provider: str
    model: str
    capability: Literal["masked-image-edit"]
    secrets: tuple[str, ...]

    async def edit_once(self, request: MaskedImageEditRequest) -> ProviderLoopEdit: ...

    async def aclose(self) -> None: ...


class JoinContinuity(PersistedContractModel):
    pixel_mae: float = Field(alias="pixelMae", ge=0, allow_inf_nan=False)
    pixel_p95: float = Field(alias="pixelP95", ge=0, allow_inf_nan=False)
    pixel_max: float = Field(alias="pixelMax", ge=0, allow_inf_nan=False)
    gradient_mae: float = Field(alias="gradientMae", ge=0, allow_inf_nan=False)
    gradient_p95: float = Field(alias="gradientP95", ge=0, allow_inf_nan=False)
    gradient_max: float = Field(alias="gradientMax", ge=0, allow_inf_nan=False)
    perceptual_delta_e: float = Field(alias="perceptualDeltaE", ge=0, allow_inf_nan=False)
    perceptual_delta_e_p95: float = Field(alias="perceptualDeltaEP95", ge=0, allow_inf_nan=False)
    perceptual_delta_e_max: float = Field(alias="perceptualDeltaEMax", ge=0, allow_inf_nan=False)


class LoopContinuityMetrics(PersistedContractModel):
    source_to_bridge: JoinContinuity = Field(alias="sourceToBridge")
    bridge_to_source: JoinContinuity = Field(alias="bridgeToSource")


class LoopAssetBinding(PersistedContractModel):
    path: str
    provenance_path: str = Field(alias="provenancePath")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(ge=1)
    width: int = Field(ge=1)
    height: int = Field(ge=1)

    @field_validator("path", "provenance_path")
    @classmethod
    def validate_portable_path(cls, value: str) -> str:
        return assert_safe_path_segment(value, "loop manifest path")


class LoopLineage(PersistedContractModel):
    source_sha256: str = Field(alias="sourceSha256", pattern=r"^[a-f0-9]{64}$")
    left_context_sha256: str = Field(alias="leftContextSha256", pattern=r"^[a-f0-9]{64}$")
    right_context_sha256: str = Field(alias="rightContextSha256", pattern=r"^[a-f0-9]{64}$")
    conditioning_sha256: str = Field(alias="conditioningSha256", pattern=r"^[a-f0-9]{64}$")
    mask_sha256: str = Field(alias="maskSha256", pattern=r"^[a-f0-9]{64}$")
    bridge_sha256: str = Field(alias="bridgeSha256", pattern=r"^[a-f0-9]{64}$")
    repeat_unit_sha256: str = Field(alias="repeatUnitSha256", pattern=r"^[a-f0-9]{64}$")


class LoopSynthesisManifest(PersistedContractModel):
    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")
    kind: Literal["horizontal-repeat-unit"] = "horizontal-repeat-unit"
    algorithm: Literal["endpoint-conditioned-bridge-v1"] = "endpoint-conditioned-bridge-v1"
    axis: Literal["x"] = "x"
    source: LoopAssetBinding
    repeat_unit: LoopAssetBinding = Field(alias="repeatUnit")
    period_px: int = Field(alias="periodPx", ge=2)
    source_width_px: int = Field(alias="sourceWidthPx", ge=1)
    bridge_width_px: int = Field(alias="bridgeWidthPx", ge=1)
    context_band_px: int = Field(alias="contextBandPx", ge=1)
    height_px: int = Field(alias="heightPx", ge=1)
    mask_semantics: Literal["white-edit-black-preserve"] = Field(
        default="white-edit-black-preserve", alias="maskSemantics"
    )
    immutable_bands_reimposed: Literal[True] = Field(default=True, alias="immutableBandsReimposed")
    lineage: LoopLineage
    metrics: LoopContinuityMetrics
    thresholds: JoinContinuity
    provider: str
    model: str
    attempts: int = Field(ge=1, le=6)
    rights_status: RightsStatus = Field(alias="rightsStatus")

    @field_validator("provider", "model")
    @classmethod
    def validate_provider_identity(cls, value: str, info: object) -> str:
        field_name = getattr(info, "field_name", "backend label")
        return validate_backend_label(value, str(field_name))

    @model_validator(mode="after")
    def validate_geometry(self) -> Self:
        if self.source.height != self.height_px or self.repeat_unit.height != self.height_px:
            raise ValueError("loop manifest image heights must match heightPx")
        if self.source.width != self.source_width_px:
            raise ValueError("loop manifest source width must match sourceWidthPx")
        if self.repeat_unit.width != self.period_px:
            raise ValueError("loop manifest repeat-unit width must match periodPx")
        if self.source_width_px + self.bridge_width_px != self.period_px:
            raise ValueError("loop manifest periodPx must equal sourceWidthPx + bridgeWidthPx")
        if self.context_band_px > self.source_width_px:
            raise ValueError("loop manifest contextBandPx must not exceed sourceWidthPx")
        if self.lineage.source_sha256 != self.source.sha256:
            raise ValueError("loop manifest source lineage must match source binding")
        if self.lineage.repeat_unit_sha256 != self.repeat_unit.sha256:
            raise ValueError("loop manifest output lineage must match repeat-unit binding")
        return self


@dataclass(frozen=True, slots=True)
class LoopSynthesisResult:
    data: bytes
    media_type: Literal["image/png"]
    provider: str
    model: str
    attempts: int
    artifact_path: str
    provenance_path: str
    manifest_path: str
    manifest_provenance_path: str
    period_px: int
    metrics: LoopContinuityMetrics

    @property
    def bytes(self) -> bytes:
        return self.data


class LoopSeamValidationError(ValueError):
    """A provider candidate failed one or more deterministic join thresholds."""


def validate_backend_label(
    value: object,
    label: str,
    *,
    secrets: tuple[str, ...] = (),
) -> str:
    """Return a stable non-URL provider/model identifier without secret material."""

    if not isinstance(value, str) or value != value.strip() or len(value) > 255:
        raise ValueError(f"backend {label} must be a safe identifier label")
    if redact_secrets(value, secrets) != value or not _BACKEND_LABEL_RE.fullmatch(value):
        raise ValueError(f"backend {label} must be a safe identifier label")
    return value


def _bounded_integer(value: object, label: str, *, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer from {minimum} to {maximum}")


def _bounded_finite(value: object, label: str, *, maximum: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or value < 0
        or value > maximum
    ):
        raise ValueError(f"{label} must be a finite number from 0 to {maximum:g}")
