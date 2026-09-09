from __future__ import annotations

import base64
import json
from io import BytesIO

import httpx
import pytest
from PIL import Image

from gnode import ImageGenerationRequest, ImageReference
from gnode.providers.openrouter import (
    OpenRouterImageBackend,
    supports_openrouter_sunburst_model,
)


def _png(width: int, height: int) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_openrouter_backend_declares_no_native_alpha() -> None:
    assert OpenRouterImageBackend.supports_native_alpha is False


def test_openrouter_sunburst_model_support_is_exact() -> None:
    assert supports_openrouter_sunburst_model("openai/gpt-image-2.5-sunburst") is True
    assert supports_openrouter_sunburst_model("openai/gpt-image-2.5-flare") is False
    assert supports_openrouter_sunburst_model("openai/gpt-image-2") is False


def test_openrouter_rate_limit_must_be_positive() -> None:
    with pytest.raises(ValueError, match="images_per_minute"):
        OpenRouterImageBackend(api_key="secret", images_per_minute=0)


@pytest.mark.asyncio
async def test_openrouter_generation_passes_native_size_through() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "b64_json": base64.b64encode(_png(2560, 1440)).decode("ascii"),
                        "media_type": "image/png",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = OpenRouterImageBackend(api_key="secret", client=client)
        image = await backend.generate_once(
            ImageGenerationRequest(
                prompt="a peg",
                artifact_path="unused.png",
                size="2560x1440",
                quality="max",
                background="opaque",
                output_format="png",
                moderation="low",
            )
        )
    assert image.media_type == "image/png"
    body = json.loads(requests[0].content)
    assert body["model"] == "openai/gpt-image-2.5-sunburst"
    assert body["size"] == "2560x1440"
    assert "aspect_ratio" not in body
    assert body["quality"] == "max"
    assert body["background"] == "opaque"
    assert "output_format" not in body
    assert body["provider"] == {"options": {"openai": {"moderation": "low"}}}
    assert image.applied_params == {
        "operation": "generation",
        "n": 1,
        "size": "2560x1440",
        "quality": "max",
        "background": "opaque",
        "moderation": "low",
    }


@pytest.mark.asyncio
async def test_openrouter_rejects_transparent_background_before_transport() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("transparent background must not reach transport")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = OpenRouterImageBackend(api_key="secret", client=client)
        with pytest.raises(ValueError, match="does not support transparent backgrounds"):
            await backend.generate_once(
                ImageGenerationRequest(
                    prompt="transparent peg",
                    artifact_path="unused.png",
                    background="transparent",
                    output_format="png",
                )
            )

    assert calls == 0


@pytest.mark.asyncio
async def test_openrouter_retains_masked_edit_refusal_before_transport() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("mask must not reach transport")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = OpenRouterImageBackend(api_key="secret", client=client)
        with pytest.raises(ValueError, match="no masked-edit route"):
            await backend.generate_once(
                ImageGenerationRequest(
                    prompt="masked peg",
                    artifact_path="unused.png",
                    mask_reference=ImageReference("data:image/png;base64,AA=="),
                )
            )

    assert calls == 0
