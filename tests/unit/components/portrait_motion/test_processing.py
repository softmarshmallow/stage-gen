"""Synthetic correctness gates for portrait registration and localized replacement."""

from __future__ import annotations

import io
import json
from typing import cast

import numpy as np
import pytest
from PIL import Image
from scipy.ndimage import gaussian_filter

from stage_gen.components.portrait_motion.processing import (
    composite,
    geometry_masks,
    heatmap,
    make_guide,
    png_bytes,
    split_register,
)


def textured(size: tuple[int, int] = (160, 192)) -> Image.Image:
    rng = np.random.default_rng(7319)
    noise = gaussian_filter(rng.normal(0, 1, (size[1], size[0])), 1.4)
    plane = np.clip(np.rint(128 + noise / noise.std() * 32), 0, 255).astype(np.uint8)
    return Image.fromarray(np.repeat(plane[..., None], 3, axis=2))


def box(feature_id: str, x: float, y: float, size: float = 8) -> dict[str, object]:
    return {
        "feature_id": feature_id,
        "points": [[x, y], [x + size, y], [x + size, y + size], [x, y + size]],
    }


def test_guide_has_identical_cells_without_modifying_source() -> None:
    source = textured()
    before = png_bytes(source)
    guide = make_guide(source, 2, 2)
    expected = source.resize((80, 96), Image.Resampling.LANCZOS)
    assert guide.size == source.size
    for y in (0, 96):
        for x in (0, 80):
            assert np.array_equal(
                np.asarray(guide.crop((x, y, x + 80, y + 96))), np.asarray(expected)
            )
    assert png_bytes(source) == before


@pytest.mark.parametrize("columns,rows", [(0, 2), (2, -1), (3, 2), (True, 2)])
def test_invalid_grid_is_rejected(columns: int, rows: int) -> None:
    with pytest.raises(ValueError):
        make_guide(textured(), columns, rows)


def test_split_state_order_and_failed_fit_evidence_remain_inspectable() -> None:
    source = Image.new("RGB", (40, 60), (100, 100, 100))
    atlas = Image.new("RGB", (80, 120))
    colors = [(20, 30, 40), (50, 60, 70), (80, 90, 100), (110, 120, 130)]
    states = ["half", "closed", "smile", "a"]
    for index, color in enumerate(colors):
        atlas.paste(Image.new("RGB", (40, 60), color), (index % 2 * 40, index // 2 * 60))
    donors, reports = split_register(source, atlas, states, 2, 2)
    assert list(donors) == states
    for index, state in enumerate(states):
        assert donors[state].size == (40, 60)
        assert donors[state].getpixel((10, 10)) == colors[index]
        assert reports[state]["status"] == "failed_technical_gate"
        assert reports[state]["failed_checks"] == ["insufficient_source_texture"]
        assert reports[state]["optimizer_evaluations"] == 0
    json.dumps(reports, allow_nan=False)


def test_known_translation_is_recovered_and_footprint_is_explicit() -> None:
    source = textured()
    current = Image.new("RGB", source.size)
    current.paste(source, (5, -3))
    donors, reports = split_register(source, current, ["closed"], 1, 1)
    record = reports["closed"]
    assert record["status"] == "passed_technical_gate", record
    transform = cast(dict[str, object], record["current_to_reference"])
    shift = cast(list[float], transform["translation_xy_panel_px"])
    assert shift == pytest.approx([-5.0, 3.0], abs=0.3)
    assert transform["scale"] == pytest.approx(1.0, abs=0.003)
    assert transform["rotation_degrees"] == pytest.approx(0.0, abs=0.03)
    valid = np.zeros((source.height, source.width), dtype=bool)
    for y, first, stop in cast(list[list[int]], record["valid_panel_rows"]):
        assert 0 <= first < stop <= source.width
        valid[y, first:stop] = True
    assert float(valid.mean()) == record["valid_fraction"]
    assert 0.9 < float(valid.mean()) < 1
    difference = np.abs(np.asarray(donors["closed"], float) - np.asarray(source, float))
    assert float(difference[valid].mean()) < 1.0
    assert record["semantic_acceptance"] == "not_granted"
    json.dumps(reports, allow_nan=False)


@pytest.mark.parametrize("states", [["a", "a"], [""], []])
def test_invalid_states_are_rejected(states: list[str]) -> None:
    source = textured()
    with pytest.raises(ValueError):
        split_register(source, source, states, 1, 1)


@pytest.mark.parametrize(
    "policy",
    [
        {"unknown_option": 1},
        {"source_sample_stride": 0},
        {"scale_limits": [1, 1.1]},
        {"trimmed_fraction": 2},
        {"soft_l1_scale": float("nan")},
    ],
)
def test_invalid_registration_policy_is_rejected(policy: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        split_register(textured(), textured(), ["closed"], 1, 1, policy)


def test_one_admitted_eye_does_not_invent_other_features() -> None:
    masks, metrics = geometry_masks([box("canvas_right_eye", 30, 25)], (200, 300), (100, 150), 3)
    assert list(masks) == ["canvas_right_eye"]
    alpha = masks["canvas_right_eye"]
    assert alpha.shape == (300, 200)
    assert alpha[55, 65] == 1
    assert 0 < alpha[55, 59] < 1
    assert alpha[0, 0] == 0
    assert metrics["canvas_right_eye"]["core_alpha_min"] == 1.0
    assert metrics["canvas_right_eye"]["support_source_pixels"] == int((alpha > 0).sum())
    assert np.array_equal(np.rint(alpha * 255), alpha * 255)
    assert geometry_masks([], (200, 300), (100, 150), 3) == ({}, {})


@pytest.mark.parametrize(
    "points",
    [
        [[1, 1], [2, 2]],
        [[1, 1], [5, 1], [1, 1]],
        [[1, 1], [2, 2], [3, 3]],
        [[10, 10], [20, 20], [10, 20], [20, 10]],
        [[-1, 1], [5, 1], [5, 5]],
        [[1, 1], [100, 1], [5, 5]],
        [[1, 1], [5, 1], [float("nan"), 5]],
        [[1, 1], [5, 1], [True, 5]],
    ],
)
def test_invalid_polygon_is_rejected(points: list[list[float]]) -> None:
    with pytest.raises(ValueError):
        geometry_masks([{"feature_id": "mouth", "points": points}], (200, 200), (100, 100), 3)


def test_feature_area_and_ids_are_bounded() -> None:
    with pytest.raises(ValueError, match="area"):
        geometry_masks([box("mouth", 5, 5, 60)], (200, 200), (100, 100), 3)
    with pytest.raises(ValueError, match="unique"):
        geometry_masks([box("mouth", 5, 5), box("mouth", 30, 30)], (200, 200), (100, 100), 3)
    with pytest.raises(ValueError, match="Unsupported"):
        geometry_masks([box("hidden_eye", 5, 5)], (200, 200), (100, 100), 3)
    with pytest.raises(ValueError, match="Combined eye area"):
        geometry_masks(
            [
                box("canvas_left_eye", 10, 10, 21),
                box("canvas_right_eye", 60, 10, 21),
            ],
            (200, 200),
            (100, 100),
            0,
        )


def test_disjoint_cores_with_overlapping_feathers_are_rejected() -> None:
    features = [box("canvas_left_eye", 20, 20, 4), box("canvas_right_eye", 26, 20, 4)]
    masks, _ = geometry_masks(features, (100, 100), (100, 100), 0)
    assert not ((masks["canvas_left_eye"] > 0) & (masks["canvas_right_eye"] > 0)).any()
    with pytest.raises(ValueError, match="including their feather"):
        geometry_masks(features, (100, 100), (100, 100), 3)


def test_feather_measured_in_panel_space_with_unequal_scale() -> None:
    masks, _ = geometry_masks([box("mouth", 20, 20, 5)], (200, 300), (100, 100), 3)
    alpha = masks["mouth"]
    # Both samples are exactly one panel pixel outside the opaque rectangle.
    assert alpha[66, 38] == alpha[57, 44] == pytest.approx(170 / 255)


def test_source_exterior_donor_core_and_feature_order_are_exact() -> None:
    source = textured((200, 240))
    red = Image.new("RGB", (100, 120), (240, 80, 60))
    blue = Image.new("RGB", (100, 120), (30, 60, 220))
    masks, _ = geometry_masks(
        [
            box("canvas_left_eye", 25, 25),
            box("mouth", 45, 70),
        ],
        source.size,
        red.size,
        3,
    )
    eye, mouth = masks["canvas_left_eye"], masks["mouth"]
    eye_frame = composite(source, red, eye)
    actual = np.asarray(eye_frame)
    original = np.asarray(source)
    resized = np.asarray(red.resize(source.size, Image.Resampling.LANCZOS))
    assert np.array_equal(actual[eye == 0], original[eye == 0])
    assert np.array_equal(actual[eye == 1], resized[eye == 1])
    eye_then_mouth = composite(eye_frame, blue, mouth)
    mouth_then_eye = composite(composite(source, blue, mouth), red, eye)
    assert np.array_equal(np.asarray(eye_then_mouth), np.asarray(mouth_then_eye))
    untouched = (eye == 0) & (mouth == 0)
    assert np.array_equal(np.asarray(eye_then_mouth)[untouched], original[untouched])
    with Image.open(io.BytesIO(png_bytes(eye_then_mouth))) as decoded:
        assert decoded.format == "PNG"
        assert np.array_equal(np.asarray(decoded), np.asarray(eye_then_mouth))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_alpha_is_rejected(value: float) -> None:
    image = Image.new("RGB", (10, 12))
    alpha = np.zeros((12, 10))
    alpha[3, 3] = value
    with pytest.raises(ValueError, match="Alpha"):
        composite(image, image, alpha)


def test_alpha_dimensions_and_transparency_are_rejected() -> None:
    source = Image.new("RGB", (10, 12))
    with pytest.raises(ValueError, match="dimensions"):
        composite(source, source, np.zeros((10, 12)))
    transparent = Image.new("RGBA", source.size, (100, 20, 30, 0))
    with pytest.raises(ValueError, match="opaque"):
        composite(source, transparent, np.zeros((12, 10)))
    with pytest.raises(ValueError, match="opaque"):
        make_guide(transparent, 2, 2)


def test_heatmap_uses_fixed_rgb_knots_without_per_image_normalization() -> None:
    source = Image.new("RGB", (7, 1))
    values = [0, 4, 8, 16, 32, 64, 255]
    donor = Image.fromarray(np.array([[(value, 0, 0) for value in values]], dtype=np.uint8))
    result = np.asarray(heatmap(source, donor))
    assert result.tolist() == [
        [
            [0, 0, 0],
            [30, 12, 75],
            [89, 24, 110],
            [182, 45, 79],
            [247, 121, 36],
            [255, 249, 173],
            [255, 249, 173],
        ]
    ]
    assert heatmap(Image.new("RGB", (14, 2)), donor).size == donor.size
    with pytest.raises(ValueError):
        heatmap(source, donor, 0)
