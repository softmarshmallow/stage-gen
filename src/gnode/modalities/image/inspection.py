"""Decode-level image inspection: dimensions, format, and alpha presence.

This is the modality-generic half of image inspection — what any caller needs
to check a provider result or route a request. Application-side normalization
and compositing stay with the application.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from gnode.modalities.signatures import assert_image_signature


@dataclass(frozen=True, slots=True)
class ImageFacts:
    width: int
    height: int
    media_type: str
    format: str
    has_alpha: bool


def inspect_image(data: bytes, *, expected_media_type: str | None = None) -> ImageFacts:
    if not data:
        raise ValueError("image data must be non-empty")
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            image_format = (image.format or "").upper()
            media_type = {
                "PNG": "image/png",
                "JPEG": "image/jpeg",
                "WEBP": "image/webp",
                "GIF": "image/gif",
            }.get(image_format)
            if media_type is None:
                raise ValueError(f"unsupported image format: {image_format or 'unknown'}")
            assert_image_signature(data, media_type)
            if expected_media_type is not None:
                expected = expected_media_type.lower()
                if expected == "image/jpg":
                    expected = "image/jpeg"
                if media_type != expected:
                    raise ValueError(
                        f"decoded image type {media_type} does not match {expected_media_type}"
                    )
            has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
            return ImageFacts(
                width=image.width,
                height=image.height,
                media_type=media_type,
                format=image_format,
                has_alpha=has_alpha,
            )
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("image data is not decodable") from exc
