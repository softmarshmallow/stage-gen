"""Direct OpenAI adapter for one GPT Image request attempt."""

from __future__ import annotations

import asyncio
import re

import httpx

from stage_gen.components.image_generation.models import (
    ImageGenerationRequest,
    ProviderImage,
)
from stage_gen.media import decode_base64_strict, inspect_image
from stage_gen.providers._http import (
    assert_success,
    json_object,
    normalized_base_url,
    response_metadata,
)

OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENAI_IMAGE_MODEL = "gpt-image-2"
OPENAI_IMAGE_REQUESTS_PER_MINUTE = 5

_SIZE_RE = re.compile(r"^([1-9]\d*)x([1-9]\d*)$")
_MIN_PIXELS = 655_360
_MAX_PIXELS = 8_294_400
_MAX_EDGE = 3_840
_MAX_ASPECT_RATIO = 3
_OUTPUT_MEDIA_TYPES = {
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}
_REFERENCE_DATA_URL = re.compile(r"^data:(image/[^;,]+);base64,(.+)$", re.IGNORECASE | re.DOTALL)
_REFERENCE_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
_SIZE_BY_ASPECT_RATIO = {
    "1:1": "1024x1024",
    "3:2": "1536x1024",
    "2:3": "1024x1536",
    "4:3": "1536x1152",
    "3:4": "1152x1536",
    "16:9": "2048x1152",
    "9:16": "1152x2048",
    "21:9": "2688x1152",
}


class OpenAIImageBackend:
    """Make exactly one direct OpenAI Image API request.

    Retry, caller validation, and persistence deliberately remain owned by
    ``ImageGenerationService``.
    """

    provider = "openai"
    supports_native_alpha = True

    def __init__(
        self,
        *,
        api_key: str,
        model: str = OPENAI_IMAGE_MODEL,
        base_url: str = OPENAI_BASE_URL,
        client: httpx.AsyncClient | None = None,
        requests_per_minute: int = OPENAI_IMAGE_REQUESTS_PER_MINUTE,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenAI api_key must be non-empty")
        if not model.strip():
            raise ValueError("OpenAI image model must be non-empty")
        if (
            isinstance(requests_per_minute, bool)
            or not isinstance(requests_per_minute, int)
            or requests_per_minute <= 0
        ):
            raise ValueError("OpenAI image requests_per_minute must be a positive integer")
        self._api_key = api_key
        self.secrets: tuple[str, ...] = (api_key,)
        self.model = model.strip()
        self.supports_native_alpha = bool(
            re.fullmatch(r"gpt-image-2(?:-\d{4}-\d{2}-\d{2})?", self.model)
        )
        self._base_url = normalized_base_url(base_url, "OpenAI base_url")
        self._client = client or httpx.AsyncClient(timeout=None)
        self._owns_client = client is None
        self._request_interval_seconds = 60.0 / requests_per_minute
        self._request_start_lock = asyncio.Lock()
        self._next_request_start = 0.0

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def generate_once(self, request: ImageGenerationRequest) -> ProviderImage:
        output_format = request.output_format or "png"
        media_type = _OUTPUT_MEDIA_TYPES[output_format]
        body: dict[str, object] = {
            "model": self.model,
            "prompt": request.prompt,
            "n": 1,
            "output_format": output_format,
        }
        size = request.size
        aspect_ratio = request.aspect_ratio
        if size is None and aspect_ratio is not None and aspect_ratio != "auto":
            try:
                size = _SIZE_BY_ASPECT_RATIO[aspect_ratio]
            except KeyError as error:
                raise ValueError(
                    f"OpenAI GPT Image 2 has no verified size mapping for "
                    f"aspect ratio {aspect_ratio}"
                ) from error
        if size is not None:
            _validate_gpt_image_2_size(size)
            body["size"] = size
        if request.quality is not None:
            body["quality"] = request.quality
        if request.background is not None:
            body["background"] = request.background
        # The direct generations schema supports moderation. The edits schema does not;
        # provider-neutral callers may still carry the intent, so omit it at this adapter
        # boundary instead of sending an undocumented multipart field.
        if request.moderation is not None and not request.input_references:
            body["moderation"] = request.moderation
        if request.output_compression is not None:
            if output_format == "png":
                raise ValueError("OpenAI PNG output does not support output_compression")
            body["output_compression"] = request.output_compression

        endpoint = "images/generations"
        files: list[tuple[str, tuple[str, bytes, str]]] | None = None
        if request.input_references:
            if len(request.input_references) > 16:
                raise ValueError("OpenAI image edits support at most 16 input references")
            endpoint = "images/edits"
            files = [
                _multipart_reference(reference.url, index=index)
                for index, reference in enumerate(request.input_references, start=1)
            ]

        headers = {"Authorization": f"Bearer {self._api_key}"}
        await self._pace_request_start()
        if files is None:
            response = await self._client.post(
                f"{self._base_url}/{endpoint}",
                headers={**headers, "Content-Type": "application/json"},
                json=body,
            )
        else:
            response = await self._client.post(
                f"{self._base_url}/{endpoint}",
                headers=headers,
                data={key: str(value) for key, value in body.items()},
                files=files,
            )
        assert_success(
            response,
            "OpenAI image generation",
            include_safe_error_detail=True,
            redactions=self.secrets,
        )
        payload = json_object(response, "OpenAI image generation")
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise ValueError("OpenAI image generation returned no single image")
        image_data = decode_base64_strict(data[0].get("b64_json"), "OpenAI image b64_json")
        inspect_image(image_data, expected_media_type=media_type)
        return ProviderImage(
            data=image_data,
            media_type=media_type,
            response_metadata=response_metadata(response, payload),
            applied_params={
                "operation": "edit" if files is not None else "generation",
                **{key: value for key, value in body.items() if key not in {"model", "prompt"}},
            },
        )

    async def _pace_request_start(self) -> None:
        """Conservatively respect the lowest supported GPT Image 2 IPM tier."""

        loop = asyncio.get_running_loop()
        async with self._request_start_lock:
            now = loop.time()
            if self._next_request_start > now:
                await asyncio.sleep(self._next_request_start - now)
            self._next_request_start = loop.time() + self._request_interval_seconds


def _multipart_reference(url: str, *, index: int) -> tuple[str, tuple[str, bytes, str]]:
    match = _REFERENCE_DATA_URL.fullmatch(url)
    if match is None:
        raise ValueError("direct OpenAI image edits require base64 image data URL references")
    declared_media_type = match.group(1).lower()
    if declared_media_type == "image/jpg":
        declared_media_type = "image/jpeg"
    try:
        extension = _REFERENCE_EXTENSIONS[declared_media_type]
    except KeyError as error:
        raise ValueError(
            "direct OpenAI image edits require PNG, JPEG, or WebP references"
        ) from error
    data = decode_base64_strict(match.group(2), f"OpenAI image reference {index}")
    inspect_image(data, expected_media_type=declared_media_type)
    return (
        "image[]",
        (f"reference-{index:02d}.{extension}", data, declared_media_type),
    )


def _validate_gpt_image_2_size(value: str) -> None:
    if value == "auto":
        return
    match = _SIZE_RE.fullmatch(value)
    if match is None:
        raise ValueError("OpenAI image size must be auto or WIDTHxHEIGHT")
    width, height = (int(edge) for edge in match.groups())
    if width % 16 != 0 or height % 16 != 0:
        raise ValueError("OpenAI GPT Image 2 size edges must be multiples of 16")
    if max(width, height) > _MAX_EDGE:
        raise ValueError("OpenAI GPT Image 2 size edges must not exceed 3840 pixels")
    if max(width, height) > _MAX_ASPECT_RATIO * min(width, height):
        raise ValueError("OpenAI GPT Image 2 size aspect ratio must not exceed 3:1")
    pixels = width * height
    if not _MIN_PIXELS <= pixels <= _MAX_PIXELS:
        raise ValueError("OpenAI GPT Image 2 size must contain between 655360 and 8294400 pixels")


__all__ = [
    "OPENAI_BASE_URL",
    "OPENAI_IMAGE_MODEL",
    "OPENAI_IMAGE_REQUESTS_PER_MINUTE",
    "OpenAIImageBackend",
]
