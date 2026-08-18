"""Retry-owned endpoint-conditioned loop synthesis and persistence."""

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

from stage_gen.contracts import (
    ArtifactProvenance,
    ArtifactRights,
    BinaryArtifact,
    InputProvenance,
    ProvenanceInput,
    SoftwareIdentity,
)
from stage_gen.media import inspect_image
from stage_gen.reliability import (
    RetryContext,
    RetryPolicy,
    assert_safe_path_segment,
    build_artifact_provenance,
    resolve_writable_path_within_root,
    retry_with_backoff,
    sanitize_for_persistence,
    serialize_provenance,
    sha256_hex,
)

from .models import (
    LOOP_SYNTHESIS_ALGORITHM,
    MASKED_IMAGE_EDIT_CAPABILITY,
    MAX_LOOP_PROVIDER_BYTES,
    MAX_LOOP_SOURCE_BYTES,
    JoinContinuity,
    LoopAssetBinding,
    LoopLineage,
    LoopSynthesisManifest,
    LoopSynthesisRequest,
    LoopSynthesisResult,
    MaskedImageEditBackend,
    MaskedImageEditRequest,
    ProviderLoopEdit,
    validate_backend_label,
)
from .persistence import (
    PendingLoopFile,
    PersistenceCheckpoint,
    persist_loop_files,
)
from .processing import (
    AcceptedLoopCandidate,
    PreparedLoopConditioning,
    accept_loop_candidate,
    prepare_loop_conditioning,
)

LOOP_SYNTHESIS_COMPONENT = SoftwareIdentity(name="@stage-gen/loop-synthesis", version="0.0.0")
LOCAL_MANIFEST_MODEL = "endpoint-conditioned-loop-manifest-v1"
DEFAULT_TOOL = SoftwareIdentity(name="stage-gen", version="0.0.0")
_MAX_PROVENANCE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class _LoadedSource:
    data: bytes
    provenance: ArtifactProvenance
    source_ref: str
    provenance_ref: str


@dataclass(frozen=True, slots=True)
class _OutputPaths:
    artifact: Path
    artifact_provenance: Path
    manifest: Path
    manifest_provenance: Path

    @property
    def all(self) -> tuple[Path, ...]:
        return (
            self.artifact,
            self.artifact_provenance,
            self.manifest,
            self.manifest_provenance,
        )


class LoopSynthesisService:
    """Own masked edit retries, deterministic seam gates, and artifact manifests."""

    def __init__(
        self,
        backend: MaskedImageEditBackend,
        *,
        retry_policy: RetryPolicy | None = None,
        tool: SoftwareIdentity = DEFAULT_TOOL,
        now: datetime | None = None,
        persistence_checkpoint: PersistenceCheckpoint | None = None,
    ) -> None:
        try:
            secrets = backend.secrets
            capability = backend.capability
            provider = backend.provider
            model = backend.model
        except Exception:
            raise ValueError("loop synthesis backend identity is invalid") from None
        if not isinstance(secrets, tuple) or any(not isinstance(item, str) for item in secrets):
            raise ValueError("loop synthesis backend secrets must be a tuple of strings")
        if capability != MASKED_IMAGE_EDIT_CAPABILITY:
            raise ValueError("loop synthesis requires a masked-image-edit backend")
        self._backend = backend
        self._secrets = secrets
        self._provider = validate_backend_label(provider, "provider", secrets=secrets)
        self._model = validate_backend_label(model, "model", secrets=secrets)
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
        await self._backend.aclose()

    async def synthesize(self, request: LoopSynthesisRequest) -> LoopSynthesisResult:
        outputs = await asyncio.to_thread(_resolve_outputs, request)
        source = await asyncio.to_thread(_load_source, request)
        rights = _resolve_rights(source.provenance.rights, request.output_rights)
        prepared = await asyncio.to_thread(
            prepare_loop_conditioning,
            source.data,
            context_band_px=request.context_band_px,
            bridge_width_px=request.bridge_width_px,
        )
        prompt = _edit_prompt(request.prompt)
        safe_metadata = sanitize_for_persistence(dict(request.metadata), self._secrets)
        if not isinstance(safe_metadata, dict):
            raise TypeError("loop synthesis metadata must be an object")
        conditioning_hash = sha256_hex(prepared.conditioning_png)
        mask_hash = sha256_hex(prepared.mask_png)
        attempts = 0

        async def attempt(
            context: RetryContext,
        ) -> tuple[ProviderLoopEdit, AcceptedLoopCandidate]:
            nonlocal attempts
            attempts = context.attempt
            edited = await self._backend.edit_once(
                MaskedImageEditRequest(
                    prompt=prompt,
                    conditioning_image=prepared.conditioning_png,
                    mask_image=prepared.mask_png,
                    width=prepared.conditioning_width,
                    height=prepared.height,
                    context_band_px=request.context_band_px,
                    bridge_width_px=request.bridge_width_px,
                    metadata={
                        **safe_metadata,
                        "algorithm": LOOP_SYNTHESIS_ALGORITHM,
                        "mask_semantics": "white-edit-black-preserve",
                        "conditioning_sha256": conditioning_hash,
                        "mask_sha256": mask_hash,
                    },
                    cancellation=context.cancellation,
                )
            )
            _validate_provider_envelope(edited)
            accepted = await asyncio.to_thread(
                accept_loop_candidate,
                prepared,
                edited.data,
                context_band_px=request.context_band_px,
                bridge_width_px=request.bridge_width_px,
                thresholds=request.thresholds,
            )
            return edited, accepted

        edited, accepted = await retry_with_backoff(
            attempt,
            policy=self._retry_policy,
            label=f"{self._provider} endpoint-conditioned loop synthesis",
            secrets=self._secrets,
            timeout_s=request.timeout_seconds,
            cancellation=request.cancellation,
        )
        if request.cancellation is not None:
            request.cancellation.raise_if_cancelled()
        lineage = _lineage(source, prepared, accepted)
        repeat_artifact = BinaryArtifact(data=accepted.repeat_unit_png, media_type="image/png")
        repeat_provenance = _repeat_unit_provenance(
            request=request,
            source=source,
            prepared=prepared,
            accepted=accepted,
            edited=edited,
            prompt=prompt,
            rights=rights,
            attempts=attempts,
            lineage=lineage,
            safe_metadata=safe_metadata,
            provider=self._provider,
            model=self._model,
            tool=self._tool,
        )
        repeat_record = build_artifact_provenance(
            repeat_artifact,
            repeat_provenance,
            secrets=self._secrets,
            now=self._now,
        )
        repeat_sidecar_bytes = serialize_provenance(repeat_record)
        manifest, manifest_bytes = _build_manifest(
            request=request,
            source=source,
            prepared=prepared,
            accepted=accepted,
            artifact_path=outputs.artifact,
            artifact_sidecar=outputs.artifact_provenance,
            provider=self._provider,
            model=self._model,
            attempts=attempts,
            rights=rights,
            lineage=lineage,
        )
        manifest_artifact = BinaryArtifact(data=manifest_bytes, media_type="application/json")
        manifest_provenance = _manifest_provenance(
            manifest=manifest,
            source=source,
            accepted=accepted,
            artifact_name=outputs.artifact.name,
            rights=rights,
            lineage=lineage,
            tool=self._tool,
        )
        manifest_record = build_artifact_provenance(
            manifest_artifact,
            manifest_provenance,
            secrets=self._secrets,
            now=self._now,
        )
        manifest_sidecar_bytes = serialize_provenance(manifest_record)
        if request.cancellation is not None:
            request.cancellation.raise_if_cancelled()
        await persist_loop_files(
            (
                PendingLoopFile("artifact", outputs.artifact, repeat_artifact.data),
                PendingLoopFile(
                    "artifact-provenance",
                    outputs.artifact_provenance,
                    repeat_sidecar_bytes,
                ),
                PendingLoopFile("manifest", outputs.manifest, manifest_artifact.data),
                PendingLoopFile(
                    "manifest-provenance",
                    outputs.manifest_provenance,
                    manifest_sidecar_bytes,
                ),
            ),
            cancellation=request.cancellation,
            secrets=self._secrets,
            checkpoint=self._persistence_checkpoint,
        )
        return LoopSynthesisResult(
            data=accepted.repeat_unit_png,
            media_type="image/png",
            provider=self._provider,
            model=self._model,
            attempts=attempts,
            artifact_path=str(outputs.artifact),
            provenance_path=str(outputs.artifact_provenance),
            manifest_path=str(outputs.manifest),
            manifest_provenance_path=str(outputs.manifest_provenance),
            period_px=prepared.width + request.bridge_width_px,
            metrics=accepted.metrics,
        )


def _resolve_outputs(request: LoopSynthesisRequest) -> _OutputPaths:
    artifact = resolve_writable_path_within_root(
        request.output_dir, request.artifact_name, "artifact_name"
    )
    manifest = resolve_writable_path_within_root(
        request.output_dir, request.manifest_name, "manifest_name"
    )
    source = Path(request.source_path).resolve()
    result = _OutputPaths(
        artifact=artifact,
        artifact_provenance=Path(f"{artifact}.meta.json"),
        manifest=manifest,
        manifest_provenance=Path(f"{manifest}.meta.json"),
    )
    identities = [_path_identity(path) for path in result.all]
    if len(set(identities)) != len(identities):
        raise ValueError("loop artifact, sidecar, and manifest targets must be distinct")
    protected = [
        source,
        Path(request.source_provenance_path).resolve()
        if request.source_provenance_path is not None
        else Path(f"{source}.meta.json").resolve(),
    ]
    protected_identities = {_path_identity(path) for path in protected}
    if protected_identities & set(identities):
        raise ValueError("loop outputs must not overwrite the source or source provenance")
    for target in result.all:
        if os.path.lexists(target):
            raise ValueError(f"loop output already exists: {target.name}")
    return result


def _path_identity(path: Path) -> str:
    normalized = unicodedata.normalize("NFC", os.path.normpath(str(path.resolve())))
    return normalized.casefold()


def _load_source(request: LoopSynthesisRequest) -> _LoadedSource:
    source_path = Path(request.source_path)
    source_data = _read_regular_file(source_path, "loop source", MAX_LOOP_SOURCE_BYTES)
    provenance_path = (
        Path(request.source_provenance_path)
        if request.source_provenance_path is not None
        else Path(f"{source_path}.meta.json")
    )
    provenance_data = _read_regular_file(
        provenance_path, "loop source provenance", _MAX_PROVENANCE_BYTES
    )
    try:
        provenance = ArtifactProvenance.model_validate_json(provenance_data)
    except Exception as error:
        raise ValueError("loop source provenance is not valid provenance-v1 JSON") from error
    if provenance.artifact is None:
        raise ValueError("loop source provenance has no artifact digest")
    if provenance.artifact.media_type != "image/png":
        raise ValueError("loop source provenance must declare image/png")
    if provenance.artifact.bytes != len(source_data) or provenance.artifact.sha256 != sha256_hex(
        source_data
    ):
        raise ValueError("loop source bytes do not match provenance digest")
    inspect_image(source_data, expected_media_type="image/png")
    source_ref = request.source_ref or source_path.name
    assert_safe_path_segment(source_ref, "derived source_ref")
    provenance_ref = f"{source_ref}.meta.json"
    assert_safe_path_segment(provenance_ref, "derived source provenance ref")
    return _LoadedSource(
        data=source_data,
        provenance=provenance,
        source_ref=source_ref,
        provenance_ref=provenance_ref,
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


def _resolve_rights(
    source_rights: ArtifactRights | None, requested: ArtifactRights | None
) -> ArtifactRights:
    if source_rights is not None and source_rights.status == "restricted":
        if requested is not None and requested.status != "restricted":
            raise ValueError("a restricted source requires restricted loop output rights")
        return requested or source_rights
    if (
        requested is not None
        and requested.status == "redistribution-approved"
        and (source_rights is None or source_rights.status != "redistribution-approved")
    ):
        raise ValueError("redistribution-approved loop output requires an approved source")
    if requested is not None:
        return requested
    return ArtifactRights(
        status="unreviewed",
        license_id=None,
        notice="Endpoint-conditioned loop output requires an independent rights review.",
        attribution=[],
        basis=[],
        reviewed_at=None,
    )


def _validate_provider_envelope(edited: ProviderLoopEdit) -> None:
    if not edited.data or len(edited.data) > MAX_LOOP_PROVIDER_BYTES:
        raise ValueError(f"masked edit output must be from 1 to {MAX_LOOP_PROVIDER_BYTES} bytes")
    if edited.media_type.strip().lower() != "image/png":
        raise ValueError("masked edit provider must return exact image/png")


def _edit_prompt(user_prompt: str) -> str:
    return (
        "Fill only the white-masked middle bridge of the supplied horizontal conditioning "
        "canvas. The black-masked source-end band on the left and source-start band on the "
        "right are immutable context. Continue structures, palette, lighting, alpha, and "
        "texture naturally across both boundaries. Do not blur, crossfade, mirror, copy, add "
        "borders, or modify either context band. Return one PNG at the exact input dimensions.\n"
        f"Creative direction: {user_prompt.strip()}"
    )


def _build_manifest(
    *,
    request: LoopSynthesisRequest,
    source: _LoadedSource,
    prepared: PreparedLoopConditioning,
    accepted: AcceptedLoopCandidate,
    artifact_path: Path,
    artifact_sidecar: Path,
    provider: str,
    model: str,
    attempts: int,
    rights: ArtifactRights,
    lineage: LoopLineage,
) -> tuple[LoopSynthesisManifest, bytes]:
    source_artifact = source.provenance.artifact
    if source_artifact is None:
        raise ValueError("loop source provenance has no artifact digest")
    manifest = LoopSynthesisManifest(
        source=LoopAssetBinding(
            path=source.source_ref,
            provenance_path=source.provenance_ref,
            sha256=source_artifact.sha256,
            bytes=source_artifact.bytes,
            width=prepared.width,
            height=prepared.height,
        ),
        repeat_unit=LoopAssetBinding(
            path=artifact_path.name,
            provenance_path=artifact_sidecar.name,
            sha256=sha256_hex(accepted.repeat_unit_png),
            bytes=len(accepted.repeat_unit_png),
            width=prepared.width + request.bridge_width_px,
            height=prepared.height,
        ),
        period_px=prepared.width + request.bridge_width_px,
        source_width_px=prepared.width,
        bridge_width_px=request.bridge_width_px,
        context_band_px=request.context_band_px,
        height_px=prepared.height,
        lineage=lineage,
        metrics=accepted.metrics,
        thresholds=_threshold_contract(request),
        provider=provider,
        model=model,
        attempts=attempts,
        rights_status=rights.status,
    )
    payload = manifest.model_dump(mode="json", by_alias=True)
    return manifest, (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()


def _threshold_dict(request: LoopSynthesisRequest) -> dict[str, float]:
    return {
        "pixel_mae": float(request.thresholds.pixel_mae),
        "pixel_p95": float(request.thresholds.pixel_p95),
        "pixel_max": float(request.thresholds.pixel_max),
        "gradient_mae": float(request.thresholds.gradient_mae),
        "gradient_p95": float(request.thresholds.gradient_p95),
        "gradient_max": float(request.thresholds.gradient_max),
        "perceptual_delta_e": float(request.thresholds.perceptual_delta_e),
        "perceptual_delta_e_p95": float(request.thresholds.perceptual_delta_e_p95),
        "perceptual_delta_e_max": float(request.thresholds.perceptual_delta_e_max),
    }


def _threshold_contract(request: LoopSynthesisRequest) -> JoinContinuity:
    return JoinContinuity.model_validate(_threshold_dict(request))


def _lineage(
    source: _LoadedSource,
    prepared: PreparedLoopConditioning,
    accepted: AcceptedLoopCandidate,
) -> LoopLineage:
    return LoopLineage(
        source_sha256=sha256_hex(source.data),
        left_context_sha256=sha256_hex(prepared.left_context_png),
        right_context_sha256=sha256_hex(prepared.right_context_png),
        conditioning_sha256=sha256_hex(prepared.conditioning_png),
        mask_sha256=sha256_hex(prepared.mask_png),
        bridge_sha256=sha256_hex(accepted.bridge_png),
        repeat_unit_sha256=sha256_hex(accepted.repeat_unit_png),
    )


def _repeat_unit_provenance(
    *,
    request: LoopSynthesisRequest,
    source: _LoadedSource,
    prepared: PreparedLoopConditioning,
    accepted: AcceptedLoopCandidate,
    edited: ProviderLoopEdit,
    prompt: str,
    rights: ArtifactRights,
    attempts: int,
    lineage: LoopLineage,
    safe_metadata: Mapping[str, object],
    provider: str,
    model: str,
    tool: SoftwareIdentity,
) -> ProvenanceInput:
    response: dict[str, object] = {
        "media_type": edited.media_type,
        "bytes": len(edited.data),
    }
    metadata = edited.response_metadata
    if metadata.request_id:
        response["request_id"] = metadata.request_id
    if metadata.created is not None:
        response["created"] = metadata.created
    if metadata.usage is not None:
        response["usage"] = metadata.usage
    lineage_dict = lineage.model_dump(mode="json", by_alias=True)
    hash_inputs = (
        (lineage.left_context_sha256, prepared.left_context_png),
        (lineage.right_context_sha256, prepared.right_context_png),
        (lineage.conditioning_sha256, prepared.conditioning_png),
        (lineage.mask_sha256, prepared.mask_png),
    )
    return ProvenanceInput(
        provider=provider,
        model=model,
        prompt=prompt,
        refs=[source.source_ref, *(f"sha256:{digest}" for digest, _data in hash_inputs)],
        inputs=[
            _input(source.source_ref, source.data, "content", "image/png"),
            *(
                _input(f"sha256:{digest}", data, "content", "image/png")
                for digest, data in hash_inputs
            ),
        ],
        params={
            "algorithm": LOOP_SYNTHESIS_ALGORITHM,
            "axis": "x",
            "context_band_px": request.context_band_px,
            "bridge_width_px": request.bridge_width_px,
            "period_px": prepared.width + request.bridge_width_px,
            "mask_semantics": "white-edit-black-preserve",
            "lineage": lineage_dict,
            "thresholds": _threshold_dict(request),
            "metadata": dict(safe_metadata),
        },
        validation={
            "source_provenance_bound": True,
            "source_dimensions": [prepared.width, prepared.height],
            "provider_dimensions": [prepared.conditioning_width, prepared.height],
            "provider_media_type": "image/png",
            "immutable_bands_verified": True,
            "immutable_bands_reimposed": True,
            "provider_band_changed_pixels": accepted.provider_band_changed_pixels,
            "bridge_cropped_without_context": True,
            "repeat_period_px": prepared.width + request.bridge_width_px,
            "joins": accepted.metrics.model_dump(mode="json", by_alias=True),
            "seam_thresholds_passed": True,
        },
        component=LOOP_SYNTHESIS_COMPONENT,
        tool=tool,
        attempts=attempts,
        response=response,
        rights=rights,
    )


def _manifest_provenance(
    *,
    manifest: LoopSynthesisManifest,
    source: _LoadedSource,
    accepted: AcceptedLoopCandidate,
    artifact_name: str,
    rights: ArtifactRights,
    lineage: LoopLineage,
    tool: SoftwareIdentity,
) -> ProvenanceInput:
    return ProvenanceInput(
        provider="local",
        model=LOCAL_MANIFEST_MODEL,
        prompt="assemble endpoint-conditioned horizontal loop manifest",
        refs=[source.source_ref, artifact_name],
        inputs=[
            _input(source.source_ref, source.data, "content", "image/png"),
            _input(artifact_name, accepted.repeat_unit_png, "content", "image/png"),
        ],
        params={
            "algorithm": LOOP_SYNTHESIS_ALGORITHM,
            "period_px": manifest.period_px,
            "provider_attempts": manifest.attempts,
            "lineage": lineage.model_dump(mode="json", by_alias=True),
        },
        validation={
            "schema_version": 1,
            "typed_contract": True,
            "repeat_unit_binding": True,
            "lineage_binding": True,
        },
        component=LOOP_SYNTHESIS_COMPONENT,
        tool=tool,
        attempts=1,
        rights=rights,
    )


def _input(
    ref: str,
    data: bytes,
    source: str,
    media_type: str,
) -> InputProvenance:
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
