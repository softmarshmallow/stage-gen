"""Deterministic conditioning, bridge extraction, and seam measurement."""

from __future__ import annotations

import math
from dataclasses import dataclass
from io import BytesIO
from typing import cast

from PIL import Image, UnidentifiedImageError

from stage_gen.media import inspect_image

from .models import (
    MAX_LOOP_DIMENSION,
    MAX_LOOP_PIXELS,
    JoinContinuity,
    LoopContinuityMetrics,
    LoopContinuityThresholds,
    LoopSeamValidationError,
)


@dataclass(frozen=True, slots=True)
class PreparedLoopConditioning:
    source_rgba_png: bytes
    left_context_png: bytes
    right_context_png: bytes
    conditioning_png: bytes
    mask_png: bytes
    width: int
    height: int
    conditioning_width: int


@dataclass(frozen=True, slots=True)
class AcceptedLoopCandidate:
    repeat_unit_png: bytes
    bridge_png: bytes
    metrics: LoopContinuityMetrics
    provider_band_changed_pixels: int


@dataclass(frozen=True, slots=True)
class VerifiedLoopArtifact:
    prepared: PreparedLoopConditioning
    bridge_png: bytes
    metrics: LoopContinuityMetrics
    repeat_width: int


def prepare_loop_conditioning(
    source_data: bytes,
    *,
    context_band_px: int,
    bridge_width_px: int,
) -> PreparedLoopConditioning:
    """Place source-end and source-start bands around one editable bridge mask."""

    facts = inspect_image(source_data, expected_media_type="image/png")
    if facts.width < 2 or facts.height < 1:
        raise ValueError("loop source must be at least 2x1 pixels")
    if facts.width > MAX_LOOP_DIMENSION or facts.height > MAX_LOOP_DIMENSION:
        raise ValueError(f"loop source dimensions must not exceed {MAX_LOOP_DIMENSION}px")
    if facts.width * facts.height > MAX_LOOP_PIXELS:
        raise ValueError(f"loop source must not exceed {MAX_LOOP_PIXELS} pixels")
    if context_band_px > facts.width:
        raise ValueError("context_band_px must not exceed the source width")
    if bridge_width_px < 2:
        raise ValueError("bridge_width_px must be at least 2 for gradient validation")
    conditioning_width = context_band_px * 2 + bridge_width_px
    if conditioning_width > MAX_LOOP_DIMENSION:
        raise ValueError(f"conditioning canvas width must not exceed {MAX_LOOP_DIMENSION}px")
    if conditioning_width * facts.height > MAX_LOOP_PIXELS:
        raise ValueError(f"conditioning canvas must not exceed {MAX_LOOP_PIXELS} pixels")

    source = _decode_rgba(source_data)
    left_context = source.crop((facts.width - context_band_px, 0, facts.width, facts.height))
    right_context = source.crop((0, 0, context_band_px, facts.height))
    conditioning = Image.new("RGBA", (conditioning_width, facts.height), (0, 0, 0, 0))
    conditioning.paste(left_context, (0, 0))
    conditioning.paste(right_context, (context_band_px + bridge_width_px, 0))
    mask = Image.new("L", conditioning.size, 0)
    mask.paste(255, (context_band_px, 0, context_band_px + bridge_width_px, facts.height))
    return PreparedLoopConditioning(
        source_rgba_png=_encode_png(source),
        left_context_png=_encode_png(left_context),
        right_context_png=_encode_png(right_context),
        conditioning_png=_encode_png(conditioning),
        mask_png=_encode_png(mask),
        width=facts.width,
        height=facts.height,
        conditioning_width=conditioning_width,
    )


def verify_loop_repeat_unit(
    source_data: bytes,
    repeat_unit_data: bytes,
    *,
    context_band_px: int,
    bridge_width_px: int,
    thresholds: LoopContinuityThresholds,
) -> VerifiedLoopArtifact:
    """Reconstruct and verify a persisted repeat unit without trusting its manifest."""

    prepared = prepare_loop_conditioning(
        source_data,
        context_band_px=context_band_px,
        bridge_width_px=bridge_width_px,
    )
    repeat_facts = inspect_image(repeat_unit_data, expected_media_type="image/png")
    expected_width = prepared.width + bridge_width_px
    if (repeat_facts.width, repeat_facts.height) != (expected_width, prepared.height):
        raise ValueError(
            "loop repeat-unit dimensions mismatch: "
            f"received {repeat_facts.width}x{repeat_facts.height}, "
            f"expected {expected_width}x{prepared.height}"
        )
    source = _decode_rgba(prepared.source_rgba_png)
    repeat_unit = _decode_rgba(repeat_unit_data)
    if repeat_unit.crop((0, 0, prepared.width, prepared.height)).tobytes() != source.tobytes():
        raise ValueError("loop repeat unit does not preserve source pixels")
    bridge = repeat_unit.crop((prepared.width, 0, expected_width, prepared.height))
    metrics = measure_loop_continuity(source, bridge)
    _assert_thresholds(metrics, thresholds)
    return VerifiedLoopArtifact(
        prepared=prepared,
        bridge_png=_encode_png(bridge),
        metrics=metrics,
        repeat_width=expected_width,
    )


def accept_loop_candidate(
    prepared: PreparedLoopConditioning,
    provider_data: bytes,
    *,
    context_band_px: int,
    bridge_width_px: int,
    thresholds: LoopContinuityThresholds,
) -> AcceptedLoopCandidate:
    """Reimpose immutable context, crop the bridge, and reject discontinuous joins."""

    facts = inspect_image(provider_data, expected_media_type="image/png")
    expected_size = (prepared.conditioning_width, prepared.height)
    if (facts.width, facts.height) != expected_size:
        raise ValueError(
            "masked edit output dimensions changed: "
            f"received {facts.width}x{facts.height}, expected {expected_size[0]}x{expected_size[1]}"
        )
    source = _decode_rgba(prepared.source_rgba_png)
    conditioned = _decode_rgba(prepared.conditioning_png)
    edited = _decode_rgba(provider_data)
    left_box = (0, 0, context_band_px, prepared.height)
    right_x = context_band_px + bridge_width_px
    right_box = (right_x, 0, prepared.conditioning_width, prepared.height)
    changed = _changed_pixels(edited.crop(left_box), conditioned.crop(left_box))
    changed += _changed_pixels(edited.crop(right_box), conditioned.crop(right_box))

    # Provider edits outside the mask never become authoritative. Exact context
    # pixels are restored before bridge extraction and acceptance measurement.
    edited.paste(conditioned.crop(left_box), (0, 0))
    edited.paste(conditioned.crop(right_box), (right_x, 0))
    if edited.crop(left_box).tobytes() != conditioned.crop(left_box).tobytes():
        raise ValueError("left immutable context band could not be reimposed")
    if edited.crop(right_box).tobytes() != conditioned.crop(right_box).tobytes():
        raise ValueError("right immutable context band could not be reimposed")

    bridge = edited.crop((context_band_px, 0, context_band_px + bridge_width_px, prepared.height))
    repeat_unit = Image.new(
        "RGBA", (prepared.width + bridge_width_px, prepared.height), (0, 0, 0, 0)
    )
    repeat_unit.paste(source, (0, 0))
    repeat_unit.paste(bridge, (prepared.width, 0))
    metrics = measure_loop_continuity(source, bridge)
    _assert_thresholds(metrics, thresholds)
    return AcceptedLoopCandidate(
        repeat_unit_png=_encode_png(repeat_unit),
        bridge_png=_encode_png(bridge),
        metrics=metrics,
        provider_band_changed_pixels=changed,
    )


def measure_loop_continuity(source: Image.Image, bridge: Image.Image) -> LoopContinuityMetrics:
    """Measure the source→bridge and bridge→source joins without smoothing pixels."""

    source_rgba = source.convert("RGBA")
    bridge_rgba = bridge.convert("RGBA")
    if source_rgba.height != bridge_rgba.height:
        raise ValueError("source and bridge heights must match")
    if source_rgba.width < 2 or bridge_rgba.width < 2:
        raise ValueError("source and bridge must each be at least two pixels wide")
    source_columns = [
        _column(source_rgba, x) for x in (0, 1, source_rgba.width - 2, source_rgba.width - 1)
    ]
    bridge_columns = [
        _column(bridge_rgba, x) for x in (0, 1, bridge_rgba.width - 2, bridge_rgba.width - 1)
    ]
    return LoopContinuityMetrics(
        source_to_bridge=_join_metrics(
            before_previous=source_columns[2],
            before=source_columns[3],
            after=bridge_columns[0],
            after_next=bridge_columns[1],
        ),
        bridge_to_source=_join_metrics(
            before_previous=bridge_columns[2],
            before=bridge_columns[3],
            after=source_columns[0],
            after_next=source_columns[1],
        ),
    )


def _join_metrics(
    *,
    before_previous: tuple[tuple[int, int, int, int], ...],
    before: tuple[tuple[int, int, int, int], ...],
    after: tuple[tuple[int, int, int, int], ...],
    after_next: tuple[tuple[int, int, int, int], ...],
) -> JoinContinuity:
    pixel_rows: list[float] = []
    gradient_rows: list[float] = []
    perceptual_rows: list[float] = []
    for previous_pixel, before_pixel, after_pixel, next_pixel in zip(
        before_previous, before, after, after_next, strict=True
    ):
        previous = _visual_rgba(previous_pixel)
        boundary_before = _visual_rgba(before_pixel)
        boundary_after = _visual_rgba(after_pixel)
        following = _visual_rgba(next_pixel)
        pixel_total = 0.0
        gradient_total = 0.0
        for channel in range(4):
            seam_gradient = boundary_after[channel] - boundary_before[channel]
            neighboring_gradient = (
                (boundary_before[channel] - previous[channel])
                + (following[channel] - boundary_after[channel])
            ) / 2.0
            pixel_total += abs(boundary_after[channel] - boundary_before[channel])
            gradient_total += abs(seam_gradient - neighboring_gradient)
        before_lab = _rgba_to_lab(before_pixel)
        after_lab = _rgba_to_lab(after_pixel)
        delta_e = math.sqrt(
            sum((left - right) ** 2 for left, right in zip(before_lab, after_lab, strict=True))
        )
        alpha_delta = abs(before_pixel[3] - after_pixel[3]) / 2.55
        pixel_rows.append(pixel_total / 4.0)
        gradient_rows.append(gradient_total / 4.0)
        perceptual_rows.append(math.hypot(delta_e, alpha_delta))
    return JoinContinuity(
        pixel_mae=_mean(pixel_rows),
        pixel_p95=_percentile95(pixel_rows),
        pixel_max=_maximum(pixel_rows),
        gradient_mae=_mean(gradient_rows),
        gradient_p95=_percentile95(gradient_rows),
        gradient_max=_maximum(gradient_rows),
        perceptual_delta_e=_mean(perceptual_rows),
        perceptual_delta_e_p95=_percentile95(perceptual_rows),
        perceptual_delta_e_max=_maximum(perceptual_rows),
    )


def _assert_thresholds(
    metrics: LoopContinuityMetrics, thresholds: LoopContinuityThresholds
) -> None:
    failures: list[str] = []
    for label, join in (
        ("source-to-bridge", metrics.source_to_bridge),
        ("bridge-to-source", metrics.bridge_to_source),
    ):
        if join.pixel_mae > thresholds.pixel_mae:
            failures.append(f"{label} pixel MAE {join.pixel_mae:g}>{thresholds.pixel_mae:g}")
        if join.pixel_p95 > thresholds.pixel_p95:
            failures.append(f"{label} pixel p95 {join.pixel_p95:g}>{thresholds.pixel_p95:g}")
        if join.pixel_max > thresholds.pixel_max:
            failures.append(f"{label} pixel max {join.pixel_max:g}>{thresholds.pixel_max:g}")
        if join.gradient_mae > thresholds.gradient_mae:
            failures.append(
                f"{label} gradient MAE {join.gradient_mae:g}>{thresholds.gradient_mae:g}"
            )
        if join.gradient_p95 > thresholds.gradient_p95:
            failures.append(
                f"{label} gradient p95 {join.gradient_p95:g}>{thresholds.gradient_p95:g}"
            )
        if join.gradient_max > thresholds.gradient_max:
            failures.append(
                f"{label} gradient max {join.gradient_max:g}>{thresholds.gradient_max:g}"
            )
        if join.perceptual_delta_e > thresholds.perceptual_delta_e:
            failures.append(
                f"{label} perceptual delta-E "
                f"{join.perceptual_delta_e:g}>{thresholds.perceptual_delta_e:g}"
            )
        if join.perceptual_delta_e_p95 > thresholds.perceptual_delta_e_p95:
            failures.append(
                f"{label} perceptual delta-E p95 "
                f"{join.perceptual_delta_e_p95:g}>{thresholds.perceptual_delta_e_p95:g}"
            )
        if join.perceptual_delta_e_max > thresholds.perceptual_delta_e_max:
            failures.append(
                f"{label} perceptual delta-E max "
                f"{join.perceptual_delta_e_max:g}>{thresholds.perceptual_delta_e_max:g}"
            )
    if failures:
        raise LoopSeamValidationError("loop candidate rejected: " + "; ".join(failures))


def _column(image: Image.Image, x: int) -> tuple[tuple[int, int, int, int], ...]:
    pixels = image.load()
    if pixels is None:
        raise ValueError("image pixel access is unavailable")
    return tuple(cast(tuple[int, int, int, int], pixels[x, y]) for y in range(image.height))


def _mean(values: list[float]) -> float:
    if not values:
        raise ValueError("loop continuity metrics require at least one row")
    return round(sum(values) / len(values), 6)


def _percentile95(values: list[float]) -> float:
    if not values:
        raise ValueError("loop continuity metrics require at least one row")
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return round(ordered[index], 6)


def _maximum(values: list[float]) -> float:
    if not values:
        raise ValueError("loop continuity metrics require at least one row")
    return round(max(values), 6)


def _visual_rgba(pixel: tuple[int, int, int, int]) -> tuple[float, float, float, float]:
    alpha = pixel[3] / 255.0
    return (pixel[0] * alpha, pixel[1] * alpha, pixel[2] * alpha, float(pixel[3]))


def _rgba_to_lab(pixel: tuple[int, int, int, int]) -> tuple[float, float, float]:
    alpha = pixel[3] / 255.0
    # Composite only for measurement, over deterministic middle grey. The
    # actual artifact is never blended, blurred, or modified by this metric.
    srgb = tuple((channel * alpha + 127.5 * (1.0 - alpha)) / 255.0 for channel in pixel[:3])
    linear = tuple(
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in srgb
    )
    red, green, blue = linear
    x = (red * 0.4124564 + green * 0.3575761 + blue * 0.1804375) / 0.95047
    y = red * 0.2126729 + green * 0.7151522 + blue * 0.0721750
    z = (red * 0.0193339 + green * 0.1191920 + blue * 0.9503041) / 1.08883
    fx, fy, fz = (_lab_curve(value) for value in (x, y, z))
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def _lab_curve(value: float) -> float:
    delta = 6.0 / 29.0
    return value ** (1.0 / 3.0) if value > delta**3 else value / (3.0 * delta**2) + 4.0 / 29.0


def _changed_pixels(left: Image.Image, right: Image.Image) -> int:
    left_bytes = left.convert("RGBA").tobytes()
    right_bytes = right.convert("RGBA").tobytes()
    return sum(
        left_bytes[offset : offset + 4] != right_bytes[offset : offset + 4]
        for offset in range(0, len(left_bytes), 4)
    )


def _decode_rgba(data: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            return image.convert("RGBA")
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("image data is not decodable") from error


def _encode_png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", compress_level=9, optimize=False)
    data = output.getvalue()
    inspect_image(data, expected_media_type="image/png")
    return data
