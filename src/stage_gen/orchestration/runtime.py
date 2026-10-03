"""The provider services Stage Gen composes: each concrete backend behind its retry owner.

The gnode plugin builds its capability handlers from these, and an application such as
concept studio calls one directly.
"""

from __future__ import annotations

from gnode import (
    BackgroundRemovalService,
    ImageGenerationService,
    MusicGenerationService,
    RetryPolicy,
    SoundEffectGenerationService,
    SpeechGenerationService,
    StructuredGenerationService,
)
from gnode.providers.elevenlabs import ElevenLabsSoundEffectBackend, ElevenLabsSpeechBackend
from gnode.providers.fal import FalBackgroundRemovalBackend
from gnode.providers.openrouter import (
    OpenRouterImageBackend,
    OpenRouterMusicBackend,
    OpenRouterStructuredBackend,
    OpenRouterStructuredRequestPolicy,
)
from stage_gen.identity import (
    BACKGROUND_REMOVAL_COMPONENT,
    IMAGE_GENERATION_COMPONENT,
    MUSIC_GENERATION_COMPONENT,
    SOUND_EFFECT_GENERATION_COMPONENT,
    SPEECH_GENERATION_COMPONENT,
    STAGE_GEN_TOOL,
    STRUCTURED_GENERATION_COMPONENT,
)


def create_image_service(
    *,
    api_key: str,
    model: str,
    base_url: str = "https://openrouter.ai/api/v1",
    images_per_minute: int = 150,
    retry_policy: RetryPolicy | None = None,
) -> ImageGenerationService:
    return ImageGenerationService(
        OpenRouterImageBackend(
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
    request_policy: OpenRouterStructuredRequestPolicy | None = None,
) -> StructuredGenerationService[object]:
    return StructuredGenerationService(
        OpenRouterStructuredBackend(
            api_key=api_key, model=model, base_url=base_url, request_policy=request_policy
        ),
        component=STRUCTURED_GENERATION_COMPONENT,
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


__all__ = [
    "create_background_removal_service",
    "create_image_service",
    "create_music_service",
    "create_sound_effect_service",
    "create_speech_service",
    "create_structured_service",
]
