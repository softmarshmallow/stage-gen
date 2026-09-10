from __future__ import annotations

import base64
import json
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from typing import Any, ClassVar, Literal

import httpx
import pytest
from PIL import Image

from gnode import (
    ImageGenerationRequest,
    ImageGenerationService,
    ImageReference,
    ModelRef,
    ProviderImage,
    ProviderResponseMetadata,
    ResolvedBindingV1,
    RetryExhaustedError,
    RetryPolicy,
    RouteCatalog,
    RouteContractV1,
    WorkloadPolicyV1,
    WorkloadRequestV1,
)
from gnode.providers.openai import OpenAIImageBackend
from gnode.providers.openrouter import OpenRouterImageBackend
from stage_gen.identity import IMAGE_GENERATION_COMPONENT, STAGE_GEN_TOOL

from ..._helpers import png_bytes

_OPENAI_MODEL = "fixture-openai-image-v1"
_OPENROUTER_MODEL = "fixture-openrouter-image-v1"


def _openai_backend(**kwargs: Any) -> OpenAIImageBackend:
    return OpenAIImageBackend(
        model=_OPENAI_MODEL,
        supports_native_alpha=True,
        **kwargs,
    )


def _openrouter_backend(**kwargs: Any) -> OpenRouterImageBackend:
    return OpenRouterImageBackend(model=_OPENROUTER_MODEL, **kwargs)


def _bound_generation() -> tuple[ImageGenerationRequest, RouteContractV1]:
    route = RouteContractV1(
        route_id="fixture.image.generation",
        product_id="fixture-image",
        operation="image_generation",
        operation_variant="generation",
        model=ModelRef("fixture-image-v1", "fixture-provider"),
        modality_spec_version="image-generation-v1",
        surface="fixture-api",
        endpoint="https://fixture.invalid/v1/images/generations",
        adapter_id="fixture-image-adapter",
        adapter_behavior_version="1",
        features=frozenset(
            {
                "authored_prompt_passthrough",
                "exact_size",
                "maximum_quality",
                "opaque_background",
                "png_output",
                "text_to_image",
            }
        ),
        resource_id="fixture-image",
        estimated_duration_seconds=0,
        estimated_cost_low_usd=0,
        estimated_cost_high_usd=0,
        rate_limit_owner="none",
    )
    policy = WorkloadPolicyV1(
        policy_id="fixture.image.opaque",
        policy_version="1",
        product_id=route.product_id,
        route_id=route.route_id,
    )
    workload = WorkloadRequestV1(
        policy_id=policy.policy_id,
        operation=route.operation,
        modality_spec_version=route.modality_spec_version,
        required_features=route.features,
        output_options={
            "operation_variant": "generation",
            "quality_goal": "maximum_verified",
            "quality": "max",
            "background": "opaque",
            "output_format": "png",
            "size": "2x2",
            "reference_count": 0,
            "mask_present": False,
            "moderation_goal": "low_when_supported",
            "prompt_policy": "authored_verbatim",
        },
    )
    binding = RouteCatalog((route,)).resolve(workload, policy)
    return (
        ImageGenerationRequest(
            prompt="Bound route test.",
            artifact_path="unused.png",
            quality="max",
            background="opaque",
            output_format="png",
            size="2x2",
            resolved_binding=binding,
        ),
        route,
    )


class _AppliedParamsBackend:
    spec_version: ClassVar[Literal[1]] = 1
    provider = "fixture-provider"
    model = "fixture-image-v1"
    adapter_id = "fixture-image-adapter"
    adapter_behavior_version = "1"
    secrets: tuple[str, ...] = ()
    supports_native_alpha = False

    def __init__(
        self,
        applied_params: dict[str, object],
        *,
        response_metadata: ProviderResponseMetadata | None = None,
        data: bytes | None = None,
        supports_native_alpha: bool = False,
    ) -> None:
        self.applied_params = applied_params
        self.response_metadata = response_metadata or ProviderResponseMetadata()
        self.data = data or png_bytes()
        self.supports_native_alpha = supports_native_alpha
        self.calls = 0

    def endpoint_for(self, _request: ImageGenerationRequest) -> str:
        return "https://fixture.invalid/v1/images/generations"

    async def generate_once(self, _request: ImageGenerationRequest) -> ProviderImage:
        self.calls += 1
        return ProviderImage(
            data=self.data,
            media_type="image/png",
            response_metadata=self.response_metadata,
            applied_params=self.applied_params,
        )

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("applied_params", "message"),
    (
        (
            {
                "operation": "generation",
                "endpoint": "https://fixture.invalid/v1/images/generations",
                "quality": "low",
                "background": "opaque",
                "output_format": "png",
                "size": "2x2",
            },
            "different quality",
        ),
        (
            {
                "operation": "generation",
                "quality": "max",
                "background": "opaque",
                "output_format": "png",
                "size": "2x2",
            },
            "applied endpoint",
        ),
    ),
)
async def test_bound_applied_parameter_drift_refuses_before_persistence(
    tmp_path: Path,
    applied_params: dict[str, object],
    message: str,
) -> None:
    request, _route = _bound_generation()
    output = tmp_path / "drifted.png"
    backend = _AppliedParamsBackend(applied_params)
    service = ImageGenerationService(
        backend,
        component=IMAGE_GENERATION_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )

    with pytest.raises(RetryExhaustedError, match=message) as failure:
        await service.generate(replace(request, artifact_path=output))

    assert failure.value.attempts == backend.calls == 6
    assert len(failure.value.failure_history) == 6
    assert not output.exists()
    assert not output.with_name(f"{output.name}.meta.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("change", "value", "message"),
    (
        ("endpoint", "https://other.invalid/v1/images", "composed endpoint"),
        ("adapter_id", "other-image-adapter", "composed adapter"),
        ("adapter_behavior_version", "2", "composed adapter"),
    ),
)
async def test_bound_backend_identity_drift_refuses_before_provider_call(
    tmp_path: Path,
    change: str,
    value: str,
    message: str,
) -> None:
    request, route = _bound_generation()
    assert request.resolved_binding is not None
    if change == "endpoint":
        changed_route = replace(route, endpoint=value)
    elif change == "adapter_id":
        changed_route = replace(route, adapter_id=value)
    else:
        assert change == "adapter_behavior_version"
        changed_route = replace(route, adapter_behavior_version=value)
    binding = ResolvedBindingV1(
        route=changed_route,
        request=request.resolved_binding.request,
        policy=request.resolved_binding.policy,
    )
    backend = _AppliedParamsBackend(
        {
            "operation": "generation",
            "endpoint": route.endpoint,
            "quality": "max",
            "background": "opaque",
            "output_format": "png",
            "size": "2x2",
        }
    )
    service = ImageGenerationService(
        backend,
        component=IMAGE_GENERATION_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )

    with pytest.raises(ValueError, match=message):
        await service.generate(
            replace(
                request,
                artifact_path=tmp_path / "identity-drift.png",
                resolved_binding=binding,
            )
        )

    assert backend.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("usage", "expected_cost_complete"),
    (
        (None, False),
        ({"images": 1}, False),
        ({"cost": True}, False),
        ({"cost": -1}, False),
        ({"cost": "0.10"}, False),
        ({"cost": 0}, True),
        ({"cost": 0.125}, True),
    ),
)
async def test_bound_provenance_marks_only_returned_total_cost_complete(
    tmp_path: Path,
    usage: dict[str, object] | None,
    expected_cost_complete: bool,
) -> None:
    request, route = _bound_generation()
    output = tmp_path / "cost-coverage.png"
    backend = _AppliedParamsBackend(
        {
            "operation": "generation",
            "endpoint": route.endpoint,
            "quality": "max",
            "background": "opaque",
            "output_format": "png",
            "size": "2x2",
        },
        response_metadata=ProviderResponseMetadata(usage=usage),
    )
    service = ImageGenerationService(
        backend,
        component=IMAGE_GENERATION_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )

    await service.generate(replace(request, artifact_path=output))

    sidecar = json.loads(output.with_name(f"{output.name}.meta.json").read_text())
    assert sidecar["response"]["cost_complete"] is expected_cost_complete
    assert "usage_complete" not in sidecar["response"]
    if usage is None:
        assert sidecar["response"]["usage"] is None
    else:
        assert sidecar["response"]["usage"] == usage


@pytest.mark.asyncio
async def test_bound_output_dimensions_are_validated_inside_retry_owner(tmp_path: Path) -> None:
    request, route = _bound_generation()
    backend = _AppliedParamsBackend(
        {
            "operation": "generation",
            "endpoint": route.endpoint,
            "quality": "max",
            "background": "opaque",
            "output_format": "png",
            "size": "2x2",
        },
        data=png_bytes(size=(3, 2)),
    )
    service = ImageGenerationService(
        backend,
        component=IMAGE_GENERATION_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )

    with pytest.raises(RetryExhaustedError, match="output dimensions") as failure:
        await service.generate(replace(request, artifact_path=tmp_path / "wrong-size.png"))

    assert failure.value.attempts == backend.calls == 6


@pytest.mark.asyncio
async def test_bound_mapped_aspect_ratio_does_not_retry_a_paid_success(tmp_path: Path) -> None:
    request, route = _bound_generation()
    assert request.resolved_binding is not None
    options = dict(request.resolved_binding.request.output_options)
    del options["size"]
    options["aspect_ratio"] = "16:9"
    binding = ResolvedBindingV1(
        route=route,
        request=replace(request.resolved_binding.request, output_options=options),
        policy=request.resolved_binding.policy,
    )
    backend = _AppliedParamsBackend(
        {
            "operation": "generation",
            "endpoint": route.endpoint,
            "quality": "max",
            "background": "opaque",
            "output_format": "png",
            "size": "2048x1152",
        },
        data=png_bytes(size=(16, 9)),
    )
    service = ImageGenerationService(
        backend,
        component=IMAGE_GENERATION_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    output = tmp_path / "mapped-aspect.png"

    await service.generate(
        replace(
            request,
            artifact_path=output,
            size=None,
            aspect_ratio="16:9",
            resolved_binding=binding,
        )
    )

    assert backend.calls == 1
    assert output.exists()


@pytest.mark.asyncio
async def test_bound_transparency_requires_decoded_alpha_inside_retry_owner(tmp_path: Path) -> None:
    request, route = _bound_generation()
    assert request.resolved_binding is not None
    options = {**request.resolved_binding.request.output_options, "background": "transparent"}
    transparent_route = replace(
        route,
        features=route.features | {"transparent_background"},
    )
    transparent_workload = replace(
        request.resolved_binding.request,
        required_features=request.resolved_binding.request.required_features
        | {"transparent_background"},
        output_options=options,
    )
    binding = ResolvedBindingV1(
        route=transparent_route,
        request=transparent_workload,
        policy=request.resolved_binding.policy,
    )
    output = BytesIO()
    Image.new("RGB", (2, 2), (10, 20, 30)).save(output, format="PNG")
    backend = _AppliedParamsBackend(
        {
            "operation": "generation",
            "endpoint": route.endpoint,
            "quality": "max",
            "background": "transparent",
            "output_format": "png",
            "size": "2x2",
        },
        data=output.getvalue(),
        supports_native_alpha=True,
    )
    service = ImageGenerationService(
        backend,
        component=IMAGE_GENERATION_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )

    with pytest.raises(RetryExhaustedError, match="no alpha channel") as failure:
        await service.generate(
            replace(
                request,
                artifact_path=tmp_path / "opaque-rgb.png",
                background="transparent",
                resolved_binding=binding,
            )
        )

    assert failure.value.attempts == backend.calls == 6


@pytest.mark.asyncio
async def test_image_retries_invalid_success_and_persists_provenance(tmp_path: Path) -> None:
    calls = 0
    request_bodies: list[Any] = []
    image = png_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        request_bodies.append(json.loads(request.content))
        payload = (
            {"data": [{"b64_json": "broken", "media_type": "image/png"}]}
            if calls == 1
            else {
                "data": [
                    {
                        "b64_json": base64.b64encode(image).decode(),
                    }
                ],
                "created": 731,
                "usage": {"images": 1},
            }
        )
        return httpx.Response(200, json=payload, headers={"x-request-id": "img-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = _openrouter_backend(api_key="image-secret", client=client)
        service = ImageGenerationService(
            backend,
            component=IMAGE_GENERATION_COMPONENT,
            tool=STAGE_GEN_TOOL,
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        )
        output = tmp_path / "asset.png"
        result = await service.generate(
            ImageGenerationRequest(
                prompt="original neutral icon",
                artifact_path=output,
                aspect_ratio="1:1",
                quality="max",
                background="opaque",
                output_format="png",
                input_references=(
                    ImageReference(
                        "data:image/png;base64," + base64.b64encode(image).decode(),
                        "reference.png",
                    ),
                ),
                validate=lambda artifact: {"decoded_bytes": len(artifact.data)},
            )
        )
    assert calls == result.attempts == 2
    assert result.media_type == "image/png"
    assert output.read_bytes() == image
    sidecar_text = (tmp_path / "asset.png.meta.json").read_text()
    sidecar = json.loads(sidecar_text)
    assert sidecar["attempts"] == 2
    assert sidecar["params"]["quality"] == "max"
    assert sidecar["params"]["operation"] == "edit"
    assert sidecar["params"]["output_format"] == "png"
    assert sidecar["params"]["endpoint"] == "https://openrouter.ai/api/v1/images"
    assert sidecar["response"]["media_type"] == "image/png"
    assert sidecar["validation"]["decoded_bytes"] == len(image)
    assert "image-secret" not in sidecar_text
    assert request_bodies[-1]["input_references"][0]["type"] == "image_url"


@pytest.mark.asyncio
async def test_image_provenance_binds_the_edit_mask_as_a_direct_input(tmp_path: Path) -> None:
    image = png_bytes()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(image).decode()}]},
        )

    encoded = "data:image/png;base64," + base64.b64encode(image).decode()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = ImageGenerationService(
            _openai_backend(api_key="secret", client=client),
            component=IMAGE_GENERATION_COMPONENT,
            tool=STAGE_GEN_TOOL,
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        )
        output = tmp_path / "masked.png"
        await service.generate(
            ImageGenerationRequest(
                prompt="fill only the declared mask",
                artifact_path=output,
                input_references=(ImageReference(encoded, "conditioning.png"),),
                mask_reference=ImageReference(encoded, "mask.png"),
            )
        )

    sidecar = json.loads((tmp_path / "masked.png.meta.json").read_text())
    assert sidecar["refs"] == ["conditioning.png", "mask.png"]
    assert [entry["ref"] for entry in sidecar["inputs"]] == [
        "conditioning.png",
        "mask.png",
    ]


@pytest.mark.parametrize("resolution", ["512", "1K", "2K", "4K"])
def test_image_request_accepts_normalized_resolution(resolution: Any) -> None:
    request = ImageGenerationRequest(
        prompt="neutral icon",
        artifact_path="unused",
        resolution=resolution,
    )

    assert request.resolution == resolution


@pytest.mark.parametrize("resolution", ["", "1k", "2k", "8K", "1024", 512, True])
def test_image_request_rejects_noncanonical_resolution(resolution: Any) -> None:
    with pytest.raises(ValueError, match="resolution must be 512, 1K, 2K, or 4K"):
        ImageGenerationRequest(
            prompt="neutral icon",
            artifact_path="unused",
            resolution=resolution,
        )


@pytest.mark.parametrize("quality", ["auto", "low", "medium", "high", "xhigh", "max"])
def test_image_request_accepts_supported_quality(quality: Any) -> None:
    request = ImageGenerationRequest(
        prompt="neutral icon",
        artifact_path="unused",
        quality=quality,
    )

    assert request.quality == quality


@pytest.mark.parametrize("quality", ["", "highest", "ultra", 1, True])
def test_image_request_rejects_unsupported_quality(quality: Any) -> None:
    with pytest.raises(ValueError, match="quality must be auto, low, medium, high, xhigh, or max"):
        ImageGenerationRequest(
            prompt="neutral icon",
            artifact_path="unused",
            quality=quality,
        )


@pytest.mark.asyncio
async def test_openrouter_image_omits_unset_optional_fields() -> None:
    image = png_bytes()
    bodies: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "b64_json": base64.b64encode(image).decode(),
                        "media_type": "image/png",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _openrouter_backend(api_key="secret", client=client).generate_once(
            ImageGenerationRequest(prompt="neutral icon", artifact_path="unused")
        )

    assert result.media_type == "image/png"
    assert bodies == [
        {
            "model": _OPENROUTER_MODEL,
            "prompt": "neutral icon",
            "n": 1,
            "provider": {"allow_fallbacks": False},
        }
    ]
    assert result.applied_params == {
        "operation": "generation",
        "endpoint": "https://openrouter.ai/api/v1/images",
        "n": 1,
        "allow_fallbacks": False,
    }


@pytest.mark.asyncio
async def test_openrouter_image_refuses_unverified_resolution_before_transport() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("unverified resolution must not reach transport")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="no verified resolution"):
            await OpenRouterImageBackend(
                api_key="secret",
                model="x-ai/grok-imagine-image-2.0",
                client=client,
            ).generate_once(
                ImageGenerationRequest(
                    prompt="neutral concept",
                    artifact_path="unused",
                    aspect_ratio="16:9",
                    resolution="1K",
                    quality="medium",
                )
            )

    assert calls == 0


@pytest.mark.asyncio
async def test_image_service_owns_exactly_six_attempts(tmp_path: Path) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"data": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = ImageGenerationService(
            _openrouter_backend(api_key="secret", client=client),
            component=IMAGE_GENERATION_COMPONENT,
            tool=STAGE_GEN_TOOL,
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        )
        with pytest.raises(RetryExhaustedError):
            await service.generate(
                ImageGenerationRequest(prompt="neutral icon", artifact_path=tmp_path / "x.png")
            )
    assert calls == 6
    assert not (tmp_path / "x.png").exists()


@pytest.mark.asyncio
async def test_image_service_refuses_unavailable_native_alpha_before_retry(
    tmp_path: Path,
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("unsupported transparency must not reach transport")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = ImageGenerationService(
            _openrouter_backend(api_key="secret", client=client),
            component=IMAGE_GENERATION_COMPONENT,
            tool=STAGE_GEN_TOOL,
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        )
        with pytest.raises(ValueError, match="does not support transparent backgrounds"):
            await service.generate(
                ImageGenerationRequest(
                    prompt="transparent icon",
                    artifact_path=tmp_path / "transparent.png",
                    background="transparent",
                    output_format="png",
                )
            )

    assert calls == 0
    assert not (tmp_path / "transparent.png").exists()


@pytest.mark.asyncio
async def test_image_caller_validation_retries_inside_provider_boundary(tmp_path: Path) -> None:
    calls = 0
    image = png_bytes()

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "b64_json": base64.b64encode(image).decode(),
                        "media_type": "image/png",
                    }
                ]
            },
        )

    def validate(_artifact: Any) -> None:
        if calls < 3:
            raise ValueError("dimension mismatch")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await ImageGenerationService(
            _openrouter_backend(api_key="secret", client=client),
            component=IMAGE_GENERATION_COMPONENT,
            tool=STAGE_GEN_TOOL,
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ).generate(
            ImageGenerationRequest(
                prompt="validate dimensions elsewhere",
                artifact_path=tmp_path / "validated.png",
                validate=validate,
            )
        )
    assert calls == result.attempts == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("media_type", "data"),
    [
        ("image/gif", b"GIF89aforbidden"),
        ("image/png; charset=binary", b"\x89PNG\r\n\x1a\nparameterized"),
        ("image/bmp", b"BMunsupported"),
        ("image/jpg", b"\xff\xd8\xffalias"),
        (None, b"\x89PNG\r\n\x1a\nexplicit-null"),
    ],
)
async def test_openrouter_image_rejects_unsupported_or_parameterized_media(
    media_type: object,
    data: bytes,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "b64_json": base64.b64encode(data).decode(),
                        "media_type": media_type,
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = _openrouter_backend(api_key="secret", client=client)
        with pytest.raises(ValueError, match="PNG, JPEG, or WebP"):
            await backend.generate_once(
                ImageGenerationRequest(prompt="neutral icon", artifact_path="unused.png")
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("data", "expected_media_type"),
    [
        (b"\x89PNG\r\n\x1a\nsynthetic", "image/png"),
        (b"\xff\xd8\xffsynthetic", "image/jpeg"),
        (b"RIFF\x04\x00\x00\x00WEBPsynthetic", "image/webp"),
    ],
)
async def test_openrouter_image_infers_supported_media_type_when_omitted(
    data: bytes,
    expected_media_type: str,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(data).decode()}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _openrouter_backend(api_key="secret", client=client).generate_once(
            ImageGenerationRequest(prompt="neutral icon", artifact_path="unused")
        )

    assert result.media_type == expected_media_type
    assert result.data == data


@pytest.mark.asyncio
async def test_openrouter_image_rejects_unknown_bytes_when_media_type_is_omitted() -> None:
    data = b"GIF89asynthetic"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(data).decode()}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = _openrouter_backend(api_key="secret", client=client)
        with pytest.raises(ValueError, match="omitted media_type"):
            await backend.generate_once(
                ImageGenerationRequest(prompt="neutral icon", artifact_path="unused")
            )
