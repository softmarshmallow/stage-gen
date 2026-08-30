from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from gnode import (
    ImageGenerationRequest,
    ImageGenerationService,
    ImageReference,
    RetryExhaustedError,
    RetryPolicy,
)
from gnode.providers.openrouter import OpenRouterImageBackend
from stage_gen.identity import IMAGE_GENERATION_COMPONENT, STAGE_GEN_TOOL

from ..._helpers import png_bytes


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
        backend = OpenRouterImageBackend(api_key="image-secret", client=client)
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
                resolution="2K",
                quality="high",
                background="opaque",
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
    assert sidecar["params"]["resolution"] == "2K"
    assert sidecar["response"]["media_type"] == "image/png"
    assert sidecar["validation"]["decoded_bytes"] == len(image)
    assert "image-secret" not in sidecar_text
    assert request_bodies[-1]["resolution"] == "2K"
    assert request_bodies[-1]["input_references"][0]["type"] == "image_url"


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
        result = await OpenRouterImageBackend(api_key="secret", client=client).generate_once(
            ImageGenerationRequest(prompt="neutral icon", artifact_path="unused")
        )

    assert result.media_type == "image/png"
    assert bodies == [
        {
            "model": "openai/gpt-image-2",
            "prompt": "neutral icon",
            "n": 1,
        }
    ]


@pytest.mark.asyncio
async def test_openrouter_image_serializes_resolution_and_validates_declared_jpeg() -> None:
    image = b"\xff\xd8\xffsynthetic-jpeg"
    bodies: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "b64_json": base64.b64encode(image).decode(),
                        "media_type": "image/jpeg",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OpenRouterImageBackend(
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

    assert result.data == image
    assert result.media_type == "image/jpeg"
    assert bodies == [
        {
            "model": "x-ai/grok-imagine-image-2.0",
            "prompt": "neutral concept",
            "n": 1,
            "aspect_ratio": "16:9",
            "resolution": "1K",
            "quality": "medium",
        }
    ]


@pytest.mark.asyncio
async def test_image_service_owns_exactly_six_attempts(tmp_path: Path) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"data": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = ImageGenerationService(
            OpenRouterImageBackend(api_key="secret", client=client),
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
            OpenRouterImageBackend(api_key="secret", client=client),
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
        backend = OpenRouterImageBackend(api_key="secret", client=client)
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
        result = await OpenRouterImageBackend(api_key="secret", client=client).generate_once(
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
        backend = OpenRouterImageBackend(api_key="secret", client=client)
        with pytest.raises(ValueError, match="omitted media_type"):
            await backend.generate_once(
                ImageGenerationRequest(prompt="neutral icon", artifact_path="unused")
            )
