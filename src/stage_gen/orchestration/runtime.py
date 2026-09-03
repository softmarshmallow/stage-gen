"""Application composition root for concrete providers and runtime adapters."""

from __future__ import annotations

import asyncio
import base64
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn, Protocol, Self, cast

from gnode import (
    ArtifactRights,
    BackgroundMaskArtifact,
    BackgroundRemovalRequest,
    BackgroundRemovalService,
    BinaryArtifact,
    ImageGenerationRequest,
    ImageGenerationService,
    ImageReference,
    MusicGenerationRequest,
    MusicGenerationService,
    MusicOutputFormat,
    RetryPolicy,
    SoundEffectGenerationRequest,
    SoundEffectGenerationService,
    SpeechGenerationRequest,
    SpeechGenerationService,
    StructuredGenerationService,
    ToolLoopService,
    inspect_image,
)
from gnode.providers.elevenlabs import ElevenLabsSoundEffectBackend, ElevenLabsSpeechBackend
from gnode.providers.fal import FalBackgroundRemovalBackend
from gnode.providers.openai import OpenAIImageBackend
from gnode.providers.openrouter import (
    OpenRouterImageBackend,
    OpenRouterMusicBackend,
    OpenRouterStructuredBackend,
    OpenRouterToolLoopBackend,
)
from stage_gen.components.audio_normalization import (
    AudioNormalizationRequest,
    FfmpegAudioNormalizer,
)
from stage_gen.components.sound_effect import admit_sound_effect_bytes
from stage_gen.components.speech import admit_speech_bytes
from stage_gen.config import StageGenConfig, TransparencyMode
from stage_gen.identity import (
    BACKGROUND_REMOVAL_COMPONENT,
    IMAGE_GENERATION_COMPONENT,
    MUSIC_GENERATION_COMPONENT,
    SOUND_EFFECT_GENERATION_COMPONENT,
    SPEECH_GENERATION_COMPONENT,
    STAGE_GEN_TOOL,
    STRUCTURED_GENERATION_COMPONENT,
    TOOL_LOOP_COMPONENT,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from stage_gen.capabilities import CapabilityArtifactResult


class _AsyncClosable(Protocol):
    async def aclose(self) -> None: ...


def create_image_service(
    *,
    api_key: str,
    model: str = "openai/gpt-image-2",
    base_url: str = "https://openrouter.ai/api/v1",
    retry_policy: RetryPolicy | None = None,
) -> ImageGenerationService:
    return ImageGenerationService(
        OpenRouterImageBackend(api_key=api_key, model=model, base_url=base_url),
        component=IMAGE_GENERATION_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=retry_policy,
    )


def create_openai_image_service(
    *,
    api_key: str,
    model: str = "gpt-image-2",
    base_url: str = "https://api.openai.com/v1",
    images_per_minute: int = 150,
    retry_policy: RetryPolicy | None = None,
) -> ImageGenerationService:
    """Compose the direct OpenAI GPT Image backend behind the shared retry owner."""

    return ImageGenerationService(
        OpenAIImageBackend(
            api_key=api_key,
            model=model,
            base_url=base_url,
            images_per_minute=images_per_minute,
        ),
        component=IMAGE_GENERATION_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=retry_policy,
    )


def create_structured_service(
    *,
    api_key: str,
    model: str,
    base_url: str = "https://openrouter.ai/api/v1",
    retry_policy: RetryPolicy | None = None,
) -> StructuredGenerationService[object]:
    return StructuredGenerationService(
        OpenRouterStructuredBackend(api_key=api_key, model=model, base_url=base_url),
        component=STRUCTURED_GENERATION_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=retry_policy,
    )


def create_tool_loop_service(
    *,
    api_key: str,
    model: str,
    base_url: str = "https://openrouter.ai/api/v1",
    retry_policy: RetryPolicy | None = None,
) -> ToolLoopService[dict[str, object]]:
    return ToolLoopService(
        OpenRouterToolLoopBackend(api_key=api_key, model=model, base_url=base_url),
        component=TOOL_LOOP_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=retry_policy,
    )


def create_background_removal_service(
    *,
    api_key: str,
    model: str = "fal-ai/birefnet/v2",
    base_url: str = "https://fal.run",
    retry_policy: RetryPolicy | None = None,
) -> BackgroundRemovalService:
    return BackgroundRemovalService(
        FalBackgroundRemovalBackend(api_key=api_key, model=model, base_url=base_url),
        component=BACKGROUND_REMOVAL_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=retry_policy,
    )


def create_music_service(
    *,
    api_key: str,
    model: str = "google/lyria-3-pro-preview",
    base_url: str = "https://openrouter.ai/api/v1",
    retry_policy: RetryPolicy | None = None,
) -> MusicGenerationService:
    return MusicGenerationService(
        OpenRouterMusicBackend(api_key=api_key, model=model, base_url=base_url),
        component=MUSIC_GENERATION_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=retry_policy,
    )


def create_sound_effect_service(
    *,
    api_key: str,
    model: str = "eleven_text_to_sound_v2",
    base_url: str = "https://api.elevenlabs.io/v1",
    retry_policy: RetryPolicy | None = None,
) -> SoundEffectGenerationService:
    return SoundEffectGenerationService(
        ElevenLabsSoundEffectBackend(api_key=api_key, model=model, base_url=base_url),
        component=SOUND_EFFECT_GENERATION_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=retry_policy,
    )


def create_speech_service(
    *,
    api_key: str,
    model: str = "eleven_v3",
    base_url: str = "https://api.elevenlabs.io/v1",
    retry_policy: RetryPolicy | None = None,
) -> SpeechGenerationService:
    return SpeechGenerationService(
        ElevenLabsSpeechBackend(api_key=api_key, model=model, base_url=base_url),
        component=SPEECH_GENERATION_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=retry_policy,
    )


class DefaultHeadlessRuntime:
    """Compose generic standalone operations; recipes supply their own executor."""

    def __init__(
        self,
        config: StageGenConfig,
        *,
        image_service: ImageGenerationService | None = None,
        background_service: BackgroundRemovalService | None = None,
        music_service: MusicGenerationService | None = None,
        sound_effect_service: SoundEffectGenerationService | None = None,
        speech_service: SpeechGenerationService | None = None,
    ) -> None:
        self._config = config
        openrouter_url = config.open_router_base_url or "https://openrouter.ai/api/v1"
        self._image = image_service or _configured_image_service(config)
        self._music = music_service or (
            create_music_service(
                api_key=config.open_router_api_key,
                model=config.music_model,
                base_url=openrouter_url,
            )
            if config.open_router_api_key
            else None
        )
        self._sound_effect = sound_effect_service or (
            create_sound_effect_service(
                api_key=config.elevenlabs_api_key,
                model=config.sound_effect_model,
                base_url=config.elevenlabs_base_url or "https://api.elevenlabs.io/v1",
            )
            if config.elevenlabs_api_key
            else None
        )
        self._speech = speech_service or (
            create_speech_service(
                api_key=config.elevenlabs_api_key,
                model=config.speech_model,
                base_url=config.elevenlabs_base_url or "https://api.elevenlabs.io/v1",
            )
            if config.elevenlabs_api_key
            else None
        )
        self._background = background_service or (
            create_background_removal_service(
                api_key=config.fal_key,
                model=config.background_removal_model,
                base_url=config.fal_base_url or "https://fal.run",
            )
            if config.fal_key
            else None
        )
        self._audio_normalizer = FfmpegAudioNormalizer()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        del exc_type, exc, traceback
        await self.aclose()

    async def aclose(self) -> None:
        services = (self._image, self._background, self._music, self._sound_effect)
        closed: set[int] = set()
        first_error: BaseException | None = None
        for service in services:
            if service is not None and id(service) not in closed:
                closed.add(id(service))
                try:
                    await service.aclose()
                except BaseException as error:
                    if first_error is None:
                        first_error = error
        if first_error is not None:
            raise first_error

    async def generate_image(
        self,
        *,
        prompt: str,
        output_path: str,
        aspect_ratio: str,
        reference_paths: Sequence[str],
    ) -> CapabilityArtifactResult:
        service = self._image or _missing(
            "OPENAI_API_KEY"
            if self._config.transparency_mode is TransparencyMode.NATIVE
            else "OPENROUTER_API_KEY"
        )
        references: list[ImageReference] = []
        for reference in reference_paths:
            path = await asyncio.to_thread(Path(reference).resolve)
            data = await asyncio.to_thread(path.read_bytes)
            facts = inspect_image(data)
            references.append(
                ImageReference(
                    url=(
                        f"data:{facts.media_type};base64," + base64.b64encode(data).decode("ascii")
                    ),
                    provenance_ref=str(path),
                )
            )

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            data = artifact.data
            media_type = artifact.media_type
            facts = inspect_image(data, expected_media_type="image/png")
            if media_type != "image/png":
                raise ValueError(f"expected image/png, received {media_type}")
            return {"width": facts.width, "height": facts.height}

        result = await service.generate(
            ImageGenerationRequest(
                prompt=prompt,
                artifact_path=output_path,
                aspect_ratio=aspect_ratio,
                input_references=tuple(references),
                quality="high",
                background="opaque",
                output_format="png",
                moderation="low",
                timeout_seconds=self._config.capability_timeout_ms / 1000,
                metadata={"source": "stage-gen-headless"},
                validate=validate,
            )
        )
        return _result(
            output_path,
            result.provenance_path,
            result.media_type,
            len(result.data),
            result.attempts,
        )

    async def remove_background(
        self, *, input_path: str, output_path: str
    ) -> CapabilityArtifactResult:
        service = self._background or _missing("FAL_KEY")
        source_path = await asyncio.to_thread(Path(input_path).resolve)
        source_data = await asyncio.to_thread(source_path.read_bytes)
        source_facts = inspect_image(source_data)

        def validate(
            artifact: BinaryArtifact, _mask: BackgroundMaskArtifact | None
        ) -> dict[str, object]:
            data = artifact.data
            media_type = artifact.media_type
            facts = inspect_image(data, expected_media_type="image/png")
            if media_type != "image/png":
                raise ValueError(f"expected image/png, received {media_type}")
            if not facts.has_alpha:
                raise ValueError("background removal output has no alpha channel")
            if (facts.width, facts.height) != (source_facts.width, source_facts.height):
                raise ValueError("background removal dimensions changed")
            return {"dimensions_preserved": True, "has_alpha": True}

        result = await service.remove(
            BackgroundRemovalRequest(
                image_url=(
                    f"data:{source_facts.media_type};base64,"
                    + base64.b64encode(source_data).decode("ascii")
                ),
                artifact_path=output_path,
                output_format="png",
                timeout_seconds=self._config.capability_timeout_ms / 1000,
                metadata={"source_path": str(source_path)},
                validate=validate,
            )
        )
        return _result(
            output_path,
            result.provenance_path,
            result.media_type,
            len(result.data),
            result.attempts,
        )

    async def generate_music(
        self,
        *,
        prompt: str,
        output_path: str,
        output_format: str,
        metadata: Mapping[str, object] | None = None,
    ) -> CapabilityArtifactResult:
        service = self._music or _missing("OPENROUTER_API_KEY")
        if output_format not in {"mp3", "wav"}:
            raise ValueError("output_format must be mp3 or wav")
        music_format = cast("MusicOutputFormat", output_format)
        output = await asyncio.to_thread(Path(output_path).resolve)
        if output.suffix.lower() != f".{music_format}":
            raise ValueError(
                f"generate-music {music_format} output must use a .{music_format} extension"
            )
        raw = output.parent / f".{output.name}.{uuid.uuid4().hex}.raw.{output_format}"
        try:
            generated = await service.generate(
                MusicGenerationRequest(
                    prompt=prompt,
                    artifact_path=raw,
                    output_format=music_format,
                    timeout_seconds=self._config.capability_timeout_ms / 1000,
                    metadata=dict(metadata)
                    if metadata is not None
                    else {"source": "stage-gen-headless"},
                    rights=_unreviewed_generated_music_rights(),
                    validate=lambda artifact: _minimum_audio_size(artifact.data),
                )
            )
            normalized = await self._audio_normalizer.normalize(
                AudioNormalizationRequest(
                    source_path=raw,
                    source_provenance_path=f"{raw}.meta.json",
                    artifact_path=output,
                    output_format=music_format,
                    timeout_seconds=self._config.capability_timeout_ms / 1000,
                )
            )
            return _result(
                str(output),
                normalized.provenance_path,
                normalized.media_type,
                len(normalized.data),
                generated.attempts,
            )
        finally:
            await asyncio.to_thread(raw.unlink, missing_ok=True)
            await asyncio.to_thread(Path(f"{raw}.meta.json").unlink, missing_ok=True)

    async def generate_sound_effect(
        self,
        *,
        prompt: str,
        output_path: str,
        duration_seconds: float,
        prompt_influence: float | None = None,
        loop: bool = False,
        metadata: Mapping[str, object] | None = None,
    ) -> CapabilityArtifactResult:
        """One verbatim-prompt draw, admitted on level and never post-processed."""

        service = self._sound_effect or _missing("ELEVENLABS_API_KEY")
        output = await asyncio.to_thread(Path(output_path).resolve)
        if output.suffix.lower() != ".mp3":
            raise ValueError("generate-sound-effect output must use a .mp3 extension")
        generated = await service.generate(
            SoundEffectGenerationRequest(
                prompt=prompt,
                artifact_path=output,
                duration_seconds=duration_seconds,
                prompt_influence=prompt_influence,
                loop=loop,
                output_format="mp3",
                timeout_seconds=self._config.capability_timeout_ms / 1000,
                metadata=dict(metadata)
                if metadata is not None
                else {"source": "stage-gen-headless"},
                rights=_unreviewed_generated_music_rights(),
                validate=lambda artifact: admit_sound_effect_bytes(artifact.data),
            )
        )
        return _result(
            str(output),
            generated.provenance_path,
            generated.media_type,
            len(generated.data),
            generated.attempts,
        )

    async def generate_speech(
        self,
        *,
        text: str,
        output_path: str,
        voice: str,
        stability: float | None = None,
        language_code: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> CapabilityArtifactResult:
        """One verbatim-text read on one provider voice, admitted on level, never post-processed.

        The audition tool: the voice is the provider's own reference, exactly as
        the sound-effect twin takes a raw prompt. Which voice a game-owned name
        resolves to is the package's business, not this command's.
        """

        service = self._speech or _missing("ELEVENLABS_API_KEY")
        output = await asyncio.to_thread(Path(output_path).resolve)
        if output.suffix.lower() != ".mp3":
            raise ValueError("generate-speech output must use a .mp3 extension")
        generated = await service.generate(
            SpeechGenerationRequest(
                text=text,
                voice=voice,
                artifact_path=output,
                stability=stability,
                language_code=language_code,
                output_format="mp3",
                timeout_seconds=self._config.capability_timeout_ms / 1000,
                metadata=dict(metadata)
                if metadata is not None
                else {"source": "stage-gen-headless"},
                rights=_unreviewed_generated_music_rights(),
                validate=lambda artifact: admit_speech_bytes(artifact.data),
            )
        )
        return _result(
            str(output),
            generated.provenance_path,
            generated.media_type,
            len(generated.data),
            generated.attempts,
        )


def create_headless_runtime(
    config: StageGenConfig,
    *,
    image_service: ImageGenerationService | None = None,
    background_service: BackgroundRemovalService | None = None,
    music_service: MusicGenerationService | None = None,
    sound_effect_service: SoundEffectGenerationService | None = None,
    speech_service: SpeechGenerationService | None = None,
) -> DefaultHeadlessRuntime:
    return DefaultHeadlessRuntime(
        config,
        image_service=image_service,
        background_service=background_service,
        music_service=music_service,
        sound_effect_service=sound_effect_service,
        speech_service=speech_service,
    )


def _configured_image_service(config: StageGenConfig) -> ImageGenerationService | None:
    if config.transparency_mode is TransparencyMode.NATIVE:
        if config.openai_api_key is None:
            return None
        return create_openai_image_service(
            api_key=config.openai_api_key,
            model=config.openai_image_model,
            base_url=config.openai_base_url or "https://api.openai.com/v1",
            images_per_minute=config.openai_image_ipm,
        )
    if config.open_router_api_key is None:
        return None
    return create_image_service(
        api_key=config.open_router_api_key,
        model=config.image_model,
        base_url=config.open_router_base_url or "https://openrouter.ai/api/v1",
    )


def _minimum_audio_size(data: bytes) -> dict[str, object]:
    if len(data) < 1024:
        raise ValueError("music output is unexpectedly small")
    return {"minimum_size": 1024}


def _unreviewed_generated_music_rights() -> ArtifactRights:
    return ArtifactRights(
        status="unreviewed",
        attribution=[],
        basis=[],
        reviewed_at=None,
    )


def _missing(name: str) -> NoReturn:
    raise ValueError(f"missing required environment variable: {name}")


def _result(
    artifact_path: str,
    provenance_path: str,
    media_type: str,
    byte_count: int,
    attempts: int,
) -> CapabilityArtifactResult:
    from stage_gen.capabilities import CapabilityArtifactResult

    return CapabilityArtifactResult(
        artifact_path=artifact_path,
        provenance_path=provenance_path,
        media_type=media_type,
        bytes=byte_count,
        attempts=attempts,
    )
