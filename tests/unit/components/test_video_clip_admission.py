"""The clip gates: shape, and the one failure no still ever had."""

from __future__ import annotations

import pytest

from stage_gen.components.video_clip import (
    CLIP_MOTION_FLOOR_MEAN,
    ClipAdmissionError,
    clip_admission_facts,
)
from stage_gen.media import ClipAudioTrack, LumaMeasurement, MotionMeasurement, VideoProbe


def _probe(**overrides: object) -> VideoProbe:
    fields: dict[str, object] = {
        "duration_seconds": 10.0,
        "width": 1920,
        "height": 1080,
        "codec_name": "theora",
        "frames_per_second": 24.0,
        "video_stream_count": 1,
        "audio": None,
    }
    fields.update(overrides)
    return VideoProbe(**fields)  # type: ignore[arg-type]


def _motion(mean: float = 0.44) -> MotionMeasurement:
    return MotionMeasurement(mean=mean, median=mean, minimum=mean / 2, maximum=mean * 2, samples=79)


def _luma(mean: float = 107.5, minimum: float = 1.5, maximum: float = 197.7) -> LumaMeasurement:
    return LumaMeasurement(mean=mean, minimum=minimum, maximum=maximum, samples=20)


def _admit(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "probe": _probe(),
        "motion": _motion(),
        "luma": _luma(),
        "expected_seconds": 10.0,
        "expected_size": (1920, 1080),
        "expected_codec": "theora",
    }
    fields.update(overrides)
    probe = fields.pop("probe")
    motion = fields.pop("motion")
    luma = fields.pop("luma")
    return clip_admission_facts(probe, motion, luma, **fields)  # type: ignore[arg-type]


def test_a_still_encoded_as_video_is_refused() -> None:
    """The failure this component exists for, and the one nothing else catches.

    Measured on the shell spike: a still encoded as video reads 0.0004 as h264
    and 0.0011 through Theora, while the quietest clip anyone wanted reads
    0.4405. The floor sits between them with 45x and 8.8x of room.
    """

    with pytest.raises(ClipAdmissionError, match="barely moves"):
        _admit(motion=_motion(0.0011))
    # ...and the clip that was actually wanted is admitted.
    assert _admit(motion=_motion(0.4405))["motion_mean"] == 0.4405
    assert CLIP_MOTION_FLOOR_MEAN == 0.05


def test_a_clip_that_opens_on_darkness_is_not_an_empty_clip() -> None:
    """A per-frame luma band would refuse a fade, which is a real shot."""

    admitted = _admit(luma=_luma(mean=107.5, minimum=1.5, maximum=226.6))
    assert admitted["luma_minimum"] == 1.5

    with pytest.raises(ClipAdmissionError, match="outside the"):
        _admit(luma=_luma(mean=2.0, minimum=0.0, maximum=4.0))
    with pytest.raises(ClipAdmissionError, match="outside the"):
        _admit(luma=_luma(mean=250.0, minimum=245.0, maximum=255.0))


def test_shape_refusals_name_what_was_wrong() -> None:
    with pytest.raises(ClipAdmissionError, match="carries 2"):
        _admit(probe=_probe(video_stream_count=2))
    with pytest.raises(ClipAdmissionError, match="h264 where theora"):
        _admit(probe=_probe(codec_name="h264"))
    with pytest.raises(ClipAdmissionError, match=r"runs 10\.000s against an asked-for 4\.000s"):
        _admit(expected_seconds=4.0)
    with pytest.raises(ClipAdmissionError, match="1920x1080 where the layout declares"):
        _admit(expected_size=(1280, 720))
    with pytest.raises(ClipAdmissionError, match="16:9"):
        _admit(probe=_probe(width=1920, height=1440), expected_size=(1920, 1440))


def test_a_frame_of_length_tolerance_is_allowed_and_two_are_not() -> None:
    """Asked for in whole seconds, answered to the frame: 24 fps is 0.042 s."""

    assert _admit(probe=_probe(duration_seconds=10.1))["duration_seconds"] == 10.1
    with pytest.raises(ClipAdmissionError, match=r"runs 10\.300s"):
        _admit(probe=_probe(duration_seconds=10.3))


def test_the_audio_a_route_generated_is_recorded_not_refused() -> None:
    """The transcode drops it; saying what was dropped is what makes that auditable."""

    facts = _admit(
        probe=_probe(
            codec_name="h264",
            audio=ClipAudioTrack(codec_name="aac", channels=2, sample_rate=48000),
        ),
        expected_codec="h264",
    )
    assert facts["source_audio"] == {"codec": "aac", "channels": 2, "sample_rate": 48000}
    assert _admit()["source_audio"] is None
