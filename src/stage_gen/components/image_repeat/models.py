"""Provider-neutral contracts for verified single-axis image repetition."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, field_validator, model_validator

from stage_gen.components._types import ProviderResponseMetadata, validate_optional_timeout
from stage_gen.contracts import ArtifactRights
from stage_gen.contracts.artifacts import PersistedContractModel
from stage_gen.contracts.provenance import RightsStatus
from stage_gen.reliability import assert_safe_path_segment, redact_secrets
from stage_gen.reliability.cancellation import CancellationToken

IMAGE_REPEAT_SCHEMA_VERSION: Literal[2] = 2
DIRECT_WRAP_ADMISSION_ALGORITHM: Literal["direct-wrap-admission-v2"] = "direct-wrap-admission-v2"
ENDPOINT_CONDITIONED_REPAIR_ALGORITHM: Literal[
    "endpoint-alpha-reconstructed-anchored-repair-v4"
] = "endpoint-alpha-reconstructed-anchored-repair-v4"
ENDPOINT_ANCHOR_ALGORITHM: Literal["linear-light-premultiplied-smoothstep-v1"] = (
    "linear-light-premultiplied-smoothstep-v1"
)
ALPHA_RECONSTRUCTION_ALGORITHM: Literal["source-endpoint-alpha-smoothstep-v1"] = (
    "source-endpoint-alpha-smoothstep-v1"
)
DETERMINISTIC_VALIDATOR_VERSION: Literal["single-axis-continuity-v2"] = "single-axis-continuity-v2"
THREE_REPEAT_PREVIEW_VERSION: Literal["alpha-checkerboard-three-repeat-v2"] = (
    "alpha-checkerboard-three-repeat-v2"
)
INTENDED_LOOP_REVIEW_CONTRACT_VERSION: Literal["intended-loop-review-v1"] = (
    "intended-loop-review-v1"
)
INTENDED_LOOP_REVIEW_PROMPT_VERSION: Literal["intended-loop-rubric-v3"] = "intended-loop-rubric-v3"
INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE = 0.90
MASKED_IMAGE_EDIT_CAPABILITY = "masked-image-edit"
MAX_IMAGE_REPEAT_SOURCE_BYTES = 32 * 1024 * 1024
MAX_IMAGE_REPEAT_PROVIDER_BYTES = 64 * 1024 * 1024
MAX_IMAGE_REPEAT_DIMENSION = 8192
MAX_IMAGE_REPEAT_PIXELS = 24_000_000
MAX_CONTEXT_SPAN_PX = 1024
MAX_REPAIR_SPAN_PX = 4096

type ImageRepeatAxis = Literal["x", "y"]
type ImageRepeatAlphaPolicy = Literal["preserve", "require_opaque"]
type ImageRepeatCoveragePolicy = Literal["continuous", "sparse_allowed"]
type ImageRepeatDecision = Literal["admitted", "repaired"]
type ImageRepeatReviewVerdict = Literal["accept", "reject", "uncertain"]
type ImageRepeatFailureCode = Literal[
    "visible_boundary_pop",
    "clipped_or_disconnected_form",
    "unintended_transparent_gap",
    "structure_or_horizon_reset",
    "lighting_or_texture_reset",
    "mirror_or_reverse_shortcut",
    "salient_periodic_cadence",
    "orientation_or_gravity_break",
    "alpha_halo_or_matte_contamination",
    "intended_behavior_mismatch",
    "insufficient_evidence",
]

IMAGE_REPEAT_FAILURE_CODES: tuple[ImageRepeatFailureCode, ...] = (
    "visible_boundary_pop",
    "clipped_or_disconnected_form",
    "unintended_transparent_gap",
    "structure_or_horizon_reset",
    "lighting_or_texture_reset",
    "mirror_or_reverse_shortcut",
    "salient_periodic_cadence",
    "orientation_or_gravity_break",
    "alpha_halo_or_matte_contamination",
    "intended_behavior_mismatch",
    "insufficient_evidence",
)

_BACKEND_LABEL_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,63})"
    r"(?:/[A-Za-z0-9](?:[A-Za-z0-9._-]{0,63}))*$"
)


@dataclass(frozen=True, slots=True)
class ImageRepeatValidationPolicy:
    """Versioned deterministic thresholds in normalized visual-channel units."""

    scales: tuple[float, ...] = (1.0, 0.5, 0.25)
    color_mae: float = 0.12
    color_p95: float = 0.25
    color_max: float = 0.45
    gradient_mae: float = 0.18
    gradient_p95: float = 0.35
    gradient_max: float = 0.70
    alpha_mae: float = 0.08
    alpha_p95: float = 0.20
    alpha_max: float = 0.50
    coverage_mismatch_ratio: float = 0.10
    internal_baseline_multiplier: float = 2.0
    coverage_alpha_threshold: float = 0.05

    def __post_init__(self) -> None:
        if not self.scales or self.scales[0] != 1.0:
            raise ValueError("image-repeat validation scales must start with 1.0")
        if len(set(self.scales)) != len(self.scales):
            raise ValueError("image-repeat validation scales must be unique")
        for scale in self.scales:
            _bounded_finite(scale, "validation scale", minimum=0.01, maximum=1.0)
        for name in (
            "color_mae",
            "color_p95",
            "color_max",
            "gradient_mae",
            "gradient_p95",
            "gradient_max",
            "alpha_mae",
            "alpha_p95",
            "alpha_max",
            "coverage_mismatch_ratio",
            "coverage_alpha_threshold",
        ):
            _bounded_finite(getattr(self, name), name, minimum=0.0, maximum=1.0)
        _bounded_finite(
            self.internal_baseline_multiplier,
            "internal_baseline_multiplier",
            minimum=1.0,
            maximum=10.0,
        )
        for prefix in ("color", "gradient", "alpha"):
            mean = float(getattr(self, f"{prefix}_mae"))
            percentile = float(getattr(self, f"{prefix}_p95"))
            maximum = float(getattr(self, f"{prefix}_max"))
            if not mean <= percentile <= maximum:
                raise ValueError(f"{prefix} thresholds must be ordered mae <= p95 <= max")


@dataclass(frozen=True, slots=True)
class ImageRepeatAdmissionRequest:
    """Request to admit an unchanged image as a one-axis repeat unit."""

    source_path: str | Path
    output_dir: str | Path
    artifact_name: str
    manifest_name: str
    axis: ImageRepeatAxis
    intended_behavior: str
    source_provenance_path: str | Path | None = None
    source_ref: str | None = None
    alpha_policy: ImageRepeatAlphaPolicy = "preserve"
    coverage_policy: ImageRepeatCoveragePolicy = "continuous"
    validation_policy: ImageRepeatValidationPolicy = field(
        default_factory=ImageRepeatValidationPolicy
    )
    output_rights: ArtifactRights | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    cancellation: CancellationToken | None = None

    def __post_init__(self) -> None:
        _validate_common_request(self)


@dataclass(frozen=True, slots=True)
class ImageRepeatRepairRequest:
    """Explicit request to append an endpoint-conditioned repair span."""

    source_path: str | Path
    output_dir: str | Path
    artifact_name: str
    manifest_name: str
    axis: ImageRepeatAxis
    intended_behavior: str
    prompt: str
    source_provenance_path: str | Path | None = None
    source_ref: str | None = None
    context_span_px: int = 96
    repair_span_px: int = 384
    alpha_policy: ImageRepeatAlphaPolicy = "preserve"
    coverage_policy: ImageRepeatCoveragePolicy = "continuous"
    validation_policy: ImageRepeatValidationPolicy = field(
        default_factory=ImageRepeatValidationPolicy
    )
    output_rights: ArtifactRights | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    timeout_seconds: float | None = None
    cancellation: CancellationToken | None = None

    def __post_init__(self) -> None:
        _validate_common_request(self)
        prompt = self.prompt.strip()
        if not prompt or len(prompt) > 8192:
            raise ValueError("image-repeat repair prompt must contain from 1 to 8192 characters")
        _bounded_integer(
            self.context_span_px,
            "context_span_px",
            minimum=2,
            maximum=MAX_CONTEXT_SPAN_PX,
        )
        _bounded_integer(
            self.repair_span_px,
            "repair_span_px",
            minimum=4,
            maximum=MAX_REPAIR_SPAN_PX,
        )
        validate_optional_timeout(self.timeout_seconds)


@dataclass(frozen=True, slots=True)
class MaskedImageEditRequest:
    """Exact provider boundary for an axis-aware masked repair operation."""

    prompt: str
    conditioning_image: bytes
    mask_image: bytes
    width: int
    height: int
    axis: ImageRepeatAxis
    context_span_px: int
    repair_span_px: int
    metadata: Mapping[str, object]
    cancellation: CancellationToken | None = None


@dataclass(frozen=True, slots=True)
class ProviderImageRepeatEdit:
    data: bytes
    media_type: str
    response_metadata: ProviderResponseMetadata = field(default_factory=ProviderResponseMetadata)


class MaskedImageEditBackend(Protocol):
    provider: str
    model: str
    capability: Literal["masked-image-edit"]
    secrets: tuple[str, ...]

    async def edit_once(self, request: MaskedImageEditRequest) -> ProviderImageRepeatEdit: ...

    async def aclose(self) -> None: ...


class ImageRepeatScaleMetrics(PersistedContractModel):
    scale: float = Field(gt=0, le=1, allow_inf_nan=False)
    boundary_width_px: int = Field(ge=1)
    color_mae: float = Field(ge=0, le=1, allow_inf_nan=False)
    color_p95: float = Field(ge=0, le=1, allow_inf_nan=False)
    color_max: float = Field(ge=0, le=1, allow_inf_nan=False)
    gradient_mae: float = Field(ge=0, le=1, allow_inf_nan=False)
    gradient_p95: float = Field(ge=0, le=1, allow_inf_nan=False)
    gradient_max: float = Field(ge=0, le=1, allow_inf_nan=False)
    alpha_mae: float = Field(ge=0, le=1, allow_inf_nan=False)
    alpha_p95: float = Field(ge=0, le=1, allow_inf_nan=False)
    alpha_max: float = Field(ge=0, le=1, allow_inf_nan=False)
    coverage_mismatch_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)
    internal_color_p95: float = Field(ge=0, le=1, allow_inf_nan=False)
    color_limit: float = Field(ge=0, le=1, allow_inf_nan=False)
    gradient_limit: float = Field(ge=0, le=1, allow_inf_nan=False)
    alpha_limit: float = Field(ge=0, le=1, allow_inf_nan=False)
    coverage_limit: float = Field(ge=0, le=1, allow_inf_nan=False)


class ImageRepeatJoinReport(PersistedContractModel):
    name: Literal["wrap", "source_to_repair", "repair_to_source"]
    verdict: Literal["pass", "reject"]
    scales: list[ImageRepeatScaleMetrics] = Field(min_length=1)
    failure_codes: list[ImageRepeatFailureCode]

    @model_validator(mode="after")
    def validate_verdict(self) -> Self:
        _validate_unique_codes(self.failure_codes)
        if self.verdict == "pass" and self.failure_codes:
            raise ValueError("passing join report must not contain failure codes")
        if self.verdict == "reject" and not self.failure_codes:
            raise ValueError("rejected join report must contain failure codes")
        return self


class ImageRepeatDeterministicReport(PersistedContractModel):
    validator_version: Literal["single-axis-continuity-v2"] = DETERMINISTIC_VALIDATOR_VERSION
    axis: ImageRepeatAxis
    verdict: Literal["pass", "reject"]
    alpha_policy: ImageRepeatAlphaPolicy
    coverage_policy: ImageRepeatCoveragePolicy
    source_immutable: bool
    joins: list[ImageRepeatJoinReport] = Field(min_length=1, max_length=2)
    failure_codes: list[ImageRepeatFailureCode]

    @model_validator(mode="after")
    def validate_verdict(self) -> Self:
        _validate_unique_codes(self.failure_codes)
        join_codes = _unique_codes(code for join in self.joins for code in join.failure_codes)
        if any(code not in self.failure_codes for code in join_codes):
            raise ValueError("deterministic report must include every join failure code")
        if self.verdict == "pass":
            if self.failure_codes or any(join.verdict != "pass" for join in self.joins):
                raise ValueError("passing deterministic report must contain only passing joins")
            if not self.source_immutable:
                raise ValueError("passing deterministic report must preserve the source")
        elif not self.failure_codes:
            raise ValueError("rejected deterministic report must contain failure codes")
        return self


@dataclass(frozen=True, slots=True)
class IntendedLoopReviewRequest:
    preview_png: bytes
    preview_sha256: str
    judged_sha256: str
    criteria_sha256: str
    review_artifact_path: str | Path
    axis: ImageRepeatAxis
    intended_behavior: str
    deterministic_report: ImageRepeatDeterministicReport
    cancellation: CancellationToken | None = None

    def __post_init__(self) -> None:
        for name in ("preview_sha256", "judged_sha256", "criteria_sha256"):
            if not re.fullmatch(r"[a-f0-9]{64}", str(getattr(self, name))):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        if not self.preview_png:
            raise ValueError("intended-loop preview must be non-empty")
        if self.axis not in {"x", "y"}:
            raise ValueError("intended-loop review axis must be x or y")
        _trimmed_text(self.intended_behavior, "intended_behavior", maximum=512)
        if self.deterministic_report.axis != self.axis:
            raise ValueError("intended-loop review axis must match deterministic report")


@dataclass(frozen=True, slots=True)
class IntendedLoopReview:
    verdict: ImageRepeatReviewVerdict
    confidence: float
    failure_codes: tuple[ImageRepeatFailureCode, ...]
    evidence: str
    response_metadata: ProviderResponseMetadata = field(default_factory=ProviderResponseMetadata)
    artifact_path: str | None = None
    provenance_path: str | None = None

    def __post_init__(self) -> None:
        if self.verdict not in {"accept", "reject", "uncertain"}:
            raise ValueError("intended-loop verdict must be accept, reject, or uncertain")
        _bounded_finite(self.confidence, "review confidence", minimum=0.0, maximum=1.0)
        _trimmed_text(self.evidence, "review evidence", maximum=4096)
        _validate_unique_codes(list(self.failure_codes))
        if self.verdict == "accept" and self.failure_codes:
            raise ValueError("accepted intended-loop review must not contain failure codes")
        if self.verdict == "reject" and not self.failure_codes:
            raise ValueError("rejected intended-loop review must contain failure codes")
        if self.verdict == "uncertain" and "insufficient_evidence" not in self.failure_codes:
            raise ValueError("uncertain intended-loop review must include insufficient_evidence")
        if (self.artifact_path is None) != (self.provenance_path is None):
            raise ValueError("review artifact and provenance paths must be supplied together")


class IntendedLoopReviewer(Protocol):
    """Already retry-owned semantic reviewer; callers invoke it exactly once."""

    provider: str
    model: str
    secrets: tuple[str, ...]

    async def review(self, request: IntendedLoopReviewRequest) -> IntendedLoopReview: ...

    async def aclose(self) -> None: ...


class ImageRepeatAssetBinding(PersistedContractModel):
    path: str
    provenance_path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(ge=1)
    width: int = Field(ge=1)
    height: int = Field(ge=1)

    @field_validator("path", "provenance_path")
    @classmethod
    def validate_portable_path(cls, value: str) -> str:
        return assert_safe_path_segment(value, "image-repeat manifest path")


class ImageRepeatReviewArtifactBinding(PersistedContractModel):
    path: str
    provenance_path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provenance_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(ge=1)

    @field_validator("path", "provenance_path")
    @classmethod
    def validate_portable_path(cls, value: str) -> str:
        return assert_safe_path_segment(value, "image-repeat review path")


class ImageRepeatSemanticReview(PersistedContractModel):
    review_version: Literal["intended-loop-review-v1"] = "intended-loop-review-v1"
    verdict: ImageRepeatReviewVerdict
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    failure_codes: list[ImageRepeatFailureCode]
    evidence: str
    judged_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    criteria_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer_provider: str
    reviewer_model: str
    independent: bool
    review_artifact: ImageRepeatReviewArtifactBinding | None = None

    @field_validator("evidence")
    @classmethod
    def validate_evidence(cls, value: str) -> str:
        return _trimmed_text(value, "review evidence", maximum=4096)

    @field_validator("reviewer_provider", "reviewer_model")
    @classmethod
    def validate_reviewer_identity(cls, value: str) -> str:
        return validate_backend_label(value, "reviewer identity")

    @model_validator(mode="after")
    def validate_verdict(self) -> Self:
        _validate_unique_codes(self.failure_codes)
        if self.verdict == "accept" and self.failure_codes:
            raise ValueError("accepted semantic review must not contain failure codes")
        if self.verdict == "accept" and self.confidence < INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE:
            raise ValueError(
                "accepted semantic review confidence must meet the fail-closed minimum"
            )
        if self.verdict == "reject" and not self.failure_codes:
            raise ValueError("rejected semantic review must contain failure codes")
        if self.verdict == "uncertain" and "insufficient_evidence" not in self.failure_codes:
            raise ValueError("uncertain semantic review must include insufficient_evidence")
        return self


class ImageRepeatIntent(PersistedContractModel):
    intended_behavior: str
    alpha_policy: ImageRepeatAlphaPolicy
    coverage_policy: ImageRepeatCoveragePolicy
    criteria_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("intended_behavior")
    @classmethod
    def validate_intended_behavior(cls, value: str) -> str:
        return _trimmed_text(value, "intended_behavior", maximum=512)


class ImageRepeatAdmissionConstruction(PersistedContractModel):
    mode: Literal["admitted"] = "admitted"
    algorithm: Literal["direct-wrap-admission-v2"] = DIRECT_WRAP_ADMISSION_ALGORITHM
    source_bytes_preserved: Literal[True] = True


class ImageRepeatRepairConstruction(PersistedContractModel):
    mode: Literal["repaired"] = "repaired"
    algorithm: Literal["endpoint-alpha-reconstructed-anchored-repair-v4"] = (
        ENDPOINT_CONDITIONED_REPAIR_ALGORITHM
    )
    context_span_px: int = Field(ge=2, le=MAX_CONTEXT_SPAN_PX)
    repair_span_px: int = Field(ge=4, le=MAX_REPAIR_SPAN_PX)
    mask_semantics: Literal["white_edit_black_preserve"] = "white_edit_black_preserve"
    immutable_regions_reimposed: Literal[True] = True
    endpoint_anchor_algorithm: Literal["linear-light-premultiplied-smoothstep-v1"] = (
        ENDPOINT_ANCHOR_ALGORITHM
    )
    endpoint_anchor_span_px: int = Field(ge=1, le=8)
    endpoint_anchors_reimposed: Literal[True] = True
    alpha_reconstruction_algorithm: Literal["source-endpoint-alpha-smoothstep-v1"] = (
        ALPHA_RECONSTRUCTION_ALGORITHM
    )
    alpha_topology_reconstructed: Literal[True] = True
    provider_rgb_interior_preserved: Literal[True] = True
    deterministically_reconstructible: Literal[True] = True
    provider_candidate: ImageRepeatAssetBinding
    provider: str
    model: str
    attempts: int = Field(ge=1, le=6)

    @field_validator("provider", "model")
    @classmethod
    def validate_provider_identity(cls, value: str) -> str:
        return validate_backend_label(value, "repair provider identity")

    @model_validator(mode="after")
    def validate_reconstruction_geometry(self) -> Self:
        if self.repair_span_px < self.endpoint_anchor_span_px * 2 + 2:
            raise ValueError(
                "repair span must leave at least two provider RGB interior pixels after anchors"
            )
        return self


type ImageRepeatConstruction = Annotated[
    ImageRepeatAdmissionConstruction | ImageRepeatRepairConstruction,
    Field(discriminator="mode"),
]


class ImageRepeatAdmissionLineage(PersistedContractModel):
    mode: Literal["admitted"] = "admitted"
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    repeat_unit_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ImageRepeatRepairLineage(PersistedContractModel):
    mode: Literal["repaired"] = "repaired"
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    head_context_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    tail_context_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    conditioning_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mask_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider_candidate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    raw_repair_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider_interior_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    alpha_reconstructed_repair_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    repair_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    repeat_unit_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


type ImageRepeatLineage = Annotated[
    ImageRepeatAdmissionLineage | ImageRepeatRepairLineage,
    Field(discriminator="mode"),
]


class ImageRepeatValidation(PersistedContractModel):
    policy: ImageRepeatValidationPolicy
    deterministic: ImageRepeatDeterministicReport
    intended_loop: ImageRepeatSemanticReview
    other_axis_status: Literal["not_evaluated"] = "not_evaluated"


class ImageRepeatManifest(PersistedContractModel):
    schema_version: Literal[2] = IMAGE_REPEAT_SCHEMA_VERSION
    kind: Literal["single_axis_repeat_unit"] = "single_axis_repeat_unit"
    axis: ImageRepeatAxis
    decision: ImageRepeatDecision
    source: ImageRepeatAssetBinding
    repeat_unit: ImageRepeatAssetBinding
    period_px: int = Field(ge=2)
    cross_axis_extent_px: int = Field(ge=1)
    intent: ImageRepeatIntent
    construction: ImageRepeatConstruction
    validation: ImageRepeatValidation
    lineage: ImageRepeatLineage
    rights_status: RightsStatus

    @model_validator(mode="after")
    def validate_bindings(self) -> Self:
        if self.decision != self.construction.mode or self.decision != self.lineage.mode:
            raise ValueError("image-repeat decision must match construction and lineage modes")
        source_period = self.source.width if self.axis == "x" else self.source.height
        source_cross = self.source.height if self.axis == "x" else self.source.width
        repeat_period = self.repeat_unit.width if self.axis == "x" else self.repeat_unit.height
        repeat_cross = self.repeat_unit.height if self.axis == "x" else self.repeat_unit.width
        if repeat_period != self.period_px or source_cross != self.cross_axis_extent_px:
            raise ValueError("image-repeat declared geometry does not match asset bindings")
        if repeat_cross != self.cross_axis_extent_px:
            raise ValueError("image-repeat source and repeat-unit cross-axis extents must match")
        if self.decision == "admitted":
            if repeat_period != source_period or self.source.sha256 != self.repeat_unit.sha256:
                raise ValueError(
                    "admitted repeat unit must be a byte-identical source pass-through"
                )
        else:
            construction = self.construction
            if not isinstance(construction, ImageRepeatRepairConstruction):
                raise ValueError("repaired repeat unit requires repair construction")
            if repeat_period != source_period + construction.repair_span_px:
                raise ValueError("repaired repeat period must append the declared repair span")
            candidate_primary = (
                construction.provider_candidate.width
                if self.axis == "x"
                else construction.provider_candidate.height
            )
            candidate_cross = (
                construction.provider_candidate.height
                if self.axis == "x"
                else construction.provider_candidate.width
            )
            if candidate_primary != construction.context_span_px * 2 + construction.repair_span_px:
                raise ValueError("provider candidate geometry does not match repair construction")
            if candidate_cross != self.cross_axis_extent_px:
                raise ValueError("provider candidate cross-axis extent does not match repeat unit")
            if not isinstance(self.lineage, ImageRepeatRepairLineage):
                raise ValueError("repaired repeat unit requires repair lineage")
            if construction.provider_candidate.sha256 != self.lineage.provider_candidate_sha256:
                raise ValueError("provider candidate binding does not match repair lineage")
        if self.lineage.source_sha256 != self.source.sha256:
            raise ValueError("image-repeat source lineage must match source binding")
        if self.lineage.repeat_unit_sha256 != self.repeat_unit.sha256:
            raise ValueError("image-repeat output lineage must match repeat-unit binding")
        deterministic = self.validation.deterministic
        semantic = self.validation.intended_loop
        if deterministic.axis != self.axis or deterministic.verdict != "pass":
            raise ValueError(
                "persisted image-repeat artifact requires a passing declared-axis gate"
            )
        if semantic.verdict != "accept" or not semantic.independent:
            raise ValueError(
                "persisted image-repeat artifact requires independent semantic acceptance"
            )
        if semantic.judged_sha256 != self.repeat_unit.sha256:
            raise ValueError("semantic review must bind the exact repeat-unit digest")
        if semantic.criteria_sha256 != self.intent.criteria_sha256:
            raise ValueError("semantic review and intent criteria digests must match")
        return self


@dataclass(frozen=True, slots=True)
class ImageRepeatResult:
    data: bytes
    media_type: Literal["image/png"]
    axis: ImageRepeatAxis
    decision: ImageRepeatDecision
    artifact_path: str
    provenance_path: str
    manifest_path: str
    manifest_provenance_path: str
    period_px: int
    deterministic_report: ImageRepeatDeterministicReport
    semantic_review: ImageRepeatSemanticReview
    provider_candidate_path: str | None = None
    provider_candidate_provenance_path: str | None = None
    provider: str | None = None
    model: str | None = None
    attempts: int | None = None

    def __post_init__(self) -> None:
        candidate_paths = (
            self.provider_candidate_path,
            self.provider_candidate_provenance_path,
        )
        if self.decision == "repaired" and any(path is None for path in candidate_paths):
            raise ValueError("repaired image-repeat result requires provider-candidate evidence")
        if self.decision == "admitted" and any(path is not None for path in candidate_paths):
            raise ValueError(
                "admitted image-repeat result must not bind provider-candidate evidence"
            )

    @property
    def bytes(self) -> bytes:
        return self.data


class ImageRepeatValidationError(ValueError):
    """A candidate was not proven repeatable on its declared axis."""


class ImageRepeatDeterministicValidationError(ImageRepeatValidationError):
    def __init__(self, report: ImageRepeatDeterministicReport) -> None:
        self.report = report
        codes = ", ".join(report.failure_codes)
        super().__init__(f"image-repeat deterministic validation rejected candidate: {codes}")


class ImageRepeatSemanticValidationError(ImageRepeatValidationError):
    def __init__(self, review: IntendedLoopReview) -> None:
        self.review = review
        codes = ", ".join(review.failure_codes) or "no_failure_code"
        if review.verdict == "accept" and review.confidence < INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE:
            detail = (
                "accept_below_minimum_confidence: "
                f"{review.confidence:g} < {INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE:g}"
            )
        else:
            detail = codes
        super().__init__(f"intended-loop review {review.verdict}: {detail}")


class ImageRepeatReviewerUnavailableError(ImageRepeatValidationError):
    """No independent semantic reviewer was configured."""


class ImageRepeatRepairUnavailableError(ImageRepeatValidationError):
    """Explicit repair was requested without a masked-edit backend."""


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


def _validate_common_request(
    request: ImageRepeatAdmissionRequest | ImageRepeatRepairRequest,
) -> None:
    if not str(request.source_path).strip():
        raise ValueError("source_path must be non-empty")
    if not str(request.output_dir).strip():
        raise ValueError("output_dir must be non-empty")
    if request.axis not in {"x", "y"}:
        raise ValueError("image-repeat axis must be x or y")
    if request.alpha_policy not in {"preserve", "require_opaque"}:
        raise ValueError("image-repeat alpha_policy is invalid")
    if request.coverage_policy not in {"continuous", "sparse_allowed"}:
        raise ValueError("image-repeat coverage_policy is invalid")
    if not isinstance(request.validation_policy, ImageRepeatValidationPolicy):
        raise TypeError("validation_policy must be ImageRepeatValidationPolicy")
    assert_safe_path_segment(request.artifact_name, "artifact_name")
    assert_safe_path_segment(request.manifest_name, "manifest_name")
    assert_safe_path_segment(f"{request.artifact_name}.meta.json", "artifact provenance name")
    assert_safe_path_segment(f"{request.manifest_name}.meta.json", "manifest provenance name")
    if Path(request.artifact_name).suffix.lower() != ".png":
        raise ValueError("artifact_name must use a .png extension")
    if not request.manifest_name.endswith(".repeat.json"):
        raise ValueError("manifest_name must use an exact .repeat.json suffix")
    if request.artifact_name == request.manifest_name:
        raise ValueError("artifact_name and manifest_name must differ")
    _trimmed_text(request.intended_behavior, "intended_behavior", maximum=512)
    if request.source_ref is not None:
        assert_safe_path_segment(request.source_ref, "source_ref")
        assert_safe_path_segment(f"{request.source_ref}.meta.json", "source provenance ref")


def _trimmed_text(value: str, label: str, *, maximum: int) -> str:
    if not value or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{label} must be a trimmed string from 1 to {maximum} characters")
    return value


def _validate_unique_codes(codes: list[ImageRepeatFailureCode]) -> None:
    if len(codes) != len(set(codes)):
        raise ValueError("image-repeat failure codes must be unique")
    if any(code not in IMAGE_REPEAT_FAILURE_CODES for code in codes):
        raise ValueError("image-repeat failure code is not recognized")


def _unique_codes(codes: Iterable[ImageRepeatFailureCode]) -> list[ImageRepeatFailureCode]:
    result: list[ImageRepeatFailureCode] = []
    for code in codes:
        if code not in result:
            result.append(code)
    return result


def _bounded_integer(value: object, label: str, *, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer from {minimum} to {maximum}")


def _bounded_finite(
    value: object,
    label: str,
    *,
    minimum: float,
    maximum: float,
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or value < minimum
        or value > maximum
    ):
        raise ValueError(f"{label} must be finite from {minimum:g} to {maximum:g}")
