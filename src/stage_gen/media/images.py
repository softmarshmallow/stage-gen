"""Pillow-backed deterministic image normalization and alpha composition."""

from __future__ import annotations

import math
from array import array
from dataclasses import asdict, dataclass
from hashlib import sha256
from io import BytesIO
from typing import Any

from PIL import Image, ImageChops, ImageFilter, UnidentifiedImageError
from PIL import __version__ as pillow_version

from gnode import inspect_image

CHROMA_DISTANCE_THRESHOLD = 36
# Distance at or above which a pixel is wholly foreground. Between this and
# CHROMA_DISTANCE_THRESHOLD the matte ramps, so anti-aliased silhouettes keep partial
# coverage instead of being forced opaque.
CHROMA_SOLID_DISTANCE_THRESHOLD = 200
# Radius, in pixels, of the band around the silhouette within which key spill is removed.
# Limiting the correction keeps genuinely key-adjacent interior art unchanged.
CHROMA_DESPILL_RADIUS = 9
# Coverage below which a pixel is treated as key noise rather than signal. Provider backdrops
# are not perfectly uniform, so compression speckle sits just above the keying threshold and
# survives as a few percent of alpha. That is invisible on its own, but downstream isolation
# contracts count any nonzero alpha as content, so a handful of imperceptible specks can fail an
# otherwise clean subject. A genuine anti-aliased edge always carries higher-coverage neighbours,
# so flooring the faintest tail costs nothing visible.
CHROMA_MINIMUM_COVERAGE = 24
CHROMA_MATTE_VERSION = "chroma-soft-key-despill-floor-v3"
MAGENTA_EDGE_BOUNDARY_RADIUS = 32
MAGENTA_EDGE_MINIMUM_RED = 190
MAGENTA_EDGE_MAXIMUM_GREEN = 80
MAGENTA_EDGE_MINIMUM_BLUE = 130
MAGENTA_EDGE_MINIMUM_RED_GREEN_DELTA = 120
MAGENTA_EDGE_MINIMUM_BLUE_GREEN_DELTA = 70
MAGENTA_EDGE_MAXIMUM_RED_BLUE_DELTA = 255
MAGENTA_EDGE_HIGH_ALPHA_THRESHOLD = 224
MAGENTA_EDGE_DECONTAMINATION_VERSION = "rgba-magenta-transparency-boundary-v2"
NATIVE_ALPHA_OPAQUE_THRESHOLD = 250


@dataclass(frozen=True, slots=True)
class AlphaFacts:
    transparent_pixels: int
    nontransparent_pixels: int


@dataclass(frozen=True, slots=True)
class MagentaEdgeDecontaminationFacts:
    width: int
    height: int
    source_hot_magenta_pixels: int
    output_hot_magenta_pixels: int
    removed_pixels: int
    high_alpha_removed_pixels: int
    opaque_removed_pixels: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ImageNormalizationRecord:
    operation: str
    source: dict[str, Any]
    output: dict[str, Any]
    transform: dict[str, Any]
    tool: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_png(
    data: bytes, *, width: int, height: int
) -> tuple[bytes, ImageNormalizationRecord]:
    _positive_dimension(width, "width")
    _positive_dimension(height, "height")
    source = inspect_image(data, expected_media_type="image/png")
    decoded = _decode_image(data)
    resized = decoded.resize((width, height), resample=Image.Resampling.LANCZOS)
    output = _encode_png(resized)
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


def normalize_png_cover(
    data: bytes, *, width: int, height: int
) -> tuple[bytes, ImageNormalizationRecord]:
    """Resize a PNG without distortion, then center-crop it to the exact canvas.

    RGBA inputs are resized in premultiplied-alpha space. That prevents colour from fully
    transparent pixels bleeding into antialiased edges when a provider canvas must be adapted
    to a narrower recipe-owned artifact contract.
    """

    _positive_dimension(width, "width")
    _positive_dimension(height, "height")
    source = inspect_image(data, expected_media_type="image/png")
    decoded = _decode_image(data)
    has_alpha = "A" in decoded.getbands() or "transparency" in decoded.info
    if (source.width, source.height) == (width, height):
        resized_width, resized_height = width, height
        crop_box = (0, 0, width, height)
        normalized = decoded.convert("RGBA" if has_alpha else "RGB")
        operation = "png-reencode"
    else:
        scale = max(width / source.width, height / source.height)
        resized_width = max(width, math.ceil(source.width * scale))
        resized_height = max(height, math.ceil(source.height * scale))
        resize_source = decoded.convert("RGBa" if has_alpha else "RGB")
        resized = resize_source.resize(
            (resized_width, resized_height),
            resample=Image.Resampling.LANCZOS,
        )
        if has_alpha:
            resized = resized.convert("RGBA")
        left = (resized_width - width) // 2
        top = (resized_height - height) // 2
        crop_box = (left, top, left + width, top + height)
        normalized = resized.crop(crop_box)
        operation = "resize-cover"
    promoted_to_opaque_pixels = 0
    if has_alpha:
        normalized = normalized.convert("RGBA")
        alpha = normalized.getchannel("A")
        promoted_to_opaque_pixels = sum(
            NATIVE_ALPHA_OPAQUE_THRESHOLD <= value < 255 for value in alpha.tobytes()
        )
        alpha = alpha.point(lambda value: 255 if value >= NATIVE_ALPHA_OPAQUE_THRESHOLD else value)
        normalized.putalpha(alpha)
    output = _encode_png(normalized)
    result = inspect_image(output, expected_media_type="image/png")
    if (result.width, result.height) != (width, height):
        raise ValueError(
            f"normalization produced {result.width}x{result.height}, expected {width}x{height}"
        )
    record = ImageNormalizationRecord(
        operation=operation,
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
            "fit": "cover",
            "kernel": "lanczos3",
            "resized_width": resized_width,
            "resized_height": resized_height,
            "crop_box": list(crop_box),
            "premultiplied_alpha": has_alpha,
            "near_opaque_threshold": NATIVE_ALPHA_OPAQUE_THRESHOLD if has_alpha else None,
            "promoted_to_opaque_pixels": promoted_to_opaque_pixels,
            "format": "png",
            "compression_level": 9,
        },
        tool={"name": "Pillow", "version": pillow_version},
    )
    return output, record


def normalize_image_to_png(data: bytes) -> tuple[bytes, ImageNormalizationRecord]:
    """Decode a supported provider image and re-encode its exact pixel dimensions as PNG."""

    source = inspect_image(data)
    decoded = _decode_image(data)
    has_alpha = "A" in decoded.getbands() or "transparency" in decoded.info
    color_mode = "RGBA" if has_alpha else "RGB"
    output = _encode_png(decoded.convert(color_mode))
    result = inspect_image(output, expected_media_type="image/png")
    if (result.width, result.height) != (source.width, source.height):
        raise ValueError("image-to-PNG normalization changed pixel dimensions")
    record = ImageNormalizationRecord(
        operation="image-to-png",
        source={
            "width": source.width,
            "height": source.height,
            "bytes": len(data),
            "sha256": sha256(data).hexdigest(),
            "media_type": source.media_type,
        },
        output={
            "width": result.width,
            "height": result.height,
            "bytes": len(output),
            "sha256": sha256(output).hexdigest(),
            "media_type": result.media_type,
        },
        transform={
            "format": "png",
            "color_mode": color_mode,
            "compression_level": 9,
            "metadata": "stripped",
            "pixels_resampled": False,
        },
        tool={"name": "Pillow", "version": pillow_version},
    )
    return output, record


def apply_chroma_transparency(
    data: bytes,
    *,
    threshold: int = CHROMA_DISTANCE_THRESHOLD,
    solid_threshold: int = CHROMA_SOLID_DISTANCE_THRESHOLD,
    despill_radius: int = CHROMA_DESPILL_RADIUS,
    minimum_coverage: int = CHROMA_MINIMUM_COVERAGE,
) -> tuple[bytes, AlphaFacts]:
    """Key the magenta backdrop out with a soft matte and remove its spill.

    Coverage ramps between ``threshold`` and ``solid_threshold`` rather than snapping to fully
    transparent or fully opaque, so anti-aliased silhouettes keep partial alpha. Because the
    source was painted over the key, surviving edge colour is still contaminated by it; the key
    raises red and blue equally above green, so the cast is measurable as ``min(R, B) - G`` and
    is subtracted directly, with no coverage estimate required. The correction is confined to a
    band around the silhouette so interior art that is legitimately pink stays untouched.
    """

    if isinstance(threshold, bool) or not isinstance(threshold, int) or not 0 <= threshold <= 765:
        raise ValueError("chroma threshold must be an integer from 0 to 765")
    if (
        isinstance(solid_threshold, bool)
        or not isinstance(solid_threshold, int)
        or not threshold < solid_threshold <= 765
    ):
        raise ValueError("chroma solid threshold must be an integer above the keying threshold")
    if (
        isinstance(despill_radius, bool)
        or not isinstance(despill_radius, int)
        or despill_radius < 0
    ):
        raise ValueError("chroma despill radius must be a non-negative integer")
    if (
        isinstance(minimum_coverage, bool)
        or not isinstance(minimum_coverage, int)
        or not 0 <= minimum_coverage <= 255
    ):
        raise ValueError("chroma minimum coverage must be an integer from 0 to 255")

    image = _decode_rgba(data)
    red, green, blue, _ = image.split()

    # Manhattan distance from the key colour ranges from 0 to 765. Pillow's ImageChops.add
    # saturates each intermediate result at 255, which makes valid thresholds above 255 lie: a
    # black pixel has distance 510 but would be reported as 255 and could be keyed out. Compute
    # the three-channel sum without saturating so the documented threshold domain is real.
    source_pixels = image.tobytes()
    span = solid_threshold - threshold

    def ramp(value: int) -> int:
        if value <= threshold:
            return 0
        if value >= solid_threshold:
            return 255
        coverage = round((value - threshold) / span * 255)
        return 0 if coverage < minimum_coverage else coverage

    alpha_values = bytearray(len(source_pixels) // 4)
    for pixel_index, offset in enumerate(range(0, len(source_pixels), 4)):
        alpha_values[pixel_index] = ramp(
            (255 - source_pixels[offset])
            + source_pixels[offset + 1]
            + (255 - source_pixels[offset + 2])
        )
    alpha = Image.frombytes("L", image.size, bytes(alpha_values))

    cast = ImageChops.subtract(ImageChops.darker(red, blue), green)
    if despill_radius:
        band = alpha.point(lambda value: 255 if value < 255 else 0).filter(
            ImageFilter.MaxFilter(despill_radius * 2 + 1)
        )
        cast = ImageChops.multiply(cast, band)
    corrected = Image.merge(
        "RGBA",
        (
            ImageChops.subtract(red, cast),
            green,
            ImageChops.subtract(blue, cast),
            alpha,
        ),
    )

    # Fully keyed pixels carry no recoverable colour; pin them so the artifact is byte-stable.
    cleared = Image.new("RGBA", image.size, (255, 0, 255, 0))
    output = Image.composite(corrected, cleared, alpha.point(lambda value: 255 if value else 0))
    facts = _alpha_facts(output.tobytes())
    return _encode_png(output), facts


def decontaminate_magenta_edges(
    data: bytes,
    *,
    boundary_radius: int = MAGENTA_EDGE_BOUNDARY_RADIUS,
    minimum_red: int = MAGENTA_EDGE_MINIMUM_RED,
    maximum_green: int = MAGENTA_EDGE_MAXIMUM_GREEN,
    minimum_blue: int = MAGENTA_EDGE_MINIMUM_BLUE,
    minimum_red_green_delta: int = MAGENTA_EDGE_MINIMUM_RED_GREEN_DELTA,
    minimum_blue_green_delta: int = MAGENTA_EDGE_MINIMUM_BLUE_GREEN_DELTA,
    maximum_red_blue_delta: int = MAGENTA_EDGE_MAXIMUM_RED_BLUE_DELTA,
    transparent_alpha_max: int = 0,
) -> tuple[bytes, MagentaEdgeDecontaminationFacts]:
    """Clear hot-magenta pixels in a band connected to existing transparency.

    The transform preserves every decoded RGBA pixel outside the boundary-and-colour
    intersection. Selected pixels are pinned to transparent black so their contaminating colour
    cannot bleed through later resampling. The boundary uses Chebyshev distance, making the
    radius independent of scan order and inclusive across diagonal anti-aliased edges.
    """

    _nonnegative_integer(boundary_radius, "magenta edge boundary radius")
    _byte_parameter(minimum_red, "magenta edge minimum red")
    _byte_parameter(maximum_green, "magenta edge maximum green")
    _byte_parameter(minimum_blue, "magenta edge minimum blue")
    _byte_parameter(minimum_red_green_delta, "magenta edge minimum red-green delta")
    _byte_parameter(minimum_blue_green_delta, "magenta edge minimum blue-green delta")
    _byte_parameter(maximum_red_blue_delta, "magenta edge maximum red-blue delta")
    if (
        isinstance(transparent_alpha_max, bool)
        or not isinstance(transparent_alpha_max, int)
        or not 0 <= transparent_alpha_max < 255
    ):
        raise ValueError("magenta edge transparent alpha maximum must be an integer below 255")

    decoded = _decode_image(data)
    if "A" not in decoded.getbands() and "transparency" not in decoded.info:
        raise ValueError("magenta edge decontamination requires an alpha-bearing image")
    image = decoded.convert("RGBA")
    width, height = image.size
    pixels = bytearray(image.tobytes())
    alpha = pixels[3::4]
    transparency = _transparency_integral(alpha, width, height, transparent_alpha_max)
    stride = width + 1

    source_hot = removed = high_alpha_removed = opaque_removed = 0
    for y in range(height):
        y0 = max(0, y - boundary_radius)
        y1 = min(height - 1, y + boundary_radius)
        for x in range(width):
            offset = (y * width + x) * 4
            red, green, blue, coverage = pixels[offset : offset + 4]
            if coverage == 0 or not _is_hot_magenta(
                red,
                green,
                blue,
                minimum_red=minimum_red,
                maximum_green=maximum_green,
                minimum_blue=minimum_blue,
                minimum_red_green_delta=minimum_red_green_delta,
                minimum_blue_green_delta=minimum_blue_green_delta,
                maximum_red_blue_delta=maximum_red_blue_delta,
            ):
                continue
            source_hot += 1
            x0 = max(0, x - boundary_radius)
            x1 = min(width - 1, x + boundary_radius)
            if not _integral_rectangle_has_value(
                transparency,
                stride=stride,
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
            ):
                continue
            removed += 1
            if coverage >= MAGENTA_EDGE_HIGH_ALPHA_THRESHOLD:
                high_alpha_removed += 1
            if coverage == 255:
                opaque_removed += 1
            pixels[offset : offset + 4] = bytes((0, 0, 0, 0))

    output = Image.frombytes("RGBA", image.size, bytes(pixels))
    facts = MagentaEdgeDecontaminationFacts(
        width=width,
        height=height,
        source_hot_magenta_pixels=source_hot,
        output_hot_magenta_pixels=source_hot - removed,
        removed_pixels=removed,
        high_alpha_removed_pixels=high_alpha_removed,
        opaque_removed_pixels=opaque_removed,
    )
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
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("animated images are not supported")
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


def _transparency_integral(
    alpha: bytes | bytearray, width: int, height: int, transparent_alpha_max: int
) -> array[int]:
    stride = width + 1
    result = array("I", [0]) * (stride * (height + 1))
    for y in range(height):
        source_row = y * width
        target_row = (y + 1) * stride
        previous_row = y * stride
        row_total = 0
        for x in range(width):
            if alpha[source_row + x] <= transparent_alpha_max:
                row_total += 1
            result[target_row + x + 1] = result[previous_row + x + 1] + row_total
    return result


def _integral_rectangle_has_value(
    integral: array[int], *, stride: int, x0: int, y0: int, x1: int, y1: int
) -> bool:
    top = y0 * stride
    bottom = (y1 + 1) * stride
    total = (
        integral[bottom + x1 + 1]
        - integral[top + x1 + 1]
        - integral[bottom + x0]
        + integral[top + x0]
    )
    return total > 0


def _is_hot_magenta(
    red: int,
    green: int,
    blue: int,
    *,
    minimum_red: int,
    maximum_green: int,
    minimum_blue: int,
    minimum_red_green_delta: int,
    minimum_blue_green_delta: int,
    maximum_red_blue_delta: int,
) -> bool:
    return (
        red >= minimum_red
        and green <= maximum_green
        and blue >= minimum_blue
        and red - green >= minimum_red_green_delta
        and blue - green >= minimum_blue_green_delta
        and abs(red - blue) <= maximum_red_blue_delta
    )


def _byte_parameter(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
        raise ValueError(f"{label} must be an integer from 0 to 255")


def _nonnegative_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")


def _positive_dimension(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
