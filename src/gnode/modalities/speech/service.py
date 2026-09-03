from __future__ import annotations

from datetime import datetime
from typing import Self

from gnode.contracts import ProvenanceInput, SoftwareIdentity
from gnode.modalities._types import BinaryArtifact, run_validator
from gnode.modalities.signatures import assert_audio_signature
from gnode.reliability import (
    RetryContext,
    RetryPolicy,
    retry_with_backoff,
    write_artifact_with_provenance_async,
)

from .models import (
    ProviderSpeech,
    SpeechGenerationRequest,
    SpeechGenerationResult,
    SpeechModelV1,
)


class SpeechGenerationService:
    """The one retry owner for a text-to-speech route.

    Transport, the audio-signature floor, and the caller's validator all run
    inside the single bounded attempt loop, so a silent, clipped, or over-long
    read is a retried attempt and never a persisted artifact.
    """

    def __init__(
        self,
        backend: SpeechModelV1,
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

    async def generate(self, request: SpeechGenerationRequest) -> SpeechGenerationResult:
        attempts = 0

        async def attempt(
            context: RetryContext,
        ) -> tuple[ProviderSpeech, dict[str, object]]:
            nonlocal attempts
            attempts = context.attempt
            generated = await self._backend.generate_once(request)
            assert_audio_signature(generated.data, generated.media_type)
            facts = await run_validator(
                request.validate,
                BinaryArtifact(data=generated.data, media_type=generated.media_type),
            )
            return generated, facts

        generated, caller_facts = await retry_with_backoff(
            attempt,
            policy=self._retry_policy,
            label=f"{self._backend.provider} speech generation",
            secrets=self._backend.secrets,
            timeout_s=request.timeout_seconds,
            cancellation=request.cancellation,
        )
        params: dict[str, object] = {
            "voice": request.voice,
            "output_format": request.output_format,
            "validated": request.validate is not None,
        }
        if request.stability is not None:
            params["stability"] = request.stability
        if request.language_code is not None:
            params["language_code"] = request.language_code
        if request.metadata:
            params["metadata"] = dict(request.metadata)
        response: dict[str, object] = {
            "media_type": generated.media_type,
            "bytes": len(generated.data),
            "source_shape": generated.source_shape,
        }
        if generated.response_metadata.request_id:
            response["request_id"] = generated.response_metadata.request_id
        if generated.response_metadata.usage is not None:
            response["usage"] = generated.response_metadata.usage
        provenance_path = await write_artifact_with_provenance_async(
            request.artifact_path,
            BinaryArtifact(data=generated.data, media_type=generated.media_type),
            ProvenanceInput(
                provider=self._backend.provider,
                model=self._backend.model,
                seed=None,
                prompt=request.text,
                refs=[],
                inputs=[],
                params=params,
                validation={
                    "output_nonempty": True,
                    "media_type": generated.media_type,
                    "signature": "matched",
                    "source_shape": generated.source_shape,
                    "caller": request.validate is not None,
                    **caller_facts,
                },
                component=self._component,
                tool=self._tool,
                attempts=attempts,
                response=response,
                rights=request.rights,
            ),
            secrets=self._backend.secrets,
            now=self._now,
        )
        return SpeechGenerationResult(
            data=generated.data,
            media_type=generated.media_type,
            provider=self._backend.provider,
            model=self._backend.model,
            attempts=attempts,
            provenance_path=str(provenance_path),
            response_metadata=generated.response_metadata,
        )
