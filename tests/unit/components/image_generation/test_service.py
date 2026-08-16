from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from stage_gen.components.image_generation import (
    ImageGenerationRequest,
    ImageGenerationService,
    ImageReference,
)
from stage_gen.providers.openrouter import OpenRouterImageBackend
from stage_gen.reliability import RetryExhaustedError, RetryPolicy

from .._helpers import png_bytes


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
                        "media_type": "image/png",
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
            backend, retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0)
        )
        output = tmp_path / "asset.png"
        result = await service.generate(
            ImageGenerationRequest(
                prompt="original neutral icon",
                artifact_path=output,
                aspect_ratio="1:1",
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
    assert output.read_bytes() == image
    sidecar_text = (tmp_path / "asset.png.meta.json").read_text()
    sidecar = json.loads(sidecar_text)
    assert sidecar["attempts"] == 2
    assert sidecar["validation"]["decoded_bytes"] == len(image)
    assert "image-secret" not in sidecar_text
    assert request_bodies[-1]["input_references"][0]["type"] == "image_url"


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
    ],
)
async def test_openrouter_image_rejects_unsupported_or_parameterized_media(
    media_type: str,
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
