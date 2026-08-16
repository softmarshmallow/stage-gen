"""Pillow-backed deterministic image normalization and alpha composition."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from io import BytesIO
from typing import Any

from PIL import Image, UnidentifiedImageError
from PIL import __version__ as pillow_version

from .validation import assert_image_signature

CHROMA_DISTANCE_THRESHOLD = 36


@dataclass(frozen=True, slots=True)
class ImageFacts:
    width: int
    height: int
    media_type: str
    format: str
    has_alpha: bool


@dataclass(frozen=True, slots=True)
class AlphaFacts:
    transparent_pixels: int
    nontransparent_pixels: int


@dataclass(frozen=True, slots=True)
class ImageNormalizationRecord:
    operation: str
    source: dict[str, Any]
    output: dict[str, Any]
    transform: dict[str, Any]
    tool: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def normalize_png(
    data: bytes, *, width: int, height: int
) -> tuple[bytes, ImageNormalizationRecord]:
    _positive_dimension(width, "width")
    _positive_dimension(height, "height")
    source = inspect_image(data, expected_media_type="image/png")
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            resized = image.resize((width, height), resample=Image.Resampling.LANCZOS)
            output_io = BytesIO()
            resized.save(output_io, format="PNG", compress_level=9, optimize=False)
            output = output_io.getvalue()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("provider image must be a decodable PNG with dimensions") from exc
    result = inspect_image(output, expected_media_type="image/png")
    if (result.width, result.height) != (width, height):
        raise ValueError(
            f"normalization produced {result.width}x{result.height}, expected {width}x{height}"
        )
    record = ImageNormalizationRecord(
        operation=(
            "png-reencode" if (source.width, source.height) == (width, height) else "resize"
        ),
        source={
            "width": source.width,
            "height": source.height,
            "bytes": len(data),
            "sha256": sha256(data).hexdigest(),
            "media_type": "image/png",
        },
        output={
            "width": width,
            "height": height,
            "bytes": len(output),
            "sha256": sha256(output).hexdigest(),
            "media_type": "image/png",
        },
        transform={
            "fit": "fill",
            "kernel": "lanczos3",
            "format": "png",
            "compression_level": 9,
        },
        tool={"name": "Pillow", "version": pillow_version},
    )
    return output, record


def apply_chroma_transparency(
    data: bytes,
    *,
    threshold: int = CHROMA_DISTANCE_THRESHOLD,
) -> tuple[bytes, AlphaFacts]:
    if not isinstance(threshold, int) or threshold < 0 or threshold > 765:
        raise ValueError("chroma threshold must be an integer from 0 to 765")
    image = _decode_rgba(data)
    pixels = bytearray(image.tobytes())
    for offset in range(0, len(pixels), 4):
        distance = (
            abs(pixels[offset] - 255) + abs(pixels[offset + 1]) + abs(pixels[offset + 2] - 255)
        )
        if distance <= threshold:
            pixels[offset : offset + 4] = bytes((255, 0, 255, 0))
        else:
            pixels[offset + 3] = 255
    facts = _alpha_facts(pixels)
    output = Image.frombytes("RGBA", image.size, bytes(pixels))
    return _encode_png(output), facts


def compose_source_with_alpha(
    source_data: bytes,
    *,
    removed_data: bytes | None = None,
    mask_data: bytes | None = None,
) -> tuple[bytes, AlphaFacts]:
    if removed_data is None and mask_data is None:
        raise ValueError("background removal returned neither a mask nor alpha")
    source = _decode_rgba(source_data)
    if mask_data is not None:
        mask = _decode_image(mask_data).convert("L")
        if mask.size != source.size:
            raise ValueError("background removal mask dimensions changed")
        alpha = mask
    else:
        removed = _decode_image(removed_data or b"")
        if removed.size != source.size:
            raise ValueError("background removal output dimensions changed")
        if "A" not in removed.getbands() and "transparency" not in removed.info:
            raise ValueError("background removal returned neither a mask nor alpha")
        alpha = removed.convert("RGBA").getchannel("A")
    source.putalpha(alpha)
    facts = _alpha_facts(source.tobytes())
    return _encode_png(source), facts


def _decode_image(data: bytes) -> Image.Image:
    if not data:
        raise ValueError("image data must be non-empty")
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            return image.copy()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("image data is not decodable") from exc


def _decode_rgba(data: bytes) -> Image.Image:
    return _decode_image(data).convert("RGBA")


def _encode_png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", compress_level=9, optimize=False)
    data = output.getvalue()
    inspect_image(data, expected_media_type="image/png")
    return data


def _alpha_facts(rgba: bytes | bytearray) -> AlphaFacts:
    if len(rgba) % 4:
        raise ValueError("RGBA buffer size is invalid")
    alpha = rgba[3::4]
    transparent = sum(value < 255 for value in alpha)
    nontransparent = sum(value > 0 for value in alpha)
    if transparent == 0 or nontransparent == 0:
        raise ValueError(
            "transparency output must contain both transparent and nontransparent pixels"
        )
    return AlphaFacts(transparent_pixels=transparent, nontransparent_pixels=nontransparent)


def _positive_dimension(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
