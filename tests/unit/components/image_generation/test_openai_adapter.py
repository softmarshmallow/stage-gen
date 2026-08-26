from __future__ import annotations

import base64
import json
from io import BytesIO
from typing import Any

import httpx
import pytest
from PIL import Image

from stage_gen.components.image_generation import ImageGenerationRequest, ImageReference
from stage_gen.providers.openai import OpenAIImageBackend

from .._helpers import png_bytes


def test_openai_backend_declares_native_alpha_capability() -> None:
    assert OpenAIImageBackend.supports_native_alpha is True


@pytest.mark.asyncio
async def test_openai_native_alpha_capability_is_model_specific() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(500))
    ) as client:
        assert OpenAIImageBackend(api_key="secret", client=client).supports_native_alpha is True
        assert (
            OpenAIImageBackend(
                api_key="secret",
                model="gpt-image-2-2026-04-21",
                client=client,
            ).supports_native_alpha
            is True
        )
        assert (
            OpenAIImageBackend(
                api_key="secret",
                model="unverified-image-model",
                client=client,
            ).supports_native_alpha
            is False
        )


def test_openai_rate_limit_must_be_positive() -> None:
    with pytest.raises(ValueError, match="requests_per_minute"):
        OpenAIImageBackend(api_key="secret", requests_per_minute=0)


@pytest.mark.asyncio
async def test_openai_generation_uses_native_alpha_payload_and_retains_metadata() -> None:
    requests: list[httpx.Request] = []
    image = png_bytes(size=(16, 16), color=(24, 48, 96, 128))

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"x-request-id": "openai-image-1"},
            json={
                "created": 731,
                "usage": {"total_tokens": 42},
                "data": [{"b64_json": base64.b64encode(image).decode("ascii")}],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OpenAIImageBackend(api_key="openai-secret", client=client).generate_once(
            ImageGenerationRequest(
                prompt="One isolated hand-painted sprite.",
                artifact_path="unused.png",
                aspect_ratio="3:2",
                resolution="2K",
                size="1536x1024",
                quality="high",
                background="transparent",
                moderation="low",
            )
        )

    assert len(requests) == 1
    request = requests[0]
    assert request.url == "https://api.openai.com/v1/images/generations"
    assert request.headers["authorization"] == "Bearer openai-secret"
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {
        "model": "gpt-image-2",
        "prompt": "One isolated hand-painted sprite.",
        "n": 1,
        "output_format": "png",
        "size": "1536x1024",
        "quality": "high",
        "background": "transparent",
        "moderation": "low",
    }
    assert b"openai-secret" not in request.content
    assert result.data == image
    assert result.media_type == "image/png"
    assert result.response_metadata.request_id == "openai-image-1"
    assert result.response_metadata.created == 731
    assert result.response_metadata.usage == {"total_tokens": 42}
    assert result.applied_params == {
        "operation": "generation",
        "n": 1,
        "output_format": "png",
        "size": "1536x1024",
        "quality": "high",
        "background": "transparent",
        "moderation": "low",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("aspect_ratio", "expected_size"),
    [
        ("1:1", "1024x1024"),
        ("3:2", "1536x1024"),
        ("2:3", "1024x1536"),
        ("4:3", "1536x1152"),
        ("3:4", "1152x1536"),
        ("16:9", "2048x1152"),
        ("9:16", "1152x2048"),
        ("21:9", "2688x1152"),
    ],
)
async def test_openai_maps_verified_aspect_ratio_to_provider_size(
    aspect_ratio: str,
    expected_size: str,
) -> None:
    bodies: list[dict[str, Any]] = []
    image = png_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(image).decode("ascii")}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await OpenAIImageBackend(api_key="secret", client=client).generate_once(
            ImageGenerationRequest(
                prompt="Mapped aspect ratio canary.",
                artifact_path="unused.png",
                aspect_ratio=aspect_ratio,
            )
        )

    assert bodies[0]["size"] == expected_size
    assert "aspect_ratio" not in bodies[0]


@pytest.mark.asyncio
async def test_openai_rejects_unmapped_aspect_ratio_before_transport() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("unmapped aspect ratio must not reach transport")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="no verified size mapping for aspect ratio 5:4"):
            await OpenAIImageBackend(api_key="secret", client=client).generate_once(
                ImageGenerationRequest(
                    prompt="Unmapped aspect ratio canary.",
                    artifact_path="unused.png",
                    aspect_ratio="5:4",
                )
            )

    assert calls == 0


@pytest.mark.asyncio
async def test_openai_edit_uses_multipart_image_files() -> None:
    requests: list[httpx.Request] = []
    image = png_bytes()
    reference_data_url = "data:image/png;base64," + base64.b64encode(image).decode("ascii")

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(image).decode("ascii")}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OpenAIImageBackend(api_key="secret", client=client).generate_once(
            ImageGenerationRequest(
                prompt="Preserve the character identity and change the pose.",
                artifact_path="unused.png",
                input_references=(
                    ImageReference(reference_data_url, "inline-reference-1"),
                    ImageReference(reference_data_url, "inline-reference-2"),
                ),
                size="auto",
                background="transparent",
                moderation="low",
            )
        )

    assert len(requests) == 1
    request = requests[0]
    assert request.url.path == "/v1/images/edits"
    assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
    assert b'name="model"' in request.content
    assert b"gpt-image-2" in request.content
    assert b'name="prompt"' in request.content
    assert b"Preserve the character identity and change the pose." in request.content
    assert b'name="n"' in request.content
    assert b'name="output_format"' in request.content
    assert b'name="size"' in request.content
    assert b'name="background"' in request.content
    assert b'name="moderation"' not in request.content
    assert request.content.count(b'name="image[]"') == 2
    assert b'filename="reference-01.png"' in request.content
    assert b'filename="reference-02.png"' in request.content
    assert request.content.count(b"Content-Type: image/png") == 2
    assert reference_data_url.encode("ascii") not in request.content
    assert result.media_type == "image/png"
    assert result.applied_params == {
        "operation": "edit",
        "n": 1,
        "output_format": "png",
        "size": "auto",
        "background": "transparent",
    }


@pytest.mark.asyncio
async def test_openai_edit_rejects_remote_references_before_transport() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("remote references must not reach transport")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="require base64 image data URL references"):
            await OpenAIImageBackend(api_key="secret", client=client).generate_once(
                ImageGenerationRequest(
                    prompt="Remote reference canary.",
                    artifact_path="unused.png",
                    input_references=(
                        ImageReference("https://example.com/reference.png", "remote-reference"),
                    ),
                )
            )

    assert calls == 0


@pytest.mark.asyncio
async def test_openai_output_format_selects_and_validates_returned_media() -> None:
    image = _encoded_image("JPEG")
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(image).decode("ascii")}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OpenAIImageBackend(api_key="secret", client=client).generate_once(
            ImageGenerationRequest(
                prompt="Opaque landscape study.",
                artifact_path="unused.jpeg",
                output_format="jpeg",
                output_compression=81,
            )
        )

    assert bodies[0]["output_format"] == "jpeg"
    assert bodies[0]["output_compression"] == 81
    assert result.media_type == "image/jpeg"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("size", "message"),
    [
        ("1000x1024", "multiples of 16"),
        ("256x1024", "aspect ratio"),
        ("3856x1024", "must not exceed 3840"),
        ("3840x2176", "between 655360 and 8294400"),
        ("256x768", "between 655360 and 8294400"),
    ],
)
async def test_openai_rejects_unsupported_gpt_image_2_size_before_transport(
    size: str,
    message: str,
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("invalid size must not reach transport")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match=message):
            await OpenAIImageBackend(api_key="secret", client=client).generate_once(
                ImageGenerationRequest(
                    prompt="Invalid size canary.", artifact_path="unused.png", size=size
                )
            )

    assert calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"data": []},
        {"data": [{"b64_json": "one"}, {"b64_json": "two"}]},
        {"data": [{}]},
        {"data": [{"b64_json": "not-base64!"}]},
    ],
)
async def test_openai_requires_exactly_one_strict_base64_image(payload: object) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError):
            await OpenAIImageBackend(api_key="secret", client=client).generate_once(
                ImageGenerationRequest(prompt="Strict response canary.", artifact_path="unused.png")
            )


@pytest.mark.asyncio
async def test_openai_rejects_media_that_disagrees_with_requested_format() -> None:
    jpeg = _encoded_image("JPEG")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(jpeg).decode("ascii")}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="does not match image/png"):
            await OpenAIImageBackend(api_key="secret", client=client).generate_once(
                ImageGenerationRequest(prompt="Wrong media canary.", artifact_path="unused.png")
            )


@pytest.mark.asyncio
async def test_openai_rejects_png_compression_before_transport() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("invalid compression must not reach transport")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="PNG output does not support output_compression"):
            await OpenAIImageBackend(api_key="secret", client=client).generate_once(
                ImageGenerationRequest(
                    prompt="PNG compression canary.",
                    artifact_path="unused.png",
                    output_compression=80,
                )
            )

    assert calls == 0


@pytest.mark.asyncio
async def test_openai_safe_error_does_not_leak_api_key() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "unsupported parameter contains openai-secret",
                    "type": "invalid_request_error",
                    "code": "invalid_value",
                    "param": "size",
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError) as raised:
            await OpenAIImageBackend(api_key="openai-secret", client=client).generate_once(
                ImageGenerationRequest(prompt="Safe error canary.", artifact_path="unused.png")
            )

    assert "unsupported parameter" in str(raised.value)
    assert "openai-secret" not in str(raised.value)


def _encoded_image(format_name: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), (12, 24, 48)).save(output, format=format_name)
    return output.getvalue()
