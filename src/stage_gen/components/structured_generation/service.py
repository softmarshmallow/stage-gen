from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
from typing import Self, cast

from stage_gen.contracts import BinaryArtifact, ProvenanceInput, SoftwareIdentity
from stage_gen.reliability import (
    RetryContext,
    RetryPolicy,
    hash_input_reference,
    retry_with_backoff,
    sanitize_reference,
    write_artifact_with_provenance_async,
)

from .models import (
    ProviderStructuredOutput,
    StructuredGenerationBackend,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)

STRUCTURED_GENERATION_COMPONENT = SoftwareIdentity(
    name="@stage-gen/structured-generation", version="0.0.0"
)
DEFAULT_TOOL = SoftwareIdentity(name="stage-gen", version="0.0.0")


class StructuredGenerationService[T]:
    def __init__(
        self,
        backend: StructuredGenerationBackend,
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

    async def generate(
        self, request: StructuredGenerationRequest[T]
    ) -> StructuredGenerationResult[T]:
        attempts = 0

        async def attempt(
            context: RetryContext,
        ) -> tuple[ProviderStructuredOutput, T, bytes, dict[str, object]]:
            nonlocal attempts
            attempts = context.attempt
            provider_request = cast(StructuredGenerationRequest[object], request)
            generated = await self._backend.generate_once(provider_request)
            try:
                value = request.parse(generated.decoded)
                artifact_value = (
                    request.artifact_value(value)
                    if request.artifact_value is not None
                    else generated.decoded
                )
                validation = request.validate(value) if request.validate is not None else None
                if validation is not None and not isinstance(validation, Mapping):
                    raise ValueError("structured validator must return a mapping or None")
            except Exception:
                raise ValueError("structured output failed schema validation") from None
            artifact_data = _serialize_json_artifact(artifact_value)
            return generated, value, artifact_data, dict(validation or {})

        generated, value, artifact_data, caller_validation = await retry_with_backoff(
            attempt,
            policy=self._retry_policy,
            label=f"{self._backend.provider} structured generation",
            secrets=self._backend.secrets,
            timeout_s=request.timeout_seconds,
            cancellation=request.cancellation,
        )
        references = [
            reference.provenance_ref or sanitize_reference(reference.url)
            for reference in request.references
        ]
        params: dict[str, object] = {
            "schema_name": request.schema.name,
            "schema": dict(request.schema.json_schema),
            "strict": request.schema.strict,
            "require_parameters": True,
        }
        if request.system:
            params["system"] = request.system
            params["system_sha256"] = sha256(request.system.encode()).hexdigest()
        if request.temperature is not None:
            params["temperature"] = request.temperature
        if request.max_tokens is not None:
            params["max_tokens"] = request.max_tokens
        if request.seed is not None:
            params["seed"] = request.seed
        if request.metadata:
            params["metadata"] = dict(request.metadata)
        if request.artifact_value is not None:
            params["artifact_value"] = "caller-canonicalized"
        if request.validate is not None:
            params["validated"] = True
        response: dict[str, object] = {"characters": len(generated.raw_text)}
        if generated.response_metadata.request_id:
            response["request_id"] = generated.response_metadata.request_id
        if generated.response_metadata.usage is not None:
            response["usage"] = generated.response_metadata.usage
        provenance_path = await write_artifact_with_provenance_async(
            request.artifact_path,
            BinaryArtifact(data=artifact_data, media_type="application/json"),
            ProvenanceInput(
                schema_version=request.provenance_schema_version,
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
                    "json": "parsed",
                    "schema": "caller-validated",
                    **caller_validation,
                },
                component=STRUCTURED_GENERATION_COMPONENT,
                tool=self._tool,
                attempts=attempts,
                response=response,
            ),
            secrets=self._backend.secrets,
            now=self._now,
        )
        return StructuredGenerationResult(
            value=value,
            raw_text=generated.raw_text,
            provider=self._backend.provider,
            model=self._backend.model,
            attempts=attempts,
            provenance_path=str(provenance_path),
            response_metadata=generated.response_metadata,
        )


def _serialize_json_artifact(value: object) -> bytes:
    try:
        return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
    except (TypeError, ValueError) as exc:
        raise ValueError("structured output was not standards-compliant JSON") from exc
