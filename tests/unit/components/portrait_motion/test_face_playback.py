"""Native crop placement, single blending, and exact RGBA animation contracts."""

from __future__ import annotations

import io
import json
from dataclasses import replace

import numpy as np
import pytest
from PIL import Image

from stage_gen.components.portrait_motion.face_crop import (
    FloatArray,
    Transform,
    create_working_crop,
)
from stage_gen.components.portrait_motion.face_patches import apply_offset_patch
from stage_gen.components.portrait_motion.face_playback import (
    build_face_combinations,
    encode_face_preview,
)
from stage_gen.components.portrait_motion.models import (
    MotionState,
    PlaybackSegment,
    PortraitMotionSpec,
)


def fixture() -> tuple[
    Image.Image, dict[str, Image.Image], dict[str, FloatArray], PortraitMotionSpec, Transform
]:
    source = Image.new("RGBA", (64, 96), (20, 40, 60, 255))
    source.putpixel((5, 5), (20, 40, 60, 128))
    source.putpixel((6, 6), (123, 44, 55, 0))
    _, transform = create_working_crop(
        source, (0, 0, 16, 16), work_size=(128, 128), padding_fraction=0.5
    )
    masks = {
        name: np.zeros((128, 128)) for name in ("canvas_left_eye", "canvas_right_eye", "mouth")
    }
    masks["canvas_left_eye"][44:68, 44:68] = 0.5
    masks["canvas_left_eye"][48:64, 48:64] = 1
    masks["canvas_right_eye"][48:64, 80:96] = 1
    masks["mouth"][80:96, 64:80] = 1
    donors = {
        name: Image.new("RGB", (64, 64), color)
        for name, color in (
            ("eyes_half", (220, 80, 40)),
            ("eyes_closed", (100, 200, 80)),
            ("mouth_smile", (60, 80, 220)),
            ("mouth_a", (180, 20, 200)),
        )
    }
    spec = PortraitMotionSpec(
        width=128,
        height=128,
        columns=2,
        rows=2,
        states=[
            MotionState(state_id="eyes_half", feature_group="eyes", instruction="Half blink."),
            MotionState(state_id="eyes_closed", feature_group="eyes", instruction="Closed eyes."),
            MotionState(state_id="mouth_smile", feature_group="mouth", instruction="Smile."),
            MotionState(state_id="mouth_a", feature_group="mouth", instruction="Pronounce A."),
        ],
        requested_features=["canvas_left_eye", "canvas_right_eye", "mouth"],
        playback=[
            PlaybackSegment(eyes="rest", mouth="rest", duration_ms=100),
            PlaybackSegment(eyes="eyes_half", mouth="rest", duration_ms=40),
            PlaybackSegment(eyes="eyes_half", mouth="rest", duration_ms=60),
            PlaybackSegment(eyes="eyes_closed", mouth="mouth_a", duration_ms=80),
            PlaybackSegment(eyes="rest", mouth="rest", duration_ms=120),
        ],
    )
    return source, donors, masks, spec, transform


def test_native_offset_patches_keep_alpha_and_feather_once() -> None:
    source, donors, masks, spec, transform = fixture()
    original = source.tobytes()
    result = build_face_combinations(source, donors, masks, spec, transform)
    assert result.offset_xy == (-8, -8)
    assert result.crop_size == (32, 32)
    assert len(result.patches) == 6 and len(result.combinations) == 9
    assert result.combinations[("rest", "rest")].tobytes() == original
    frame = result.combinations[("eyes_half", "rest")]
    assert frame.getpixel((4, 4)) == (220, 80, 40, 255)
    assert frame.getpixel((3, 4)) == (120, 60, 50, 255)
    assert frame.getpixel((5, 5)) == (200, 0, 0, 128)
    assert frame.getpixel((6, 6)) == (123, 44, 55, 0)
    for patch in result.patches.values():
        assert patch.size == result.crop_size and patch.mode == "RGBA"
        assert set(np.unique(np.asarray(patch)[..., 3])) == {0, 255}
    pasted = source.copy()
    for feature in ("canvas_left_eye", "canvas_right_eye"):
        pasted = apply_offset_patch(
            pasted, result.patches[("eyes_half", feature)], result.offset_xy
        )
    assert pasted.tobytes() == frame.tobytes()
    assert source.tobytes() == original
    assert result.exactness["feather_applied_again"] is False
    json.dumps(result.exactness, allow_nan=False)


def test_all_combinations_keep_original_pixels_outside_their_active_groups() -> None:
    source, donors, masks, spec, transform = fixture()
    result = build_face_combinations(source, donors, masks, spec, transform)
    base = np.asarray(source)
    eyes = (result.masks["canvas_left_eye"] > 0) | (result.masks["canvas_right_eye"] > 0)
    mouth = result.masks["mouth"] > 0
    for (eye_state, mouth_state), frame in result.combinations.items():
        pixels = np.asarray(frame)
        active = np.zeros(source.size[::-1], dtype=np.bool_)
        if eye_state != "rest":
            active |= eyes
        if mouth_state != "rest":
            active |= mouth
        np.testing.assert_array_equal(pixels[~active], base[~active])
        np.testing.assert_array_equal(pixels[..., 3], base[..., 3])
        if eye_state != "rest":
            expected = np.asarray(result.combinations[(eye_state, "rest")])
            np.testing.assert_array_equal(pixels[eyes], expected[eyes])
        if mouth_state != "rest":
            expected = np.asarray(result.combinations[("rest", mouth_state)])
            np.testing.assert_array_equal(pixels[mouth], expected[mouth])


def test_absent_features_stay_at_rest_without_inventing_motion() -> None:
    source, donors, masks, spec, transform = fixture()
    result = build_face_combinations(
        source, donors, {"canvas_left_eye": masks["canvas_left_eye"]}, spec, transform
    )
    assert result.exactness["inactive_groups"] == ["mouth"]
    assert len(result.combinations) == 9 and len(result.patches) == 2
    for eye_state in ("rest", "eyes_half", "eyes_closed"):
        for mouth_state in ("rest", "mouth_smile", "mouth_a"):
            assert (
                result.combinations[(eye_state, mouth_state)].tobytes()
                == result.combinations[(eye_state, "rest")].tobytes()
            )
    _, facts = encode_face_preview(result, spec)
    assert facts["active_features"] == {"eyes": ["canvas_left_eye"], "mouth": []}
    assert facts["inactive_groups"] == ["mouth"]


def test_lossless_preview_preserves_native_visible_rgba_and_exact_holds() -> None:
    source, donors, masks, spec, transform = fixture()
    result = build_face_combinations(source, donors, masks, spec, transform)
    data, facts = encode_face_preview(result, spec)
    assert facts["frames"] == 4 and facts["duration_ms"] == 400
    assert facts["logical_segment_count"] == 5 and facts["size"] == [64, 96]
    assert facts["encoded_segments"][1] == {
        "segment_start": 1,
        "segment_end_exclusive": 3,
        "duration_ms": 100,
    }
    assert facts["temporal_review"] == "not_performed"
    expected_keys = [
        ("rest", "rest"),
        ("eyes_half", "rest"),
        ("eyes_closed", "mouth_a"),
        ("rest", "rest"),
    ]
    with Image.open(io.BytesIO(data)) as decoded:
        assert decoded.size == source.size and getattr(decoded, "n_frames", 0) == 4
        assert decoded.info["loop"] == 0
        for index, (key, duration) in enumerate(
            zip(expected_keys, [100, 100, 80, 120], strict=True)
        ):
            decoded.seek(index)
            decoded.load()
            actual = np.asarray(decoded.convert("RGBA"))
            expected = np.asarray(result.combinations[key])
            visible = expected[..., 3] > 0
            np.testing.assert_array_equal(actual[..., 3], expected[..., 3])
            np.testing.assert_array_equal(actual[visible], expected[visible])
            assert decoded.info["duration"] == duration
    json.dumps(facts, allow_nan=False)


def test_static_timeline_is_not_reported_as_animation() -> None:
    source, donors, _, spec, transform = fixture()
    result = build_face_combinations(source, donors, {}, spec, transform)
    with pytest.raises(ValueError, match="no visible motion"):
        encode_face_preview(result, spec)


def test_overlapping_or_empty_admitted_masks_are_refused() -> None:
    source, donors, masks, spec, transform = fixture()
    masks["canvas_right_eye"] = masks["canvas_left_eye"].copy()
    with pytest.raises(ValueError, match="overlap"):
        build_face_combinations(source, donors, masks, spec, transform)
    with pytest.raises(ValueError, match="nonempty"):
        build_face_combinations(source, donors, {"mouth": np.zeros((128, 128))}, spec, transform)


def test_donor_set_panel_size_and_work_canvas_are_checked() -> None:
    source, donors, masks, spec, transform = fixture()
    with pytest.raises(ValueError, match="complete declared state set"):
        build_face_combinations(source, {"eyes_half": donors["eyes_half"]}, masks, spec, transform)
    wrong = {**donors, "eyes_half": Image.new("RGB", (32, 32))}
    with pytest.raises(ValueError, match="declared panel size"):
        build_face_combinations(source, wrong, masks, spec, transform)
    _, other_transform = create_working_crop(
        source, (0, 0, 16, 16), work_size=(256, 256), padding_fraction=0.5
    )
    with pytest.raises(ValueError, match="work_size"):
        build_face_combinations(source, donors, masks, spec, other_transform)


@pytest.mark.parametrize("value", [float("nan"), -0.1, 1.1])
def test_malformed_work_mask_is_refused(value: float) -> None:
    source, donors, _, spec, transform = fixture()
    with pytest.raises(ValueError, match="mask"):
        build_face_combinations(
            source, donors, {"mouth": np.full((128, 128), value)}, spec, transform
        )


def test_preview_refuses_incomplete_frames_or_changes_outside_their_masks() -> None:
    source, donors, masks, spec, transform = fixture()
    result = build_face_combinations(source, donors, masks, spec, transform)
    incomplete = dict(result.combinations)
    del incomplete[("eyes_half", "rest")]
    with pytest.raises(ValueError, match="complete declared Cartesian"):
        encode_face_preview(replace(result, combinations=incomplete), spec)
    changed = dict(result.combinations)
    changed[("eyes_half", "rest")] = changed[("eyes_half", "rest")].copy()
    changed[("eyes_half", "rest")].putpixel((50, 80), (1, 2, 3, 255))
    with pytest.raises(ValueError, match="outside active feature support"):
        encode_face_preview(replace(result, combinations=changed), spec)
    changed[("eyes_half", "rest")].putpixel((50, 80), (1, 2, 3, 128))
    with pytest.raises(ValueError, match="original alpha"):
        encode_face_preview(replace(result, combinations=changed), spec)
