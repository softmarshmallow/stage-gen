"""Objective admission for a generated clip.

Five facts a decoder can state about a clip, each refusing rather than
repairing. Four are shape - one video stream, the expected codec, the picture
size the layout declared, and a length within a frame of what was asked for.
The fifth is the one that matters and the one no still ever needed: **does it
move**. A video route answering a clip brief with a beautiful still is the
failure this component exists to catch, and it is invisible to every other
check in the tree.

Whether the clip is *good* is a person's call and a reviewer's, never inferred
here. So is whether any lettering crept into a frame: no gate can read a frame
for text, and one that pretended to would be worse than none.

Every constant carries the measurement that set it. They were taken on the
shell spike's own clips - fifteen generated files and a synthesized still - and
re-taken after the Theora transcode, because the picture a player sees is the
published one and the gates run on both.
"""

from __future__ import annotations

import math
from pathlib import Path

from stage_gen.media import (
    LumaMeasurement,
    MotionMeasurement,
    VideoProbe,
    measure_luma,
    measure_motion,
    probe_video,
    scratch_clip,
)

#: A clip is asked for in whole seconds and answered to the frame. At 24 fps one
#: frame is 0.042 s; measured, every spike response landed on its ask exactly.
CLIP_DURATION_TOLERANCE_SECONDS = 0.20

#: 16:9, and tightly. Both canvases in the shell are 16:9, which is what lets a
#: card band published against one land in the same place over the other.
CLIP_ASPECT_RATIO = 16 / 9
CLIP_ASPECT_TOLERANCE = 0.005

#: Mean sample-to-sample difference, 0-255. Measured: a still encoded as video
#: reads 0.0004 as h264 and 0.0011 through Theora; the quietest clip anyone
#: actually wanted - "the smallest motion that still reads as alive" - reads
#: 0.4405; a cut trailer reads 5.8. This floor sits 45x above the still and
#: 8.8x below the quiet clip. A "sensible" 1.0 would have refused the good one.
CLIP_MOTION_FLOOR_MEAN = 0.05

#: Mean luma over the clip, and a band at least one sample must sit inside.
#: Measured: a multi-beat clip dips to YAVG 1.5 at a fade and peaks at 226.6 at
#: a flare, so a per-frame band would refuse a fade. Judging the mean, plus
#: requiring one frame that is neither black nor blown out, refuses an empty
#: return without refusing a clip that opens or closes on darkness.
CLIP_LUMA_MEAN_BAND = (16.0, 235.0)
CLIP_LUMA_LIVE_FRAME_BAND = (24.0, 224.0)


class ClipAdmissionError(ValueError):
    """A generated clip that cannot be published as it stands."""


def clip_admission_facts(
    probe: VideoProbe,
    motion: MotionMeasurement,
    luma: LumaMeasurement,
    *,
    expected_seconds: float,
    expected_size: tuple[int, int] | None = None,
    expected_codec: str | None = None,
    expected_aspect_ratio: float | None = None,
) -> dict[str, object]:
    """The verdict, as the facts that produced it.

    ``expected_size`` is the layout's canvas and ``expected_codec`` whichever
    codec this pass is checking - the route's on the way in, Theora on the way
    out. Both are optional so the same function serves both passes.
    """

    if probe.video_stream_count != 1:
        raise ClipAdmissionError(
            f"a clip carries one picture; this one carries {probe.video_stream_count}"
        )
    if expected_codec is not None and probe.codec_name != expected_codec:
        raise ClipAdmissionError(f"clip is {probe.codec_name} where {expected_codec} was expected")
    duration = round(probe.duration_seconds, 3)
    if abs(duration - expected_seconds) > CLIP_DURATION_TOLERANCE_SECONDS:
        raise ClipAdmissionError(
            f"clip runs {duration:.3f}s against an asked-for {expected_seconds:.3f}s"
        )
    if expected_size is not None and (probe.width, probe.height) != expected_size:
        raise ClipAdmissionError(
            f"clip is {probe.width}x{probe.height} where the layout declares "
            f"{expected_size[0]}x{expected_size[1]}"
        )
    if expected_aspect_ratio is not None:
        if not math.isfinite(expected_aspect_ratio) or expected_aspect_ratio <= 0:
            raise ValueError("expected_aspect_ratio must be a positive finite number")
        if abs(probe.aspect_ratio - expected_aspect_ratio) > CLIP_ASPECT_TOLERANCE:
            raise ClipAdmissionError(
                f"clip aspect ratio is {probe.aspect_ratio:.4f}, "
                f"expected {expected_aspect_ratio:.4f}"
            )
    if motion.mean < CLIP_MOTION_FLOOR_MEAN:
        raise ClipAdmissionError(
            f"clip barely moves: mean sample difference {motion.mean:.4f} is under the "
            f"{CLIP_MOTION_FLOOR_MEAN} floor, which is what a still encoded as video reads"
        )
    low, high = CLIP_LUMA_MEAN_BAND
    if not low <= luma.mean <= high:
        raise ClipAdmissionError(
            f"clip averages luma {luma.mean:.1f}, outside the {low}-{high} band"
        )
    live_low, live_high = CLIP_LUMA_LIVE_FRAME_BAND
    if not any(live_low <= value <= live_high for value in (luma.mean, luma.minimum, luma.maximum)):
        raise ClipAdmissionError(
            "no sampled frame of the clip is a lit picture; it is black or blown out throughout"
        )
    facts: dict[str, object] = {
        "duration_seconds": duration,
        "width": probe.width,
        "height": probe.height,
        "codec": probe.codec_name,
        "frames_per_second": round(probe.frames_per_second, 3),
        "motion_mean": round(motion.mean, 4),
        "motion_minimum": round(motion.minimum, 4),
        "motion_samples": motion.samples,
        "luma_mean": round(luma.mean, 2),
        "luma_minimum": round(luma.minimum, 2),
        "luma_maximum": round(luma.maximum, 2),
    }
    # Record source audio. Consumers explicitly choose whether to preserve or transform it.
    facts["source_audio"] = (
        None
        if probe.audio is None
        else {
            "codec": probe.audio.codec_name,
            "channels": probe.audio.channels,
            "sample_rate": probe.audio.sample_rate,
        }
    )
    return facts


async def admit_clip_file(
    path: Path,
    *,
    expected_seconds: float,
    expected_size: tuple[int, int] | None = None,
    expected_codec: str | None = None,
    expected_aspect_ratio: float | None = None,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
) -> dict[str, object]:
    """Measure a clip on disk and state the verdict."""

    probe = await probe_video(path, ffprobe=ffprobe)
    motion = await measure_motion(path, ffmpeg=ffmpeg)
    luma = await measure_luma(path, ffmpeg=ffmpeg)
    return clip_admission_facts(
        probe,
        motion,
        luma,
        expected_seconds=expected_seconds,
        expected_size=expected_size,
        expected_codec=expected_codec,
        expected_aspect_ratio=expected_aspect_ratio,
    )


async def admit_clip_bytes(
    data: bytes,
    *,
    expected_seconds: float,
    expected_size: tuple[int, int] | None = None,
    expected_codec: str | None = None,
    expected_aspect_ratio: float | None = None,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
) -> dict[str, object]:
    """The live validator, run inside the provider's retry owner before persistence.

    The bytes go to a scratch file rather than a pipe. A container that puts its
    index after its payload cannot be measured from a stream, and redrawing a
    good clip six times over a property of the muxer would be the worst kind of
    gate: expensive and about nothing.
    """

    async with scratch_clip(data) as scratch:
        return await admit_clip_file(
            scratch,
            expected_seconds=expected_seconds,
            expected_size=expected_size,
            expected_codec=expected_codec,
            expected_aspect_ratio=expected_aspect_ratio,
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
        )


__all__ = [
    "CLIP_ASPECT_RATIO",
    "CLIP_ASPECT_TOLERANCE",
    "CLIP_DURATION_TOLERANCE_SECONDS",
    "CLIP_LUMA_LIVE_FRAME_BAND",
    "CLIP_LUMA_MEAN_BAND",
    "CLIP_MOTION_FLOOR_MEAN",
    "ClipAdmissionError",
    "admit_clip_bytes",
    "admit_clip_file",
    "clip_admission_facts",
]
