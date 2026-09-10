"""Checks for source-space crop mapping and single-blend feature replacement."""

from __future__ import annotations

import copy
import json
from typing import Any

import numpy as np
import pytest
from PIL import Image

from stage_gen.components.portrait_motion import face_crop as processing


def test_off_center_edge_crop_records_padding_and_flattens_only_local_pixels() -> None:
    source = Image.new("RGBA", (100, 160), (20, 80, 140, 255))
    source.putpixel((1, 10), (40, 80, 120, 0))
    source.putpixel((2, 10), (40, 80, 120, 128))
    before = source.tobytes()
    work, transform = processing.create_working_crop(source, (0, 5, 20, 45), work_size=(68, 68))
    assert transform["crop_box_xyxy"] == [-24, -9, 44, 59]
    assert transform["padding_ltrb"] == [24, 9, 0, 0]
    assert transform["source_size"] == [100, 160]
    assert transform["work_size"] == [68, 68]
    assert transform["source_to_work_scale"] == 1
    assert json.loads(json.dumps(transform)) == transform
    assert work.mode == "RGB"
    assert work.getpixel((0, 0)) == (240, 240, 240)
    assert work.getpixel((24, 19)) == (20, 80, 140)
    assert work.getpixel((25, 19)) == (240, 240, 240)
    assert work.getpixel((26, 19)) == (140, 160, 180)
    assert source.tobytes() == before


def test_square_face_context_scales_both_axes_equally() -> None:
    yy, xx = np.mgrid[:100, :80]
    source = Image.fromarray(np.stack([xx * 2, yy * 2, xx * 0], axis=2).astype(np.uint8))
    work, transform = processing.create_working_crop(
        source, (20, 30, 40, 70), work_size=(80, 80), padding_fraction=0
    )
    assert transform["crop_box_xyxy"] == [10, 30, 50, 70]
    assert transform["source_to_work_scale"] == 2
    pixels = np.asarray(work).astype(int)
    assert tuple(pixels[30, 32] - pixels[30, 30]) == (2, 0, 0)
    assert tuple(pixels[32, 30] - pixels[30, 30]) == (0, 2, 0)


def test_fractional_bbox_is_completely_contained_after_integer_rounding() -> None:
    _, transform = processing.create_working_crop(
        Image.new("RGB", (30, 30)),
        (2.2, 3.2, 10.2, 11.2),
        work_size=(32, 32),
        padding_fraction=0,
    )
    left, top, right, bottom = transform["crop_box_xyxy"]
    assert left <= 2.2 and top <= 3.2 and right >= 10.2 and bottom >= 11.2
    assert right - left == bottom - top


def test_restore_preserves_alpha_and_all_pixels_outside_effective_mask() -> None:
    rng = np.random.default_rng(17)
    pixels = rng.integers(0, 256, (159, 101, 4), dtype=np.uint8)
    pixels[..., 3] = 255
    pixels[:40, :20, 3] = 0
    pixels[40:60, :20, 3] = 128
    source = Image.fromarray(pixels)
    _, transform = processing.create_working_crop(source, (4, 20, 36, 64), work_size=(64, 64))
    result, source_mask = processing.restore_feature(
        source,
        Image.new("RGB", (32, 32), (200, 80, 10)),
        np.ones((64, 64)),
        transform,
    )
    output = np.asarray(result)
    assert result.mode == "RGBA" and result.size == source.size
    np.testing.assert_array_equal(output[..., 3], pixels[..., 3])
    np.testing.assert_array_equal(output[source_mask == 0], pixels[source_mask == 0])
    assert np.all(output[(source_mask == 1) & (pixels[..., 3] == 255), :3] == (200, 80, 10))
    assert np.count_nonzero(source_mask) > 100
    assert np.all(source_mask[pixels[..., 3] == 0] == 0)
    assert np.any(source_mask[pixels[..., 3] == 128] > 0)
    np.testing.assert_array_equal(np.asarray(source), pixels)


def test_zero_mask_is_an_exact_rest_frame_including_hidden_rgb() -> None:
    source = Image.new("RGBA", (100, 180), (70, 20, 140, 0))
    _, transform = processing.create_working_crop(source, (20, 10, 60, 60), work_size=(64, 64))
    result, source_mask = processing.restore_feature(
        source, Image.new("RGB", (32, 32), "red"), np.zeros((64, 64)), transform
    )
    assert result.tobytes() == source.tobytes()
    assert not np.any(source_mask)


def test_near_opaque_sprite_can_change_features_without_changing_alpha() -> None:
    source = Image.new("RGBA", (40, 60), (20, 80, 140, 254))
    _, transform = processing.create_working_crop(
        source, (10, 10, 26, 26), work_size=(16, 16), padding_fraction=0
    )
    mask = np.zeros((16, 16))
    mask[4:12, 4:12] = 1
    output, effective = processing.restore_feature(
        source, Image.new("RGB", (8, 8), (220, 160, 100)), mask, transform
    )
    assert output.getpixel((18, 18)) == (220, 160, 99, 254)
    assert np.all(np.asarray(output)[..., 3] == 254)
    np.testing.assert_array_equal(
        np.asarray(output)[effective == 0], np.asarray(source)[effective == 0]
    )


@pytest.mark.parametrize("feature_alpha", [0.5, 1.0])
def test_half_alpha_donor_unmatting_matches_neutral_composite_with_one_blend(
    feature_alpha: float,
) -> None:
    source = Image.new("RGBA", (40, 60), (20, 80, 140, 128))
    _, transform = processing.create_working_crop(
        source, (10, 10, 26, 26), work_size=(16, 16), padding_fraction=0
    )
    donor_color = np.asarray([180, 150, 130])
    output, _ = processing.restore_feature(
        source,
        Image.new("RGB", (8, 8), tuple(donor_color)),
        np.full((16, 16), feature_alpha),
        transform,
    )
    neutral = Image.new("RGBA", source.size, (240, 240, 240, 255))
    source_matte = np.asarray(Image.alpha_composite(neutral, source))[18, 18, :3]
    output_matte = np.asarray(Image.alpha_composite(neutral, output))[18, 18, :3]
    expected = source_matte * (1 - feature_alpha) + donor_color * feature_alpha
    np.testing.assert_allclose(output_matte, expected, atol=1)
    assert output.getchannel("A").getpixel((18, 18)) == 128


def test_lowest_visible_alpha_stays_finite_with_negative_crop_padding() -> None:
    source = Image.new("RGBA", (40, 60), (10, 200, 80, 1))
    source.putpixel((0, 0), (70, 90, 110, 0))
    _, transform = processing.create_working_crop(source, (0, 0, 12, 12), work_size=(32, 32))
    assert transform["crop_box_xyxy"][0] < 0 and transform["crop_box_xyxy"][1] < 0
    with np.errstate(divide="raise", invalid="raise", over="raise"):
        output, mask = processing.restore_feature(
            source, Image.new("RGB", (16, 16), "black"), np.ones((32, 32)), transform
        )
    assert output.getpixel((5, 5)) == (0, 0, 0, 1)
    assert output.getpixel((0, 0)) == source.getpixel((0, 0))
    assert mask[0, 0] == 0
    np.testing.assert_array_equal(np.asarray(output)[..., 3], np.asarray(source)[..., 3])
    neutral = Image.new("RGBA", source.size, (240, 240, 240, 255))
    before = np.asarray(Image.alpha_composite(neutral, source)).astype(int)
    after = np.asarray(Image.alpha_composite(neutral, output)).astype(int)
    # Alpha is fixed at 1/255: clipped straight RGB can change its visible
    # neutral-composited value by at most one level, never produce a halo.
    assert np.max(np.abs(after - before)) <= 1


def test_opaque_core_replaces_once_and_feather_blends_once() -> None:
    source = Image.new("RGB", (20, 30), (20, 20, 20))
    _, transform = processing.create_working_crop(
        source, (4, 5, 12, 13), work_size=(8, 8), padding_fraction=0
    )
    mask = np.zeros((8, 8))
    mask[1:7, 1:7] = 0.5
    mask[2:6, 2:6] = 1
    result, source_mask = processing.restore_feature(
        source, Image.new("RGB", (4, 4), (220, 220, 220)), mask, transform
    )
    assert result.mode == "RGB"
    assert result.getpixel((6, 7)) == (220, 220, 220)
    assert result.getpixel((5, 6)) == (120, 120, 120)
    assert result.getpixel((4, 5)) == (20, 20, 20)
    np.testing.assert_array_equal(source_mask[5:13, 4:12], mask)


def test_lower_resolution_donor_maps_directly_to_original_pixel_centers() -> None:
    source = Image.new("RGB", (20, 30), "white")
    _, transform = processing.create_working_crop(
        source, (4, 5, 12, 13), work_size=(16, 16), padding_fraction=0
    )
    values = np.tile(np.arange(4, dtype=np.uint8) * 40, (4, 1))
    donor = Image.fromarray(np.repeat(values[..., None], 3, axis=2))
    result, _ = processing.restore_feature(source, donor, np.ones((16, 16)), transform)
    np.testing.assert_array_equal(np.asarray(result)[7, 4:12, 0], [0, 10, 30, 50, 70, 90, 110, 120])


def test_work_mask_maps_to_the_same_original_pixel_centers_as_donor() -> None:
    source = Image.new("RGB", (20, 30), "black")
    _, transform = processing.create_working_crop(
        source, (4, 5, 12, 13), work_size=(16, 16), padding_fraction=0
    )
    mask = np.tile(np.arange(16) / 15, (16, 1))
    _, source_mask = processing.restore_feature(
        source, Image.new("RGB", (4, 4), "white"), mask, transform
    )
    np.testing.assert_allclose(source_mask[7, 4:12], np.arange(1, 30, 4) / 30)


@pytest.mark.parametrize(
    "bbox",
    [
        (-1, 0, 20, 20),
        (0, 0, 101, 20),
        (4, 5, 4, 9),
        (5, 8, 4, 12),
        (0, 0, float("nan"), 20),
        (1, 2, 3),
    ],
)
def test_invalid_face_coordinates_are_rejected(bbox: tuple[float, ...]) -> None:
    with pytest.raises(ValueError, match="bbox"):
        processing.create_working_crop(Image.new("RGB", (100, 100)), bbox)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"padding_fraction": -0.1},
        {"padding_fraction": float("inf")},
        {"work_size": (64, 32)},
        {"work_size": (0, 0)},
        {"work_size": (64.0, 64.0)},
    ],
)
def test_invalid_work_geometry_is_rejected(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        processing.create_working_crop(Image.new("RGB", (100, 100)), (20, 20, 40, 40), **kwargs)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_size", [101, 100]),
        ("crop_box_xyxy", [0, 0, 100, 100]),
        ("source_to_work_scale", 999),
        ("source_to_work_scale", float("nan")),
        ("padding_ltrb", [1, 0, 0, 0]),
        ("version", "unrecognized"),
    ],
)
def test_inconsistent_transform_is_rejected(field: str, value: object) -> None:
    source = Image.new("RGB", (100, 100))
    _, transform = processing.create_working_crop(source, (20, 20, 40, 40), work_size=(64, 64))
    malformed = copy.deepcopy(transform)
    malformed[field] = value
    with pytest.raises(ValueError, match="transform"):
        processing.restore_feature(source, Image.new("RGB", (32, 32)), np.ones((64, 64)), malformed)


@pytest.mark.parametrize(
    "mask",
    [
        np.ones((32, 32)),
        np.full((64, 64), np.nan),
        np.full((64, 64), -0.01),
        np.full((64, 64), 1.01),
        np.full((64, 64), 0.5 + 0.5j),
        np.full((64, 64), "0.5"),
    ],
)
def test_malformed_mask_is_rejected(mask: np.ndarray) -> None:
    source = Image.new("RGB", (100, 100))
    _, transform = processing.create_working_crop(source, (20, 20, 40, 40), work_size=(64, 64))
    with pytest.raises(ValueError, match="mask"):
        processing.restore_feature(source, Image.new("RGB", (32, 32)), mask, transform)
