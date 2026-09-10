"""One-attempt fal adapter for GPT Image 2.5 Sunburst generation and edits."""

from __future__ import annotations

import re
from typing import ClassVar, Literal
from urllib.parse import urlsplit

import httpx

from gnode.modalities.image import (
    ImageGenerationRequest,
    ProviderImage,
    classify_image_reference_delivery,
    inspect_image,
)
from gnode.modalities.image.inspection import ImageFacts
from gnode.modalities.signatures import normalize_media_type
from gnode.providers._http import (
    assert_success,
    json_object,
    normalized_base_url,
    response_metadata,
)
from gnode.reliability import decode_base64_strict

FAL_BASE_URL = "https://fal.run"
FAL_IMAGE_ADAPTER_ID = "gnode-fal-image-v1"
FAL_IMAGE_ADAPTER_BEHAVIOR_VERSION = "1"
_DATA_URI = re.compile(r"^data:([^;,]+);base64,(.+)$", re.IGNORECASE | re.DOTALL)
_SIZE_RE = re.compile(r"^([1-9]\d*)x([1-9]\d*)$")
_MIN_PIXELS = 655_360
_MAX_PIXELS = 8_294_400
_MAX_EDGE = 3_840
_MAX_ASPECT_RATIO = 3
_MAX_OUTPUT_BYTES = 64 * 1024 * 1024
_OUTPUT_MEDIA_TYPES = {
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


class FalImageBackend:
    """Make exactly one synchronous fal image request.

    The provider exposes separate public routes for text-to-image and edit. This
    adapter selects only between those two actions; retry, default model policy,
    caller validation, and persistence remain outside it.
    """

    spec_version: ClassVar[Literal[1]] = 1

    provider = "fal"
    adapter_id = FAL_IMAGE_ADAPTER_ID
    adapter_behavior_version = FAL_IMAGE_ADAPTER_BEHAVIOR_VERSION
    supports_native_alpha: bool

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        text_to_image_endpoint: str,
        edit_endpoint: str,
        supports_native_alpha: bool,
        base_url: str = FAL_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("fal api_key must be non-empty")
        model_id = model.strip().strip("/")
        if not model_id:
            raise ValueError("fal image model must be non-empty")
        if not isinstance(supports_native_alpha, bool):
            raise ValueError("fal image supports_native_alpha must be a boolean")
        self.text_to_image_endpoint = _endpoint_id(
            text_to_image_endpoint, "fal text-to-image endpoint"
        )
        self.edit_endpoint = _endpoint_id(edit_endpoint, "fal edit endpoint")
        if self.text_to_image_endpoint == self.edit_endpoint:
            raise ValueError("fal image generation and edit endpoints must be distinct")
        self._api_key = api_key
        self.secrets: tuple[str, ...] = (api_key,)
        self.model = model_id
        self.supports_native_alpha = supports_native_alpha
        self._base_url = normalized_base_url(base_url, "fal base_url")
        self._client = client or httpx.AsyncClient(timeout=None)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def endpoint_for(self, request: ImageGenerationRequest) -> str:
        endpoint_id = (
            self.edit_endpoint if request.input_references else self.text_to_image_endpoint
        )
        return f"{self._base_url}/{endpoint_id}"

    async def generate_once(self, request: ImageGenerationRequest) -> ProviderImage:
        is_edit = bool(request.input_references)
        if request.mask_reference is not None and not is_edit:
            raise ValueError("fal masked edits require at least one input reference")
        if len(request.input_references) > 16:
            raise ValueError("fal image edits support at most 16 input references")
        if request.resolution is not None:
            raise ValueError("fal exact-canvas image requests do not accept resolution")
        if request.moderation is not None:
            raise ValueError("fal GPT Image routes do not accept moderation")
        if request.output_compression is not None and request.output_format not in {
            "jpeg",
            "webp",
        }:
            raise ValueError("fal output_compression requires explicit JPEG or WebP output")

        image_size, expected_size = _fal_image_size(request.size, request.aspect_ratio)
        endpoint = self.endpoint_for(request)
        operation = "edit" if is_edit else "generation"
        body: dict[str, object] = {
            "prompt": request.prompt,
            "num_images": 1,
        }
        applied_params: dict[str, object] = {
            "operation": operation,
            "endpoint": endpoint,
            "n": 1,
        }
        if image_size is not None:
            body["image_size"] = image_size
            applied_params["size"] = request.size or "auto"
        if request.quality is not None:
            body["quality"] = request.quality
            applied_params["quality"] = request.quality
        if request.background is not None:
            body["background"] = request.background
            applied_params["background"] = request.background
        if request.output_format is not None:
            body["output_format"] = request.output_format
            applied_params["output_format"] = request.output_format
        if request.output_compression is not None:
            body["output_compression"] = request.output_compression
            applied_params["output_compression"] = request.output_compression
        if is_edit:
            body["image_urls"] = [reference.url for reference in request.input_references]
            applied_params["input_reference_count"] = len(request.input_references)
            applied_params["reference_delivery"] = classify_image_reference_delivery(
                (
                    *request.input_references,
                    *((request.mask_reference,) if request.mask_reference is not None else ()),
                )
            )
            if request.mask_reference is not None:
                body["mask_url"] = request.mask_reference.url
                applied_params["mask_present"] = True

        response = await self._client.post(
            endpoint,
            headers={
                "Authorization": f"Key {self._api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        assert_success(response, "fal image generation")
        payload = json_object(response, "fal image generation")
        root = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        images = root.get("images") if isinstance(root, dict) else None
        if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict):
            raise ValueError("fal image generation returned no single image")
        image = images[0]
        source_url = image.get("url")
        if not isinstance(source_url, str) or not source_url.strip():
            raise ValueError("fal output image url must be non-empty")
        declared_media_type = _optional_image_media_type(image.get("content_type"))
        data, facts = await self._load_image(source_url, declared_media_type)
        _validate_response_dimensions(image, facts)
        if expected_size is not None and (facts.width, facts.height) != expected_size:
            width, height = expected_size
            raise ValueError(
                f"fal output dimensions {facts.width}x{facts.height} do not match "
                f"requested {width}x{height}"
            )
        if request.output_format is not None:
            expected_media_type = _OUTPUT_MEDIA_TYPES[request.output_format]
            if facts.media_type != expected_media_type:
                raise ValueError(
                    f"fal output type {facts.media_type} does not match requested "
                    f"{expected_media_type}"
                )
        if request.background == "transparent" and not facts.has_alpha:
            raise ValueError("fal transparent-background output has no alpha channel")
        return ProviderImage(
            data=data,
            media_type=facts.media_type,
            response_metadata=response_metadata(response, payload),
            applied_params=applied_params,
        )

    async def _load_image(
        self,
        source_url: str,
        declared_media_type: str | None,
    ) -> tuple[bytes, ImageFacts]:
        match = _DATA_URI.fullmatch(source_url)
        if match is not None:
            data_uri_media_type = _fal_image_media_type(match.group(1))
            if declared_media_type is not None and declared_media_type != data_uri_media_type:
                raise ValueError("fal data URI media type does not match response metadata")
            data = decode_base64_strict(match.group(2), "fal output image data")
            if len(data) > _MAX_OUTPUT_BYTES:
                raise ValueError("fal output image exceeds the 64 MiB safety limit")
            return data, inspect_image(data, expected_media_type=data_uri_media_type)
        _validate_fal_output_url(source_url)

        # The Fal key authenticates the API request, never the provider-selected output host.
        # Hosted output is restricted to Fal's media domain, redirects stay disabled, and
        # the body is streamed under a fixed ceiling before it can consume unbounded memory.
        download = await self._client.send(
            httpx.Request("GET", source_url, headers={"Accept": "image/*"}),
            stream=True,
            follow_redirects=False,
        )
        try:
            assert_success(download, "fal output image download")
            _validate_content_length(download.headers.get("content-length"))
            header_media_type = _optional_image_media_type(download.headers.get("content-type"))
            if (
                declared_media_type is not None
                and header_media_type is not None
                and declared_media_type != header_media_type
            ):
                raise ValueError("fal output download media type does not match response metadata")
            expected_media_type = declared_media_type or header_media_type
            chunks: list[bytes] = []
            byte_count = 0
            async for chunk in download.aiter_bytes():
                byte_count += len(chunk)
                if byte_count > _MAX_OUTPUT_BYTES:
                    raise ValueError("fal output image exceeds the 64 MiB safety limit")
                chunks.append(chunk)
            data = b"".join(chunks)
        finally:
            await download.aclose()
        if not data:
            raise ValueError("fal output image download was empty")
        return data, inspect_image(data, expected_media_type=expected_media_type)


def _endpoint_id(value: str, label: str) -> str:
    endpoint = value.strip().strip("/")
    if not endpoint:
        raise ValueError(f"{label} must be non-empty")
    return endpoint


def _fal_image_size(
    size: str | None,
    aspect_ratio: str | None,
) -> tuple[object | None, tuple[int, int] | None]:
    if size is None:
        if aspect_ratio not in {None, "auto"}:
            raise ValueError("fal exact-canvas image requests require size with aspect_ratio")
        return None, None
    if size == "auto":
        if aspect_ratio not in {None, "auto"}:
            raise ValueError("fal exact-canvas image requests require size with aspect_ratio")
        return "auto", None

    match = _SIZE_RE.fullmatch(size)
    if match is None:
        raise ValueError("fal image size must be auto or WIDTHxHEIGHT")
    width, height = (int(edge) for edge in match.groups())
    if width % 16 != 0 or height % 16 != 0:
        raise ValueError("fal image size edges must be multiples of 16")
    if max(width, height) > _MAX_EDGE:
        raise ValueError("fal image size edges must not exceed 3840 pixels")
    if max(width, height) > _MAX_ASPECT_RATIO * min(width, height):
        raise ValueError("fal image size aspect ratio must not exceed 3:1")
    pixels = width * height
    if not _MIN_PIXELS <= pixels <= _MAX_PIXELS:
        raise ValueError("fal image size must contain between 655360 and 8294400 pixels")
    if aspect_ratio is not None and aspect_ratio != "auto":
        aspect_width, aspect_height = (int(edge) for edge in aspect_ratio.split(":"))
        if width * aspect_height != height * aspect_width:
            raise ValueError("fal image size does not match requested aspect_ratio")
    return {"width": width, "height": height}, (width, height)


def _optional_image_media_type(value: object) -> str | None:
    if value is None:
        return None
    return _fal_image_media_type(value)


def _fal_image_media_type(value: object) -> str:
    media_type = normalize_media_type(value, "image")
    if media_type == "image/jpg":
        media_type = "image/jpeg"
    if media_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise ValueError("fal image media type must be PNG, JPEG, or WebP")
    return media_type


def _validate_response_dimensions(image: dict[object, object], facts: ImageFacts) -> None:
    width = _response_dimension(image, "width")
    height = _response_dimension(image, "height")
    if (width is None) != (height is None):
        raise ValueError("fal output image dimensions must include both width and height")
    if width is not None and height is not None and (width, height) != (facts.width, facts.height):
        raise ValueError("fal output image dimensions do not match decoded bytes")


def _response_dimension(image: dict[object, object], key: str) -> int | None:
    if key not in image or image[key] is None:
        return None
    value = image[key]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"fal output image {key} must be a positive integer")
    return value


def _validate_fal_output_url(value: str) -> None:
    parsed = urlsplit(value)
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if (
        parsed.scheme != "https"
        or not hostname
        or (hostname != "fal.media" and not hostname.endswith(".fal.media"))
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.fragment
    ):
        raise ValueError(
            "fal hosted output must use HTTPS on fal.media without userinfo or a custom port"
        )


def _validate_content_length(value: str | None) -> None:
    if value is None:
        return
    try:
        byte_count = int(value)
    except ValueError as error:
        raise ValueError("fal output content-length must be a non-negative integer") from error
    if byte_count < 0:
        raise ValueError("fal output content-length must be a non-negative integer")
    if byte_count > _MAX_OUTPUT_BYTES:
        raise ValueError("fal output image exceeds the 64 MiB safety limit")


__all__ = [
    "FAL_IMAGE_ADAPTER_BEHAVIOR_VERSION",
    "FAL_IMAGE_ADAPTER_ID",
    "FalImageBackend",
]
