from __future__ import annotations

import base64
import json

import httpx
import pytest

from stage_gen.components.image_repeat import MaskedImageEditRequest
from stage_gen.media import inspect_image
from stage_gen.providers.openrouter import OpenRouterMaskedImageEditBackend

from .._helpers import png_bytes


@pytest.mark.asyncio
async def test_openrouter_masked_edit_is_one_call_and_normalizes_exact_geometry() -> None:
    request_bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"x-request-id": "repeat-edit-1"},
            json={
                "data": [
                    {
                        "b64_json": base64.b64encode(
                            png_bytes(size=(5, 3), color=(32, 80, 120, 192))
                        ).decode(),
                        "media_type": "image/png",
                    }
                ]
            },
        )

    conditioning = png_bytes(size=(8, 4), color=(12, 24, 36, 128))
    mask = png_bytes(size=(8, 4), color=(255, 255, 255, 255))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = OpenRouterMaskedImageEditBackend(
            api_key="repeat-secret",
            model="openai/gpt-image-2",
            client=client,
        )
        result = await backend.edit_once(
            MaskedImageEditRequest(
                prompt="Continue the game foliage naturally.",
                conditioning_image=conditioning,
                mask_image=mask,
                width=8,
                height=4,
                axis="x",
                context_span_px=2,
                repair_span_px=4,
                metadata={"proof": "unit"},
            )
        )

    assert len(request_bodies) == 1
    body = request_bodies[0]
    assert body["model"] == "openai/gpt-image-2"
    assert body["aspect_ratio"] == "auto"
    assert body["quality"] == "high"
    assert body["background"] == "auto"
    references = body["input_references"]
    assert isinstance(references, list) and len(references) == 2
    assert all(
        isinstance(reference, dict)
        and reference.get("type") == "image_url"
        and str(reference.get("image_url", {}).get("url", "")).startswith("data:image/png;base64,")
        for reference in references
    )
    assert "white is the only span to paint" in str(body["prompt"])
    assert "repeat-secret" not in json.dumps(body)
    assert result.media_type == "image/png"
    assert result.response_metadata.request_id == "repeat-edit-1"
    facts = inspect_image(result.data, expected_media_type="image/png")
    assert (facts.width, facts.height) == (8, 4)
