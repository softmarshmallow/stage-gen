"""Axis-normalized conditioning, repeat previews, and deterministic validation."""

from __future__ import annotations

import hashlib
import json
import math
from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Literal, cast

from PIL import Image

from stage_gen.media import inspect_image
from stage_gen.media.codec import decode_rgba, encode_png

from .models import (
    DETERMINISTIC_VALIDATOR_VERSION,
    IMAGE_REPEAT_FAILURE_CODES,
    INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE,
    INTENDED_LOOP_REVIEW_CONTRACT_VERSION,
    INTENDED_LOOP_REVIEW_PROMPT_VERSION,
    MAX_IMAGE_REPEAT_DIMENSION,
    MAX_IMAGE_REPEAT_PIXELS,
    THREE_REPEAT_PREVIEW_VERSION,
    ImageRepeatAlphaPolicy,
    ImageRepeatAxis,
    ImageRepeatCoveragePolicy,
    ImageRepeatDeterministicReport,
    ImageRepeatDeterministicValidationError,
    ImageRepeatFailureCode,
    ImageRepeatJoinReport,
    ImageRepeatManifest,
    ImageRepeatRepairConstruction,
    ImageRepeatRepairLineage,
    ImageRepeatScaleMetrics,
    ImageRepeatStitch,
    ImageRepeatValidationPolicy,
)

_PREVIEW_REPEAT_COUNT = 3
_PREVIEW_CHECKER_TARGET_TILE_PX = 32
_PREVIEW_CHECKER_MAX_PRIMARY_TILES = 64
_PREVIEW_CHECKER_LIGHT: _Rgba = (224, 224, 224, 255)
_PREVIEW_CHECKER_DARK: _Rgba = (192, 192, 192, 255)
_MAX_BASELINE_PRIMARY_SAMPLES = 32
_MAX_CROSS_AXIS_SAMPLES = 2048
_ENDPOINT_ANCHOR_MAX_SPAN_PX = 8
_INTEGER_WEIGHT_SCALE = 65_535
_LINEAR_CHANNEL_SCALE = 65_535

type _Rgba = tuple[int, int, int, int]
type _JoinName = Literal["wrap", "stitch", "source_to_repair", "repair_to_source"]

_SRGB_TO_LINEAR_U16 = tuple(
    int(
        (
            channel / 255.0 / 12.92
            if channel / 255.0 <= 0.04045
            else ((channel / 255.0 + 0.055) / 1.055) ** 2.4
        )
        * _LINEAR_CHANNEL_SCALE
        + 0.5
    )
    for channel in range(256)
)


@dataclass(frozen=True, slots=True)
class PreparedImageRepeatConditioning:
    source_rgba_png: bytes
    head_context_png: bytes
    tail_context_png: bytes
    conditioning_png: bytes
    mask_png: bytes
    axis: ImageRepeatAxis
    source_width: int
    source_height: int
    conditioning_width: int
    conditioning_height: int


@dataclass(frozen=True, slots=True)
class AcceptedImageRepeatCandidate:
    repeat_unit_png: bytes
    repair_png: bytes
    raw_repair_png: bytes
    alpha_reconstructed_repair_png: bytes
    provider_interior_png: bytes
    endpoint_anchor_span_px: int
    alpha_reconstructed_changed_pixels: int
    anchored_repair_changed_pixels: int
    deterministic_report: ImageRepeatDeterministicReport
    provider_context_changed_pixels: int


@dataclass(frozen=True, slots=True)
class VerifiedImageRepeatArtifact:
    deterministic_report: ImageRepeatDeterministicReport
    preview_png: bytes
    repair_png: bytes | None
    repair_conditioning: PreparedImageRepeatConditioning | None = None
    raw_repair_png: bytes | None = None
    alpha_reconstructed_repair_png: bytes | None = None
    provider_interior_png: bytes | None = None
    endpoint_anchor_span_px: int | None = None
    alpha_reconstructed_changed_pixels: int | None = None
    anchored_repair_changed_pixels: int | None = None


@dataclass(frozen=True, slots=True)
class _EndpointAnchoredRepair:
    repair: Image.Image
    provider_interior: Image.Image
    span_px: int
    changed_pixels: int


@dataclass(frozen=True, slots=True)
class _AlphaReconstructedRepair:
    repair: Image.Image
    changed_pixels: int


def canonical_intended_loop_criteria(
    *,
    axis: ImageRepeatAxis,
    intended_behavior: str,
    alpha_policy: ImageRepeatAlphaPolicy,
    coverage_policy: ImageRepeatCoveragePolicy,
    validation_policy: ImageRepeatValidationPolicy,
) -> bytes:
    """Canonical digest-bound rubric inputs shared by producer and verifier."""

    payload = {
        "contract_version": INTENDED_LOOP_REVIEW_CONTRACT_VERSION,
        "prompt_version": INTENDED_LOOP_REVIEW_PROMPT_VERSION,
        "deterministic_validator_version": DETERMINISTIC_VALIDATOR_VERSION,
        "preview_version": THREE_REPEAT_PREVIEW_VERSION,
        "preview_repeat_count": 3,
        "axis": axis,
        "intended_behavior": intended_behavior,
        "alpha_policy": alpha_policy,
        "coverage_policy": coverage_policy,
        "validation_policy": asdict(validation_policy),
        "allowed_failure_codes": list(IMAGE_REPEAT_FAILURE_CODES),
        "minimum_accept_confidence": INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE,
        "below_threshold_policy": "fail_closed",
        "uncertainty_policy": "fail_closed",
        "other_axis_status": "not_evaluated",
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def verify_image_repeat_artifact(
    source_data: bytes,
    repeat_unit_data: bytes,
    manifest: ImageRepeatManifest,
    *,
    provider_candidate_data: bytes | None = None,
) -> VerifiedImageRepeatArtifact:
    """Recompute a persisted v2 repeat without trusting its signed claims."""

    source_facts = inspect_image(source_data, expected_media_type="image/png")
    repeat_facts = inspect_image(repeat_unit_data, expected_media_type="image/png")
    if (
        manifest.source.sha256 != hashlib.sha256(source_data).hexdigest()
        or manifest.source.bytes != len(source_data)
        or (manifest.source.width, manifest.source.height)
        != (source_facts.width, source_facts.height)
    ):
        raise ValueError("image-repeat source binding does not match decoded bytes")
    if (
        manifest.repeat_unit.sha256 != hashlib.sha256(repeat_unit_data).hexdigest()
        or manifest.repeat_unit.bytes != len(repeat_unit_data)
        or (manifest.repeat_unit.width, manifest.repeat_unit.height)
        != (repeat_facts.width, repeat_facts.height)
    ):
        raise ValueError("image-repeat repeat-unit binding does not match decoded bytes")

    repair_png: bytes | None = None
    repair_conditioning: PreparedImageRepeatConditioning | None = None
    raw_repair_png: bytes | None = None
    alpha_reconstructed_repair_png: bytes | None = None
    provider_interior_png: bytes | None = None
    endpoint_anchor_span_px: int | None = None
    alpha_reconstructed_changed_pixels: int | None = None
    anchored_repair_changed_pixels: int | None = None
    if manifest.decision == "admitted":
        if provider_candidate_data is not None:
            raise ValueError("admitted image-repeat must not bind a provider repair candidate")
        if source_data != repeat_unit_data:
            raise ValueError("admitted image-repeat bytes are not an exact pass-through")
        report = validate_image_repeat(
            repeat_unit_data,
            axis=manifest.axis,
            alpha_policy=manifest.intent.alpha_policy,
            coverage_policy=manifest.intent.coverage_policy,
            validation_policy=manifest.validation.policy,
        )
    else:
        if provider_candidate_data is None:
            raise ValueError("repaired image-repeat requires its exact provider candidate")
        construction = manifest.construction
        if not isinstance(construction, ImageRepeatRepairConstruction):
            raise ValueError("repaired image-repeat is missing repair construction")
        provider_facts = inspect_image(
            provider_candidate_data,
            expected_media_type="image/png",
        )
        provider_binding = construction.provider_candidate
        if (
            provider_binding.sha256 != hashlib.sha256(provider_candidate_data).hexdigest()
            or provider_binding.bytes != len(provider_candidate_data)
            or (provider_binding.width, provider_binding.height)
            != (provider_facts.width, provider_facts.height)
        ):
            raise ValueError("provider repair candidate binding does not match decoded bytes")
        source = _decode_rgba(source_data)
        repeat = _decode_rgba(repeat_unit_data)
        if _source_region(repeat, manifest.axis, source.size).tobytes() != source.tobytes():
            raise ValueError("repaired image-repeat does not preserve exact source pixels")
        if manifest.axis == "x":
            repair = repeat.crop((source.width, 0, repeat.width, repeat.height))
        else:
            repair = repeat.crop((0, source.height, repeat.width, repeat.height))
        if _primary_extent(repair, manifest.axis) != construction.repair_span_px:
            raise ValueError("repaired image-repeat span does not match construction")
        repair_conditioning = prepare_repair_conditioning(
            source_data,
            axis=manifest.axis,
            context_span_px=construction.context_span_px,
            repair_span_px=construction.repair_span_px,
        )
        raw_repair, _provider_context_changed_pixels = _constrain_provider_repair(
            repair_conditioning,
            provider_candidate_data,
            context_span_px=construction.context_span_px,
            repair_span_px=construction.repair_span_px,
        )
        alpha_reconstructed = _reconstruct_repair_alpha(
            source,
            raw_repair,
            axis=manifest.axis,
        )
        anchored = _anchor_repair_endpoints(
            source,
            alpha_reconstructed.repair,
            raw_repair=raw_repair,
            axis=manifest.axis,
        )
        if anchored.span_px != construction.endpoint_anchor_span_px:
            raise ValueError("derived endpoint anchor span does not match construction")
        reconstructed_repeat = _append_along_axis(source, anchored.repair, manifest.axis)
        if reconstructed_repeat.tobytes() != repeat.tobytes():
            raise ValueError("repaired image-repeat does not match its anchored provider candidate")
        if anchored.repair.tobytes() != repair.tobytes():
            raise ValueError("repaired image-repeat bridge reconstruction mismatch")
        report = validate_repaired_segments(
            source,
            repair,
            axis=manifest.axis,
            alpha_policy=manifest.intent.alpha_policy,
            coverage_policy=manifest.intent.coverage_policy,
            validation_policy=manifest.validation.policy,
            source_immutable=True,
        )
        repair_png = _encode_png(repair)
        raw_repair_png = _encode_png(raw_repair)
        alpha_reconstructed_repair_png = _encode_png(alpha_reconstructed.repair)
        provider_interior_png = _encode_png(anchored.provider_interior)
        endpoint_anchor_span_px = anchored.span_px
        alpha_reconstructed_changed_pixels = alpha_reconstructed.changed_pixels
        anchored_repair_changed_pixels = anchored.changed_pixels
        expected_lineage = ImageRepeatRepairLineage(
            source_sha256=hashlib.sha256(source_data).hexdigest(),
            head_context_sha256=hashlib.sha256(repair_conditioning.head_context_png).hexdigest(),
            tail_context_sha256=hashlib.sha256(repair_conditioning.tail_context_png).hexdigest(),
            conditioning_sha256=hashlib.sha256(repair_conditioning.conditioning_png).hexdigest(),
            mask_sha256=hashlib.sha256(repair_conditioning.mask_png).hexdigest(),
            provider_candidate_sha256=hashlib.sha256(provider_candidate_data).hexdigest(),
            raw_repair_sha256=hashlib.sha256(raw_repair_png).hexdigest(),
            alpha_reconstructed_repair_sha256=hashlib.sha256(
                alpha_reconstructed_repair_png
            ).hexdigest(),
            provider_interior_sha256=hashlib.sha256(provider_interior_png).hexdigest(),
            repair_sha256=hashlib.sha256(repair_png).hexdigest(),
            repeat_unit_sha256=hashlib.sha256(repeat_unit_data).hexdigest(),
        )
        if manifest.lineage != expected_lineage:
            raise ValueError("repaired image-repeat lineage does not match reconstructed media")

    if report != manifest.validation.deterministic or report.verdict != "pass":
        raise ValueError("image-repeat deterministic report does not match decoded media")
    preview = build_three_repeat_preview(repeat_unit_data, axis=manifest.axis)
    if hashlib.sha256(preview).hexdigest() != manifest.validation.intended_loop.preview_sha256:
        raise ValueError("image-repeat semantic review does not bind the exact preview")
    criteria = canonical_intended_loop_criteria(
        axis=manifest.axis,
        intended_behavior=manifest.intent.intended_behavior,
        alpha_policy=manifest.intent.alpha_policy,
        coverage_policy=manifest.intent.coverage_policy,
        validation_policy=manifest.validation.policy,
    )
    criteria_sha256 = hashlib.sha256(criteria).hexdigest()
    if (
        criteria_sha256 != manifest.intent.criteria_sha256
        or criteria_sha256 != manifest.validation.intended_loop.criteria_sha256
    ):
        raise ValueError("image-repeat criteria digest is not reproducible")
    return VerifiedImageRepeatArtifact(
        deterministic_report=report,
        preview_png=preview,
        repair_png=repair_png,
        repair_conditioning=repair_conditioning,
        raw_repair_png=raw_repair_png,
        alpha_reconstructed_repair_png=alpha_reconstructed_repair_png,
        provider_interior_png=provider_interior_png,
        endpoint_anchor_span_px=endpoint_anchor_span_px,
        alpha_reconstructed_changed_pixels=alpha_reconstructed_changed_pixels,
        anchored_repair_changed_pixels=anchored_repair_changed_pixels,
    )


def prepare_repair_conditioning(
    source_data: bytes,
    *,
    axis: ImageRepeatAxis,
    context_span_px: int,
    repair_span_px: int,
) -> PreparedImageRepeatConditioning:
    """Place tail and head context around one editable span without rotating content."""

    facts = inspect_image(source_data, expected_media_type="image/png")
    _validate_dimensions(facts.width, facts.height, "image-repeat source")
    source_primary = facts.width if axis == "x" else facts.height
    if source_primary < 2:
        raise ValueError("image-repeat source must span at least two pixels on its repeat axis")
    if context_span_px > source_primary:
        raise ValueError("context_span_px must not exceed the source repeat-axis extent")
    if repair_span_px < 4:
        raise ValueError("repair_span_px must be at least four pixels for endpoint anchoring")

    conditioning_primary = context_span_px * 2 + repair_span_px
    conditioning_width = conditioning_primary if axis == "x" else facts.width
    conditioning_height = facts.height if axis == "x" else conditioning_primary
    _validate_dimensions(
        conditioning_width,
        conditioning_height,
        "image-repeat conditioning canvas",
    )

    output_primary = source_primary + repair_span_px
    output_width = output_primary if axis == "x" else facts.width
    output_height = facts.height if axis == "x" else output_primary
    _validate_dimensions(output_width, output_height, "image-repeat repaired output")

    source = _decode_rgba(source_data)
    head = _head_context(source, axis, context_span_px)
    tail = _tail_context(source, axis, context_span_px)
    conditioning = Image.new(
        "RGBA",
        (conditioning_width, conditioning_height),
        (0, 0, 0, 0),
    )
    mask = Image.new("L", conditioning.size, 0)
    if axis == "x":
        conditioning.paste(tail, (0, 0))
        conditioning.paste(head, (context_span_px + repair_span_px, 0))
        mask.paste(255, (context_span_px, 0, context_span_px + repair_span_px, facts.height))
    else:
        conditioning.paste(tail, (0, 0))
        conditioning.paste(head, (0, context_span_px + repair_span_px))
        mask.paste(255, (0, context_span_px, facts.width, context_span_px + repair_span_px))
    return PreparedImageRepeatConditioning(
        source_rgba_png=_encode_png(source),
        head_context_png=_encode_png(head),
        tail_context_png=_encode_png(tail),
        conditioning_png=_encode_png(conditioning),
        mask_png=_encode_png(mask),
        axis=axis,
        source_width=facts.width,
        source_height=facts.height,
        conditioning_width=conditioning_width,
        conditioning_height=conditioning_height,
    )


def accept_repair_candidate(
    prepared: PreparedImageRepeatConditioning,
    provider_data: bytes,
    *,
    context_span_px: int,
    repair_span_px: int,
    alpha_policy: ImageRepeatAlphaPolicy,
    coverage_policy: ImageRepeatCoveragePolicy,
    validation_policy: ImageRepeatValidationPolicy,
) -> AcceptedImageRepeatCandidate:
    """Constrain raw provider pixels, anchor endpoints, and require both final joins to pass."""

    source = _decode_rgba(prepared.source_rgba_png)
    raw_repair, changed = _constrain_provider_repair(
        prepared,
        provider_data,
        context_span_px=context_span_px,
        repair_span_px=repair_span_px,
    )
    alpha_reconstructed = _reconstruct_repair_alpha(
        source,
        raw_repair,
        axis=prepared.axis,
    )
    anchored = _anchor_repair_endpoints(
        source,
        alpha_reconstructed.repair,
        raw_repair=raw_repair,
        axis=prepared.axis,
    )
    repeat_unit = _append_along_axis(source, anchored.repair, prepared.axis)
    if _source_region(repeat_unit, prepared.axis, source.size).tobytes() != source.tobytes():
        raise ValueError("image-repeat repair did not preserve source pixels exactly")
    report = validate_repaired_segments(
        source,
        anchored.repair,
        axis=prepared.axis,
        alpha_policy=alpha_policy,
        coverage_policy=coverage_policy,
        validation_policy=validation_policy,
        source_immutable=True,
    )
    if report.verdict != "pass":
        raise ImageRepeatDeterministicValidationError(report)
    return AcceptedImageRepeatCandidate(
        repeat_unit_png=_encode_png(repeat_unit),
        repair_png=_encode_png(anchored.repair),
        raw_repair_png=_encode_png(raw_repair),
        alpha_reconstructed_repair_png=_encode_png(alpha_reconstructed.repair),
        provider_interior_png=_encode_png(anchored.provider_interior),
        endpoint_anchor_span_px=anchored.span_px,
        alpha_reconstructed_changed_pixels=alpha_reconstructed.changed_pixels,
        anchored_repair_changed_pixels=anchored.changed_pixels,
        deterministic_report=report,
        provider_context_changed_pixels=changed,
    )


def _constrain_provider_repair(
    prepared: PreparedImageRepeatConditioning,
    provider_data: bytes,
    *,
    context_span_px: int,
    repair_span_px: int,
) -> tuple[Image.Image, int]:
    if repair_span_px < 4:
        raise ValueError("repair_span_px must be at least four pixels for endpoint anchoring")
    expected_primary = context_span_px * 2 + repair_span_px
    prepared_primary = (
        prepared.conditioning_width if prepared.axis == "x" else prepared.conditioning_height
    )
    if prepared_primary != expected_primary:
        raise ValueError("prepared image-repeat conditioning geometry is inconsistent")
    facts = inspect_image(provider_data, expected_media_type="image/png")
    expected_size = (prepared.conditioning_width, prepared.conditioning_height)
    if (facts.width, facts.height) != expected_size:
        raise ValueError(
            "conditioned repair output dimensions changed: "
            f"received {facts.width}x{facts.height}, expected {expected_size[0]}x{expected_size[1]}"
        )
    conditioned = _decode_rgba(prepared.conditioning_png)
    edited = _decode_rgba(provider_data)
    leading_box, repair_box, trailing_box = _conditioning_boxes(
        prepared,
        context_span_px=context_span_px,
        repair_span_px=repair_span_px,
    )
    leading = conditioned.crop(leading_box)
    trailing = conditioned.crop(trailing_box)
    changed = _changed_pixels(edited.crop(leading_box), leading)
    changed += _changed_pixels(edited.crop(trailing_box), trailing)
    edited.paste(leading, (leading_box[0], leading_box[1]))
    edited.paste(trailing, (trailing_box[0], trailing_box[1]))
    if edited.crop(leading_box).tobytes() != leading.tobytes():
        raise ValueError("leading immutable context could not be reimposed")
    if edited.crop(trailing_box).tobytes() != trailing.tobytes():
        raise ValueError("trailing immutable context could not be reimposed")
    repair = edited.crop(repair_box)
    if _primary_extent(repair, prepared.axis) != repair_span_px:
        raise ValueError("constrained provider repair span changed")
    return repair, changed


def _reconstruct_repair_alpha(
    source: Image.Image,
    raw_repair: Image.Image,
    *,
    axis: ImageRepeatAxis,
) -> _AlphaReconstructedRepair:
    """Replace provider alpha with the smoothstep between exact source edge profiles.

    The provider continues to own visible RGB. Fully transparent, non-endpoint pixels are
    canonicalized so hidden provider RGB cannot affect evidence or later resampling.
    """

    source_rgba = source.convert("RGBA")
    raw_rgba = raw_repair.convert("RGBA")
    _assert_cross_extent(source_rgba, raw_rgba, axis)
    repair_span_px = _primary_extent(raw_rgba, axis)
    if repair_span_px < 4:
        raise ValueError("repair span must be at least four pixels for alpha reconstruction")

    tail = _edge_line(source_rgba, axis, -1)
    head = _edge_line(source_rgba, axis, 0)
    if len(tail) != len(head):
        raise ValueError("source endpoint cross-axis extents do not match")
    reconstructed = raw_rgba.copy()
    final_position = repair_span_px - 1
    for primary in range(repair_span_px):
        head_weight = _integer_smoothstep_weight(primary, final_position)
        tail_weight = _INTEGER_WEIGHT_SCALE - head_weight
        for cross, (tail_pixel, head_pixel) in enumerate(zip(tail, head, strict=True)):
            alpha = _round_div(
                tail_pixel[3] * tail_weight + head_pixel[3] * head_weight,
                _INTEGER_WEIGHT_SCALE,
            )
            provider_pixel = _primary_pixel(raw_rgba, axis, primary, cross)
            pixel = (
                (provider_pixel[0], provider_pixel[1], provider_pixel[2], alpha)
                if alpha > 0
                else (0, 0, 0, 0)
            )
            _put_primary_pixel(reconstructed, axis, primary, cross, pixel)

    if tuple(pixel[3] for pixel in _edge_line(reconstructed, axis, 0)) != tuple(
        pixel[3] for pixel in tail
    ):
        raise ValueError("leading reconstructed alpha does not match the source tail")
    if tuple(pixel[3] for pixel in _edge_line(reconstructed, axis, -1)) != tuple(
        pixel[3] for pixel in head
    ):
        raise ValueError("trailing reconstructed alpha does not match the source head")
    _assert_visible_provider_rgb(raw_rgba, reconstructed, axis=axis)
    return _AlphaReconstructedRepair(
        repair=reconstructed,
        changed_pixels=_changed_pixels(raw_rgba, reconstructed),
    )


def _anchor_repair_endpoints(
    source: Image.Image,
    alpha_reconstructed_repair: Image.Image,
    *,
    raw_repair: Image.Image,
    axis: ImageRepeatAxis,
) -> _EndpointAnchoredRepair:
    """Anchor endpoint RGB while preserving the deterministic alpha topology."""

    source_rgba = source.convert("RGBA")
    raw_rgba = raw_repair.convert("RGBA")
    reconstructed_rgba = alpha_reconstructed_repair.convert("RGBA")
    _assert_cross_extent(source_rgba, raw_rgba, axis)
    _assert_cross_extent(source_rgba, reconstructed_rgba, axis)
    if raw_rgba.size != reconstructed_rgba.size:
        raise ValueError("raw and alpha-reconstructed repair geometry must match")
    _assert_visible_provider_rgb(raw_rgba, reconstructed_rgba, axis=axis)
    repair_span_px = _primary_extent(reconstructed_rgba, axis)
    if repair_span_px < 4:
        raise ValueError("repair span must be at least four pixels for endpoint anchoring")
    span_px = min(_ENDPOINT_ANCHOR_MAX_SPAN_PX, repair_span_px // 4)
    if span_px < 1 or repair_span_px - span_px * 2 < 2:
        raise ValueError("repair span cannot preserve a provider-owned interior")

    tail = _edge_line(source_rgba, axis, -1)
    head = _edge_line(source_rgba, axis, 0)
    anchored = reconstructed_rgba.copy()
    cross_extent = len(tail)
    if len(head) != cross_extent:
        raise ValueError("source endpoint cross-axis extents do not match")

    for offset in range(span_px):
        leading_primary = offset
        trailing_primary = repair_span_px - span_px + offset
        if span_px == 1:
            leading_weight = 0
            trailing_weight = _INTEGER_WEIGHT_SCALE
        else:
            leading_weight = _integer_smoothstep_weight(offset, span_px - 1)
            trailing_weight = leading_weight
        for cross in range(cross_extent):
            leading_provider = _primary_pixel(
                reconstructed_rgba,
                axis,
                leading_primary,
                cross,
            )
            trailing_provider = _primary_pixel(
                reconstructed_rgba,
                axis,
                trailing_primary,
                cross,
            )
            leading_endpoint = (*tail[cross][:3], leading_provider[3])
            trailing_endpoint = (*head[cross][:3], trailing_provider[3])
            _put_primary_pixel(
                anchored,
                axis,
                leading_primary,
                cross,
                _blend_linear_premultiplied_rgba(
                    leading_endpoint,
                    leading_provider,
                    leading_weight,
                ),
            )
            _put_primary_pixel(
                anchored,
                axis,
                trailing_primary,
                cross,
                _blend_linear_premultiplied_rgba(
                    trailing_provider,
                    trailing_endpoint,
                    trailing_weight,
                ),
            )

    if _edge_line(anchored, axis, 0) != tail:
        raise ValueError("leading endpoint anchor is not an exact source-tail copy")
    if _edge_line(anchored, axis, -1) != head:
        raise ValueError("trailing endpoint anchor is not an exact source-head copy")
    provider_interior = _primary_crop(
        reconstructed_rgba,
        axis,
        span_px,
        repair_span_px - span_px,
    )
    anchored_interior = _primary_crop(
        anchored,
        axis,
        span_px,
        repair_span_px - span_px,
    )
    if anchored_interior.tobytes() != provider_interior.tobytes():
        raise ValueError("endpoint anchoring changed the provider-owned interior")
    _assert_alpha_topology_preserved(reconstructed_rgba, anchored, axis=axis)
    _assert_visible_provider_rgb(
        _primary_crop(raw_rgba, axis, span_px, repair_span_px - span_px),
        provider_interior,
        axis=axis,
    )
    return _EndpointAnchoredRepair(
        repair=anchored,
        provider_interior=provider_interior,
        span_px=span_px,
        changed_pixels=_changed_pixels(reconstructed_rgba, anchored),
    )


def _assert_alpha_topology_preserved(
    before: Image.Image,
    after: Image.Image,
    *,
    axis: ImageRepeatAxis,
) -> None:
    if before.size != after.size:
        raise ValueError("alpha topology comparison geometry changed")
    primary_extent = _primary_extent(before, axis)
    cross_extent = before.height if axis == "x" else before.width
    for primary in range(primary_extent):
        for cross in range(cross_extent):
            if (
                _primary_pixel(before, axis, primary, cross)[3]
                != _primary_pixel(
                    after,
                    axis,
                    primary,
                    cross,
                )[3]
            ):
                raise ValueError("endpoint anchoring changed reconstructed alpha topology")


def _assert_visible_provider_rgb(
    provider: Image.Image,
    reconstructed: Image.Image,
    *,
    axis: ImageRepeatAxis,
) -> None:
    if provider.size != reconstructed.size:
        raise ValueError("provider RGB comparison geometry changed")
    primary_extent = _primary_extent(provider, axis)
    cross_extent = provider.height if axis == "x" else provider.width
    for primary in range(primary_extent):
        for cross in range(cross_extent):
            provider_pixel = _primary_pixel(provider, axis, primary, cross)
            reconstructed_pixel = _primary_pixel(reconstructed, axis, primary, cross)
            if reconstructed_pixel[3] > 0:
                if reconstructed_pixel[:3] != provider_pixel[:3]:
                    raise ValueError("alpha reconstruction changed visible provider RGB")
            elif reconstructed_pixel[:3] != (0, 0, 0):
                raise ValueError("alpha reconstruction retained hidden provider RGB")


def _integer_smoothstep_weight(position: int, final_position: int) -> int:
    if final_position < 1 or not 0 <= position <= final_position:
        raise ValueError("integer smoothstep position is invalid")
    denominator = final_position**3
    numerator = position * position * (3 * final_position - 2 * position)
    return _round_div(numerator * _INTEGER_WEIGHT_SCALE, denominator)


def _blend_linear_premultiplied_rgba(
    left: _Rgba,
    right: _Rgba,
    right_weight: int,
) -> _Rgba:
    if not 0 <= right_weight <= _INTEGER_WEIGHT_SCALE:
        raise ValueError("premultiplied blend weight is out of range")
    if right_weight == 0:
        return left
    if right_weight == _INTEGER_WEIGHT_SCALE:
        return right
    left_weight = _INTEGER_WEIGHT_SCALE - right_weight
    alpha_numerator = left[3] * left_weight + right[3] * right_weight
    alpha = _round_div(alpha_numerator, _INTEGER_WEIGHT_SCALE)
    if alpha == 0:
        return (0, 0, 0, 0)
    channels: list[int] = []
    for index in range(3):
        premultiplied_numerator = (
            _SRGB_TO_LINEAR_U16[left[index]] * left[3] * left_weight
            + _SRGB_TO_LINEAR_U16[right[index]] * right[3] * right_weight
        )
        linear = _round_div(premultiplied_numerator, alpha_numerator)
        channels.append(_linear_u16_to_srgb(linear))
    return (channels[0], channels[1], channels[2], alpha)


def _linear_u16_to_srgb(value: int) -> int:
    bounded = min(_LINEAR_CHANNEL_SCALE, max(0, value))
    index = bisect_left(_SRGB_TO_LINEAR_U16, bounded)
    if index <= 0:
        return 0
    if index >= len(_SRGB_TO_LINEAR_U16):
        return 255
    lower = _SRGB_TO_LINEAR_U16[index - 1]
    upper = _SRGB_TO_LINEAR_U16[index]
    return index - 1 if bounded - lower <= upper - bounded else index


def _round_div(numerator: int, denominator: int) -> int:
    if numerator < 0 or denominator <= 0:
        raise ValueError("rounded integer division requires non-negative values")
    return (numerator + denominator // 2) // denominator


def _primary_pixel(
    image: Image.Image,
    axis: ImageRepeatAxis,
    primary: int,
    cross: int,
) -> _Rgba:
    coordinates = (primary, cross) if axis == "x" else (cross, primary)
    return cast(_Rgba, image.getpixel(coordinates))


def _put_primary_pixel(
    image: Image.Image,
    axis: ImageRepeatAxis,
    primary: int,
    cross: int,
    value: _Rgba,
) -> None:
    coordinates = (primary, cross) if axis == "x" else (cross, primary)
    image.putpixel(coordinates, value)


def _primary_crop(
    image: Image.Image,
    axis: ImageRepeatAxis,
    start: int,
    end: int,
) -> Image.Image:
    box = (start, 0, end, image.height) if axis == "x" else (0, start, image.width, end)
    return image.crop(box)


def validate_image_repeat(
    repeat_unit_data: bytes,
    *,
    axis: ImageRepeatAxis,
    alpha_policy: ImageRepeatAlphaPolicy,
    coverage_policy: ImageRepeatCoveragePolicy,
    validation_policy: ImageRepeatValidationPolicy,
    stitches: Sequence[ImageRepeatStitch] = (),
) -> ImageRepeatDeterministicReport:
    """Evaluate the declared-axis wrap, and every stitch a construction cut into the unit.

    The other axis is intentionally ignored. A construction that writes provider pixels into the
    source leaves joins inside the unit as well as at its wrap, and a verdict that measured only
    the wrap would pass whatever those inner joins look like.
    """

    facts = inspect_image(repeat_unit_data, expected_media_type="image/png")
    _validate_dimensions(facts.width, facts.height, "image-repeat candidate")
    primary = facts.width if axis == "x" else facts.height
    if primary < 2:
        raise ValueError("image-repeat candidate must span at least two pixels on its repeat axis")
    if len(stitches) > 2:
        raise ValueError("image-repeat validation measures at most two stitches")
    image = _decode_rgba(repeat_unit_data)
    join = _join_report(
        image,
        image,
        axis=axis,
        name="wrap",
        coverage_policy=coverage_policy,
        policy=validation_policy,
    )
    joins = [join]
    joins.extend(
        _join_report(
            image,
            image,
            axis=axis,
            name="stitch",
            coverage_policy=coverage_policy,
            policy=validation_policy,
            stitch=stitch,
        )
        for stitch in stitches
    )
    if alpha_policy == "require_opaque" and _has_nonopaque_pixels(image):
        joins[0] = _add_join_failure(join, "alpha_halo_or_matte_contamination")
    return _deterministic_report(
        axis=axis,
        alpha_policy=alpha_policy,
        coverage_policy=coverage_policy,
        source_immutable=True,
        joins=joins,
    )


def validate_repaired_segments(
    source: Image.Image,
    repair: Image.Image,
    *,
    axis: ImageRepeatAxis,
    alpha_policy: ImageRepeatAlphaPolicy,
    coverage_policy: ImageRepeatCoveragePolicy,
    validation_policy: ImageRepeatValidationPolicy,
    source_immutable: bool,
) -> ImageRepeatDeterministicReport:
    """Evaluate source-to-repair and repair-to-source as separate joins."""

    _assert_cross_extent(source, repair, axis)
    joins = [
        _join_report(
            source,
            repair,
            axis=axis,
            name="source_to_repair",
            coverage_policy=coverage_policy,
            policy=validation_policy,
        ),
        _join_report(
            repair,
            source,
            axis=axis,
            name="repair_to_source",
            coverage_policy=coverage_policy,
            policy=validation_policy,
        ),
    ]
    repeat_unit = _append_along_axis(source, repair, axis)
    if alpha_policy == "require_opaque" and _has_nonopaque_pixels(repeat_unit):
        joins[0] = _add_join_failure(joins[0], "alpha_halo_or_matte_contamination")
    if not source_immutable:
        joins[0] = _add_join_failure(joins[0], "clipped_or_disconnected_form")
    return _deterministic_report(
        axis=axis,
        alpha_policy=alpha_policy,
        coverage_policy=coverage_policy,
        source_immutable=source_immutable,
        joins=joins,
    )


def build_three_repeat_preview(
    repeat_unit_data: bytes,
    *,
    axis: ImageRepeatAxis,
) -> bytes:
    """Return three repeats composited over a deterministic neutral checkerboard.

    The opaque preview is a semantic-review visualization, not candidate media. Compositing
    makes partial alpha visible and guarantees that RGB hidden by zero alpha cannot influence
    the reviewer. The checker unit has an even number of tiles on the declared axis, so it is
    itself continuous when copied and cannot introduce a false join at a repeat boundary.
    """

    facts = inspect_image(repeat_unit_data, expected_media_type="image/png")
    _validate_dimensions(facts.width, facts.height, "image-repeat preview source")
    primary_extent = facts.width if axis == "x" else facts.height
    if primary_extent < 2:
        raise ValueError("image-repeat preview source must span two pixels on its repeat axis")
    image = _decode_rgba(repeat_unit_data)
    width = facts.width * _PREVIEW_REPEAT_COUNT if axis == "x" else facts.width
    height = facts.height if axis == "x" else facts.height * _PREVIEW_REPEAT_COUNT
    if width * height > MAX_IMAGE_REPEAT_PIXELS * _PREVIEW_REPEAT_COUNT:
        raise ValueError("three-repeat preview exceeds the bounded image-repeat pixel budget")
    checker = _neutral_checkerboard_unit(image.size, axis=axis)
    visualized_unit = Image.alpha_composite(checker, image).convert("RGB")
    preview = Image.new("RGB", (width, height))
    for index in range(_PREVIEW_REPEAT_COUNT):
        position = (index * facts.width, 0) if axis == "x" else (0, index * facts.height)
        preview.paste(visualized_unit, position)
    return _encode_png(preview)


def _neutral_checkerboard_unit(
    size: tuple[int, int],
    *,
    axis: ImageRepeatAxis,
) -> Image.Image:
    width, height = size
    primary_extent = width if axis == "x" else height
    approximate_tiles = max(
        2,
        (primary_extent + _PREVIEW_CHECKER_TARGET_TILE_PX - 1) // _PREVIEW_CHECKER_TARGET_TILE_PX,
    )
    primary_tiles = min(
        _PREVIEW_CHECKER_MAX_PRIMARY_TILES,
        approximate_tiles + approximate_tiles % 2,
    )
    approximate_tile_px = max(
        1,
        (primary_extent + primary_tiles // 2) // primary_tiles,
    )
    checker = Image.new("RGBA", size, _PREVIEW_CHECKER_LIGHT)
    cross_extent = height if axis == "x" else width
    for primary_tile in range(primary_tiles):
        primary_start = (primary_tile * primary_extent + primary_tiles - 1) // primary_tiles
        primary_end = ((primary_tile + 1) * primary_extent + primary_tiles - 1) // primary_tiles
        for cross_start in range(0, cross_extent, approximate_tile_px):
            cross_tile = cross_start // approximate_tile_px
            if (primary_tile + cross_tile) % 2 == 0:
                continue
            cross_end = min(cross_extent, cross_start + approximate_tile_px)
            box = (
                (primary_start, cross_start, primary_end, cross_end)
                if axis == "x"
                else (cross_start, primary_start, cross_end, primary_end)
            )
            checker.paste(_PREVIEW_CHECKER_DARK, box)
    return checker


def _join_report(
    before: Image.Image,
    after: Image.Image,
    *,
    axis: ImageRepeatAxis,
    name: _JoinName,
    coverage_policy: ImageRepeatCoveragePolicy,
    policy: ImageRepeatValidationPolicy,
    stitch: ImageRepeatStitch | None = None,
) -> ImageRepeatJoinReport:
    """Judge one join against the interior of the picture it sits in.

    A straight join compares the last line of ``before`` with the first line of ``after``. A
    ``stitch`` is a path through a single image (``before is after``), judged on the step across it
    like any join, and also on how far the two stitched pictures disagreed where they were blended.
    """

    _assert_cross_extent(before, after, axis)
    if stitch is not None:
        if before is not after:
            raise ValueError("a stitched join is measured inside a single image")
        if len(stitch.positions) != _cross_extent(before, axis):
            raise ValueError("a stitch must name one position per cross-axis line")
    metrics: list[ImageRepeatScaleMetrics] = []
    failures: list[ImageRepeatFailureCode] = []
    seen_sizes: set[tuple[int, int, int, int]] = set()
    for scale in policy.scales:
        scaled_before = _scale_image(before, scale)
        scaled_after = scaled_before if after is before else _scale_image(after, scale)
        if _primary_extent(scaled_before, axis) < 2 or _primary_extent(scaled_after, axis) < 2:
            continue
        size_key = (*scaled_before.size, *scaled_after.size)
        if size_key in seen_sizes:
            continue
        seen_sizes.add(size_key)
        lines: tuple[Sequence[_Rgba], Sequence[_Rgba], Sequence[_Rgba], Sequence[_Rgba]]
        if stitch is None:
            lines = (
                _edge_line(scaled_before, axis, -2),
                _edge_line(scaled_before, axis, -1),
                _edge_line(scaled_after, axis, 0),
                _edge_line(scaled_after, axis, 1),
            )
        else:
            scaled_stitch = _scaled_stitch(stitch.positions, scale, scaled_before, axis)
            lines = _stitch_lines(scaled_before, axis, scaled_stitch)
        sample = _step_sample(*lines, policy=policy)
        interior = _interior_means(scaled_before, axis, policy)
        if scaled_after is not scaled_before:
            interior += _interior_means(scaled_after, axis, policy)
        color_limit, gradient_limit, alpha_limit = (
            min(
                1.0,
                max(
                    floor,
                    _percentile([means[index] for means in interior], policy.interior_quantile)
                    * policy.interior_margin,
                ),
            )
            for index, floor in enumerate(
                (policy.color_mae_floor, policy.gradient_mae_floor, policy.alpha_mae_floor)
            )
        )
        measured = ImageRepeatScaleMetrics(
            scale=float(scale),
            boundary_width_px=max(1, round(1.0 / scale)),
            color_mae=float(_mean(sample.color)),
            color_p95=float(_percentile(sample.color, 0.95)),
            color_max=float(max(sample.color, default=0.0)),
            gradient_mae=float(_mean(sample.gradient)),
            gradient_p95=float(_percentile(sample.gradient, 0.95)),
            gradient_max=float(max(sample.gradient, default=0.0)),
            alpha_mae=float(_mean(sample.alpha)),
            alpha_p95=float(_percentile(sample.alpha, 0.95)),
            alpha_max=float(max(sample.alpha, default=0.0)),
            coverage_mismatch_ratio=float(sample.coverage_mismatches / max(1, len(sample.color))),
            interior_samples=max(1, len(interior)),
            color_limit=float(color_limit),
            gradient_limit=float(gradient_limit),
            alpha_limit=float(alpha_limit),
            coverage_limit=float(
                policy.coverage_mismatch_ratio if coverage_policy == "continuous" else 1.0
            ),
            color_disagreement=(
                stitch.color_disagreement if stitch is not None and scale == 1.0 else None
            ),
            alpha_disagreement=(
                stitch.alpha_disagreement if stitch is not None and scale == 1.0 else None
            ),
        )
        metrics.append(measured)
        if measured.color_mae > measured.color_limit:
            _append_unique(failures, "visible_boundary_pop")
        if measured.gradient_mae > measured.gradient_limit:
            _append_unique(failures, "lighting_or_texture_reset")
        if measured.alpha_mae > measured.alpha_limit:
            _append_unique(failures, "alpha_halo_or_matte_contamination")
        if measured.coverage_mismatch_ratio > measured.coverage_limit:
            _append_unique(failures, "unintended_transparent_gap")
        if (
            measured.color_disagreement is not None
            and measured.color_disagreement > measured.color_limit
        ) or (
            measured.alpha_disagreement is not None
            and measured.alpha_disagreement > measured.alpha_limit
        ):
            _append_unique(failures, "clipped_or_disconnected_form")
    if not metrics:
        raise ValueError("image-repeat validation could not evaluate any configured scale")
    return ImageRepeatJoinReport(
        name=name,
        verdict="reject" if failures else "pass",
        scales=metrics,
        failure_codes=failures,
    )


@dataclass(frozen=True, slots=True)
class _StepSample:
    """Per-line steps across one join, sampled along its cross axis."""

    color: list[float]
    gradient: list[float]
    alpha: list[float]
    coverage_mismatches: int


def _step_sample(
    previous_line: Sequence[_Rgba],
    before_line: Sequence[_Rgba],
    after_line: Sequence[_Rgba],
    following_line: Sequence[_Rgba],
    *,
    policy: ImageRepeatValidationPolicy,
) -> _StepSample:
    color_values: list[float] = []
    gradient_values: list[float] = []
    alpha_values: list[float] = []
    coverage_mismatches = 0
    for index in _sample_indices(len(before_line), _MAX_CROSS_AXIS_SAMPLES):
        boundary_before = before_line[index]
        boundary_after = after_line[index]
        previous_visual = _visual_rgb(previous_line[index])
        before_visual = _visual_rgb(boundary_before)
        after_visual = _visual_rgb(boundary_after)
        following_visual = _visual_rgb(following_line[index])
        color_values.append(
            sum(abs(left - right) for left, right in zip(before_visual, after_visual, strict=True))
            / 3.0
        )
        gradient_values.append(
            sum(
                abs(
                    (after_visual[channel] - before_visual[channel])
                    - (
                        (before_visual[channel] - previous_visual[channel])
                        + (following_visual[channel] - after_visual[channel])
                    )
                    / 2.0
                )
                / 2.0
                for channel in range(3)
            )
            / 3.0
        )
        alpha_before = boundary_before[3] / 255.0
        alpha_after = boundary_after[3] / 255.0
        alpha_values.append(abs(alpha_before - alpha_after))
        before_covered = alpha_before > policy.coverage_alpha_threshold
        after_covered = alpha_after > policy.coverage_alpha_threshold
        if before_covered != after_covered:
            coverage_mismatches += 1
    return _StepSample(
        color=color_values,
        gradient=gradient_values,
        alpha=alpha_values,
        coverage_mismatches=coverage_mismatches,
    )


def _interior_means(
    image: Image.Image, axis: ImageRepeatAxis, policy: ImageRepeatValidationPolicy
) -> list[tuple[float, float, float]]:
    """Mean colour, gradient and alpha steps at evenly spaced interior lines of one image.

    Interior lines are continuous by definition, so their steps are what an unremarkable column of
    this particular picture looks like: the baseline a join is held to.
    """

    rgba = image.convert("RGBA")
    primary = _primary_extent(rgba, axis)
    if primary < 4:
        return []
    pixels = rgba.load()
    if pixels is None:
        raise ValueError("image-repeat pixels are unavailable")
    cross = _cross_extent(rgba, axis)

    def line(index: int) -> tuple[_Rgba, ...]:
        if axis == "x":
            return tuple(cast(_Rgba, pixels[index, y]) for y in range(cross))
        return tuple(cast(_Rgba, pixels[x, index]) for x in range(cross))

    means: list[tuple[float, float, float]] = []
    for position in _sample_indices(primary - 3, _MAX_BASELINE_PRIMARY_SAMPLES, offset=2):
        sample = _step_sample(
            line(position - 2),
            line(position - 1),
            line(position),
            line(position + 1),
            policy=policy,
        )
        means.append((_mean(sample.color), _mean(sample.gradient), _mean(sample.alpha)))
    return means


def _scaled_stitch(
    stitch: Sequence[int], scale: float, scaled: Image.Image, axis: ImageRepeatAxis
) -> list[int]:
    """Carry a full-resolution stitch onto a scaled copy, one position per scaled line."""

    primary = _primary_extent(scaled, axis)
    positions: list[int] = []
    for index in range(_cross_extent(scaled, axis)):
        source = stitch[min(len(stitch) - 1, math.floor(index / scale))]
        positions.append(min(max(2, round(source * scale)), primary - 2))
    return positions


def _stitch_lines(
    image: Image.Image, axis: ImageRepeatAxis, stitch: Sequence[int]
) -> tuple[list[_Rgba], list[_Rgba], list[_Rgba], list[_Rgba]]:
    """The two pixels either side of a stitch on every line, as four join lines."""

    rgba = image.convert("RGBA")
    pixels = rgba.load()
    if pixels is None:
        raise ValueError("image-repeat pixels are unavailable")
    lines: tuple[list[_Rgba], ...] = ([], [], [], [])
    for index, position in enumerate(stitch):
        for offset, target in zip((-2, -1, 0, 1), lines, strict=True):
            at = position + offset
            pixel = pixels[at, index] if axis == "x" else pixels[index, at]
            target.append(cast(_Rgba, pixel))
    return lines[0], lines[1], lines[2], lines[3]


def _deterministic_report(
    *,
    axis: ImageRepeatAxis,
    alpha_policy: ImageRepeatAlphaPolicy,
    coverage_policy: ImageRepeatCoveragePolicy,
    source_immutable: bool,
    joins: list[ImageRepeatJoinReport],
) -> ImageRepeatDeterministicReport:
    failure_codes: list[ImageRepeatFailureCode] = []
    for join in joins:
        for code in join.failure_codes:
            _append_unique(failure_codes, code)
    return ImageRepeatDeterministicReport(
        axis=axis,
        verdict="reject" if failure_codes else "pass",
        alpha_policy=alpha_policy,
        coverage_policy=coverage_policy,
        source_immutable=source_immutable,
        joins=joins,
        failure_codes=failure_codes,
    )


def _add_join_failure(
    report: ImageRepeatJoinReport,
    code: ImageRepeatFailureCode,
) -> ImageRepeatJoinReport:
    codes = list(report.failure_codes)
    _append_unique(codes, code)
    return report.model_copy(update={"verdict": "reject", "failure_codes": codes})


def _conditioning_boxes(
    prepared: PreparedImageRepeatConditioning,
    *,
    context_span_px: int,
    repair_span_px: int,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int], tuple[int, int, int, int]]:
    if prepared.axis == "x":
        return (
            (0, 0, context_span_px, prepared.conditioning_height),
            (
                context_span_px,
                0,
                context_span_px + repair_span_px,
                prepared.conditioning_height,
            ),
            (
                context_span_px + repair_span_px,
                0,
                prepared.conditioning_width,
                prepared.conditioning_height,
            ),
        )
    return (
        (0, 0, prepared.conditioning_width, context_span_px),
        (
            0,
            context_span_px,
            prepared.conditioning_width,
            context_span_px + repair_span_px,
        ),
        (
            0,
            context_span_px + repair_span_px,
            prepared.conditioning_width,
            prepared.conditioning_height,
        ),
    )


def _head_context(image: Image.Image, axis: ImageRepeatAxis, span: int) -> Image.Image:
    return image.crop((0, 0, span, image.height) if axis == "x" else (0, 0, image.width, span))


def _tail_context(image: Image.Image, axis: ImageRepeatAxis, span: int) -> Image.Image:
    return image.crop(
        (image.width - span, 0, image.width, image.height)
        if axis == "x"
        else (0, image.height - span, image.width, image.height)
    )


def _source_region(
    repeat_unit: Image.Image,
    axis: ImageRepeatAxis,
    source_size: tuple[int, int],
) -> Image.Image:
    width, height = source_size
    box = (0, 0, width, repeat_unit.height) if axis == "x" else (0, 0, repeat_unit.width, height)
    return repeat_unit.crop(box)


def _append_along_axis(
    first: Image.Image,
    second: Image.Image,
    axis: ImageRepeatAxis,
) -> Image.Image:
    first_rgba = first.convert("RGBA")
    second_rgba = second.convert("RGBA")
    _assert_cross_extent(first_rgba, second_rgba, axis)
    if axis == "x":
        output = Image.new(
            "RGBA",
            (first_rgba.width + second_rgba.width, first_rgba.height),
            (0, 0, 0, 0),
        )
        output.paste(first_rgba, (0, 0))
        output.paste(second_rgba, (first_rgba.width, 0))
    else:
        output = Image.new(
            "RGBA",
            (first_rgba.width, first_rgba.height + second_rgba.height),
            (0, 0, 0, 0),
        )
        output.paste(first_rgba, (0, 0))
        output.paste(second_rgba, (0, first_rgba.height))
    return output


def _assert_cross_extent(before: Image.Image, after: Image.Image, axis: ImageRepeatAxis) -> None:
    before_cross = before.height if axis == "x" else before.width
    after_cross = after.height if axis == "x" else after.width
    if before_cross != after_cross:
        raise ValueError("image-repeat join segments must share their cross-axis extent")
    if _primary_extent(before, axis) < 2 or _primary_extent(after, axis) < 2:
        raise ValueError(
            "image-repeat join segments must each span at least two repeat-axis pixels"
        )


def _primary_extent(image: Image.Image, axis: ImageRepeatAxis) -> int:
    return image.width if axis == "x" else image.height


def _cross_extent(image: Image.Image, axis: ImageRepeatAxis) -> int:
    return image.height if axis == "x" else image.width


def _edge_line(image: Image.Image, axis: ImageRepeatAxis, index: int) -> tuple[_Rgba, ...]:
    rgba = image.convert("RGBA")
    primary = _primary_extent(rgba, axis)
    resolved = index if index >= 0 else primary + index
    if not 0 <= resolved < primary:
        raise ValueError("image-repeat edge line is outside the image")
    pixels = rgba.load()
    if pixels is None:
        raise ValueError("image-repeat pixels are unavailable")
    if axis == "x":
        return tuple(cast(_Rgba, pixels[resolved, y]) for y in range(rgba.height))
    return tuple(cast(_Rgba, pixels[x, resolved]) for x in range(rgba.width))


def _sample_indices(length: int, maximum: int, *, offset: int = 0) -> list[int]:
    if length <= 0:
        return []
    if length <= maximum:
        return [offset + index for index in range(length)]
    return sorted(
        {offset + min(length - 1, math.floor(index * length / maximum)) for index in range(maximum)}
    )


def _scale_image(image: Image.Image, scale: float) -> Image.Image:
    if scale == 1.0:
        return image.convert("RGBA")
    width = max(1, round(image.width * scale))
    height = max(1, round(image.height * scale))
    return image.convert("RGBA").resize((width, height), resample=Image.Resampling.LANCZOS)


def _visual_rgb(pixel: _Rgba) -> tuple[float, float, float]:
    alpha = pixel[3] / 255.0
    return (
        (pixel[0] / 255.0) * alpha,
        (pixel[1] / 255.0) * alpha,
        (pixel[2] / 255.0) * alpha,
    )


def _has_nonopaque_pixels(image: Image.Image) -> bool:
    alpha = image.convert("RGBA").getchannel("A")
    minimum, _maximum = alpha.getextrema()
    return minimum != 255


def _changed_pixels(left: Image.Image, right: Image.Image) -> int:
    if left.size != right.size:
        raise ValueError("image-repeat context comparison sizes must match")
    left_bytes = left.convert("RGBA").tobytes()
    right_bytes = right.convert("RGBA").tobytes()
    return sum(
        left_bytes[offset : offset + 4] != right_bytes[offset : offset + 4]
        for offset in range(0, len(left_bytes), 4)
    )


def _validate_dimensions(width: int, height: int, label: str) -> None:
    if width < 1 or height < 1:
        raise ValueError(f"{label} dimensions must be positive")
    if width > MAX_IMAGE_REPEAT_DIMENSION or height > MAX_IMAGE_REPEAT_DIMENSION:
        raise ValueError(f"{label} dimensions must not exceed {MAX_IMAGE_REPEAT_DIMENSION}px")
    if width * height > MAX_IMAGE_REPEAT_PIXELS:
        raise ValueError(f"{label} must not exceed {MAX_IMAGE_REPEAT_PIXELS} pixels")


def _append_unique(
    values: list[ImageRepeatFailureCode],
    value: ImageRepeatFailureCode,
) -> None:
    if value not in values:
        values.append(value)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def _decode_rgba(data: bytes) -> Image.Image:
    return decode_rgba(data, label="image-repeat PNG")


def _encode_png(image: Image.Image) -> bytes:
    return encode_png(image, compress_level=9)
