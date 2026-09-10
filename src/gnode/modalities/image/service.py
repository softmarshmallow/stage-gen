from __future__ import annotations

import math
from collections.abc import Mapping
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

from .inspection import ImageFacts, inspect_image
from .models import (
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageModelV1,
    ProviderImage,
    append_prompt_anchor_once,
    classify_image_reference_delivery,
)

_MATERIAL_OPTION_FIELDS = (
    "quality",
    "background",
    "output_format",
    "output_compression",
    "moderation",
    "aspect_ratio",
    "resolution",
    "size",
)
_MISSING = object()


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

    @property
    def adapter_id(self) -> str:
        return self._backend.adapter_id

    @property
    def adapter_behavior_version(self) -> str:
        return self._backend.adapter_behavior_version

    def endpoint_for(self, request: ImageGenerationRequest) -> str:
        return self._backend.endpoint_for(request)

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        binding = request.resolved_binding
        if binding is not None:
            _validate_resolved_route(request, self._backend)
        if request.background == "transparent" and not self.supports_native_alpha:
            raise ValueError(
                f"{self._backend.provider} image generation does not support "
                "transparent backgrounds"
            )
        attempts = 0
        provider_request = request
        anchor_binding: dict[str, object] | None = None
        if request.prompt_anchor is not None:
            provider_request = replace(
                request,
                prompt=append_prompt_anchor_once(request.prompt, request.prompt_anchor),
            )
            anchor_binding = dict(request.prompt_anchor.provenance)

        async def attempt(
            context: RetryContext,
        ) -> tuple[ProviderImage, dict[str, object], ImageFacts | None]:
            nonlocal attempts
            attempts = context.attempt
            generated = await self._backend.generate_once(provider_request)
            if binding is not None:
                _validate_applied_route(request, generated)
            assert_image_signature(generated.data, generated.media_type)
            image_facts = None
            if binding is not None:
                image_facts = inspect_image(
                    generated.data,
                    expected_media_type=generated.media_type,
                )
                _validate_bound_image_output(request, image_facts)
            facts = await run_validator(
                request.validate,
                BinaryArtifact(data=generated.data, media_type=generated.media_type),
            )
            return generated, facts, image_facts

        generated, caller_facts, image_facts = await retry_with_backoff(
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
        if metadata.revised_prompt is not None:
            response["revised_prompt"] = metadata.revised_prompt
        if metadata.usage is not None or binding is not None:
            response["usage"] = metadata.usage
        if binding is not None:
            response["cost_complete"] = _has_complete_cost(metadata.usage)
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
        if binding is not None:
            params["route_binding"] = {
                "policy_id": binding.policy.policy_id,
                "policy_version": binding.policy.policy_version,
                "product_id": binding.policy.product_id,
                "route_id": binding.route.route_id,
                "route_contract_fingerprint": binding.route_contract_fingerprint,
                "behavior_fingerprint": binding.behavior_fingerprint,
                "output_fingerprint": binding.output_fingerprint,
                "modality_spec_version": binding.route.modality_spec_version,
                "operation_variant": binding.route.operation_variant,
                "surface": binding.route.surface,
                "endpoint": binding.route.endpoint,
                "adapter_id": binding.route.adapter_id,
                "adapter_behavior_version": binding.route.adapter_behavior_version,
            }
        validation: dict[str, object] = {
            "output_nonempty": True,
            "base64": "strict",
            "media_type": generated.media_type,
            "signature": "matched",
            "caller": request.validate is not None,
            **caller_facts,
        }
        if image_facts is not None:
            validation.update(
                {
                    "decoded_width": image_facts.width,
                    "decoded_height": image_facts.height,
                    "has_alpha": image_facts.has_alpha,
                }
            )
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
                validation=validation,
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


def _has_complete_cost(usage: object) -> bool:
    """Whether provider metadata carries one trustworthy total cost value."""

    if not isinstance(usage, Mapping):
        return False
    cost = usage.get("cost")
    return (
        not isinstance(cost, bool)
        and isinstance(cost, (int, float))
        and math.isfinite(cost)
        and cost >= 0
    )


def _validate_bound_image_output(
    request: ImageGenerationRequest,
    facts: ImageFacts,
) -> None:
    output_format = request.output_format
    expected_media_type = (
        {
            "png": "image/png",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
        }.get(output_format)
        if output_format is not None
        else None
    )
    if expected_media_type is not None and facts.media_type != expected_media_type:
        raise ValueError("bound image output format does not match the request")
    size = request.size
    if size is not None and size != "auto":
        width, height = (int(edge) for edge in size.split("x"))
        if (facts.width, facts.height) != (width, height):
            raise ValueError("bound image output dimensions do not match the request")
    aspect_ratio = request.aspect_ratio
    if aspect_ratio is not None and aspect_ratio != "auto":
        ratio_width, ratio_height = (int(edge) for edge in aspect_ratio.split(":"))
        if facts.width * ratio_height != facts.height * ratio_width:
            raise ValueError("bound image output aspect ratio does not match the request")
    if request.background == "transparent" and not facts.has_alpha:
        raise ValueError("bound transparent image output has no alpha channel")


def _validate_resolved_route(
    request: ImageGenerationRequest,
    backend: ImageModelV1,
) -> None:
    binding = request.resolved_binding
    if binding is None:  # pragma: no cover - caller narrows this before invocation
        raise ValueError("image request has no resolved route binding")
    route = binding.route
    if route.operation != "image_generation":
        raise ValueError("resolved route is not an image_generation operation")
    if route.modality_spec_version != "image-generation-v1":
        raise ValueError("resolved route uses an unsupported image modality spec")
    if (route.model.provider, route.model.model) != (backend.provider, backend.model):
        raise ValueError("resolved image route does not match the composed backend")
    if (route.adapter_id, route.adapter_behavior_version) != (
        backend.adapter_id,
        backend.adapter_behavior_version,
    ):
        raise ValueError("resolved image route does not match the composed adapter")
    operation = "edit" if request.input_references else "generation"
    if route.operation_variant != operation:
        raise ValueError("resolved image route operation does not match the request")
    if route.endpoint.rstrip("/") != backend.endpoint_for(request).strip().rstrip("/"):
        raise ValueError("resolved image route does not match the composed endpoint")
    options = binding.request.output_options
    for field_name in _MATERIAL_OPTION_FIELDS:
        if field_name not in options:
            continue
        expected = options[field_name]
        actual = getattr(request, field_name)
        if expected != actual:
            raise ValueError(
                f"resolved image option {field_name} does not match the provider request"
            )


def _validate_applied_route(
    request: ImageGenerationRequest,
    generated: ProviderImage,
) -> None:
    binding = request.resolved_binding
    if binding is None:  # pragma: no cover - caller narrows this before invocation
        raise ValueError("image request has no resolved route binding")
    params = generated.applied_params
    if params is None:
        raise ValueError("bound image provider did not report its applied parameters")
    operation = "edit" if request.input_references else "generation"
    if params.get("operation") != operation:
        raise ValueError("bound image provider reported a different operation")
    endpoint = params.get("endpoint")
    if not isinstance(endpoint, str):
        raise ValueError("bound image provider did not report its applied endpoint")
    expected_endpoint = binding.route.endpoint.rstrip("/")
    reported_endpoint = endpoint.strip().rstrip("/")
    if reported_endpoint != expected_endpoint:
        raise ValueError("bound image provider reported a different endpoint")

    options = binding.request.output_options
    for field_name in _MATERIAL_OPTION_FIELDS:
        if field_name not in options:
            continue
        expected = getattr(request, field_name)
        reported = params.get(field_name, _MISSING)
        # OpenAI and Fal can turn an aspect-ratio intent into the exact ``size``
        # sent to the provider.  Accept that truthful transport report only
        # when the mapped size has the sealed ratio.  Decoded output is checked
        # against the ratio separately, so a paid success cannot be retried
        # merely because the provider has no native ``aspect_ratio`` field.
        if field_name == "aspect_ratio" and reported is _MISSING:
            reported_size = params.get("size")
            if (
                isinstance(expected, str)
                and expected != "auto"
                and isinstance(reported_size, str)
                and _size_has_aspect_ratio(reported_size, expected)
            ):
                continue
        if reported is _MISSING:
            raise ValueError(f"bound image provider did not report applied {field_name}")
        if reported != expected:
            raise ValueError(f"bound image provider reported a different {field_name}")

    expected_references = options.get("reference_count")
    if (
        isinstance(expected_references, int)
        and expected_references > 0
        and params.get("input_reference_count") != expected_references
    ):
        raise ValueError("bound image provider reported a different reference count")
    expected_mask = options.get("mask_present")
    if expected_mask is True and params.get("mask_present") is not True:
        raise ValueError("bound image provider did not report the applied image mask")
    if expected_mask is False and params.get("mask_present") is True:
        raise ValueError("bound image provider reported an unexpected image mask")
    expected_delivery = options.get("reference_delivery")
    if expected_delivery is not None:
        actual_delivery = classify_image_reference_delivery(
            (
                *request.input_references,
                *((request.mask_reference,) if request.mask_reference is not None else ()),
            )
        )
        if actual_delivery != expected_delivery:
            raise ValueError("bound image request reference delivery changed after planning")
        if params.get("reference_delivery") != expected_delivery:
            raise ValueError("bound image provider reported different reference delivery")


def _size_has_aspect_ratio(size: str, aspect_ratio: str) -> bool:
    try:
        width_text, height_text = size.split("x")
        ratio_width_text, ratio_height_text = aspect_ratio.split(":")
        width, height = int(width_text), int(height_text)
        ratio_width, ratio_height = int(ratio_width_text), int(ratio_height_text)
    except (ValueError, TypeError):
        return False
    return (
        width > 0
        and height > 0
        and ratio_width > 0
        and ratio_height > 0
        and width * ratio_height == height * ratio_width
    )
