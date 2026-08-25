from __future__ import annotations

import hashlib
from io import BytesIO
from typing import Literal, cast

import pytest
from PIL import Image

from stage_gen.components.image_repeat.models import (
    ImageRepeatAssetBinding,
    ImageRepeatIntent,
    ImageRepeatManifest,
    ImageRepeatRepairConstruction,
    ImageRepeatRepairLineage,
    ImageRepeatSemanticReview,
    ImageRepeatValidation,
    ImageRepeatValidationPolicy,
)
from stage_gen.components.image_repeat.processing import (
    AcceptedImageRepeatCandidate,
    PreparedImageRepeatConditioning,
    _anchor_repair_endpoints,
    _integer_smoothstep_weight,
    _reconstruct_repair_alpha,
    accept_repair_candidate,
    build_three_repeat_preview,
    canonical_intended_loop_criteria,
    prepare_repair_conditioning,
    verify_image_repeat_artifact,
)

type Axis = Literal["x", "y"]
type Rgba = tuple[int, int, int, int]

_CONTEXT_SPAN = 4
_REPAIR_SPAN = 32


@pytest.mark.parametrize("axis", ["x", "y"])
def test_endpoint_anchoring_preserves_source_and_provider_interior(axis: Axis) -> None:
    source_data, prepared, provider_data, raw_repair = _candidate_case(axis)

    accepted = accept_repair_candidate(
        prepared,
        provider_data,
        context_span_px=_CONTEXT_SPAN,
        repair_span_px=_REPAIR_SPAN,
        alpha_policy="preserve",
        coverage_policy="sparse_allowed",
        validation_policy=ImageRepeatValidationPolicy(),
    )

    source = _decode(source_data)
    repair = _decode(accepted.repair_png)
    decoded_raw = _decode(accepted.raw_repair_png)
    alpha_reconstructed = _decode(accepted.alpha_reconstructed_repair_png)
    interior = _decode(accepted.provider_interior_png)
    repeat = _decode(accepted.repeat_unit_png)
    assert accepted.endpoint_anchor_span_px == 8
    assert accepted.alpha_reconstructed_changed_pixels > 0
    assert accepted.anchored_repair_changed_pixels > 0
    assert accepted.provider_context_changed_pixels > 0
    assert accepted.deterministic_report.verdict == "pass"
    assert decoded_raw.tobytes() == raw_repair.tobytes()
    assert _primary_crop(alpha_reconstructed, axis, 8, 24).tobytes() == interior.tobytes()
    assert _primary_crop(repair, axis, 8, 24).tobytes() == interior.tobytes()
    _assert_visible_rgb_preserved(
        _primary_crop(decoded_raw, axis, 8, 24),
        interior,
        axis,
    )
    _assert_alpha_equal(alpha_reconstructed, repair, axis)
    assert _primary_line(repair, axis, 0) == _primary_line(source, axis, -1)
    assert _primary_line(repair, axis, -1) == _primary_line(source, axis, 0)
    assert _primary_crop(repeat, axis, 0, _primary_extent(source, axis)).tobytes() == (
        source.tobytes()
    )


@pytest.mark.parametrize("axis", ["x", "y"])
def test_endpoint_anchor_uses_partial_alpha_without_leaking_hidden_rgb(axis: Axis) -> None:
    source_data, _prepared, _provider_data, raw_repair = _candidate_case(axis)
    source = _decode(source_data)
    hidden_variant = raw_repair.copy()
    for primary in range(_REPAIR_SPAN):
        _put_primary(hidden_variant, axis, primary, 0, (7, 241, 19, 0))

    reconstructed = _reconstruct_repair_alpha(source, raw_repair, axis=axis)
    reconstructed_variant = _reconstruct_repair_alpha(source, hidden_variant, axis=axis)
    anchored = _anchor_repair_endpoints(
        source,
        reconstructed.repair,
        raw_repair=raw_repair,
        axis=axis,
    )
    anchored_variant = _anchor_repair_endpoints(
        source,
        reconstructed_variant.repair,
        raw_repair=hidden_variant,
        axis=axis,
    )

    assert _primary_pixel(anchored.repair, axis, 0, 0) == _primary_pixel(source, axis, -1, 0)
    assert _primary_pixel(anchored.repair, axis, -1, 0) == _primary_pixel(source, axis, 0, 0)
    assert _primary_pixel(reconstructed.repair, axis, 3, 0) == (0, 0, 0, 0)
    assert _primary_pixel(reconstructed_variant.repair, axis, 3, 0) == (0, 0, 0, 0)
    assert _primary_pixel(anchored.repair, axis, 3, 0) == (0, 0, 0, 0)
    assert _primary_pixel(anchored_variant.repair, axis, 3, 0) == (0, 0, 0, 0)

    blended = _primary_pixel(anchored.repair, axis, 3, 1)
    assert blended[3] == _primary_pixel(reconstructed.repair, axis, 3, 1)[3]
    assert 64 < blended[3] < 192
    assert blended[0] > 150
    assert blended[2] > 60

    repeat = _append(source, anchored.repair, axis)
    variant_repeat = _append(source, anchored_variant.repair, axis)
    assert build_three_repeat_preview(_png(repeat), axis=axis) == build_three_repeat_preview(
        _png(variant_repeat),
        axis=axis,
    )


@pytest.mark.parametrize("axis", ["x", "y"])
def test_alpha_reconstruction_ignores_provider_alpha_and_preserves_visible_rgb(
    axis: Axis,
) -> None:
    source_data, _prepared, _provider_data, raw_repair = _candidate_case(axis)
    source = _decode(source_data)
    alpha_variant = raw_repair.copy()
    for primary in range(_REPAIR_SPAN):
        for cross in range(5):
            pixel = _primary_pixel(alpha_variant, axis, primary, cross)
            _put_primary(
                alpha_variant,
                axis,
                primary,
                cross,
                (*pixel[:3], 255 if (primary + cross) % 2 else 0),
            )

    reconstructed = _reconstruct_repair_alpha(source, raw_repair, axis=axis)
    reconstructed_variant = _reconstruct_repair_alpha(source, alpha_variant, axis=axis)

    assert reconstructed.repair.tobytes() == reconstructed_variant.repair.tobytes()
    assert reconstructed.changed_pixels > 0
    assert reconstructed_variant.changed_pixels > 0
    _assert_visible_rgb_preserved(raw_repair, reconstructed.repair, axis)
    assert _primary_pixel(reconstructed.repair, axis, 0, 1)[3] == 64
    assert _primary_pixel(reconstructed.repair, axis, -1, 1)[3] == 192
    assert _primary_pixel(reconstructed.repair, axis, 16, 1)[3] in {130, 131}


def test_endpoint_anchor_requires_at_least_four_repair_pixels() -> None:
    source = Image.new("RGBA", (8, 4), (30, 90, 120, 255))
    with pytest.raises(ValueError, match="at least four pixels"):
        prepare_repair_conditioning(
            _png(source),
            axis="x",
            context_span_px=2,
            repair_span_px=3,
        )
    with pytest.raises(ValueError, match="at least four pixels"):
        _reconstruct_repair_alpha(
            source,
            Image.new("RGBA", (3, 4), (30, 90, 120, 255)),
            axis="x",
        )
    with pytest.raises(ValueError, match="at least four pixels"):
        _anchor_repair_endpoints(
            source,
            Image.new("RGBA", (3, 4), (30, 90, 120, 255)),
            raw_repair=Image.new("RGBA", (3, 4), (30, 90, 120, 255)),
            axis="x",
        )


def test_integer_smoothstep_has_exact_endpoints_and_symmetric_fixed_weights() -> None:
    weights = [_integer_smoothstep_weight(position, 7) for position in range(8)]

    assert weights[0] == 0
    assert weights[-1] == 65_535
    assert weights == sorted(weights)
    assert all(weights[index] + weights[-1 - index] == 65_535 for index in range(8))


def test_repaired_verification_requires_and_reconstructs_exact_provider_candidate() -> None:
    axis: Axis = "x"
    source_data, prepared, provider_data, _raw_repair = _candidate_case(axis)
    policy = ImageRepeatValidationPolicy()
    accepted = accept_repair_candidate(
        prepared,
        provider_data,
        context_span_px=_CONTEXT_SPAN,
        repair_span_px=_REPAIR_SPAN,
        alpha_policy="preserve",
        coverage_policy="sparse_allowed",
        validation_policy=policy,
    )
    manifest = _manifest(
        source_data=source_data,
        provider_data=provider_data,
        accepted=accepted,
        policy=policy,
    )

    with pytest.raises(ValueError, match="requires its exact provider candidate"):
        verify_image_repeat_artifact(source_data, accepted.repeat_unit_png, manifest)

    verified = verify_image_repeat_artifact(
        source_data,
        accepted.repeat_unit_png,
        manifest,
        provider_candidate_data=provider_data,
    )
    assert verified.raw_repair_png == accepted.raw_repair_png
    assert verified.alpha_reconstructed_repair_png == accepted.alpha_reconstructed_repair_png
    assert verified.provider_interior_png == accepted.provider_interior_png
    assert verified.endpoint_anchor_span_px == accepted.endpoint_anchor_span_px
    assert (
        verified.alpha_reconstructed_changed_pixels == accepted.alpha_reconstructed_changed_pixels
    )
    assert verified.anchored_repair_changed_pixels == accepted.anchored_repair_changed_pixels

    tampered = _decode(provider_data)
    _put_primary(tampered, axis, _CONTEXT_SPAN + 16, 2, (250, 10, 10, 255))
    with pytest.raises(
        ValueError,
        match=r"provider repair candidate binding|anchored provider candidate|lineage",
    ):
        verify_image_repeat_artifact(
            source_data,
            accepted.repeat_unit_png,
            manifest,
            provider_candidate_data=_png(tampered),
        )


def _candidate_case(
    axis: Axis,
) -> tuple[bytes, PreparedImageRepeatConditioning, bytes, Image.Image]:
    source = _source(axis)
    source_data = _png(source)
    prepared = prepare_repair_conditioning(
        source_data,
        axis=axis,
        context_span_px=_CONTEXT_SPAN,
        repair_span_px=_REPAIR_SPAN,
    )
    provider = _decode(prepared.conditioning_png)
    raw_repair = Image.new(
        "RGBA",
        (_REPAIR_SPAN, source.height) if axis == "x" else (source.width, _REPAIR_SPAN),
    )
    middle: tuple[Rgba, ...] = (
        (11, 222, 33, 0),
        (100, 40, 120, 128),
        (45, 125, 65, 255),
        (50, 130, 70, 255),
        (55, 135, 75, 255),
    )
    for primary in range(_REPAIR_SPAN):
        for cross, pixel in enumerate(middle):
            _put_primary(raw_repair, axis, primary, cross, pixel)
            _put_primary(
                provider,
                axis,
                _CONTEXT_SPAN + primary,
                cross,
                pixel,
            )
    conditioning_primary = _CONTEXT_SPAN * 2 + _REPAIR_SPAN
    for primary in (
        *range(_CONTEXT_SPAN),
        *range(_CONTEXT_SPAN + _REPAIR_SPAN, conditioning_primary),
    ):
        for cross in range(5):
            _put_primary(provider, axis, primary, cross, (250, 230, 10, 255))
    return source_data, prepared, _png(provider), raw_repair


def _source(axis: Axis) -> Image.Image:
    primary_extent = 12
    cross_extent = 5
    size = (primary_extent, cross_extent) if axis == "x" else (cross_extent, primary_extent)
    image = Image.new("RGBA", size)
    head: tuple[Rgba, ...] = (
        (9, 8, 7, 0),
        (20, 40, 220, 192),
        (50, 130, 70, 255),
        (55, 135, 75, 255),
        (60, 140, 80, 255),
    )
    tail: tuple[Rgba, ...] = (
        (255, 0, 255, 0),
        (220, 40, 20, 64),
        (40, 120, 60, 255),
        (45, 125, 65, 255),
        (50, 130, 70, 255),
    )
    for primary in range(primary_extent):
        line = head if primary < primary_extent // 2 else tail
        for cross, pixel in enumerate(line):
            _put_primary(image, axis, primary, cross, pixel)
    return image


def _manifest(
    *,
    source_data: bytes,
    provider_data: bytes,
    accepted: AcceptedImageRepeatCandidate,
    policy: ImageRepeatValidationPolicy,
) -> ImageRepeatManifest:
    repeat_data = accepted.repeat_unit_png
    raw_repair_png = accepted.raw_repair_png
    alpha_reconstructed_repair_png = accepted.alpha_reconstructed_repair_png
    interior_png = accepted.provider_interior_png
    source = _decode(source_data)
    repeat = _decode(repeat_data)
    provider = _decode(provider_data)
    criteria = canonical_intended_loop_criteria(
        axis="x",
        intended_behavior="continuous low-salience transparent texture band",
        alpha_policy="preserve",
        coverage_policy="sparse_allowed",
        validation_policy=policy,
    )
    criteria_sha256 = hashlib.sha256(criteria).hexdigest()
    preview = build_three_repeat_preview(repeat_data, axis="x")
    source_binding = _binding("source.png", source_data, source)
    repeat_binding = _binding("repeat.png", repeat_data, repeat)
    provider_binding = _binding("provider.png", provider_data, provider)
    prepared = prepare_repair_conditioning(
        source_data,
        axis="x",
        context_span_px=_CONTEXT_SPAN,
        repair_span_px=_REPAIR_SPAN,
    )
    construction = ImageRepeatRepairConstruction(
        context_span_px=_CONTEXT_SPAN,
        repair_span_px=_REPAIR_SPAN,
        endpoint_anchor_span_px=accepted.endpoint_anchor_span_px,
        provider_candidate=provider_binding,
        provider="test-provider",
        model="test-model",
        attempts=1,
    )
    lineage = ImageRepeatRepairLineage(
        source_sha256=source_binding.sha256,
        head_context_sha256=hashlib.sha256(prepared.head_context_png).hexdigest(),
        tail_context_sha256=hashlib.sha256(prepared.tail_context_png).hexdigest(),
        conditioning_sha256=hashlib.sha256(prepared.conditioning_png).hexdigest(),
        mask_sha256=hashlib.sha256(prepared.mask_png).hexdigest(),
        provider_candidate_sha256=provider_binding.sha256,
        raw_repair_sha256=hashlib.sha256(raw_repair_png).hexdigest(),
        alpha_reconstructed_repair_sha256=hashlib.sha256(
            alpha_reconstructed_repair_png
        ).hexdigest(),
        provider_interior_sha256=hashlib.sha256(interior_png).hexdigest(),
        repair_sha256=hashlib.sha256(accepted.repair_png).hexdigest(),
        repeat_unit_sha256=repeat_binding.sha256,
    )
    semantic = ImageRepeatSemanticReview(
        verdict="accept",
        confidence=0.96,
        failure_codes=[],
        evidence="Both joins and the texture band remain visually continuous.",
        judged_sha256=repeat_binding.sha256,
        preview_sha256=hashlib.sha256(preview).hexdigest(),
        criteria_sha256=criteria_sha256,
        reviewer_provider="test-reviewer",
        reviewer_model="test-review-model",
        independent=True,
    )
    return ImageRepeatManifest(
        axis="x",
        decision="repaired",
        source=source_binding,
        repeat_unit=repeat_binding,
        period_px=repeat.width,
        cross_axis_extent_px=repeat.height,
        intent=ImageRepeatIntent(
            intended_behavior="continuous low-salience transparent texture band",
            alpha_policy="preserve",
            coverage_policy="sparse_allowed",
            criteria_sha256=criteria_sha256,
        ),
        construction=construction,
        validation=ImageRepeatValidation(
            policy=policy,
            deterministic=accepted.deterministic_report,
            intended_loop=semantic,
        ),
        lineage=lineage,
        rights_status="unreviewed",
    )


def _binding(
    name: str,
    data: bytes,
    image: Image.Image,
) -> ImageRepeatAssetBinding:
    return ImageRepeatAssetBinding(
        path=name,
        provenance_path=f"{name}.meta.json",
        sha256=hashlib.sha256(data).hexdigest(),
        bytes=len(data),
        width=image.width,
        height=image.height,
    )


def _append(source: Image.Image, repair: Image.Image, axis: Axis) -> Image.Image:
    size = (
        (source.width + repair.width, source.height)
        if axis == "x"
        else (source.width, source.height + repair.height)
    )
    output = Image.new("RGBA", size)
    output.paste(source, (0, 0))
    output.paste(repair, (source.width, 0) if axis == "x" else (0, source.height))
    return output


def _primary_extent(image: Image.Image, axis: Axis) -> int:
    return image.width if axis == "x" else image.height


def _primary_crop(
    image: Image.Image,
    axis: Axis,
    start: int,
    end: int,
) -> Image.Image:
    return image.crop(
        (start, 0, end, image.height) if axis == "x" else (0, start, image.width, end)
    )


def _primary_line(image: Image.Image, axis: Axis, primary: int) -> tuple[Rgba, ...]:
    resolved = primary if primary >= 0 else _primary_extent(image, axis) + primary
    cross_extent = image.height if axis == "x" else image.width
    return tuple(_primary_pixel(image, axis, resolved, cross) for cross in range(cross_extent))


def _primary_pixel(
    image: Image.Image,
    axis: Axis,
    primary: int,
    cross: int,
) -> Rgba:
    resolved = primary if primary >= 0 else _primary_extent(image, axis) + primary
    coordinates = (resolved, cross) if axis == "x" else (cross, resolved)
    return cast(Rgba, image.getpixel(coordinates))


def _assert_visible_rgb_preserved(
    provider: Image.Image,
    reconstructed: Image.Image,
    axis: Axis,
) -> None:
    assert provider.size == reconstructed.size
    primary_extent = _primary_extent(provider, axis)
    cross_extent = provider.height if axis == "x" else provider.width
    for primary in range(primary_extent):
        for cross in range(cross_extent):
            provider_pixel = _primary_pixel(provider, axis, primary, cross)
            reconstructed_pixel = _primary_pixel(reconstructed, axis, primary, cross)
            if reconstructed_pixel[3] > 0:
                assert reconstructed_pixel[:3] == provider_pixel[:3]
            else:
                assert reconstructed_pixel[:3] == (0, 0, 0)


def _assert_alpha_equal(before: Image.Image, after: Image.Image, axis: Axis) -> None:
    assert before.size == after.size
    primary_extent = _primary_extent(before, axis)
    cross_extent = before.height if axis == "x" else before.width
    for primary in range(primary_extent):
        for cross in range(cross_extent):
            assert (
                _primary_pixel(before, axis, primary, cross)[3]
                == _primary_pixel(
                    after,
                    axis,
                    primary,
                    cross,
                )[3]
            )


def _put_primary(
    image: Image.Image,
    axis: Axis,
    primary: int,
    cross: int,
    value: Rgba,
) -> None:
    coordinates = (primary, cross) if axis == "x" else (cross, primary)
    image.putpixel(coordinates, value)


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", compress_level=9, optimize=False)
    return output.getvalue()


def _decode(data: bytes) -> Image.Image:
    with Image.open(BytesIO(data)) as image:
        image.load()
        return image.convert("RGBA")
