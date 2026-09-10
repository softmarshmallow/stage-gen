from __future__ import annotations

import base64
import json
import sys
from collections.abc import AsyncIterator
from io import BytesIO
from typing import Any

import httpx
import pytest
from PIL import Image

from gnode import ImageGenerationRequest, ImageReference
from gnode.providers.fal import FalImageBackend

from .._helpers import png_bytes

_MODEL = "fixture-image-v1"
FAL_IMAGE_TEXT_TO_IMAGE_ENDPOINT = "fixture/image/text-to-image"
FAL_IMAGE_EDIT_ENDPOINT = "fixture/image/edit"


def _backend(
    *,
    api_key: str = "secret",
    model: str = _MODEL,
    text_to_image_endpoint: str = FAL_IMAGE_TEXT_TO_IMAGE_ENDPOINT,
    edit_endpoint: str = FAL_IMAGE_EDIT_ENDPOINT,
    supports_native_alpha: bool = True,
    **kwargs: Any,
) -> FalImageBackend:
    return FalImageBackend(
        api_key=api_key,
        model=model,
        text_to_image_endpoint=text_to_image_endpoint,
        edit_endpoint=edit_endpoint,
        supports_native_alpha=supports_native_alpha,
        **kwargs,
    )


def _data_uri(data: bytes, media_type: str = "image/png") -> str:
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"


def _encoded_image(
    format_name: str,
    *,
    size: tuple[int, int] = (16, 16),
    alpha: bool = False,
) -> bytes:
    output = BytesIO()
    mode = "RGBA" if alpha else "RGB"
    color = (12, 24, 48, 128) if alpha else (12, 24, 48)
    Image.new(mode, size, color).save(output, format=format_name)
    return output.getvalue()


def test_fal_image_backend_uses_explicit_route_facts() -> None:
    backend = _backend(api_key="fal-secret")

    assert backend.provider == "fal"
    assert backend.model == _MODEL
    assert backend.text_to_image_endpoint == FAL_IMAGE_TEXT_TO_IMAGE_ENDPOINT
    assert backend.edit_endpoint == FAL_IMAGE_EDIT_ENDPOINT
    assert backend.supports_native_alpha is True
    assert backend.secrets == ("fal-secret",)


def test_fal_image_backend_requires_route_facts() -> None:
    with pytest.raises(TypeError):
        FalImageBackend(api_key="secret")  # type: ignore[call-arg]


def test_fal_image_backend_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="api_key must be non-empty"):
        _backend(api_key="  ")
    with pytest.raises(ValueError, match="model must be non-empty"):
        _backend(model="  ")
    with pytest.raises(ValueError, match="model must be non-empty"):
        _backend(model="/")
    with pytest.raises(ValueError, match="supports_native_alpha must be a boolean"):
        _backend(supports_native_alpha=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="text-to-image endpoint must be non-empty"):
        _backend(text_to_image_endpoint="  ")
    with pytest.raises(ValueError, match="edit endpoint must be non-empty"):
        _backend(edit_endpoint="  ")
    with pytest.raises(ValueError, match="must be distinct"):
        _backend(
            text_to_image_endpoint="same/route",
            edit_endpoint="same/route",
        )


@pytest.mark.asyncio
async def test_fal_text_to_image_maps_explicit_max_alpha_format_and_exact_canvas() -> None:
    requests: list[httpx.Request] = []
    image = png_bytes(size=(1536, 1024), color=(24, 48, 96, 128))

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"x-request-id": "fal-image-1"},
            json={
                "images": [
                    {
                        "url": _data_uri(image),
                        "content_type": "image/png",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _backend(api_key="fal-secret", client=client).generate_once(
            ImageGenerationRequest(
                prompt="One isolated painted prop.",
                artifact_path="unused.png",
                size="1536x1024",
                aspect_ratio="3:2",
                quality="max",
                background="transparent",
                output_format="png",
            )
        )

    assert len(requests) == 1
    request = requests[0]
    assert request.url == f"https://fal.run/{FAL_IMAGE_TEXT_TO_IMAGE_ENDPOINT}"
    assert request.headers["authorization"] == "Key fal-secret"
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {
        "prompt": "One isolated painted prop.",
        "num_images": 1,
        "image_size": {"width": 1536, "height": 1024},
        "quality": "max",
        "background": "transparent",
        "output_format": "png",
    }
    assert b"fal-secret" not in request.content
    assert result.data == image
    assert result.media_type == "image/png"
    assert result.response_metadata.request_id == "fal-image-1"
    assert result.response_metadata.usage is None
    assert result.applied_params == {
        "operation": "generation",
        "endpoint": f"https://fal.run/{FAL_IMAGE_TEXT_TO_IMAGE_ENDPOINT}",
        "n": 1,
        "size": "1536x1024",
        "quality": "max",
        "background": "transparent",
        "output_format": "png",
    }


@pytest.mark.asyncio
async def test_fal_edit_uses_distinct_endpoint_and_maps_references_and_mask_hint() -> None:
    requests: list[httpx.Request] = []
    image = png_bytes()
    reference = _data_uri(image)
    mask = _data_uri(png_bytes(color=(0, 0, 0, 0)))

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "images": [
                        {
                            "url": _data_uri(image),
                            "content_type": "image/png",
                            "width": 2,
                            "height": 2,
                        }
                    ]
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _backend(client=client).generate_once(
            ImageGenerationRequest(
                prompt="Repaint only the marked seam.",
                artifact_path="unused.png",
                input_references=(
                    ImageReference(reference, "reference-1"),
                    ImageReference("https://assets.example/reference.png", "reference-2"),
                ),
                mask_reference=ImageReference(mask, "mask-1"),
                size="auto",
                quality="max",
                background="opaque",
                output_format="png",
            )
        )

    assert len(requests) == 1
    request = requests[0]
    assert request.url == f"https://fal.run/{FAL_IMAGE_EDIT_ENDPOINT}"
    assert json.loads(request.content) == {
        "prompt": "Repaint only the marked seam.",
        "num_images": 1,
        "image_size": "auto",
        "quality": "max",
        "background": "opaque",
        "output_format": "png",
        "image_urls": [reference, "https://assets.example/reference.png"],
        "mask_url": mask,
    }
    assert result.applied_params == {
        "operation": "edit",
        "endpoint": f"https://fal.run/{FAL_IMAGE_EDIT_ENDPOINT}",
        "n": 1,
        "size": "auto",
        "quality": "max",
        "background": "opaque",
        "output_format": "png",
        "input_reference_count": 2,
        "reference_delivery": "mixed",
        "mask_present": True,
    }


@pytest.mark.asyncio
async def test_fal_hosted_output_download_never_receives_fal_authorization() -> None:
    posted: list[dict[str, object]] = []
    download_authorization: list[str | None] = []
    download_cookie: list[str | None] = []
    image = png_bytes(size=(1024, 1024))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posted.append(json.loads(request.content))
            assert request.headers["authorization"] == "Key fal-secret"
            return httpx.Response(
                200,
                json={"images": [{"url": "https://v3b.fal.media/files/output.png"}]},
            )
        download_authorization.append(request.headers.get("authorization"))
        download_cookie.append(request.headers.get("cookie"))
        return httpx.Response(200, content=image)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer inherited-secret", "Cookie": "session=private"},
    ) as client:
        result = await _backend(api_key="fal-secret", client=client).generate_once(
            ImageGenerationRequest(
                prompt="Opaque terrain atlas.",
                artifact_path="unused.png",
                size="1024x1024",
                quality="max",
                background="opaque",
                output_format="png",
            )
        )

    assert posted == [
        {
            "prompt": "Opaque terrain atlas.",
            "num_images": 1,
            "image_size": {"width": 1024, "height": 1024},
            "quality": "max",
            "background": "opaque",
            "output_format": "png",
        }
    ]
    assert download_authorization == [None]
    assert download_cookie == [None]
    assert result.data == image
    assert result.media_type == "image/png"
    assert "https://v3b.fal.media/files/output.png" not in repr(result)


@pytest.mark.asyncio
async def test_fal_hosted_output_never_follows_redirects_from_an_injected_client() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={"images": [{"url": "https://v3b.fal.media/files/output.png"}]},
            )
        if request.url.host == "v3b.fal.media":
            return httpx.Response(
                302,
                headers={"location": "https://example.com/escaped.png"},
            )
        raise AssertionError("fal output redirect escaped the allowed media host")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    ) as client:
        with pytest.raises(ValueError, match="HTTP 302"):
            await _backend(client=client).generate_once(
                ImageGenerationRequest(prompt="Redirect refusal.", artifact_path="unused.png")
            )

    assert [request.url.host for request in requests] == ["fal.run", "v3b.fal.media"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hosted_url",
    [
        "http://v3b.fal.media/files/output.png",
        "https://127.0.0.1/output.png",
        "https://169.254.169.254/latest/meta-data",
        "https://cdn.example.test/output.png",
        "https://fal.media.evil.example/output.png",
        "https://user:secret@fal.media/output.png",
        "https://fal.media:8443/output.png",
    ],
)
async def test_fal_refuses_untrusted_hosted_output_before_get(hosted_url: str) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method != "POST":
            raise AssertionError("untrusted hosted output must not be fetched")
        return httpx.Response(200, json={"images": [{"url": hosted_url}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match=r"must use HTTPS on fal\.media"):
            await _backend(client=client).generate_once(
                ImageGenerationRequest(prompt="Hosted output.", artifact_path="unused.png")
            )

    assert len(requests) == 1


@pytest.mark.asyncio
async def test_fal_refuses_oversized_hosted_output_from_content_length() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={"images": [{"url": "https://v3b.fal.media/files/output.png"}]},
            )
        return httpx.Response(
            200,
            headers={"content-length": str(64 * 1024 * 1024 + 1)},
            content=b"",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="64 MiB safety limit"):
            await _backend(client=client).generate_once(
                ImageGenerationRequest(prompt="Oversized output.", artifact_path="unused.png")
            )


class _ChunkedOutput(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"12345"
        yield b"6789"


@pytest.mark.asyncio
async def test_fal_refuses_stream_that_crosses_the_output_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys.modules[FalImageBackend.__module__], "_MAX_OUTPUT_BYTES", 8)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={"images": [{"url": "https://v3b.fal.media/files/output.png"}]},
            )
        return httpx.Response(200, stream=_ChunkedOutput())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="64 MiB safety limit"):
            await _backend(client=client).generate_once(
                ImageGenerationRequest(prompt="Chunked output.", artifact_path="unused.png")
            )


@pytest.mark.asyncio
async def test_fal_omits_unspecified_model_options_instead_of_selecting_defaults() -> None:
    bodies: list[dict[str, object]] = []
    image = _encoded_image("JPEG")

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"images": [{"url": _data_uri(image, "image/jpeg")}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _backend(client=client).generate_once(
            ImageGenerationRequest(prompt="Provider-default canary.", artifact_path="unused.jpg")
        )

    assert bodies == [{"prompt": "Provider-default canary.", "num_images": 1}]
    assert result.media_type == "image/jpeg"
    assert result.applied_params == {
        "operation": "generation",
        "endpoint": f"https://fal.run/{FAL_IMAGE_TEXT_TO_IMAGE_ENDPOINT}",
        "n": 1,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("size", "message"),
    [
        ("1600x900", "multiples of 16"),
        ("256x1024", "aspect ratio"),
        ("3856x1024", "must not exceed 3840"),
        ("3840x2176", "between 655360 and 8294400"),
        ("256x768", "between 655360 and 8294400"),
    ],
)
async def test_fal_rejects_unsupported_exact_size_before_transport(
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
            await _backend(client=client).generate_once(
                ImageGenerationRequest(
                    prompt="Invalid exact size.", artifact_path="unused.png", size=size
                )
            )

    assert calls == 0


@pytest.mark.asyncio
async def test_fal_rejects_decoded_dimensions_that_differ_from_exact_request() -> None:
    image = png_bytes(size=(1024, 1008))

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"images": [{"url": _data_uri(image)}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match=r"1024x1008.*requested 1024x1024"):
            await _backend(client=client).generate_once(
                ImageGenerationRequest(
                    prompt="Exact size canary.",
                    artifact_path="unused.png",
                    size="1024x1024",
                    output_format="png",
                )
            )


@pytest.mark.asyncio
async def test_fal_rejects_response_dimensions_that_disagree_with_decoded_bytes() -> None:
    image = png_bytes()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "images": [
                    {
                        "url": _data_uri(image),
                        "content_type": "image/png",
                        "width": 32,
                        "height": 32,
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="dimensions do not match decoded bytes"):
            await _backend(client=client).generate_once(
                ImageGenerationRequest(prompt="Metadata canary.", artifact_path="unused.png")
            )


@pytest.mark.asyncio
async def test_fal_rejects_returned_format_that_differs_from_request() -> None:
    image = _encoded_image("JPEG")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"images": [{"url": _data_uri(image, "image/jpeg")}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match=r"image/jpeg.*requested image/png"):
            await _backend(client=client).generate_once(
                ImageGenerationRequest(
                    prompt="Wrong format canary.",
                    artifact_path="unused.png",
                    output_format="png",
                )
            )


@pytest.mark.asyncio
async def test_fal_transparent_background_requires_an_alpha_channel() -> None:
    image = _encoded_image("PNG", alpha=False)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"images": [{"url": _data_uri(image)}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="has no alpha channel"):
            await _backend(client=client).generate_once(
                ImageGenerationRequest(
                    prompt="Alpha canary.",
                    artifact_path="unused.png",
                    background="transparent",
                    output_format="png",
                )
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"images": []},
        {"images": [{"url": "one"}, {"url": "two"}]},
        {"images": ["not-an-object"]},
        {"images": [{}]},
        {"images": [{"url": "data:image/png;base64,not-base64!"}]},
    ],
)
async def test_fal_requires_exactly_one_well_formed_image(payload: object) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError):
            await _backend(client=client).generate_once(
                ImageGenerationRequest(prompt="Strict response.", artifact_path="unused.png")
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"mask_reference": ImageReference("https://example.com/mask.png")}, "input reference"),
        ({"resolution": "2K"}, "do not accept resolution"),
        ({"moderation": "low"}, "do not accept moderation"),
        ({"aspect_ratio": "5:4"}, "require size with aspect_ratio"),
        ({"output_compression": 80}, "requires explicit jpeg or webp"),
        (
            {"output_format": "png", "output_compression": 80},
            "requires explicit jpeg or webp",
        ),
    ],
)
async def test_fal_rejects_unexpressible_options_before_transport(
    overrides: dict[str, Any],
    message: str,
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("unsupported option must not reach transport")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match=message):
            await _backend(client=client).generate_once(
                ImageGenerationRequest(
                    prompt="Unsupported option.",
                    artifact_path="unused.png",
                    **overrides,
                )
            )

    assert calls == 0


@pytest.mark.asyncio
async def test_fal_does_not_retry_a_failed_provider_request() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="HTTP 500"):
            await _backend(client=client).generate_once(
                ImageGenerationRequest(prompt="One attempt.", artifact_path="unused.png")
            )

    assert calls == 1
