"""Application composition of configured provider services for one run."""

from __future__ import annotations

from typing import Protocol

from gnode import (
    BackgroundRemovalService,
    ImageGenerationService,
    MusicGenerationService,
    SoundEffectGenerationService,
    SpeechGenerationService,
    StructuredGenerationService,
    ToolLoopService,
    VideoGenerationService,
)
from stage_gen.config import StageGenConfig
from stage_gen.orchestration.image_routing import RoutedImageGenerationService
from stage_gen.orchestration.runtime import (
    create_background_removal_service,
    create_music_service,
    create_sound_effect_service,
    create_speech_service,
    create_structured_service,
    create_tool_loop_service,
    create_video_service,
)

OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"


class _Closable(Protocol):
    async def aclose(self) -> None: ...


class RunServices:
    """Provider services opened for one run and closed together after it.

    Each accessor composes the configured backend behind the shared retry owner. A
    service a recipe composes itself - the universe's route-bound image service - is
    ``adopt``ed so it closes with the rest. Credentials are the config's; a missing one
    is refused before a run opens, by ``RecipeExecutor.require``.
    """

    def __init__(self, config: StageGenConfig) -> None:
        self._config = config
        self._opened: list[_Closable] = []
        self._routed_image: RoutedImageGenerationService | None = None

    def adopt[S: _Closable](self, service: S) -> S:
        self._opened.append(service)
        return service

    def image(self) -> ImageGenerationService:
        """The binding-driven router shared by every image node in this run."""

        if self._routed_image is None:
            self._routed_image = self.adopt(RoutedImageGenerationService(self._config))
        return self._routed_image

    def opaque_image(self) -> ImageGenerationService:
        """Compatibility alias; opacity is a request capability, not a provider."""

        return self.image()

    def structured(self) -> StructuredGenerationService[object]:
        config = self._config
        return self.adopt(
            create_structured_service(
                api_key=config.open_router_api_key or "",
                model=config.text_model,
                base_url=config.open_router_base_url or OPENROUTER_BASE_URL,
            )
        )

    def tool_loop(self) -> ToolLoopService[dict[str, object]]:
        config = self._config
        return self.adopt(
            create_tool_loop_service(
                api_key=config.open_router_api_key or "",
                model=config.text_model,
                base_url=config.open_router_base_url or OPENROUTER_BASE_URL,
            )
        )

    def music(self) -> MusicGenerationService:
        config = self._config
        return self.adopt(
            create_music_service(
                api_key=config.open_router_api_key or "",
                model=config.music_model,
                base_url=config.open_router_base_url or OPENROUTER_BASE_URL,
            )
        )

    def background_removal(self) -> BackgroundRemovalService:
        config = self._config
        return self.adopt(
            create_background_removal_service(
                api_key=config.fal_key or "",
                model=config.background_removal_model,
            )
        )

    def video(self) -> VideoGenerationService:
        config = self._config
        return self.adopt(
            create_video_service(
                api_key=config.fal_key or "",
                model=config.video_model,
            )
        )

    def sound_effect(self) -> SoundEffectGenerationService:
        config = self._config
        return self.adopt(
            create_sound_effect_service(
                api_key=config.elevenlabs_api_key or "",
                model=config.sound_effect_model,
                base_url=config.elevenlabs_base_url or ELEVENLABS_BASE_URL,
            )
        )

    def speech(self) -> SpeechGenerationService:
        config = self._config
        return self.adopt(
            create_speech_service(
                api_key=config.elevenlabs_api_key or "",
                model=config.speech_model,
                base_url=config.elevenlabs_base_url or ELEVENLABS_BASE_URL,
            )
        )

    async def aclose(self) -> None:
        opened, self._opened = self._opened, []
        self._routed_image = None
        for service in reversed(opened):
            await service.aclose()

    async def __aenter__(self) -> RunServices:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()
