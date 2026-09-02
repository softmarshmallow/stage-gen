from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Self

from gnode.contracts import ProvenanceInput, SoftwareIdentity
from gnode.modalities._types import BinaryArtifact, run_validator
from gnode.modalities.signatures import assert_image_signature
from gnode.reliability import (
    RetryContext,
    RetryPolicy,
    hash_input_reference,
    retry_with_backoff,
    sanitize_reference,
    write_artifact_with_provenance_async,
)

from .models import (
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageModelV1,
    ProviderImage,
    append_prompt_anchor_once,
)


class ImageGenerationService:
    """Own the complete retry -> validate -> atomic persistence operation."""

    def __init__(
        self,
        backend: ImageModelV1,
        *,
        component: SoftwareIdentity,
        tool: SoftwareIdentity,
        retry_policy: RetryPolicy | None = None,
        now: datetime | None = None,
    ) -> None:
        self._backend = backend
        self._component = component
        self._tool = tool
        self._retry_policy = retry_policy
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
        anchor_binding: dict[str, object] | None = None
        if request.prompt_anchor is not None:
            provider_request = replace(
                request,
                prompt=append_prompt_anchor_once(request.prompt, request.prompt_anchor),
            )
            anchor_binding = dict(request.prompt_anchor.provenance)

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
        provenance_references = (
            request.input_references
            if request.mask_reference is None
            else (*request.input_references, request.mask_reference)
        )
        references = [
            reference.provenance_ref or sanitize_reference(reference.url)
            for reference in provenance_references
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
        if request.prompt_anchor is not None and anchor_binding is not None:
            params[request.prompt_anchor.provenance_key] = anchor_binding
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
                    for reference in provenance_references
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
                component=self._component,
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
