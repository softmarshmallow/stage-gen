"""Deterministic video inspection and the one publication transcode.

Everything here measures a clip the way the gates need it measured, and nothing
here repairs one. The single transform is a container change: the pinned Godot
host plays exactly one video codec, so a clip is published as Ogg Theora with
fixed parameters, no crop, no trim, no scale and no filter. What makes that
publication rather than repair is that the same measurements run again on the
result, so the transform cannot hide anything from the gate that follows it.

Measurements take a path rather than bytes. A validator inside a retry owner
holds only a response, so it writes those bytes to a scratch file and deletes
them - deliberately, instead of piping. Piping works only when a container puts
its index before its payload, and a clip that failed that test would be redrawn
six times for a property of the muxer that has nothing to do with the picture.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import tempfile
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .audio import AudioProcessRunner, run_process
from .codec import decode_image, encode_png

DEFAULT_VIDEO_PROCESS_TIMEOUT_SECONDS = 300.0

#: How the motion probe looks at a clip: eight samples a second, tiny, grey.
#: Small on purpose - the question is whether the picture changes at all, and a
#: 160x90 grey frame answers it for a fraction of the decode.
MOTION_SAMPLE_FPS = 8
MOTION_SAMPLE_SIZE = (160, 90)
#: The luma probe is slower and wider: a fade has to be visible as a fade.
LUMA_SAMPLE_FPS = 2
LUMA_SAMPLE_SIZE = (320, 180)
#: The signature two pictures are compared at. Coarse enough that a re-encode,
#: a small camera move or a grade all land on the same picture.
FRAME_SIGNATURE_SIZE = (32, 18)
#: Ogg Theora quality for publication. Measured on the shell spike: q6 halves an
#: h264 source, q8 is roughly the same size, q10 doubles it.
THEORA_QUALITY = 6

_METADATA_LINE = re.compile(r"lavfi\.signalstats\.YAVG=(-?\d+(?:\.\d+)?)")


@dataclass(frozen=True, slots=True)
class ClipAudioTrack:
    """The audio a generated clip arrived with, recorded and never played."""

    codec_name: str
    channels: int | None
    sample_rate: int | None


@dataclass(frozen=True, slots=True)
class VideoProbe:
    duration_seconds: float
    width: int
    height: int
    codec_name: str
    frames_per_second: float
    video_stream_count: int
    audio: ClipAudioTrack | None

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height


@dataclass(frozen=True, slots=True)
class MotionMeasurement:
    """How much the picture changes, sample to sample, on a 0-255 scale."""

    mean: float
    median: float
    minimum: float
    maximum: float
    samples: int


@dataclass(frozen=True, slots=True)
class LumaMeasurement:
    mean: float
    minimum: float
    maximum: float
    samples: int


@asynccontextmanager
async def scratch_clip(data: bytes, *, suffix: str = ".mp4") -> AsyncIterator[Path]:
    """Hold a provider response on disk just long enough to measure it."""

    if not data:
        raise ValueError("clip data must be non-empty")
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)  # noqa: SIM115
    try:
        handle.write(data)
        handle.close()
        yield Path(handle.name)
    finally:
        # os.remove rather than Path.unlink: the linter reads a pathlib call in
        # an async function as a blocking-IO mistake, and this one is a cleanup.
        with contextlib.suppress(FileNotFoundError):
            os.remove(handle.name)


def _finite(value: object, label: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _frame_rate(value: object) -> float:
    """ffprobe reports a rate as ``num/den``; a zero denominator is no rate."""

    if not isinstance(value, str) or "/" not in value:
        raise ValueError("ffprobe frame rate must be a ratio")
    numerator, denominator = value.split("/", 1)
    bottom = _finite(denominator, "ffprobe frame rate denominator")
    if bottom == 0:
        raise ValueError("ffprobe reported a zero frame rate denominator")
    return _finite(numerator, "ffprobe frame rate numerator") / bottom


def _optional_int(value: object) -> int | None:
    """A positive integer, however ffprobe chose to spell it.

    It reports ``channels`` as a number and ``sample_rate`` as a string in the
    same object, so accepting only one of the two silently drops half the facts.
    """

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        number = int(value)
        return number if number > 0 else None
    return None


async def probe_video(
    path: Path,
    *,
    runner: AudioProcessRunner = run_process,
    ffprobe: str = "ffprobe",
    timeout_seconds: float = DEFAULT_VIDEO_PROCESS_TIMEOUT_SECONDS,
) -> VideoProbe:
    """What is actually in the container, read from the video stream itself.

    Duration comes from the video stream rather than the format: a generated mp4
    carries an audio track whose frame padding makes the format five to ten
    milliseconds longer than the picture, and a gate that read the format would
    be measuring the muxer.
    """

    result = await runner(
        ffprobe,
        [
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_type,codec_name,width,height,r_frame_rate,duration,channels,sample_rate",
            "-of",
            "json",
            str(path),
        ],
        timeout_seconds,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("ffprobe returned invalid JSON") from exc
    streams = payload.get("streams") if isinstance(payload, dict) else None
    if not isinstance(streams, list):
        raise ValueError("ffprobe returned no streams")
    video = [s for s in streams if isinstance(s, dict) and s.get("codec_type") == "video"]
    audio = [s for s in streams if isinstance(s, dict) and s.get("codec_type") == "audio"]
    if not video:
        raise ValueError("the file carries no video stream")
    first = video[0]
    width, height = _optional_int(first.get("width")), _optional_int(first.get("height"))
    if width is None or height is None:
        raise ValueError("ffprobe reported no picture size")
    duration = _finite(first.get("duration"), "ffprobe video stream duration")
    if duration <= 0:
        raise ValueError("ffprobe video stream duration must be positive")
    codec = first.get("codec_name")
    if not isinstance(codec, str) or not codec:
        raise ValueError("ffprobe reported no video codec")
    track = None
    if audio:
        name = audio[0].get("codec_name")
        track = ClipAudioTrack(
            codec_name=name if isinstance(name, str) and name else "unknown",
            channels=_optional_int(audio[0].get("channels")),
            sample_rate=_optional_int(audio[0].get("sample_rate")),
        )
    return VideoProbe(
        duration_seconds=duration,
        width=width,
        height=height,
        codec_name=codec,
        frames_per_second=_frame_rate(first.get("r_frame_rate")),
        video_stream_count=len(video),
        audio=track,
    )


async def _signalstats(
    path: Path,
    chain: str,
    *,
    runner: AudioProcessRunner,
    ffmpeg: str,
    timeout_seconds: float,
) -> list[float]:
    result = await runner(
        ffmpeg,
        ["-v", "error", "-i", str(path), "-vf", chain, "-f", "null", "-"],
        timeout_seconds,
    )
    return [float(m) for m in _METADATA_LINE.findall(result.stdout + result.stderr)]


async def measure_motion(
    path: Path,
    *,
    runner: AudioProcessRunner = run_process,
    ffmpeg: str = "ffmpeg",
    timeout_seconds: float = DEFAULT_VIDEO_PROCESS_TIMEOUT_SECONDS,
) -> MotionMeasurement:
    """Mean absolute difference between consecutive samples.

    The failure this exists to catch is a route that answers a clip brief with a
    still: a perfectly good-looking picture that never moves. Blending each
    sample against the one before it and reading the average grey level of the
    difference separates the two by orders of magnitude.
    """

    chain = (
        f"fps={MOTION_SAMPLE_FPS},scale={MOTION_SAMPLE_SIZE[0]}:{MOTION_SAMPLE_SIZE[1]},"
        "format=gray,tblend=all_mode=difference,signalstats,metadata=print:file=-"
    )
    # The first sample has nothing before it, so its difference is against
    # itself and says nothing about the clip.
    values = (
        await _signalstats(
            path, chain, runner=runner, ffmpeg=ffmpeg, timeout_seconds=timeout_seconds
        )
    )[1:]
    if not values:
        raise ValueError("the motion probe read no frames")
    ordered = sorted(values)
    return MotionMeasurement(
        mean=sum(values) / len(values),
        median=ordered[len(ordered) // 2],
        minimum=ordered[0],
        maximum=ordered[-1],
        samples=len(values),
    )


async def measure_luma(
    path: Path,
    *,
    runner: AudioProcessRunner = run_process,
    ffmpeg: str = "ffmpeg",
    timeout_seconds: float = DEFAULT_VIDEO_PROCESS_TIMEOUT_SECONDS,
) -> LumaMeasurement:
    chain = (
        f"fps={LUMA_SAMPLE_FPS},scale={LUMA_SAMPLE_SIZE[0]}:{LUMA_SAMPLE_SIZE[1]},"
        "format=gray,signalstats,metadata=print:file=-"
    )
    values = await _signalstats(
        path, chain, runner=runner, ffmpeg=ffmpeg, timeout_seconds=timeout_seconds
    )
    if not values:
        raise ValueError("the luma probe read no frames")
    return LumaMeasurement(
        mean=sum(values) / len(values),
        minimum=min(values),
        maximum=max(values),
        samples=len(values),
    )


async def extract_frame_png(
    path: Path,
    *,
    at_seconds: float | None = None,
    from_end: bool = False,
    runner: AudioProcessRunner = run_process,
    ffmpeg: str = "ffmpeg",
    timeout_seconds: float = DEFAULT_VIDEO_PROCESS_TIMEOUT_SECONDS,
) -> bytes:
    """One frame as PNG bytes, seeking rather than decoding to it.

    ``from_end`` uses ffmpeg's own end-relative seek instead of the ``reverse``
    filter, which buffers every frame of the clip in memory to hand back the
    last one.

    The frame lands in a scratch file rather than on stdout because the shared
    process runner decodes what it captures as UTF-8 with replacement - right
    for the ffmpeg reports it was written for, and silently destructive to a
    PNG, which is what the first cut of this function did.
    """

    seek = ["-sseof", "-0.2"] if from_end else ["-ss", f"{at_seconds or 0.0:.3f}"]
    handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)  # noqa: SIM115
    handle.close()
    try:
        await runner(
            ffmpeg,
            ["-y", "-v", "error", *seek, "-i", str(path), "-frames:v", "1", handle.name],
            timeout_seconds,
        )
        with open(handle.name, "rb") as frame:  # noqa: ASYNC230 - a scratch read
            data = frame.read()
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.remove(handle.name)
    if not data:
        raise ValueError("no frame was extracted")
    return data


def frame_signature(
    data: bytes, *, size: tuple[int, int] = FRAME_SIGNATURE_SIZE
) -> tuple[int, ...]:
    """A picture reduced to a few hundred numbers, for comparing two of them."""

    image = decode_image(data, label="clip frame").convert("RGB")
    return tuple(image.resize(size, Image.Resampling.BOX).tobytes())


def signature_distance(left: Sequence[int], right: Sequence[int]) -> float:
    """Mean absolute per-channel difference, 0 (identical) to 255."""

    if len(left) != len(right) or not left:
        raise ValueError("signatures must be the same non-zero length")
    return sum(abs(a - b) for a, b in zip(left, right, strict=True)) / len(left)


def contact_sheet(
    frames: Sequence[bytes], *, columns: int = 3, cell_width: int | None = None
) -> bytes:
    """The sampled frames as one picture, in order, for a reviewer to read.

    A reviewer cannot be handed a clip, so it is handed the clip's beats. The
    composition is deterministic - uniform cell size, fixed order, no refitting
    - so two runs of the same clip produce the same sheet.
    """

    if not frames:
        raise ValueError("a contact sheet needs at least one frame")
    if columns < 1:
        raise ValueError("a contact sheet needs at least one column")
    images = [decode_image(frame, label="contact sheet frame").convert("RGB") for frame in frames]
    width, height = images[0].size
    if cell_width is not None and cell_width < width:
        # More samples, not bigger ones: what a reviewer needs from a cut sequence is
        # every beat, and a beat is legible well below native size.
        height = max(1, round(height * cell_width / width))
        width = cell_width
    cell_width, cell_height = width, height
    rows = math.ceil(len(images) / columns)
    sheet = Image.new("RGB", (cell_width * columns, cell_height * rows), (0, 0, 0))
    for index, image in enumerate(images):
        if image.size != (cell_width, cell_height):
            image = image.resize((cell_width, cell_height), Image.Resampling.BOX)
        sheet.paste(image, ((index % columns) * cell_width, (index // columns) * cell_height))
    return encode_png(sheet)


def theora_transcode_args(
    source: Path, target: Path, *, quality: int = THEORA_QUALITY
) -> list[str]:
    """The one publication transcode, with every parameter fixed.

    ``-an`` drops the audio the route generated. The opening already owns its
    sound through the package's soundtrack contract, and a second bed arriving
    inside a picture asset would be the only audio in a run that never passed a
    level gate or loudness normalization.
    """

    if not 0 <= quality <= 10:
        raise ValueError("theora quality must be between 0 and 10")
    return [
        "-y",
        "-v",
        "error",
        "-i",
        str(source),
        "-an",
        "-c:v",
        "libtheora",
        "-q:v",
        str(quality),
        "-f",
        "ogv",
        str(target),
    ]
