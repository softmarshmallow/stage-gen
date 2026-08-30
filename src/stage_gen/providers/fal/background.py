from __future__ import annotations

import re
from typing import ClassVar, Literal

import httpx

from gnode import (
    BackgroundMaskArtifact,
    BackgroundMaskMetadata,
    BackgroundRemovalRequest,
    ProviderBackgroundRemoval,
    assert_image_signature,
    decode_base64_strict,
    normalize_media_type,
)
from stage_gen.providers._http import (
    assert_success,
    json_object,
    normalized_base_url,
    response_metadata,
)

FAL_BACKGROUND_REMOVAL_MODEL = "fal-ai/birefnet/v2"
FAL_BASE_URL = "https://fal.run"
_DATA_URI = re.compile(r"^data:([^;,]+);base64,(.+)$", re.IGNORECASE | re.DOTALL)


class FalBackgroundRemovalBackend:
    spec_version: ClassVar[Literal[1]] = 1
    provider = "fal"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = FAL_BACKGROUND_REMOVAL_MODEL,
        base_url: str = FAL_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("fal api_key must be non-empty")
        if not model.strip():
            raise ValueError("fal background model must be non-empty")
        self._api_key = api_key
        self.secrets: tuple[str, ...] = (api_key,)
        self.model = model.strip().lstrip("/")
        self._base_url = normalized_base_url(base_url, "fal base_url")
        self._client = client or httpx.AsyncClient(timeout=None)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def remove_once(self, request: BackgroundRemovalRequest) -> ProviderBackgroundRemoval:
        body = {
            "image_url": request.image_url,
            "model": request.model_variant,
            "operating_resolution": request.operating_resolution,
            "output_mask": request.output_mask,
            "refine_foreground": request.refine_foreground,
            "output_format": request.output_format,
            "mask_only": request.mask_only,
            "sync_mode": request.sync_mode,
        }
        response = await self._client.post(
            f"{self._base_url}/{self.model}",
            headers={
                "Authorization": f"Key {self._api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        assert_success(response, "fal background removal")
        payload = json_object(response, "fal background removal")
        root = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        image = root.get("image") if isinstance(root, dict) else None
        if not isinstance(image, dict):
            raise ValueError("fal background removal returned no image")
        source_url = image.get("url")
        if not isinstance(source_url, str) or not source_url.strip():
            raise ValueError("fal output image url must be non-empty")
        declared = _optional_image_media_type(image.get("content_type"))
        data, media_type, source_kind = await self._load_image(source_url, declared)
        width = _positive_integer(image.get("width"))
        height = _positive_integer(image.get("height"))
        mask_metadata = _mask_metadata(root.get("mask_image") if isinstance(root, dict) else None)
        mask: BackgroundMaskArtifact | None = None
        if mask_metadata is not None:
            mask_data, mask_type, _ = await self._load_image(
                mask_metadata.url, mask_metadata.media_type
            )
            mask = BackgroundMaskArtifact(
                url=mask_metadata.url,
                data=mask_data,
                media_type=mask_type,
                width=mask_metadata.width,
                height=mask_metadata.height,
            )
        return ProviderBackgroundRemoval(
            data=data,
            media_type=media_type,
            source_url=source_url,
            source_kind=source_kind,
            width=width,
            height=height,
            mask_image=mask_metadata,
            mask=mask,
            response_metadata=response_metadata(response, payload),
        )

    async def _load_image(
        self, source_url: str, declared_media_type: str | None
    ) -> tuple[bytes, str, str]:
        match = _DATA_URI.match(source_url)
        if match:
            media_type = _fal_image_media_type(match.group(1))
            if declared_media_type and declared_media_type != media_type:
                raise ValueError("fal data URI media type does not match response metadata")
            data = decode_base64_strict(match.group(2), "fal output image data")
            assert_image_signature(data, media_type)
            return data, media_type, "data-uri"
        if not source_url.lower().startswith(("http://", "https://")):
            raise ValueError("fal output image url must be HTTP(S) or a base64 data URI")
        # Authorization is intentionally not forwarded to provider-hosted output URLs.
        response = await self._client.get(source_url, headers={})
        assert_success(response, "fal output image download")
        header = _optional_image_media_type(response.headers.get("content-type"))
        if declared_media_type and header and declared_media_type != header:
            raise ValueError("fal output download media type does not match response metadata")
        resolved_media_type = declared_media_type or header
        if resolved_media_type is None:
            raise ValueError("fal output image media type is missing")
        data = response.content
        if not data:
            raise ValueError("fal output image download was empty")
        assert_image_signature(data, resolved_media_type)
        return data, resolved_media_type, "hosted-download"


def _optional_image_media_type(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return _fal_image_media_type(value)


def _fal_image_media_type(value: object) -> str:
    media_type = normalize_media_type(value, "image")
    if media_type not in {"image/png", "image/webp", "image/gif"}:
        raise ValueError("fal image media type must be PNG, WebP, or GIF")
    return media_type


def _positive_integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _mask_metadata(value: object) -> BackgroundMaskMetadata | None:
    if not isinstance(value, dict) or not isinstance(value.get("url"), str) or not value["url"]:
        return None
    return BackgroundMaskMetadata(
        url=value["url"],
        media_type=_optional_image_media_type(value.get("content_type")),
        width=_positive_integer(value.get("width")),
        height=_positive_integer(value.get("height")),
    )
