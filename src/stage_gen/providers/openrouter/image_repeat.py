"""OpenRouter adapter for one retry-owned image-repeat repair attempt."""

from __future__ import annotations

import base64
from io import BytesIO

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from gnode import ImageGenerationRequest, ImageReference, inspect_image
from stage_gen.components.image_repeat.models import (
    MASKED_IMAGE_EDIT_CAPABILITY,
    MaskedImageEditRequest,
    ProviderImageRepeatEdit,
)

from .image import OPENROUTER_BASE_URL, OPENROUTER_IMAGE_MODEL, OpenRouterImageBackend


class OpenRouterMaskedImageEditBackend:
    """Adapt image-reference generation to the component's masked-edit protocol.

    The component remains the only retry owner. This adapter makes exactly one
    provider call, normalizes the returned raster to the conditioning geometry,
    and leaves immutable-region restoration and seam acceptance to
    ``ImageRepeatService``.
    """

    provider = "openrouter"
    capability = MASKED_IMAGE_EDIT_CAPABILITY

    def __init__(
        self,
        *,
        api_key: str,
        model: str = OPENROUTER_IMAGE_MODEL,
        base_url: str = OPENROUTER_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._backend = OpenRouterImageBackend(
            api_key=api_key,
            model=model,
            base_url=base_url,
            client=client,
        )
        self.model = self._backend.model
        self.secrets = self._backend.secrets

    async def edit_once(self, request: MaskedImageEditRequest) -> ProviderImageRepeatEdit:
        if request.cancellation is not None:
            request.cancellation.raise_if_cancelled()
        generated = await self._backend.generate_once(
            ImageGenerationRequest(
                prompt=_repair_prompt(request),
                artifact_path="provider-owned-image-repeat-attempt.png",
                input_references=(
                    ImageReference(
                        _png_data_url(request.conditioning_image),
                        "image-repeat-conditioning",
                    ),
                    ImageReference(
                        _png_data_url(request.mask_image),
                        "image-repeat-mask",
                    ),
                ),
                # OpenRouter exposes a finite aspect-ratio allowlist for image models. ``auto``
                # lets the provider infer the reference geometry; this adapter then normalizes
                # the returned raster to the component's exact conditioning dimensions.
                aspect_ratio="auto",
                quality="high",
                background="auto",
                moderation="auto",
                metadata={
                    "component": "image_repeat",
                    "operation": "explicit_repair",
                    "axis": request.axis,
                    "context_span_px": request.context_span_px,
                    "repair_span_px": request.repair_span_px,
                    **dict(request.metadata),
                },
                cancellation=request.cancellation,
            )
        )
        if request.cancellation is not None:
            request.cancellation.raise_if_cancelled()
        normalized = _normalize_png(generated.data, request.width, request.height)
        return ProviderImageRepeatEdit(
            data=normalized,
            media_type="image/png",
            response_metadata=generated.response_metadata,
        )

    async def aclose(self) -> None:
        await self._backend.aclose()


def _repair_prompt(request: MaskedImageEditRequest) -> str:
    direction = "left to right" if request.axis == "x" else "top to bottom"
    return f"""\
{request.prompt.strip()}

This is a constrained single-axis transition repair, not a request to redraw the source.
Image 1 is the exact conditioning canvas. It contains an immutable tail context, one unknown
middle span, and an immutable head context in {direction} order. Image 2 is the exact mask:
white is the only span to paint and black must remain unchanged. Fill the white span so the
tail context continues naturally into the head context. Preserve the same rendering, scale,
lighting, alpha/transparency behavior, and gravity. Do not mirror, reverse, duplicate a landmark,
add a frame, create a visible midpoint, or introduce text. Return one clean PNG containing only
the completed conditioning canvas. Keep transparent regions transparent when the contexts use
alpha; do not add a matte or checkerboard.
"""


def _png_data_url(data: bytes) -> str:
    inspect_image(data, expected_media_type="image/png")
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _normalize_png(data: bytes, width: int, height: int) -> bytes:
    try:
        with Image.open(BytesIO(data)) as decoded:
            decoded.load()
            image = ImageOps.exif_transpose(decoded).convert("RGBA")
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("masked image edit returned undecodable image data") from error
    if image.size != (width, height):
        image = image.resize((width, height), resample=Image.Resampling.LANCZOS)
    output = BytesIO()
    image.save(output, format="PNG", compress_level=9, optimize=False)
    normalized = output.getvalue()
    facts = inspect_image(normalized, expected_media_type="image/png")
    if (facts.width, facts.height) != (width, height):
        raise ValueError("masked image edit normalization changed target dimensions")
    return normalized


__all__ = ["OpenRouterMaskedImageEditBackend"]
