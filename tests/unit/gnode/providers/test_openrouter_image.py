from __future__ import annotations

import base64
import json
from io import BytesIO

import httpx
import pytest
from PIL import Image

from gnode import ImageGenerationRequest
from gnode.providers.openrouter import OpenRouterImageBackend


def _png(width: int, height: int) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_openrouter_backend_declares_no_native_alpha() -> None:
    assert OpenRouterImageBackend.supports_native_alpha is False


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
                quality="high",
                background="opaque",
                moderation="low",
            )
        )
    assert image.media_type == "image/png"
    body = json.loads(requests[0].content)
    assert body["size"] == "2560x1440"
    assert "aspect_ratio" not in body
    assert body["background"] == "opaque"
    assert body["provider"] == {"options": {"openai": {"moderation": "low"}}}
