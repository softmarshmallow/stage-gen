"""Lossless timing and independent feature-selection checks using synthetic pixels."""

from __future__ import annotations

import io
import json
from typing import cast

import numpy as np
import pytest
from PIL import Image

from stage_gen.components.portrait_motion.models import (
    FeatureGroup,
    MotionState,
    PlaybackSegment,
    PortraitMotionSpec,
)
from stage_gen.components.portrait_motion.playback import (
    build_combinations,
    encode_playback,
    encode_preview,
)
from stage_gen.components.portrait_motion.processing import FloatArray, composite, geometry_masks


def fixture() -> tuple[
    Image.Image, dict[str, Image.Image], dict[str, FeatureGroup], dict[str, FloatArray]
]:
    source = Image.new("RGB", (128, 192), (90, 120, 160))
    masks, _ = geometry_masks(
        [
            {"feature_id": "canvas_right_eye", "points": [[30, 20], [38, 20], [38, 28], [30, 28]]},
            {"feature_id": "mouth", "points": [[24, 60], [32, 60], [32, 68], [24, 68]]},
        ],
        source.size,
        (64, 96),
        3,
    )
    frames = {
        "closed": composite(
            source, Image.new("RGB", (64, 96), (220, 60, 80)), masks["canvas_right_eye"]
        ),
        "a": composite(source, Image.new("RGB", (64, 96), (40, 210, 80)), masks["mouth"]),
    }
    return source, frames, {"closed": "eyes", "a": "mouth"}, masks


def segment(eyes: str = "rest", mouth: str = "rest", duration: int = 100) -> PlaybackSegment:
    return PlaybackSegment(eyes=eyes, mouth=mouth, duration_ms=duration)


def test_lossless_playback_coalesces_equal_segments_and_preserves_timing() -> None:
    source, frames, groups, masks = fixture()
    data, manifest = encode_playback(
        source,
        frames,
        groups,
        masks,
        [
            segment(),
            segment("closed", duration=50),
            segment("closed", duration=50),
            segment("closed", "a", 80),
            segment(),
        ],
    )
    assert manifest["encoded_frame_count"] == 4
    assert manifest["logical_segment_count"] == 5
    assert manifest["total_duration_ms"] == 380
    assert manifest["feather_applied_again"] is False
    assert manifest["active_features"] == {"eyes": ["canvas_right_eye"], "mouth": ["mouth"]}
    assert manifest["audio_synchronized"] is False
    assert manifest["semantic_acceptance"] == "not_granted"
    records = cast(list[dict[str, object]], manifest["encoded_segments"])
    assert [(row["segment_start"], row["segment_end_exclusive"]) for row in records] == [
        (0, 1),
        (1, 3),
        (3, 4),
        (4, 5),
    ]
    with Image.open(io.BytesIO(data)) as decoded:
        assert getattr(decoded, "is_animated", False)
        assert decoded.info["loop"] == 0
        expected_durations = [100, 100, 80, 100]
        for index in range(getattr(decoded, "n_frames", 0)):
            decoded.seek(index)
            decoded.load()
            assert decoded.info["duration"] == expected_durations[index]
            pixels = np.asarray(decoded.convert("RGB"))
            if index in (0, 3):
                assert np.array_equal(pixels, np.asarray(source))
            elif index == 1:
                # The feathered edge must equal its saved frame, not a second blend.
                assert np.array_equal(pixels, np.asarray(frames["closed"]))
            else:
                expected = np.asarray(source).copy()
                eye, mouth = masks["canvas_right_eye"] > 0, masks["mouth"] > 0
                expected[eye] = np.asarray(frames["closed"])[eye]
                expected[mouth] = np.asarray(frames["a"])[mouth]
                assert np.array_equal(pixels, expected)
    json.dumps(manifest, allow_nan=False)


def test_one_eye_only_playback_leaves_hidden_eye_and_mouth_source_exact() -> None:
    source, frames, _, masks = fixture()
    data, manifest = encode_playback(
        source,
        {"closed": frames["closed"]},
        {"closed": "eyes"},
        {"canvas_right_eye": masks["canvas_right_eye"]},
        [segment(), segment("closed"), segment()],
    )
    assert manifest["inactive_groups"] == ["mouth"]
    with Image.open(io.BytesIO(data)) as decoded:
        decoded.seek(1)
        decoded.load()
        actual = np.asarray(decoded.convert("RGB"))
        outside = masks["canvas_right_eye"] == 0
        assert np.array_equal(actual[outside], np.asarray(source)[outside])


def test_inactive_group_is_explicit_and_never_paints_from_a_noop_state() -> None:
    source, frames, groups, masks = fixture()
    frames["a"] = source.copy()
    _, manifest = encode_playback(
        source,
        frames,
        groups,
        {"canvas_right_eye": masks["canvas_right_eye"]},
        [segment(), segment("closed", "a"), segment()],
    )
    assert manifest["inactive_groups"] == ["mouth"]


def test_preview_preserves_resized_source_endpoints_and_duration() -> None:
    source, frames, groups, masks = fixture()
    data, manifest = encode_playback(
        source, frames, groups, masks, [segment(), segment("closed"), segment()], size=(64, 96)
    )
    assert manifest["size"] == [64, 96]
    expected = source.resize((64, 96), Image.Resampling.LANCZOS)
    with Image.open(io.BytesIO(data)) as decoded:
        for index in (0, getattr(decoded, "n_frames", 0) - 1):
            decoded.seek(index)
            decoded.load()
            assert np.array_equal(np.asarray(decoded.convert("RGB")), np.asarray(expected))


def test_all_rest_refuses_static_animation_claim() -> None:
    source, frames, groups, masks = fixture()
    with pytest.raises(ValueError, match="no visible motion"):
        encode_playback(source, frames, groups, masks, [segment(), segment()])


@pytest.mark.parametrize(
    "segments",
    [
        [],
        [segment("closed"), segment()],
        [segment(), segment("closed")],
        [segment(), segment("a"), segment()],
        [segment(), segment("unknown"), segment()],
        [segment(duration=10000)] * 7,
    ],
)
def test_invalid_timeline_is_rejected(segments: list[PlaybackSegment]) -> None:
    source, frames, groups, masks = fixture()
    with pytest.raises(ValueError):
        encode_playback(source, frames, groups, masks, segments)


def test_foreign_frame_pixels_are_rejected_before_encoding() -> None:
    source, frames, groups, masks = fixture()
    frames["closed"].putpixel((0, 0), (1, 2, 3))
    with pytest.raises(ValueError, match="outside its group"):
        encode_playback(source, frames, groups, masks, [segment(), segment("closed"), segment()])


def test_frame_dimensions_and_declarations_must_agree() -> None:
    source, frames, groups, masks = fixture()
    frames["closed"] = frames["closed"].resize((64, 96))
    with pytest.raises(ValueError, match="dimensions"):
        encode_playback(source, frames, groups, masks, [segment(), segment("closed"), segment()])
    with pytest.raises(ValueError, match="declarations"):
        encode_playback(source, {}, groups, masks, [segment(), segment()])


def test_overlapping_or_malformed_masks_are_rejected() -> None:
    source, frames, groups, masks = fixture()
    masks["mouth"] = masks["canvas_right_eye"].copy()
    with pytest.raises(ValueError, match="overlap"):
        encode_playback(source, frames, groups, masks, [segment(), segment("closed"), segment()])
    masks["mouth"] = np.zeros((12, 12))
    with pytest.raises(ValueError, match="shape"):
        encode_playback(source, frames, groups, masks, [segment(), segment("closed"), segment()])
    masks["mouth"] = np.zeros((192, 128))
    with pytest.raises(ValueError, match="nonempty"):
        encode_playback(source, frames, groups, masks, [segment(), segment("closed"), segment()])


def test_invalid_preview_size_is_rejected() -> None:
    source, frames, groups, masks = fixture()
    with pytest.raises(ValueError, match="positive integer"):
        encode_playback(
            source, frames, groups, masks, [segment(), segment("closed"), segment()], size=(0, 96)
        )


def specification() -> PortraitMotionSpec:
    return PortraitMotionSpec(
        width=128,
        height=192,
        columns=2,
        rows=2,
        states=[
            MotionState(state_id="half", feature_group="eyes", instruction="Half blink"),
            MotionState(state_id="closed", feature_group="eyes", instruction="Close eyes"),
            MotionState(state_id="smile", feature_group="mouth", instruction="Small smile"),
            MotionState(state_id="a", feature_group="mouth", instruction="Open mouth"),
        ],
        requested_features=["canvas_right_eye", "mouth"],
        playback=[segment(), segment("half"), segment("closed", "a"), segment()],
    )


def panel_donors() -> dict[str, Image.Image]:
    return {
        state: Image.new("RGB", (64, 96), color)
        for state, color in zip(
            ("half", "closed", "smile", "a"),
            ((130, 30, 70), (220, 60, 80), (140, 40, 20), (40, 210, 80)),
            strict=True,
        )
    }


def test_graph_wrappers_build_all_combinations_and_verified_preview() -> None:
    source, _, _, masks = fixture()
    spec = specification()
    donors = panel_donors()
    combinations, facts = build_combinations(source, donors, masks, spec)
    assert len(combinations) == 9
    assert np.array_equal(np.asarray(combinations[("rest", "rest")]), np.asarray(source))
    assert facts["native_source_outside_active_alpha_exact"] is True
    assert facts["native_donor_opaque_cores_exact"] is True
    assert facts["composition_order_pixel_identical"] is True
    for (eyes, mouth), image in combinations.items():
        pixels = np.asarray(image)
        active = np.zeros((source.height, source.width), dtype=bool)
        for state, mask in ((eyes, masks["canvas_right_eye"]), (mouth, masks["mouth"])):
            if state != "rest":
                active |= mask > 0
                expected = np.asarray(donors[state].resize(source.size, Image.Resampling.LANCZOS))
                assert np.array_equal(pixels[mask == 1], expected[mask == 1])
        assert np.array_equal(pixels[~active], np.asarray(source)[~active])
    data, report = encode_preview(combinations, spec)
    assert report["size"] == [64, 96]
    assert report["total_duration_ms"] == 400
    with Image.open(io.BytesIO(data)) as decoded:
        assert getattr(decoded, "is_animated", False) and getattr(decoded, "n_frames", 0) == 4
        assert decoded.size == (64, 96)


def test_graph_wrapper_retains_inactive_group_combinations_without_painting() -> None:
    source, _, _, masks = fixture()
    combinations, facts = build_combinations(
        source, panel_donors(), {"canvas_right_eye": masks["canvas_right_eye"]}, specification()
    )
    assert len(combinations) == 9
    assert facts["inactive_groups"] == ["mouth"]
    assert np.array_equal(np.asarray(combinations[("rest", "a")]), np.asarray(source))
    assert np.array_equal(
        np.asarray(combinations[("closed", "a")]), np.asarray(combinations[("closed", "rest")])
    )


def test_graph_wrapper_rejects_missing_states_and_wrong_donor_dimensions() -> None:
    source, _, _, masks = fixture()
    spec = specification()
    with pytest.raises(ValueError, match="complete declared state set"):
        build_combinations(source, {}, masks, spec)
    donors = panel_donors()
    donors["half"] = donors["half"].resize(source.size)
    with pytest.raises(ValueError, match="declared panel size"):
        build_combinations(source, donors, masks, spec)
    combinations, _ = build_combinations(source, panel_donors(), masks, spec)
    del combinations[("half", "smile")]
    with pytest.raises(ValueError, match="complete declared Cartesian"):
        encode_preview(combinations, spec)
