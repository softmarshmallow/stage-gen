from __future__ import annotations

from typing import ClassVar, Literal

import httpx

from gnode.modalities.image import ImageGenerationRequest, ProviderImage
from gnode.modalities.signatures import (
    assert_image_signature,
    normalize_media_type,
)
from gnode.providers._http import (
    assert_success,
    json_object,
    normalized_base_url,
    response_metadata,
)
from gnode.reliability import decode_base64_strict

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_IMAGE_MODEL = "openai/gpt-image-2"


class OpenRouterImageBackend:
    spec_version: ClassVar[Literal[1]] = 1
    provider = "openrouter"
    supports_native_alpha = False

    def __init__(
        self,
        *,
        api_key: str,
        model: str = OPENROUTER_IMAGE_MODEL,
        base_url: str = OPENROUTER_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenRouter api_key must be non-empty")
        if not model.strip():
            raise ValueError("OpenRouter image model must be non-empty")
        self._api_key = api_key
        self.secrets: tuple[str, ...] = (api_key,)
        self.model = model.strip()
        self._base_url = normalized_base_url(base_url, "OpenRouter base_url")
        self._client = client or httpx.AsyncClient(timeout=None)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def generate_once(self, request: ImageGenerationRequest) -> ProviderImage:
        if request.mask_reference is not None:
            raise ValueError(
                "OpenRouter image generation has no masked-edit route; use the OpenAI backend"
            )
        body: dict[str, object] = {"model": self.model, "prompt": request.prompt, "n": 1}
        if request.size is not None:
            body["size"] = request.size
        if request.aspect_ratio is not None:
            body["aspect_ratio"] = request.aspect_ratio
        if request.resolution is not None:
            body["resolution"] = request.resolution
        if request.quality is not None:
            body["quality"] = request.quality
        if request.background is not None:
            body["background"] = request.background
        if request.output_compression is not None:
            body["output_compression"] = request.output_compression
        if request.input_references:
            body["input_references"] = [
                {"type": "image_url", "image_url": {"url": reference.url}}
                for reference in request.input_references
            ]
        if request.moderation is not None:
            body["provider"] = {"options": {"openai": {"moderation": request.moderation}}}
        response = await self._client.post(
            f"{self._base_url}/images",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        assert_success(response, "OpenRouter image generation")
        payload = json_object(response, "OpenRouter image generation")
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise ValueError("OpenRouter image generation returned no single image")
        encoded = data[0].get("b64_json")
        image_data = decode_base64_strict(encoded, "OpenRouter image b64_json")
        media_type = (
            _openrouter_image_media_type(data[0]["media_type"])
            if "media_type" in data[0]
            else _infer_openrouter_image_media_type(image_data)
        )
        assert_image_signature(image_data, media_type)
        return ProviderImage(
            data=image_data,
            media_type=media_type,
            response_metadata=response_metadata(response, payload),
        )


def _openrouter_image_media_type(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or ";" in value:
        raise ValueError("OpenRouter image media type must be parameter-free PNG, JPEG, or WebP")
    media_type = normalize_media_type(value, "image")
    if media_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise ValueError("OpenRouter image media type must be PNG, JPEG, or WebP")
    return media_type


def _infer_openrouter_image_media_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError(
        "OpenRouter image response omitted media_type and bytes are not PNG, JPEG, or WebP"
    )
