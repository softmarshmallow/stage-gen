"""Headless wrappers around composed provider-neutral component services."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from stage_gen.config import StageGenConfig, assert_capabilities


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
