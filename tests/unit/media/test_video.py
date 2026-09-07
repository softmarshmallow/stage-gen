"""Clip inspection: what is in the container, whether it moves, what it ends on."""

from __future__ import annotations

import io
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from PIL import Image

from stage_gen.media import (
    AudioProcessResult,
    AudioProcessRunner,
    LumaMeasurement,
    MotionMeasurement,
    contact_sheet,
    frame_signature,
    measure_luma,
    measure_motion,
    probe_video,
    scratch_clip,
    signature_distance,
    theora_transcode_args,
)
from stage_gen.media.codec import encode_png

_STREAMS = {
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1280,
            "height": 720,
            "r_frame_rate": "24/1",
            "duration": "10.000000",
        },
        {"codec_type": "audio", "codec_name": "aac", "channels": 2, "sample_rate": 48000},
    ]
}


def _probe_runner(payload: Mapping[str, object]) -> AudioProcessRunner:
    async def runner(command: str, args: Sequence[str], limit: float) -> AudioProcessResult:
        return AudioProcessResult(stdout=json.dumps(payload), stderr="")

    return runner


def _stats_runner(values: Sequence[float]) -> AudioProcessRunner:
    async def runner(command: str, args: Sequence[str], limit: float) -> AudioProcessResult:
        lines = "\n".join(f"lavfi.signalstats.YAVG={v}" for v in values)
        return AudioProcessResult(stdout="", stderr=lines)

    return runner


@pytest.mark.asyncio
async def test_the_probe_reads_the_video_stream_not_the_container() -> None:
    """A generated clip's format runs longer than its picture, by AAC padding.

    Measured on the shell spike: every response reports a format duration five
    to ten milliseconds past the video stream's own. A gate that read the
    format would be measuring the muxer.
    """

    probe = await probe_video(Path("clip.mp4"), runner=_probe_runner(_STREAMS))
    assert (probe.width, probe.height) == (1280, 720)
    assert probe.duration_seconds == 10.0
    assert probe.codec_name == "h264"
    assert probe.frames_per_second == 24.0
    assert probe.video_stream_count == 1
    assert probe.aspect_ratio == pytest.approx(16 / 9)
    # The audio a route generated is recorded as a fact and never played.
    assert probe.audio is not None
    assert (probe.audio.codec_name, probe.audio.channels) == ("aac", 2)


@pytest.mark.asyncio
async def test_a_file_with_no_picture_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="no video stream"):
        await probe_video(
            Path("x.mp4"),
            runner=_probe_runner({"streams": [{"codec_type": "audio", "codec_name": "aac"}]}),
        )
    with pytest.raises(ValueError, match="duration must be positive"):
        await probe_video(
            Path("x.mp4"),
            runner=_probe_runner(
                {
                    "streams": [
                        {
                            "codec_type": "video",
                            "codec_name": "h264",
                            "width": 4,
                            "height": 2,
                            "r_frame_rate": "24/1",
                            "duration": "0",
                        }
                    ]
                }
            ),
        )


@pytest.mark.asyncio
async def test_motion_drops_the_first_sample_and_summarises_the_rest() -> None:
    """The first sample is blended against itself and says nothing about the clip."""

    motion = await measure_motion(Path("c.mp4"), runner=_stats_runner([99.0, 1.0, 2.0, 3.0]))
    assert isinstance(motion, MotionMeasurement)
    assert motion.samples == 3
    assert motion.mean == pytest.approx(2.0)
    assert (motion.minimum, motion.maximum) == (1.0, 3.0)


@pytest.mark.asyncio
async def test_luma_keeps_every_sample_so_a_fade_stays_visible() -> None:
    luma = await measure_luma(Path("c.mp4"), runner=_stats_runner([1.5, 120.0, 197.7]))
    assert isinstance(luma, LumaMeasurement)
    assert luma.samples == 3
    assert (luma.minimum, luma.maximum) == (1.5, 197.7)


@pytest.mark.asyncio
async def test_a_probe_that_read_nothing_is_an_error_not_a_zero() -> None:
    with pytest.raises(ValueError, match="motion probe read no frames"):
        await measure_motion(Path("c.mp4"), runner=_stats_runner([]))
    with pytest.raises(ValueError, match="luma probe read no frames"):
        await measure_luma(Path("c.mp4"), runner=_stats_runner([]))


def _solid(size: tuple[int, int], colour: tuple[int, int, int]) -> bytes:
    return encode_png(Image.new("RGB", size, colour))


def test_a_signature_survives_a_re_encode_and_separates_two_pictures() -> None:
    grey = frame_signature(_solid((320, 180), (120, 120, 120)))
    same = frame_signature(_solid((1920, 1080), (120, 120, 120)))
    other = frame_signature(_solid((320, 180), (20, 40, 30)))
    # Scale is not identity: the same picture at two sizes is the same picture.
    assert signature_distance(grey, same) == 0.0
    assert signature_distance(grey, other) > 80.0
    with pytest.raises(ValueError, match="same non-zero length"):
        signature_distance(grey, grey[:-3])


def test_a_contact_sheet_is_ordered_and_uniform() -> None:
    frames = [_solid((40, 20), c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
    sheet = Image.open(io.BytesIO(contact_sheet(frames, columns=2)))
    assert sheet.size == (80, 40)
    assert sheet.convert("RGB").getpixel((0, 0)) == (255, 0, 0)
    assert sheet.convert("RGB").getpixel((40, 0)) == (0, 255, 0)
    assert sheet.convert("RGB").getpixel((0, 20)) == (0, 0, 255)
    with pytest.raises(ValueError, match="at least one frame"):
        contact_sheet([])


def test_the_publication_transcode_has_no_room_to_repair_anything() -> None:
    """Fixed parameters only: no crop, no trim, no scale, no filter."""

    args = theora_transcode_args(Path("in.mp4"), Path("out.ogv"))
    assert args == [
        "-y",
        "-v",
        "error",
        "-i",
        "in.mp4",
        "-an",
        "-c:v",
        "libtheora",
        "-q:v",
        "6",
        "-f",
        "ogv",
        "out.ogv",
    ]
    for forbidden in ("-vf", "-filter_complex", "-t", "-ss", "-s"):
        assert forbidden not in args
    with pytest.raises(ValueError, match="between 0 and 10"):
        theora_transcode_args(Path("a"), Path("b"), quality=11)


@pytest.mark.asyncio
async def test_a_scratch_clip_is_gone_once_it_has_been_measured() -> None:
    held: Path | None = None
    async with scratch_clip(b"\x00\x00\x00\x18ftypmp42") as scratch:
        held = scratch
        assert scratch.read_bytes().startswith(b"\x00\x00\x00\x18ftyp")
    assert held is not None and not held.exists()
    with pytest.raises(ValueError, match="must be non-empty"):
        async with scratch_clip(b""):
            pass
