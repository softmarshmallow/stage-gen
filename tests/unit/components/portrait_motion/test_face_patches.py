"""Native face patches cross the sprite boundary with only an integer offset."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import numpy as np
import pytest
from PIL import Image

from stage_gen.components.portrait_motion import face_crop as processing
from stage_gen.components.portrait_motion import face_patches as boundary


def source_image(mode: str = "RGBA") -> Image.Image:
    rng = np.random.default_rng(61)
    pixels = rng.integers(0, 256, (200, 130, 4), dtype=np.uint8)
    pixels[..., 3] = 255
    pixels[:30, :20, 3] = 0
    pixels[30:50, :20, 3] = 128
    return Image.fromarray(pixels).convert(mode)


@pytest.mark.parametrize("mode", ["RGB", "RGBA"])
@pytest.mark.parametrize(
    "bbox", [(45, 90, 75, 132), (0, 5, 20, 45), (105, 155, 129, 198), (2.2, 3.2, 10.2, 11.2)]
)
def test_contained_patch_matches_direct_restore_exactly(mode: str, bbox: tuple[float, ...]) -> None:
    source = source_image(mode)
    original_bytes = source.tobytes()
    _, transform = processing.create_working_crop(source, bbox, work_size=(64, 64))
    local, local_transform = boundary.make_face_input(source, transform)
    left, top, right, bottom = transform["crop_box_xyxy"]
    assert local.mode == "RGBA"
    assert local.size == (right - left, bottom - top)
    assert local_transform["source_size"] == list(local.size)
    assert local_transform["crop_box_xyxy"] == [0, 0, *local.size]
    assert local_transform["padding_ltrb"] == [0, 0, 0, 0]
    assert local_transform["source_to_work_scale"] == transform["source_to_work_scale"]
    assert local_transform["work_size"] == transform["work_size"]
    donor = source_image("RGB").resize((32, 32))
    mask = np.zeros((64, 64))
    mask[4:60, 4:60] = 0.35
    mask[12:48, 14:52] = 1
    direct, global_mask = processing.restore_feature(source, donor, mask, transform)
    composed, native_mask = processing.restore_feature(local, donor, mask, local_transform)
    patch = boundary.isolate_patch(composed, native_mask)
    reconstructed = boundary.apply_offset_patch(source, patch, (left, top))
    assert reconstructed.mode == mode
    assert patch.size == local.size
    assert set(np.unique(np.asarray(patch)[..., 3])) <= {0, 255}
    np.testing.assert_array_equal(np.asarray(reconstructed), np.asarray(direct))
    np.testing.assert_array_equal(
        np.asarray(reconstructed)[global_mask == 0], np.asarray(source)[global_mask == 0]
    )
    np.testing.assert_array_equal(
        np.asarray(reconstructed.convert("RGBA"))[..., 3],
        np.asarray(source.convert("RGBA"))[..., 3],
    )
    assert source.tobytes() == original_bytes


def test_native_input_preserves_hidden_rgb_and_has_transparent_outer_padding() -> None:
    source = source_image()
    _, transform = processing.create_working_crop(source, (0, 5, 20, 45), work_size=(64, 64))
    local, _ = boundary.make_face_input(source, transform)
    left, top, _, _ = transform["crop_box_xyxy"]
    assert left < 0 and top < 0
    assert local.getpixel((0, 0)) == (0, 0, 0, 0)
    assert local.getpixel((1 - left, 10 - top)) == source.getpixel((1, 10))
    assert local.getpixel((1 - left, 35 - top)) == source.getpixel((1, 35))


def test_fractional_center_rounding_never_moves_crop_or_patch_coordinates() -> None:
    source = Image.new("RGB", (1000, 1800), (20, 60, 100))
    _, transform = processing.create_working_crop(
        source, [468.59, 639.35, 622.41, 878.24], work_size=(64, 64)
    )
    assert transform["crop_box_xyxy"] == [342, 555, 749, 962]
    local, local_transform = boundary.make_face_input(source, transform)
    assert local.size == (407, 407)
    assert local_transform["crop_box_xyxy"] == [0, 0, 407, 407]
    assert local_transform["face_box_xyxy"] == [126.59, 84.35, 280.41, 323.24]
    assert local_transform["source_to_work_scale"] == transform["source_to_work_scale"]
    donor = Image.new("RGB", (32, 32), (220, 40, 10))
    mask = np.zeros((64, 64))
    mask[16:48, 16:48] = 0.5
    direct, _ = processing.restore_feature(source, donor, mask, transform)
    composed, local_mask = processing.restore_feature(local, donor, mask, local_transform)
    patch = boundary.isolate_patch(composed, local_mask)
    restored = boundary.apply_offset_patch(source, patch, (342, 555))
    np.testing.assert_array_equal(np.asarray(restored), np.asarray(direct))


def test_two_disjoint_feature_patches_apply_independently_with_one_blend() -> None:
    source = Image.new("RGBA", (80, 120), (20, 20, 20, 255))
    _, transform = processing.create_working_crop(
        source, (20, 30, 52, 62), work_size=(64, 64), padding_fraction=0
    )
    local, local_transform = boundary.make_face_input(source, transform)
    masks = [np.zeros((64, 64)), np.zeros((64, 64))]
    masks[0][4:20, 8:48] = 0.5
    masks[1][40:56, 24:40] = 1
    output = source
    direct = source
    for mask, color in zip(masks, [(220, 220, 220), (240, 60, 20)], strict=True):
        donor = Image.new("RGB", (32, 32), color)
        composed, local_mask = processing.restore_feature(local, donor, mask, local_transform)
        patch = boundary.isolate_patch(composed, local_mask)
        output = boundary.apply_offset_patch(output, patch, transform["crop_box_xyxy"][:2])
        direct, _ = processing.restore_feature(direct, donor, mask, transform)
    np.testing.assert_array_equal(np.asarray(output), np.asarray(direct))
    assert output.getpixel((30, 35)) == (120, 120, 120, 255)
    assert output.getpixel((35, 53)) == (240, 60, 20, 255)


def test_zero_support_is_an_exact_rest_frame_and_patch_hides_unused_rgb() -> None:
    source = source_image()
    patch = boundary.isolate_patch(source, np.zeros((source.height, source.width)))
    assert not np.any(np.asarray(patch))
    assert boundary.apply_offset_patch(source, patch, (0, 0)).tobytes() == source.tobytes()


@pytest.mark.parametrize("offset", [(-100, -100), (1000, 0), (0, 1000)])
def test_wholly_outside_patch_is_exact_rest(offset: tuple[int, int]) -> None:
    source = source_image()
    patch = Image.new("RGBA", (5, 5), (100, 50, 20, 255))
    assert boundary.apply_offset_patch(source, patch, offset).tobytes() == source.tobytes()


@pytest.mark.parametrize("offset", [(0.5, 1), (0, True), (1,), "1,2"])
def test_offset_accepts_only_two_integers(offset: object) -> None:
    with pytest.raises(ValueError, match="two integers"):
        boundary.apply_offset_patch(
            Image.new("RGB", (10, 10)), Image.new("RGBA", (4, 4)), cast(Sequence[int], offset)
        )


def test_fractional_patch_alpha_is_rejected_to_prevent_double_feather() -> None:
    with pytest.raises(ValueError, match="binary alpha"):
        boundary.apply_offset_patch(
            Image.new("RGB", (10, 10)), Image.new("RGBA", (4, 4), (100, 100, 100, 128)), (0, 0)
        )


def test_offset_patch_cannot_replace_fully_transparent_original_pixels() -> None:
    with pytest.raises(ValueError, match="visible original"):
        boundary.apply_offset_patch(
            Image.new("RGBA", (10, 10), (20, 30, 40, 0)),
            Image.new("RGBA", (4, 4), (100, 100, 100, 255)),
            (0, 0),
        )


@pytest.mark.parametrize("alpha", [128, 254])
def test_isolated_visible_patch_replaces_rgb_without_changing_partial_alpha(alpha: int) -> None:
    source = Image.new("RGBA", (10, 10), (20, 30, 40, alpha))
    composed = Image.new("RGBA", (4, 4), (100, 80, 60, alpha))
    patch = boundary.isolate_patch(composed, np.ones((4, 4)))
    result = boundary.apply_offset_patch(source, patch, (-2, 3))
    assert result.getpixel((0, 3)) == (100, 80, 60, alpha)
    assert result.getpixel((2, 3)) == source.getpixel((2, 3))
    assert np.all(np.asarray(result)[..., 3] == alpha)


@pytest.mark.parametrize(
    "mask",
    [np.zeros((3, 3)), np.full((4, 4), np.nan), np.full((4, 4), 2), np.full((4, 4), "0.5")],
)
def test_isolated_patch_rejects_malformed_masks(mask: np.ndarray) -> None:
    with pytest.raises(ValueError, match="mask"):
        boundary.isolate_patch(Image.new("RGB", (4, 4)), mask)


def test_isolated_patch_refuses_support_over_transparency() -> None:
    with pytest.raises(ValueError, match="visible original"):
        boundary.isolate_patch(Image.new("RGBA", (4, 4)), np.ones((4, 4)))
