from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Self

from stage_gen.components._types import BinaryArtifact, run_validator
from stage_gen.contracts import ProvenanceInput, SoftwareIdentity
from stage_gen.media import assert_image_signature
from stage_gen.reliability import (
    RetryContext,
    RetryPolicy,
    hash_input_reference,
    retry_with_backoff,
    sanitize_reference,
    write_artifact_with_provenance_async,
)

from .models import (
    ImageGenerationBackend,
    ImageGenerationRequest,
    ImageGenerationResult,
    ProviderImage,
)
from .style import (
    STYLE_ANCHOR_RENDERER_VERSION,
    append_style_anchor_once,
    canonical_style_anchor_digest,
)

IMAGE_GENERATION_COMPONENT = SoftwareIdentity(name="@stage-gen/image-generation", version="0.0.0")
DEFAULT_TOOL = SoftwareIdentity(name="stage-gen", version="0.0.0")


class ImageGenerationService:
    """Own the complete retry -> validate -> atomic persistence operation."""

    def __init__(
        self,
        backend: ImageGenerationBackend,
        *,
        retry_policy: RetryPolicy | None = None,
        tool: SoftwareIdentity = DEFAULT_TOOL,
        now: datetime | None = None,
    ) -> None:
        self._backend = backend
        self._retry_policy = retry_policy
        self._tool = tool
        self._now = now

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

    @property
    def provider(self) -> str:
        """Stable provider identity used by higher-level cache contracts."""

        return self._backend.provider

    @property
    def model(self) -> str:
        """Stable model identity used by higher-level cache contracts."""

        return self._backend.model

    @property
    def supports_native_alpha(self) -> bool:
        """Whether this exact backend can request provider-generated alpha."""

        return bool(getattr(self._backend, "supports_native_alpha", False))

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        attempts = 0
        provider_request = request
        style_binding: dict[str, object] | None = None
        if request.style_anchor is not None and request.asset_kind is not None:
            provider_request = replace(
                request,
                prompt=append_style_anchor_once(
                    request.prompt,
                    request.style_anchor,
                    request.asset_kind,
                ),
            )
            style_binding = {
                "anchor_sha256": canonical_style_anchor_digest(request.style_anchor),
                "asset_kind": request.asset_kind,
                "compiler_sha256": request.style_anchor.compiler_sha256,
                "compiler_version": request.style_anchor.compiler_version,
                "renderer_version": STYLE_ANCHOR_RENDERER_VERSION,
                "resource_sha256": request.style_anchor.resource_sha256,
                "skill_sha256": request.style_anchor.skill_sha256,
                "style_mode": request.style_anchor.style_mode,
                "vocabulary_sha256": request.style_anchor.vocabulary_sha256,
            }

        async def attempt(context: RetryContext) -> tuple[ProviderImage, dict[str, object]]:
            nonlocal attempts
            attempts = context.attempt
            generated = await self._backend.generate_once(provider_request)
            assert_image_signature(generated.data, generated.media_type)
            facts = await run_validator(
                request.validate,
                BinaryArtifact(data=generated.data, media_type=generated.media_type),
            )
            return generated, facts

        generated, caller_facts = await retry_with_backoff(
            attempt,
            policy=self._retry_policy,
            label=f"{self._backend.provider} image generation",
            secrets=self._backend.secrets,
            timeout_s=request.timeout_seconds,
            cancellation=request.cancellation,
        )
        references = [
            reference.provenance_ref or sanitize_reference(reference.url)
            for reference in request.input_references
        ]
        metadata = generated.response_metadata
        response: dict[str, object] = {
            "media_type": generated.media_type,
            "bytes": len(generated.data),
        }
        if metadata.request_id:
            response["request_id"] = metadata.request_id
        if metadata.created is not None:
            response["created"] = metadata.created
        if metadata.usage is not None:
            response["usage"] = metadata.usage
        params: dict[str, object] = {"n": 1, "validated": request.validate is not None}
        if generated.applied_params is not None:
            params.update(generated.applied_params)
        else:
            if request.aspect_ratio is not None:
                params["aspect_ratio"] = request.aspect_ratio
            if request.resolution is not None:
                params["resolution"] = request.resolution
            if request.quality is not None:
                params["quality"] = request.quality
            if request.background is not None:
                params["background"] = request.background
            if request.output_format is not None:
                params["output_format"] = request.output_format
            if request.output_compression is not None:
                params["output_compression"] = request.output_compression
            if request.size is not None:
                params["size"] = request.size
            if request.moderation is not None:
                params["moderation"] = request.moderation
        if request.metadata:
            params["metadata"] = dict(request.metadata)
        if style_binding is not None:
            params["style_anchor"] = style_binding
        artifact = BinaryArtifact(data=generated.data, media_type=generated.media_type)
        provenance_path = await write_artifact_with_provenance_async(
            request.artifact_path,
            artifact,
            ProvenanceInput(
                schema_version=request.provenance_schema_version,
                provider=self._backend.provider,
                model=self._backend.model,
                seed=None,
                prompt=provider_request.prompt,
                refs=references,
                inputs=[
                    hash_input_reference(reference.url, reference.provenance_ref)
                    for reference in request.input_references
                ],
                params=params,
                validation={
                    "output_nonempty": True,
                    "base64": "strict",
                    "media_type": generated.media_type,
                    "signature": "matched",
                    "caller": request.validate is not None,
                    **caller_facts,
                },
                component=IMAGE_GENERATION_COMPONENT,
                tool=self._tool,
                attempts=attempts,
                response=response,
            ),
            secrets=self._backend.secrets,
            now=self._now,
        )
        return ImageGenerationResult(
            data=generated.data,
            media_type=generated.media_type,
            provider=self._backend.provider,
            model=self._backend.model,
            attempts=attempts,
            provenance_path=str(provenance_path),
            response_metadata=generated.response_metadata,
        )
