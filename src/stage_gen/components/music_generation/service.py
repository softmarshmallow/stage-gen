from __future__ import annotations

from datetime import datetime
from typing import Self

from stage_gen.components._types import BinaryArtifact, run_validator
from stage_gen.contracts import ProvenanceInput, SoftwareIdentity
from stage_gen.media import assert_audio_signature
from stage_gen.reliability import (
    RetryContext,
    RetryPolicy,
    hash_input_reference,
    retry_with_backoff,
    sanitize_reference,
    write_artifact_with_provenance_async,
)

from .models import (
    MusicGenerationBackend,
    MusicGenerationRequest,
    MusicGenerationResult,
    ProviderMusic,
)

MUSIC_GENERATION_COMPONENT = SoftwareIdentity(name="@stage-gen/music-generation", version="0.0.0")
DEFAULT_TOOL = SoftwareIdentity(name="stage-gen", version="0.0.0")


class MusicGenerationService:
    def __init__(
        self,
        backend: MusicGenerationBackend,
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

    async def generate(self, request: MusicGenerationRequest) -> MusicGenerationResult:
        attempts = 0

        async def attempt(context: RetryContext) -> tuple[ProviderMusic, dict[str, object]]:
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
            label=f"{self._backend.provider} music generation",
            secrets=self._backend.secrets,
            timeout_s=request.timeout_seconds,
            cancellation=request.cancellation,
        )
        references = [
            reference.provenance_ref or sanitize_reference(reference.url)
            for reference in request.references
        ]
        params: dict[str, object] = {
            "output_format": request.output_format,
            "modalities": ["text", "audio"],
            "stream": True,
            "validated": request.validate is not None,
        }
        if request.temperature is not None:
            params["temperature"] = request.temperature
        if request.top_p is not None:
            params["top_p"] = request.top_p
        if request.seed is not None:
            params["seed"] = request.seed
        if request.max_tokens is not None:
            params["max_tokens"] = request.max_tokens
        if request.metadata:
            params["metadata"] = dict(request.metadata)
        response: dict[str, object] = {
            "media_type": generated.media_type,
            "bytes": len(generated.data),
            "source_shape": generated.source_shape,
        }
        if generated.text:
            response["text_characters"] = len(generated.text)
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
                seed=request.seed,
                prompt=request.prompt,
                refs=references,
                inputs=[
                    hash_input_reference(reference.url, reference.provenance_ref)
                    for reference in request.references
                ],
                params=params,
                validation={
                    "output_nonempty": True,
                    "base64": "strict",
                    "media_type": generated.media_type,
                    "signature": "matched",
                    "source_shape": generated.source_shape,
                    "caller": request.validate is not None,
                    **caller_facts,
                },
                component=MUSIC_GENERATION_COMPONENT,
                tool=self._tool,
                attempts=attempts,
                response=response,
                rights=request.rights,
            ),
            secrets=self._backend.secrets,
            now=self._now,
        )
        return MusicGenerationResult(
            data=generated.data,
            media_type=generated.media_type,
            text=generated.text,
            provider=self._backend.provider,
            model=self._backend.model,
            attempts=attempts,
            provenance_path=str(provenance_path),
            response_metadata=generated.response_metadata,
        )
