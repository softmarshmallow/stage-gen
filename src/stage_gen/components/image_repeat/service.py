"""Admission, explicit repair, semantic review, and persistence for image repeats."""

from __future__ import annotations

import asyncio
import json
import os
import stat
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Self

from gnode import (
    ArtifactProvenance,
    ArtifactRights,
    BinaryArtifact,
    InputProvenance,
    ProvenanceInput,
    RetryContext,
    RetryPolicy,
    SoftwareIdentity,
    assert_safe_path_segment,
    build_artifact_provenance,
    resolve_writable_path_within_root,
    retry_with_backoff,
    sanitize_for_persistence,
    serialize_provenance,
    sha256_hex,
)
from stage_gen.media import inspect_image

from .models import (
    ALPHA_RECONSTRUCTION_ALGORITHM,
    DIRECT_WRAP_ADMISSION_ALGORITHM,
    ENDPOINT_CONDITIONED_REPAIR_ALGORITHM,
    INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE,
    MASKED_IMAGE_EDIT_CAPABILITY,
    MAX_IMAGE_REPEAT_PROVIDER_BYTES,
    MAX_IMAGE_REPEAT_SOURCE_BYTES,
    ImageRepeatAdmissionConstruction,
    ImageRepeatAdmissionLineage,
    ImageRepeatAdmissionRequest,
    ImageRepeatAssetBinding,
    ImageRepeatConstruction,
    ImageRepeatDeterministicReport,
    ImageRepeatDeterministicValidationError,
    ImageRepeatIntent,
    ImageRepeatLineage,
    ImageRepeatManifest,
    ImageRepeatRepairConstruction,
    ImageRepeatRepairLineage,
    ImageRepeatRepairRequest,
    ImageRepeatRepairUnavailableError,
    ImageRepeatResult,
    ImageRepeatReviewArtifactBinding,
    ImageRepeatReviewerUnavailableError,
    ImageRepeatSemanticReview,
    ImageRepeatSemanticValidationError,
    ImageRepeatValidation,
    IntendedLoopReview,
    IntendedLoopReviewer,
    IntendedLoopReviewRequest,
    MaskedImageEditBackend,
    MaskedImageEditRequest,
    ProviderImageRepeatEdit,
    validate_backend_label,
)
from .persistence import (
    PendingImageRepeatFile,
    PersistenceCheckpoint,
    persist_image_repeat_files,
)
from .processing import (
    AcceptedImageRepeatCandidate,
    PreparedImageRepeatConditioning,
    accept_repair_candidate,
    build_three_repeat_preview,
    canonical_intended_loop_criteria,
    prepare_repair_conditioning,
    validate_image_repeat,
    verify_image_repeat_artifact,
)

IMAGE_REPEAT_COMPONENT = SoftwareIdentity(name="@stage-gen/image-repeat", version="0.0.0")
LOCAL_ADMISSION_MODEL = "direct-wrap-admission-v2"
LOCAL_MANIFEST_MODEL = "image-repeat-manifest-v2"
DEFAULT_TOOL = SoftwareIdentity(name="stage-gen", version="0.0.0")
_MAX_PROVENANCE_BYTES = 2 * 1024 * 1024
_MAX_REVIEW_ARTIFACT_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class _LoadedSource:
    data: bytes
    provenance: ArtifactProvenance
    source_ref: str
    provenance_ref: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class _OutputPaths:
    artifact: Path
    artifact_provenance: Path
    manifest: Path
    manifest_provenance: Path
    review: Path
    review_provenance: Path
    provider_candidate: Path
    provider_candidate_provenance: Path

    @property
    def success(self) -> tuple[Path, ...]:
        return (
            self.artifact,
            self.artifact_provenance,
            self.manifest,
            self.manifest_provenance,
        )

    @property
    def reserved(self) -> tuple[Path, ...]:
        return (
            *self.success,
            self.review,
            self.review_provenance,
            self.provider_candidate,
            self.provider_candidate_provenance,
        )


@dataclass(frozen=True, slots=True)
class _SemanticOutcome:
    review: ImageRepeatSemanticReview
    canonical_bytes: bytes


@dataclass(frozen=True, slots=True)
class _ProviderCandidateEvidence:
    data: bytes
    sidecar: bytes
    binding: ImageRepeatAssetBinding


class ImageRepeatService:
    """Admit unchanged images or perform a separately requested provider repair."""

    def __init__(
        self,
        reviewer: IntendedLoopReviewer | None = None,
        *,
        repair_backend: MaskedImageEditBackend | None = None,
        retry_policy: RetryPolicy | None = None,
        tool: SoftwareIdentity = DEFAULT_TOOL,
        now: datetime | None = None,
        persistence_checkpoint: PersistenceCheckpoint | None = None,
    ) -> None:
        self._reviewer = reviewer
        self._repair_backend = repair_backend
        self._reviewer_provider: str | None = None
        self._reviewer_model: str | None = None
        self._reviewer_secrets: tuple[str, ...] = ()
        self._repair_provider: str | None = None
        self._repair_model: str | None = None
        self._repair_secrets: tuple[str, ...] = ()
        if reviewer is not None:
            provider, model, secrets = _validated_backend_identity(reviewer, "reviewer")
            self._reviewer_provider = provider
            self._reviewer_model = model
            self._reviewer_secrets = secrets
        if repair_backend is not None:
            provider, model, secrets = _validated_backend_identity(
                repair_backend,
                "repair backend",
            )
            try:
                capability = repair_backend.capability
            except Exception:
                raise ValueError("image-repeat repair backend capability is invalid") from None
            if capability != MASKED_IMAGE_EDIT_CAPABILITY:
                raise ValueError("image-repeat repair requires a masked-image-edit backend")
            self._repair_provider = provider
            self._repair_model = model
            self._repair_secrets = secrets
        self._secrets = tuple(dict.fromkeys((*self._reviewer_secrets, *self._repair_secrets)))
        self._retry_policy = retry_policy
        self._tool = tool
        self._now = now
        self._persistence_checkpoint = persistence_checkpoint

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        del exc_type, exc, traceback
        await self.aclose()

    async def aclose(self) -> None:
        closed: set[int] = set()
        for resource in (self._reviewer, self._repair_backend):
            if resource is None or id(resource) in closed:
                continue
            closed.add(id(resource))
            await resource.aclose()

    async def admit(self, request: ImageRepeatAdmissionRequest) -> ImageRepeatResult:
        """Pass through a source only after deterministic and independent semantic gates."""

        outputs = await asyncio.to_thread(_resolve_outputs, request)
        source = await asyncio.to_thread(_load_source, request)
        rights = _resolve_rights(source.provenance.rights, request.output_rights)
        safe_metadata = _safe_metadata(request.metadata, self._secrets)
        report = await asyncio.to_thread(
            validate_image_repeat,
            source.data,
            axis=request.axis,
            alpha_policy=request.alpha_policy,
            coverage_policy=request.coverage_policy,
            validation_policy=request.validation_policy,
        )
        if report.verdict != "pass":
            raise ImageRepeatDeterministicValidationError(report)
        self._assert_reviewer_independent(source, additional_producer=None)
        preview = await asyncio.to_thread(
            build_three_repeat_preview,
            source.data,
            axis=request.axis,
        )
        criteria = _criteria_bytes(request)
        semantic = await self._review(
            request=request,
            outputs=outputs,
            repeat_unit_data=source.data,
            preview=preview,
            criteria=criteria,
            report=report,
        )
        lineage = ImageRepeatAdmissionLineage(
            source_sha256=sha256_hex(source.data),
            repeat_unit_sha256=sha256_hex(source.data),
        )
        construction = ImageRepeatAdmissionConstruction()
        return await self._persist_success(
            request=request,
            outputs=outputs,
            source=source,
            repeat_unit_data=source.data,
            report=report,
            semantic=semantic,
            criteria=criteria,
            preview=preview,
            construction=construction,
            lineage=lineage,
            rights=rights,
            safe_metadata=safe_metadata,
            generation=None,
            prepared=None,
            accepted=None,
            provider_prompt=None,
            attempts=None,
            provider_candidate=None,
        )

    async def repair(self, request: ImageRepeatRepairRequest) -> ImageRepeatResult:
        """Run provider repair only when the caller invokes this explicit operation."""

        if self._repair_backend is None:
            raise ImageRepeatRepairUnavailableError(
                "explicit image-repeat repair requires a masked-image-edit backend"
            )
        if self._repair_provider is None or self._repair_model is None:
            raise ImageRepeatRepairUnavailableError("image-repeat repair backend is unavailable")
        repair_backend = self._repair_backend
        outputs = await asyncio.to_thread(_resolve_outputs, request)
        source = await asyncio.to_thread(_load_source, request)
        self._assert_reviewer_independent(
            source,
            additional_producer=(self._repair_provider, self._repair_model),
        )
        rights = _resolve_rights(source.provenance.rights, request.output_rights)
        safe_metadata = _safe_metadata(request.metadata, self._secrets)
        prepared = await asyncio.to_thread(
            prepare_repair_conditioning,
            source.data,
            axis=request.axis,
            context_span_px=request.context_span_px,
            repair_span_px=request.repair_span_px,
        )
        prompt = _repair_prompt(request)
        attempts = 0
        conditioning_hash = sha256_hex(prepared.conditioning_png)
        mask_hash = sha256_hex(prepared.mask_png)

        async def attempt(
            context: RetryContext,
        ) -> tuple[ProviderImageRepeatEdit, AcceptedImageRepeatCandidate]:
            nonlocal attempts
            attempts = context.attempt
            edited = await repair_backend.edit_once(
                MaskedImageEditRequest(
                    prompt=prompt,
                    conditioning_image=prepared.conditioning_png,
                    mask_image=prepared.mask_png,
                    width=prepared.conditioning_width,
                    height=prepared.conditioning_height,
                    axis=request.axis,
                    context_span_px=request.context_span_px,
                    repair_span_px=request.repair_span_px,
                    metadata={
                        **safe_metadata,
                        "algorithm": ENDPOINT_CONDITIONED_REPAIR_ALGORITHM,
                        "axis": request.axis,
                        "mask_semantics": "white_edit_black_preserve",
                        "alpha_reconstruction_algorithm": ALPHA_RECONSTRUCTION_ALGORITHM,
                        "provider_responsibility": "rgb_appearance",
                        "component_responsibility": "alpha_topology_and_endpoint_continuity",
                        "conditioning_sha256": conditioning_hash,
                        "mask_sha256": mask_hash,
                    },
                    cancellation=context.cancellation,
                )
            )
            _validate_provider_envelope(edited)
            accepted = await asyncio.to_thread(
                accept_repair_candidate,
                prepared,
                edited.data,
                context_span_px=request.context_span_px,
                repair_span_px=request.repair_span_px,
                alpha_policy=request.alpha_policy,
                coverage_policy=request.coverage_policy,
                validation_policy=request.validation_policy,
            )
            return edited, accepted

        generation, accepted = await retry_with_backoff(
            attempt,
            policy=self._retry_policy,
            label=f"{self._repair_provider} endpoint-conditioned image-repeat repair",
            secrets=self._repair_secrets,
            timeout_s=request.timeout_seconds,
            cancellation=request.cancellation,
        )
        if request.cancellation is not None:
            request.cancellation.raise_if_cancelled()
        preview = await asyncio.to_thread(
            build_three_repeat_preview,
            accepted.repeat_unit_png,
            axis=request.axis,
        )
        criteria = _criteria_bytes(request)
        semantic = await self._review(
            request=request,
            outputs=outputs,
            repeat_unit_data=accepted.repeat_unit_png,
            preview=preview,
            criteria=criteria,
            report=accepted.deterministic_report,
        )
        provider_candidate = await asyncio.to_thread(
            _provider_candidate_evidence,
            request=request,
            outputs=outputs,
            generation=generation,
            prepared=prepared,
            provider_prompt=prompt,
            provider=self._repair_provider,
            model=self._repair_model,
            attempts=attempts,
            rights=rights,
            safe_metadata=safe_metadata,
            tool=self._tool,
            now=self._now,
            secrets=self._secrets,
        )
        lineage = ImageRepeatRepairLineage(
            source_sha256=sha256_hex(source.data),
            head_context_sha256=sha256_hex(prepared.head_context_png),
            tail_context_sha256=sha256_hex(prepared.tail_context_png),
            conditioning_sha256=conditioning_hash,
            mask_sha256=mask_hash,
            provider_candidate_sha256=sha256_hex(provider_candidate.data),
            raw_repair_sha256=sha256_hex(accepted.raw_repair_png),
            provider_interior_sha256=sha256_hex(accepted.provider_interior_png),
            alpha_reconstructed_repair_sha256=sha256_hex(accepted.alpha_reconstructed_repair_png),
            repair_sha256=sha256_hex(accepted.repair_png),
            repeat_unit_sha256=sha256_hex(accepted.repeat_unit_png),
        )
        construction = ImageRepeatRepairConstruction(
            context_span_px=request.context_span_px,
            repair_span_px=request.repair_span_px,
            endpoint_anchor_span_px=accepted.endpoint_anchor_span_px,
            provider_candidate=provider_candidate.binding,
            provider=self._repair_provider,
            model=self._repair_model,
            attempts=attempts,
        )
        return await self._persist_success(
            request=request,
            outputs=outputs,
            source=source,
            repeat_unit_data=accepted.repeat_unit_png,
            report=accepted.deterministic_report,
            semantic=semantic,
            criteria=criteria,
            preview=preview,
            construction=construction,
            lineage=lineage,
            rights=rights,
            safe_metadata=safe_metadata,
            generation=generation,
            prepared=prepared,
            accepted=accepted,
            provider_prompt=prompt,
            attempts=attempts,
            provider_candidate=provider_candidate,
        )

    def _assert_reviewer_independent(
        self,
        source: _LoadedSource,
        *,
        additional_producer: tuple[str, str] | None,
    ) -> None:
        if (
            self._reviewer is None
            or self._reviewer_provider is None
            or self._reviewer_model is None
        ):
            raise ImageRepeatReviewerUnavailableError(
                "image-repeat admission requires an independent intended-loop reviewer"
            )
        reviewer = (self._reviewer_provider, self._reviewer_model)
        source_producer = (source.provenance.provider, source.provenance.model)
        if reviewer in (source_producer, additional_producer):
            raise ImageRepeatReviewerUnavailableError(
                "intended-loop reviewer must be independent from the image producer"
            )

    async def _review(
        self,
        *,
        request: ImageRepeatAdmissionRequest | ImageRepeatRepairRequest,
        outputs: _OutputPaths,
        repeat_unit_data: bytes,
        preview: bytes,
        criteria: bytes,
        report: ImageRepeatDeterministicReport,
    ) -> _SemanticOutcome:
        if (
            self._reviewer is None
            or self._reviewer_provider is None
            or self._reviewer_model is None
        ):
            raise ImageRepeatReviewerUnavailableError(
                "image-repeat admission requires an independent intended-loop reviewer"
            )
        if request.cancellation is not None:
            request.cancellation.raise_if_cancelled()
        raw = await self._reviewer.review(
            IntendedLoopReviewRequest(
                preview_png=preview,
                preview_sha256=sha256_hex(preview),
                judged_sha256=sha256_hex(repeat_unit_data),
                criteria_sha256=sha256_hex(criteria),
                review_artifact_path=outputs.review,
                axis=request.axis,
                intended_behavior=request.intended_behavior,
                deterministic_report=report,
                cancellation=request.cancellation,
            )
        )
        if not isinstance(raw, IntendedLoopReview):
            raise TypeError("intended-loop reviewer must return IntendedLoopReview")
        if request.cancellation is not None:
            request.cancellation.raise_if_cancelled()
        if raw.verdict == "accept" and raw.confidence < INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE:
            raise ImageRepeatSemanticValidationError(raw)
        review_artifact = await asyncio.to_thread(
            _review_artifact_binding,
            raw,
            outputs,
        )
        semantic = ImageRepeatSemanticReview(
            verdict=raw.verdict,
            confidence=float(raw.confidence),
            failure_codes=list(raw.failure_codes),
            evidence=raw.evidence,
            judged_sha256=sha256_hex(repeat_unit_data),
            preview_sha256=sha256_hex(preview),
            criteria_sha256=sha256_hex(criteria),
            reviewer_provider=self._reviewer_provider,
            reviewer_model=self._reviewer_model,
            independent=True,
            review_artifact=review_artifact,
        )
        canonical = _canonical_review_bytes(semantic)
        if raw.verdict != "accept":
            raise ImageRepeatSemanticValidationError(raw)
        return _SemanticOutcome(review=semantic, canonical_bytes=canonical)

    async def _persist_success(
        self,
        *,
        request: ImageRepeatAdmissionRequest | ImageRepeatRepairRequest,
        outputs: _OutputPaths,
        source: _LoadedSource,
        repeat_unit_data: bytes,
        report: ImageRepeatDeterministicReport,
        semantic: _SemanticOutcome,
        criteria: bytes,
        preview: bytes,
        construction: ImageRepeatConstruction,
        lineage: ImageRepeatLineage,
        rights: ArtifactRights,
        safe_metadata: Mapping[str, object],
        generation: ProviderImageRepeatEdit | None,
        prepared: PreparedImageRepeatConditioning | None,
        accepted: AcceptedImageRepeatCandidate | None,
        provider_prompt: str | None,
        attempts: int | None,
        provider_candidate: _ProviderCandidateEvidence | None,
    ) -> ImageRepeatResult:
        if isinstance(construction, ImageRepeatRepairConstruction):
            if provider_candidate is None:
                raise ValueError("repaired image-repeat provider-candidate evidence is incomplete")
            if provider_candidate.binding != construction.provider_candidate:
                raise ValueError("provider-candidate evidence does not match repair construction")
        elif provider_candidate is not None:
            raise ValueError("admitted image-repeat must not bind provider-candidate evidence")
        repeat_artifact = BinaryArtifact(data=repeat_unit_data, media_type="image/png")
        repeat_provenance = _repeat_unit_provenance(
            request=request,
            source=source,
            repeat_unit_data=repeat_unit_data,
            report=report,
            semantic=semantic,
            criteria=criteria,
            preview=preview,
            construction=construction,
            lineage=lineage,
            rights=rights,
            safe_metadata=safe_metadata,
            generation=generation,
            prepared=prepared,
            accepted=accepted,
            provider_prompt=provider_prompt,
            attempts=attempts,
            provider_candidate=provider_candidate,
            tool=self._tool,
        )
        repeat_record = build_artifact_provenance(
            repeat_artifact,
            repeat_provenance,
            secrets=self._secrets,
            now=self._now,
        )
        repeat_sidecar = serialize_provenance(repeat_record)
        manifest, manifest_bytes = _build_manifest(
            request=request,
            source=source,
            repeat_unit_data=repeat_unit_data,
            artifact_path=outputs.artifact,
            artifact_sidecar=outputs.artifact_provenance,
            report=report,
            semantic=semantic.review,
            criteria=criteria,
            construction=construction,
            lineage=lineage,
            rights=rights,
        )
        await asyncio.to_thread(
            verify_image_repeat_artifact,
            source.data,
            repeat_unit_data,
            manifest,
            provider_candidate_data=(
                provider_candidate.data if provider_candidate is not None else None
            ),
        )
        manifest_artifact = BinaryArtifact(data=manifest_bytes, media_type="application/json")
        manifest_provenance = _manifest_provenance(
            manifest=manifest,
            manifest_bytes=manifest_bytes,
            source=source,
            repeat_unit_data=repeat_unit_data,
            artifact_name=outputs.artifact.name,
            criteria=criteria,
            preview=preview,
            semantic=semantic,
            provider_candidate=provider_candidate,
            rights=rights,
            tool=self._tool,
        )
        manifest_record = build_artifact_provenance(
            manifest_artifact,
            manifest_provenance,
            secrets=self._secrets,
            now=self._now,
        )
        manifest_sidecar = serialize_provenance(manifest_record)
        if request.cancellation is not None:
            request.cancellation.raise_if_cancelled()
        pending = [
            PendingImageRepeatFile("artifact", outputs.artifact, repeat_unit_data),
            PendingImageRepeatFile(
                "artifact-provenance",
                outputs.artifact_provenance,
                repeat_sidecar,
            ),
            PendingImageRepeatFile("manifest", outputs.manifest, manifest_bytes),
            PendingImageRepeatFile(
                "manifest-provenance",
                outputs.manifest_provenance,
                manifest_sidecar,
            ),
        ]
        if provider_candidate is not None:
            pending.extend(
                (
                    PendingImageRepeatFile(
                        "provider-candidate",
                        outputs.provider_candidate,
                        provider_candidate.data,
                    ),
                    PendingImageRepeatFile(
                        "provider-candidate-provenance",
                        outputs.provider_candidate_provenance,
                        provider_candidate.sidecar,
                    ),
                )
            )
        await persist_image_repeat_files(
            tuple(pending),
            cancellation=request.cancellation,
            secrets=self._secrets,
            checkpoint=self._persistence_checkpoint,
        )
        if isinstance(construction, ImageRepeatRepairConstruction):
            provider = construction.provider
            model = construction.model
            result_attempts = construction.attempts
        else:
            provider = None
            model = None
            result_attempts = None
        return ImageRepeatResult(
            data=repeat_unit_data,
            media_type="image/png",
            axis=request.axis,
            decision=construction.mode,
            artifact_path=str(outputs.artifact),
            provenance_path=str(outputs.artifact_provenance),
            manifest_path=str(outputs.manifest),
            manifest_provenance_path=str(outputs.manifest_provenance),
            period_px=manifest.period_px,
            deterministic_report=report,
            semantic_review=semantic.review,
            provider_candidate_path=(
                str(outputs.provider_candidate) if provider_candidate is not None else None
            ),
            provider_candidate_provenance_path=(
                str(outputs.provider_candidate_provenance)
                if provider_candidate is not None
                else None
            ),
            provider=provider,
            model=model,
            attempts=result_attempts,
        )


def _resolve_outputs(
    request: ImageRepeatAdmissionRequest | ImageRepeatRepairRequest,
) -> _OutputPaths:
    artifact = resolve_writable_path_within_root(
        request.output_dir,
        request.artifact_name,
        "artifact_name",
    )
    manifest = resolve_writable_path_within_root(
        request.output_dir,
        request.manifest_name,
        "manifest_name",
    )
    review_name = _review_artifact_name(request)
    review = resolve_writable_path_within_root(request.output_dir, review_name, "review name")
    provider_candidate_name = _provider_candidate_name(request)
    provider_candidate = resolve_writable_path_within_root(
        request.output_dir,
        provider_candidate_name,
        "provider candidate artifact name",
    )
    source = Path(request.source_path).resolve()
    result = _OutputPaths(
        artifact=artifact,
        artifact_provenance=Path(f"{artifact}.meta.json"),
        manifest=manifest,
        manifest_provenance=Path(f"{manifest}.meta.json"),
        review=review,
        review_provenance=Path(f"{review}.meta.json"),
        provider_candidate=provider_candidate,
        provider_candidate_provenance=Path(f"{provider_candidate}.meta.json"),
    )
    identities = [_path_identity(path) for path in result.reserved]
    if len(set(identities)) != len(identities):
        raise ValueError(
            "image-repeat output, review, manifest, and sidecar targets must be distinct"
        )
    protected = [
        source,
        Path(request.source_provenance_path).resolve()
        if request.source_provenance_path is not None
        else Path(f"{source}.meta.json").resolve(),
    ]
    if {_path_identity(path) for path in protected} & set(identities):
        raise ValueError("image-repeat outputs must not overwrite source or source provenance")
    for target in result.reserved:
        if os.path.lexists(target):
            raise ValueError(f"image-repeat output already exists: {target.name}")
    return result


def _provider_candidate_name(
    request: ImageRepeatAdmissionRequest | ImageRepeatRepairRequest,
) -> str:
    descriptive = f"{request.artifact_name.removesuffix('.png')}.provider-candidate.png"
    if len(f"{descriptive}.meta.json") <= 128:
        assert_safe_path_segment(descriptive, "provider candidate artifact name")
        assert_safe_path_segment(
            f"{descriptive}.meta.json",
            "provider candidate provenance name",
        )
        return descriptive

    identity = f"{request.artifact_name}\0{request.manifest_name}".encode()
    digest = sha256_hex(identity)[:24]
    bounded = f"image-repeat-provider-{digest}.png"
    assert_safe_path_segment(bounded, "provider candidate artifact name")
    assert_safe_path_segment(
        f"{bounded}.meta.json",
        "provider candidate provenance name",
    )
    return bounded


def _review_artifact_name(
    request: ImageRepeatAdmissionRequest | ImageRepeatRepairRequest,
) -> str:
    descriptive = f"{request.manifest_name.removesuffix('.repeat.json')}.repeat-review.json"
    if len(f"{descriptive}.meta.json") <= 128:
        assert_safe_path_segment(descriptive, "review artifact name")
        assert_safe_path_segment(
            f"{descriptive}.meta.json",
            "review artifact provenance name",
        )
        return descriptive

    identity = f"{request.artifact_name}\0{request.manifest_name}".encode()
    digest = sha256_hex(identity)[:24]
    bounded = f"image-repeat-review-{digest}.json"
    assert_safe_path_segment(bounded, "review artifact name")
    assert_safe_path_segment(
        f"{bounded}.meta.json",
        "review artifact provenance name",
    )
    return bounded


def _path_identity(path: Path) -> str:
    normalized = unicodedata.normalize("NFC", os.path.normpath(str(path.resolve())))
    return normalized.casefold()


def _load_source(
    request: ImageRepeatAdmissionRequest | ImageRepeatRepairRequest,
) -> _LoadedSource:
    source_path = Path(request.source_path)
    source_data = _read_regular_file(
        source_path,
        "image-repeat source",
        MAX_IMAGE_REPEAT_SOURCE_BYTES,
    )
    provenance_path = (
        Path(request.source_provenance_path)
        if request.source_provenance_path is not None
        else Path(f"{source_path}.meta.json")
    )
    provenance_data = _read_regular_file(
        provenance_path,
        "image-repeat source provenance",
        _MAX_PROVENANCE_BYTES,
    )
    try:
        provenance = ArtifactProvenance.model_validate_json(provenance_data)
    except Exception as error:
        raise ValueError("image-repeat source provenance is not valid provenance JSON") from error
    if provenance.artifact is None:
        raise ValueError("image-repeat source provenance has no artifact digest")
    if provenance.artifact.media_type != "image/png":
        raise ValueError("image-repeat source provenance must declare image/png")
    if provenance.artifact.bytes != len(source_data) or provenance.artifact.sha256 != sha256_hex(
        source_data
    ):
        raise ValueError("image-repeat source bytes do not match provenance digest")
    facts = inspect_image(source_data, expected_media_type="image/png")
    source_ref = request.source_ref or source_path.name
    assert_safe_path_segment(source_ref, "derived source_ref")
    provenance_ref = f"{source_ref}.meta.json"
    assert_safe_path_segment(provenance_ref, "derived source provenance ref")
    return _LoadedSource(
        data=source_data,
        provenance=provenance,
        source_ref=source_ref,
        provenance_ref=provenance_ref,
        width=facts.width,
        height=facts.height,
    )


def _read_regular_file(path: Path, label: str, maximum_bytes: int) -> bytes:
    try:
        status = path.lstat()
    except FileNotFoundError as error:
        raise ValueError(f"{label} is missing") from error
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
        raise ValueError(f"{label} must be a regular non-symlink file")
    if status.st_size <= 0 or status.st_size > maximum_bytes:
        raise ValueError(f"{label} must be from 1 to {maximum_bytes} bytes")
    data = path.read_bytes()
    if len(data) != status.st_size:
        raise ValueError(f"{label} changed while it was being read")
    return data


def _validated_backend_identity(resource: object, label: str) -> tuple[str, str, tuple[str, ...]]:
    try:
        secrets = resource.secrets  # type: ignore[attr-defined]
        provider = resource.provider  # type: ignore[attr-defined]
        model = resource.model  # type: ignore[attr-defined]
    except Exception:
        raise ValueError(f"image-repeat {label} identity is invalid") from None
    if not isinstance(secrets, tuple) or any(not isinstance(item, str) for item in secrets):
        raise ValueError(f"image-repeat {label} secrets must be a tuple of strings")
    return (
        validate_backend_label(provider, "provider", secrets=secrets),
        validate_backend_label(model, "model", secrets=secrets),
        secrets,
    )


def _resolve_rights(
    source_rights: ArtifactRights | None,
    requested: ArtifactRights | None,
) -> ArtifactRights:
    if source_rights is not None and source_rights.status == "restricted":
        if requested is not None and requested.status != "restricted":
            raise ValueError("a restricted source requires restricted image-repeat output rights")
        return requested or source_rights
    if (
        requested is not None
        and requested.status == "redistribution-approved"
        and (source_rights is None or source_rights.status != "redistribution-approved")
    ):
        raise ValueError("redistribution-approved image-repeat output requires approved source")
    if requested is not None:
        return requested
    return ArtifactRights(
        status="unreviewed",
        attribution=[],
        basis=[],
        reviewed_at=None,
    )


def _safe_metadata(metadata: Mapping[str, object], secrets: tuple[str, ...]) -> dict[str, object]:
    safe = sanitize_for_persistence(dict(metadata), secrets)
    if not isinstance(safe, dict):
        raise TypeError("image-repeat metadata must be an object")
    result: dict[str, object] = {}
    result.update(safe)
    return result


def _validate_provider_envelope(edited: ProviderImageRepeatEdit) -> None:
    if not edited.data or len(edited.data) > MAX_IMAGE_REPEAT_PROVIDER_BYTES:
        raise ValueError(
            f"masked edit output must be from 1 to {MAX_IMAGE_REPEAT_PROVIDER_BYTES} bytes"
        )
    if edited.media_type.strip().lower() != "image/png":
        raise ValueError("masked edit provider must return exact image/png")


def _provider_candidate_evidence(
    *,
    request: ImageRepeatRepairRequest,
    outputs: _OutputPaths,
    generation: ProviderImageRepeatEdit,
    prepared: PreparedImageRepeatConditioning,
    provider_prompt: str,
    provider: str,
    model: str,
    attempts: int,
    rights: ArtifactRights,
    safe_metadata: Mapping[str, object],
    tool: SoftwareIdentity,
    now: datetime | None,
    secrets: tuple[str, ...],
) -> _ProviderCandidateEvidence:
    facts = inspect_image(generation.data, expected_media_type="image/png")
    if (facts.width, facts.height) != (
        prepared.conditioning_width,
        prepared.conditioning_height,
    ):
        raise ValueError("provider candidate dimensions do not match repair conditioning")
    inputs = [
        _input(
            f"sha256:{sha256_hex(prepared.conditioning_png)}",
            prepared.conditioning_png,
            "content",
            "image/png",
        ),
        _input(
            f"sha256:{sha256_hex(prepared.mask_png)}",
            prepared.mask_png,
            "content",
            "image/png",
        ),
    ]
    artifact = BinaryArtifact(data=generation.data, media_type="image/png")
    record = build_artifact_provenance(
        artifact,
        ProvenanceInput(
            provider=provider,
            model=model,
            prompt=provider_prompt,
            refs=[item.ref for item in inputs],
            inputs=inputs,
            params={
                "algorithm": ENDPOINT_CONDITIONED_REPAIR_ALGORITHM,
                "axis": request.axis,
                "context_span_px": request.context_span_px,
                "repair_span_px": request.repair_span_px,
                "mask_semantics": "white_edit_black_preserve",
                "alpha_reconstruction_algorithm": ALPHA_RECONSTRUCTION_ALGORITHM,
                "provider_responsibility": "rgb_appearance",
                "component_responsibility": "alpha_topology_and_endpoint_continuity",
                "metadata": dict(safe_metadata),
            },
            validation={
                "provider_dimensions": [facts.width, facts.height],
                "provider_media_type": "image/png",
                "exact_provider_candidate_preserved": True,
                "provider_candidate_role": "rgb_appearance_input",
            },
            component=IMAGE_REPEAT_COMPONENT,
            tool=tool,
            attempts=attempts,
            response=_provider_response(generation),
            rights=rights,
        ),
        secrets=secrets,
        now=now,
    )
    sidecar = serialize_provenance(record)
    return _ProviderCandidateEvidence(
        data=generation.data,
        sidecar=sidecar,
        binding=ImageRepeatAssetBinding(
            path=outputs.provider_candidate.name,
            provenance_path=outputs.provider_candidate_provenance.name,
            sha256=sha256_hex(generation.data),
            bytes=len(generation.data),
            width=facts.width,
            height=facts.height,
        ),
    )


def _provider_response(generation: ProviderImageRepeatEdit) -> dict[str, object]:
    response: dict[str, object] = {
        "media_type": "image/png",
        "bytes": len(generation.data),
    }
    if generation.response_metadata.request_id:
        response["request_id"] = generation.response_metadata.request_id
    if generation.response_metadata.created is not None:
        response["created"] = generation.response_metadata.created
    if generation.response_metadata.usage is not None:
        response["usage"] = generation.response_metadata.usage
    return response


def _repair_prompt(request: ImageRepeatRepairRequest) -> str:
    direction = "horizontal" if request.axis == "x" else "vertical"
    tail = "right" if request.axis == "x" else "bottom"
    head = "left" if request.axis == "x" else "top"
    return (
        f"Fill only the white-masked middle span of this {direction} conditioning canvas. "
        f"The black-masked source-{tail} context before it and source-{head} context after it "
        "are immutable. Paint a complete RGB appearance across every masked pixel, continuing "
        "structures, lighting, texture, orientation, and gravity naturally across both boundaries. "
        "The provider owns RGB appearance; downstream deterministic processing owns alpha topology "
        "and exact endpoint continuity, so provider alpha is not authoritative. Do not blur, "
        "crossfade, mirror, reverse, copy, add borders, rotate, or modify context. Return one PNG "
        "at the exact input dimensions.\n"
        f"Creative direction: {request.prompt.strip()}"
    )


def _criteria_bytes(
    request: ImageRepeatAdmissionRequest | ImageRepeatRepairRequest,
) -> bytes:
    return canonical_intended_loop_criteria(
        axis=request.axis,
        intended_behavior=request.intended_behavior,
        alpha_policy=request.alpha_policy,
        coverage_policy=request.coverage_policy,
        validation_policy=request.validation_policy,
    )


def _review_artifact_binding(
    review: IntendedLoopReview,
    outputs: _OutputPaths,
) -> ImageRepeatReviewArtifactBinding | None:
    if review.artifact_path is None or review.provenance_path is None:
        return None
    artifact_path = Path(review.artifact_path)
    provenance_path = Path(review.provenance_path)
    if _path_identity(artifact_path) != _path_identity(outputs.review):
        raise ValueError("intended-loop reviewer returned an unexpected artifact path")
    if _path_identity(provenance_path) != _path_identity(outputs.review_provenance):
        raise ValueError("intended-loop reviewer returned an unexpected provenance path")
    artifact_data = _read_regular_file(
        artifact_path,
        "intended-loop review artifact",
        _MAX_REVIEW_ARTIFACT_BYTES,
    )
    provenance_data = _read_regular_file(
        provenance_path,
        "intended-loop review provenance",
        _MAX_PROVENANCE_BYTES,
    )
    try:
        provenance = ArtifactProvenance.model_validate_json(provenance_data)
    except Exception as error:
        raise ValueError("intended-loop review provenance is invalid") from error
    if provenance.artifact is None:
        raise ValueError("intended-loop review provenance has no artifact digest")
    if provenance.artifact.media_type != "application/json":
        raise ValueError("intended-loop review artifact must be application/json")
    if provenance.artifact.sha256 != sha256_hex(artifact_data):
        raise ValueError("intended-loop review artifact does not match its provenance digest")
    if provenance.artifact.bytes != len(artifact_data):
        raise ValueError("intended-loop review artifact byte count does not match provenance")
    return ImageRepeatReviewArtifactBinding(
        path=artifact_path.name,
        provenance_path=provenance_path.name,
        sha256=sha256_hex(artifact_data),
        provenance_sha256=sha256_hex(provenance_data),
        bytes=len(artifact_data),
    )


def _canonical_review_bytes(review: ImageRepeatSemanticReview) -> bytes:
    return json.dumps(
        review.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def _build_manifest(
    *,
    request: ImageRepeatAdmissionRequest | ImageRepeatRepairRequest,
    source: _LoadedSource,
    repeat_unit_data: bytes,
    artifact_path: Path,
    artifact_sidecar: Path,
    report: ImageRepeatDeterministicReport,
    semantic: ImageRepeatSemanticReview,
    criteria: bytes,
    construction: ImageRepeatConstruction,
    lineage: ImageRepeatLineage,
    rights: ArtifactRights,
) -> tuple[ImageRepeatManifest, bytes]:
    source_artifact = source.provenance.artifact
    if source_artifact is None:
        raise ValueError("image-repeat source provenance has no artifact digest")
    repeat_facts = inspect_image(repeat_unit_data, expected_media_type="image/png")
    period = repeat_facts.width if request.axis == "x" else repeat_facts.height
    cross = repeat_facts.height if request.axis == "x" else repeat_facts.width
    manifest = ImageRepeatManifest(
        axis=request.axis,
        decision=construction.mode,
        source=ImageRepeatAssetBinding(
            path=source.source_ref,
            provenance_path=source.provenance_ref,
            sha256=source_artifact.sha256,
            bytes=source_artifact.bytes,
            width=source.width,
            height=source.height,
        ),
        repeat_unit=ImageRepeatAssetBinding(
            path=artifact_path.name,
            provenance_path=artifact_sidecar.name,
            sha256=sha256_hex(repeat_unit_data),
            bytes=len(repeat_unit_data),
            width=repeat_facts.width,
            height=repeat_facts.height,
        ),
        period_px=period,
        cross_axis_extent_px=cross,
        intent=ImageRepeatIntent(
            intended_behavior=request.intended_behavior,
            alpha_policy=request.alpha_policy,
            coverage_policy=request.coverage_policy,
            criteria_sha256=sha256_hex(criteria),
        ),
        construction=construction,
        validation=ImageRepeatValidation(
            policy=request.validation_policy,
            deterministic=report,
            intended_loop=semantic,
        ),
        lineage=lineage,
        rights_status=rights.status,
    )
    payload = manifest.model_dump(mode="json", exclude_none=True)
    return manifest, (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()


def _repeat_unit_provenance(
    *,
    request: ImageRepeatAdmissionRequest | ImageRepeatRepairRequest,
    source: _LoadedSource,
    repeat_unit_data: bytes,
    report: ImageRepeatDeterministicReport,
    semantic: _SemanticOutcome,
    criteria: bytes,
    preview: bytes,
    construction: ImageRepeatConstruction,
    lineage: ImageRepeatLineage,
    rights: ArtifactRights,
    safe_metadata: Mapping[str, object],
    generation: ProviderImageRepeatEdit | None,
    prepared: PreparedImageRepeatConditioning | None,
    accepted: AcceptedImageRepeatCandidate | None,
    provider_prompt: str | None,
    attempts: int | None,
    provider_candidate: _ProviderCandidateEvidence | None,
    tool: SoftwareIdentity,
) -> ProvenanceInput:
    common_inputs = [
        _input(source.source_ref, source.data, "content", "image/png"),
        _input(f"sha256:{sha256_hex(preview)}", preview, "content", "image/png"),
        _input(
            f"sha256:{sha256_hex(criteria)}",
            criteria,
            "content",
            "application/json",
        ),
        _input(
            f"sha256:{sha256_hex(semantic.canonical_bytes)}",
            semantic.canonical_bytes,
            "content",
            "application/json",
        ),
    ]
    refs = [item.ref for item in common_inputs]
    params: dict[str, object] = {
        "axis": request.axis,
        "decision": construction.mode,
        "intended_behavior": request.intended_behavior,
        "alpha_policy": request.alpha_policy,
        "coverage_policy": request.coverage_policy,
        "criteria_sha256": sha256_hex(criteria),
        "lineage": lineage.model_dump(mode="json"),
        "metadata": dict(safe_metadata),
    }
    validation: dict[str, object] = {
        "source_provenance_bound": True,
        "source_pixels_immutable": report.source_immutable,
        "declared_axis_only": True,
        "other_axis_status": "not_evaluated",
        "deterministic": report.model_dump(mode="json"),
        "intended_loop": semantic.review.model_dump(mode="json", exclude_none=True),
        "three_repeat_preview_sha256": sha256_hex(preview),
    }
    response: dict[str, object] | None = None
    if generation is None:
        provider = "local"
        model = LOCAL_ADMISSION_MODEL
        prompt = "admit an unchanged source as one verified single-axis repeat unit"
        operation_attempts = 1
        params["algorithm"] = DIRECT_WRAP_ADMISSION_ALGORITHM
        validation["source_bytes_preserved"] = repeat_unit_data == source.data
    else:
        if (
            prepared is None
            or accepted is None
            or provider_prompt is None
            or attempts is None
            or provider_candidate is None
            or not isinstance(construction, ImageRepeatRepairConstruction)
        ):
            raise ValueError("repaired image-repeat provenance is incomplete")
        provider = construction.provider
        model = construction.model
        prompt = provider_prompt
        operation_attempts = attempts
        params.update(
            {
                "algorithm": ENDPOINT_CONDITIONED_REPAIR_ALGORITHM,
                "context_span_px": construction.context_span_px,
                "repair_span_px": construction.repair_span_px,
                "mask_semantics": construction.mask_semantics,
                "endpoint_anchor_algorithm": construction.endpoint_anchor_algorithm,
                "endpoint_anchor_span_px": construction.endpoint_anchor_span_px,
                "endpoint_anchors_reimposed": construction.endpoint_anchors_reimposed,
                "alpha_reconstruction_algorithm": construction.alpha_reconstruction_algorithm,
                "alpha_topology_reconstructed": construction.alpha_topology_reconstructed,
                "provider_rgb_interior_preserved": (construction.provider_rgb_interior_preserved),
                "deterministically_reconstructible": (
                    construction.deterministically_reconstructible
                ),
                "provider_candidate": construction.provider_candidate.model_dump(mode="json"),
            }
        )
        repair_inputs = [
            _input(
                f"sha256:{sha256_hex(prepared.head_context_png)}",
                prepared.head_context_png,
                "content",
                "image/png",
            ),
            _input(
                f"sha256:{sha256_hex(prepared.tail_context_png)}",
                prepared.tail_context_png,
                "content",
                "image/png",
            ),
            _input(
                f"sha256:{sha256_hex(prepared.conditioning_png)}",
                prepared.conditioning_png,
                "content",
                "image/png",
            ),
            _input(
                f"sha256:{sha256_hex(prepared.mask_png)}",
                prepared.mask_png,
                "content",
                "image/png",
            ),
            _input(
                construction.provider_candidate.path,
                provider_candidate.data,
                "content",
                "image/png",
            ),
            _input(
                construction.provider_candidate.provenance_path,
                provider_candidate.sidecar,
                "content",
                "application/json",
            ),
        ]
        common_inputs.extend(repair_inputs)
        refs.extend(item.ref for item in repair_inputs)
        validation.update(
            {
                "provider_dimensions": [
                    prepared.conditioning_width,
                    prepared.conditioning_height,
                ],
                "provider_media_type": "image/png",
                "immutable_regions_reimposed": True,
                "provider_context_changed_pixels": accepted.provider_context_changed_pixels,
                "repair_cropped_without_context": True,
                "endpoint_anchors_reimposed": construction.endpoint_anchors_reimposed,
                "alpha_topology_reconstructed": construction.alpha_topology_reconstructed,
                "alpha_reconstructed_changed_pixels": (accepted.alpha_reconstructed_changed_pixels),
                "provider_rgb_interior_preserved": (construction.provider_rgb_interior_preserved),
                "deterministically_reconstructible": (
                    construction.deterministically_reconstructible
                ),
                "anchored_repair_changed_pixels": accepted.anchored_repair_changed_pixels,
            }
        )
        response = _provider_response(generation)
    return ProvenanceInput(
        provider=provider,
        model=model,
        prompt=prompt,
        refs=refs,
        inputs=common_inputs,
        params=params,
        validation=validation,
        component=IMAGE_REPEAT_COMPONENT,
        tool=tool,
        attempts=operation_attempts,
        response=response,
        rights=rights,
    )


def _manifest_provenance(
    *,
    manifest: ImageRepeatManifest,
    manifest_bytes: bytes,
    source: _LoadedSource,
    repeat_unit_data: bytes,
    artifact_name: str,
    criteria: bytes,
    preview: bytes,
    semantic: _SemanticOutcome,
    provider_candidate: _ProviderCandidateEvidence | None,
    rights: ArtifactRights,
    tool: SoftwareIdentity,
) -> ProvenanceInput:
    del manifest_bytes
    inputs = [
        _input(source.source_ref, source.data, "content", "image/png"),
        _input(artifact_name, repeat_unit_data, "content", "image/png"),
        _input(
            f"sha256:{sha256_hex(criteria)}",
            criteria,
            "content",
            "application/json",
        ),
        _input(f"sha256:{sha256_hex(preview)}", preview, "content", "image/png"),
        _input(
            f"sha256:{sha256_hex(semantic.canonical_bytes)}",
            semantic.canonical_bytes,
            "content",
            "application/json",
        ),
    ]
    if isinstance(manifest.construction, ImageRepeatRepairConstruction):
        if provider_candidate is None:
            raise ValueError("repaired manifest provenance requires provider-candidate evidence")
        inputs.extend(
            (
                _input(
                    manifest.construction.provider_candidate.path,
                    provider_candidate.data,
                    "content",
                    "image/png",
                ),
                _input(
                    manifest.construction.provider_candidate.provenance_path,
                    provider_candidate.sidecar,
                    "content",
                    "application/json",
                ),
            )
        )
    elif provider_candidate is not None:
        raise ValueError("admitted manifest provenance must not bind provider-candidate evidence")
    validation: dict[str, object] = {
        "typed_contract": True,
        "lower_snake_case": True,
        "repeat_unit_binding": True,
        "lineage_binding": True,
        "deterministic_gate": "pass",
        "semantic_gate": "accept",
        "semantic_review_independent": True,
        "other_axis_status": "not_evaluated",
    }
    if provider_candidate is not None:
        validation["provider_candidate_binding"] = True
        validation["repair_reconstruction_binding"] = True
    return ProvenanceInput(
        provider="local",
        model=LOCAL_MANIFEST_MODEL,
        prompt="assemble a verified single-axis image-repeat manifest",
        refs=[item.ref for item in inputs],
        inputs=inputs,
        params={
            "schema_version": 2,
            "axis": manifest.axis,
            "decision": manifest.decision,
            "period_px": manifest.period_px,
            "construction": manifest.construction.model_dump(mode="json"),
            "lineage": manifest.lineage.model_dump(mode="json"),
        },
        validation=validation,
        component=IMAGE_REPEAT_COMPONENT,
        tool=tool,
        attempts=1,
        rights=rights,
    )


def _input(ref: str, data: bytes, source: str, media_type: str) -> InputProvenance:
    if source not in {"content", "reference"}:
        raise ValueError("input provenance source must be content or reference")
    return InputProvenance.model_validate(
        {
            "ref": ref,
            "sha256": sha256_hex(data),
            "source": source,
            "bytes": len(data),
            "media_type": media_type,
        }
    )
