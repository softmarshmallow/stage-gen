"""Headless wrappers around composed provider-neutral component services."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from stage_gen.components.video_clip import (
    CLIP_REVIEW_CELL_WIDTH,
    CLIP_REVIEW_COLUMNS,
    ClipAdmissionError,
    clip_admission_facts,
    clip_sample_times,
)
from stage_gen.config import StageGenConfig, assert_capabilities
from stage_gen.media import (
    contact_sheet,
    extract_frame_png,
    measure_luma,
    measure_motion,
    probe_video,
)


@dataclass(frozen=True, slots=True)
class CapabilityArtifactResult:
    artifact_path: str
    provenance_path: str
    media_type: str
    bytes: int
    attempts: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "artifactPath": self.artifact_path,
            "provenancePath": self.provenance_path,
            "mediaType": self.media_type,
            "bytes": self.bytes,
            "attempts": self.attempts,
        }


class HeadlessRuntime(Protocol):
    async def generate_image(
        self,
        *,
        prompt: str,
        output_path: str,
        aspect_ratio: str,
        reference_paths: Sequence[str],
    ) -> CapabilityArtifactResult: ...

    async def remove_background(
        self, *, input_path: str, output_path: str
    ) -> CapabilityArtifactResult: ...

    async def generate_music(
        self,
        *,
        prompt: str,
        output_path: str,
        output_format: str,
        metadata: Mapping[str, object] | None = None,
    ) -> CapabilityArtifactResult: ...

    async def generate_sound_effect(
        self,
        *,
        prompt: str,
        output_path: str,
        duration_seconds: float,
        prompt_influence: float | None = None,
        loop: bool = False,
        metadata: Mapping[str, object] | None = None,
    ) -> CapabilityArtifactResult: ...

    async def generate_video(
        self,
        *,
        prompt: str,
        output_path: str,
        duration_seconds: float,
        resolution: str,
        aspect_ratio: str,
        reference_paths: Sequence[str] = (),
        metadata: Mapping[str, object] | None = None,
    ) -> CapabilityArtifactResult: ...

    async def generate_speech(
        self,
        *,
        text: str,
        output_path: str,
        voice: str,
        stability: float | None = None,
        language_code: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> CapabilityArtifactResult: ...


async def generate_image_artifact(
    *,
    prompt: str,
    output_path: str,
    config: StageGenConfig,
    aspect_ratio: str = "1:1",
    reference_paths: Sequence[str] = (),
    runtime: HeadlessRuntime | None = None,
) -> CapabilityArtifactResult:
    assert_capabilities(config, ("image_generation",))
    if not output_path.lower().endswith(".png"):
        raise ValueError("generate-image output must use a .png extension")
    owned = None
    if runtime is None:
        from stage_gen.orchestration.runtime import create_headless_runtime

        owned = create_headless_runtime(config)
    active = runtime or owned
    assert active is not None
    try:
        return await active.generate_image(
            prompt=prompt,
            output_path=output_path,
            aspect_ratio=aspect_ratio,
            reference_paths=reference_paths,
        )
    finally:
        if owned is not None:
            await owned.aclose()


async def remove_background(
    *,
    input_path: str,
    output_path: str,
    config: StageGenConfig,
    runtime: HeadlessRuntime | None = None,
) -> CapabilityArtifactResult:
    assert_capabilities(config, ("background_removal",))
    owned = None
    if runtime is None:
        from stage_gen.orchestration.runtime import create_headless_runtime

        owned = create_headless_runtime(config)
    active = runtime or owned
    assert active is not None
    try:
        return await active.remove_background(input_path=input_path, output_path=output_path)
    finally:
        if owned is not None:
            await owned.aclose()


async def generate_music(
    *,
    prompt: str,
    output_path: str,
    output_format: str,
    config: StageGenConfig,
    runtime: HeadlessRuntime | None = None,
    metadata: Mapping[str, object] | None = None,
) -> CapabilityArtifactResult:
    assert_capabilities(config, ("music_generation",))
    if output_format not in {"mp3", "wav"}:
        raise ValueError("format must be mp3 or wav")
    owned = None
    if runtime is None:
        from stage_gen.orchestration.runtime import create_headless_runtime

        owned = create_headless_runtime(config)
    active = runtime or owned
    assert active is not None
    try:
        return await active.generate_music(
            prompt=prompt,
            output_path=output_path,
            output_format=output_format,
            metadata=metadata,
        )
    finally:
        if owned is not None:
            await owned.aclose()


def _write_sheet(sheet: Path, frames: Sequence[bytes]) -> None:
    sheet.parent.mkdir(parents=True, exist_ok=True)
    sheet.write_bytes(
        contact_sheet(list(frames), columns=CLIP_REVIEW_COLUMNS, cell_width=CLIP_REVIEW_CELL_WIDTH)
    )


async def inspect_video(
    *,
    input_path: str,
    output_path: str,
    expected_seconds: float | None = None,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
) -> dict[str, object]:
    """Measure a clip and lay its frames out for somebody to read. No provider call.

    The manual gate. An LLM or a person judging a clip does it by looking at the frames,
    and this is what puts them in front of one - sampled exactly as the pipeline's own
    reviewer samples them, so a verdict formed here and a verdict formed in a run are
    about the same pictures.

    A clip the gate would refuse still gets its sheet: the reason to look at a refused
    clip is to find out what went wrong with it, and a tool that withheld the picture at
    exactly that moment would be useless. The verdict is reported, not raised.
    """

    source = await asyncio.to_thread(Path(input_path).resolve)
    probe = await probe_video(source, ffprobe=ffprobe)
    motion = await measure_motion(source, ffmpeg=ffmpeg)
    luma = await measure_luma(source, ffmpeg=ffmpeg)
    seconds = probe.duration_seconds if expected_seconds is None else expected_seconds
    sampled_at = clip_sample_times(probe.duration_seconds)
    frames = [await extract_frame_png(source, at_seconds=at, ffmpeg=ffmpeg) for at in sampled_at]
    sheet = await asyncio.to_thread(Path(output_path).resolve)
    await asyncio.to_thread(_write_sheet, sheet, frames)
    report: dict[str, object] = {
        "input": str(source),
        "sheet": str(sheet),
        "frames": len(frames),
        "sampledAt": list(sampled_at),
    }
    try:
        report.update(clip_admission_facts(probe, motion, luma, expected_seconds=seconds))
    except ClipAdmissionError as error:
        report["admitted"] = False
        report["refused"] = str(error)
        return report
    report["admitted"] = True
    report["refused"] = None
    return report


#: The rungs a video route draws. A generic broadcast ladder, not a vendor enum: which
#: of them a given route actually answers is that route's business.
VIDEO_RESOLUTIONS: tuple[str, ...] = ("360p", "720p", "1080p", "4k")


async def generate_video(
    *,
    prompt: str,
    output_path: str,
    duration_seconds: float,
    config: StageGenConfig,
    resolution: str = "720p",
    aspect_ratio: str = "16:9",
    reference_paths: Sequence[str] = (),
    runtime: HeadlessRuntime | None = None,
    metadata: Mapping[str, object] | None = None,
) -> CapabilityArtifactResult:
    """Draw one clip outside any run: the audition step before a take is adopted.

    Video is the most expensive thing this repository buys and its routes take no seed,
    so drawing a brief twice costs twice and answers differently. This exists so the
    drawing and the choosing happen where a person can look at the frames, and the
    pipeline is handed the file that was chosen rather than the lottery ticket.
    """

    assert_capabilities(config, ("video_generation",))
    if not output_path.lower().endswith(".mp4"):
        raise ValueError("generate-video output must use a .mp4 extension")
    if resolution not in VIDEO_RESOLUTIONS:
        raise ValueError(f"--resolution must be one of {', '.join(VIDEO_RESOLUTIONS)}")
    owned = None
    if runtime is None:
        from stage_gen.orchestration.runtime import create_headless_runtime

        owned = create_headless_runtime(config)
    active = runtime or owned
    assert active is not None
    try:
        return await active.generate_video(
            prompt=prompt,
            output_path=output_path,
            duration_seconds=duration_seconds,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            reference_paths=reference_paths,
            metadata=metadata,
        )
    finally:
        if owned is not None:
            await owned.aclose()


async def generate_sound_effect(
    *,
    prompt: str,
    output_path: str,
    duration_seconds: float,
    config: StageGenConfig,
    prompt_influence: float | None = None,
    loop: bool = False,
    runtime: HeadlessRuntime | None = None,
    metadata: Mapping[str, object] | None = None,
) -> CapabilityArtifactResult:
    assert_capabilities(config, ("sound_effect_generation",))
    if not output_path.lower().endswith(".mp3"):
        raise ValueError("generate-sound-effect output must use a .mp3 extension")
    owned = None
    if runtime is None:
        from stage_gen.orchestration.runtime import create_headless_runtime

        owned = create_headless_runtime(config)
    active = runtime or owned
    assert active is not None
    try:
        return await active.generate_sound_effect(
            prompt=prompt,
            output_path=output_path,
            duration_seconds=duration_seconds,
            prompt_influence=prompt_influence,
            loop=loop,
            metadata=metadata,
        )
    finally:
        if owned is not None:
            await owned.aclose()


async def generate_speech(
    *,
    text: str,
    output_path: str,
    voice: str,
    config: StageGenConfig,
    stability: float | None = None,
    language_code: str | None = None,
    runtime: HeadlessRuntime | None = None,
    metadata: Mapping[str, object] | None = None,
) -> CapabilityArtifactResult:
    assert_capabilities(config, ("speech_generation",))
    if not output_path.lower().endswith(".mp3"):
        raise ValueError("generate-speech output must use a .mp3 extension")
    owned = None
    if runtime is None:
        from stage_gen.orchestration.runtime import create_headless_runtime

        owned = create_headless_runtime(config)
    active = runtime or owned
    assert active is not None
    try:
        return await active.generate_speech(
            text=text,
            output_path=output_path,
            voice=voice,
            stability=stability,
            language_code=language_code,
            metadata=metadata,
        )
    finally:
        if owned is not None:
            await owned.aclose()
