from __future__ import annotations

from datetime import datetime
from typing import Self

from stage_gen.components._types import BinaryArtifact
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
    BackgroundRemovalBackend,
    BackgroundRemovalRequest,
    BackgroundRemovalResult,
    ProviderBackgroundRemoval,
    run_background_validator,
)

BACKGROUND_REMOVAL_COMPONENT = SoftwareIdentity(
    name="@stage-gen/background-removal", version="0.0.0"
)
DEFAULT_TOOL = SoftwareIdentity(name="stage-gen", version="0.0.0")


class BackgroundRemovalService:
    def __init__(
        self,
        backend: BackgroundRemovalBackend,
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

    async def remove(self, request: BackgroundRemovalRequest) -> BackgroundRemovalResult:
        attempts = 0

        async def attempt(
            context: RetryContext,
        ) -> tuple[ProviderBackgroundRemoval, dict[str, object]]:
            nonlocal attempts
            attempts = context.attempt
            removed = await self._backend.remove_once(request)
            assert_image_signature(removed.data, removed.media_type)
            facts = await run_background_validator(
                request.validate,
                BinaryArtifact(data=removed.data, media_type=removed.media_type),
                removed.mask,
            )
            return removed, facts

        removed, caller_facts = await retry_with_backoff(
            attempt,
            policy=self._retry_policy,
            label=f"{self._backend.provider} background removal",
            secrets=self._backend.secrets,
            timeout_s=request.timeout_seconds,
            cancellation=request.cancellation,
        )
        stable_ref = sanitize_reference(request.image_url)
        params: dict[str, object] = {
            "model_variant": request.model_variant,
            "operating_resolution": request.operating_resolution,
            "output_mask": request.output_mask,
            "refine_foreground": request.refine_foreground,
            "output_format": request.output_format,
            "mask_only": request.mask_only,
            "sync_mode": request.sync_mode,
            "validated": request.validate is not None,
        }
        if request.metadata:
            params["metadata"] = dict(request.metadata)
        response: dict[str, object] = {
            "media_type": removed.media_type,
            "bytes": len(removed.data),
            "mask_present": removed.mask is not None,
        }
        if removed.mask is not None:
            response["mask_media_type"] = removed.mask.media_type
            response["mask_bytes"] = len(removed.mask.data)
        if removed.width is not None:
            response["width"] = removed.width
        if removed.height is not None:
            response["height"] = removed.height
        if removed.response_metadata.request_id:
            response["request_id"] = removed.response_metadata.request_id
        provenance_path = await write_artifact_with_provenance_async(
            request.artifact_path,
            BinaryArtifact(data=removed.data, media_type=removed.media_type),
            ProvenanceInput(
                schema_version=request.provenance_schema_version,
                provider=self._backend.provider,
                model=self._backend.model,
                seed=None,
                prompt="Remove the background while preserving the foreground subject.",
                refs=[stable_ref],
                inputs=[hash_input_reference(request.image_url, stable_ref)],
                params=params,
                validation={
                    "output_nonempty": True,
                    "base64_or_download": "validated",
                    "media_type": removed.media_type,
                    "signature": "matched",
                    "source": removed.source_kind,
                    "mask_requested": request.output_mask,
                    "mask_received": removed.mask is not None,
                    "caller": request.validate is not None,
                    **caller_facts,
                },
                component=BACKGROUND_REMOVAL_COMPONENT,
                tool=self._tool,
                attempts=attempts,
                response=response,
            ),
            secrets=self._backend.secrets,
            now=self._now,
        )
        return BackgroundRemovalResult(
            data=removed.data,
            media_type=removed.media_type,
            source_url=removed.source_url,
            width=removed.width,
            height=removed.height,
            mask_image=removed.mask_image,
            mask=removed.mask,
            provider=self._backend.provider,
            model=self._backend.model,
            attempts=attempts,
            provenance_path=str(provenance_path),
            response_metadata=removed.response_metadata,
        )
