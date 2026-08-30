"""Application composition root for concrete providers and runtime adapters."""

from __future__ import annotations

import asyncio
import base64
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn, Protocol, Self, cast

from gnode import ArtifactRights, BinaryArtifact, RetryPolicy
from stage_gen.components.background_removal import (
    BackgroundMaskArtifact,
    BackgroundRemovalRequest,
    BackgroundRemovalService,
)
from stage_gen.components.image_generation import (
    ImageGenerationRequest,
    ImageGenerationService,
    ImageReference,
)
from stage_gen.components.music_generation import (
    AudioNormalizationRequest,
    FfmpegAudioNormalizer,
    MusicGenerationRequest,
    MusicGenerationService,
)
from stage_gen.components.music_generation.models import MusicOutputFormat
from stage_gen.components.structured_generation import StructuredGenerationService
from stage_gen.config import StageGenConfig, TransparencyMode
from stage_gen.media import inspect_image
from stage_gen.providers import (
    FalBackgroundRemovalBackend,
    OpenAIImageBackend,
    OpenRouterImageBackend,
    OpenRouterMusicBackend,
    OpenRouterStructuredBackend,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence

    from stage_gen.capabilities import CapabilityArtifactResult, HeadlessRuntime
    from stage_gen.recipes.base import RecipeExecutor, StageContext


class _AsyncClosable(Protocol):
    async def aclose(self) -> None: ...


class _RecipeExecutorFactory(Protocol):
    def __call__(
        self,
        *,
        image_service: ImageGenerationService,
        structured_service: StructuredGenerationService[object],
        background_service: BackgroundRemovalService | None,
    ) -> RecipeExecutor: ...


class _CallableRecipeExecutor:
    """Adapt an existing recipe-owned stage callable to the generic protocol."""

    def __init__(
        self,
        run_stage: Callable[[str, StageContext], Awaitable[Sequence[str]]],
    ) -> None:
        self._run_stage = run_stage

    async def run_stage(self, stage_name: str, context: StageContext) -> Sequence[str]:
        return await self._run_stage(stage_name, context)


class _ComposedHeadlessRuntime:
    """Join generic capability operations to recipe-id-keyed executors."""

    def __init__(
        self,
        standalone: HeadlessRuntime,
        executors: Mapping[str, RecipeExecutor],
        *,
        standalone_resource: _AsyncClosable,
        resources: Sequence[_AsyncClosable] = (),
    ) -> None:
        self._standalone = standalone
        self._executors = dict(executors)
        self._standalone_resource = standalone_resource
        self._resources = tuple(resources)

    async def generate_image(
        self,
        *,
        prompt: str,
        output_path: str,
        aspect_ratio: str,
        reference_paths: Sequence[str],
    ) -> CapabilityArtifactResult:
        return await self._standalone.generate_image(
            prompt=prompt,
            output_path=output_path,
            aspect_ratio=aspect_ratio,
            reference_paths=reference_paths,
        )

    async def remove_background(
        self, *, input_path: str, output_path: str
    ) -> CapabilityArtifactResult:
        return await self._standalone.remove_background(
            input_path=input_path, output_path=output_path
        )

    async def generate_music(
        self,
        *,
        prompt: str,
        output_path: str,
        output_format: str,
        metadata: Mapping[str, object] | None = None,
    ) -> CapabilityArtifactResult:
        return await self._standalone.generate_music(
            prompt=prompt,
            output_path=output_path,
            output_format=output_format,
            metadata=metadata,
        )

    async def run_recipe_stage(
        self, recipe_id: str, stage_name: str, context: StageContext
    ) -> Sequence[str]:
        try:
            executor = self._executors[recipe_id]
        except KeyError as error:
            raise ValueError(f"no recipe executor registered for recipe: {recipe_id}") from error
        return await executor.run_stage(stage_name, context)

    async def aclose(self) -> None:
        first_error: BaseException | None = None
        for resource in (self._standalone_resource, *self._resources):
            try:
                await resource.aclose()
            except BaseException as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error


def create_image_service(
    *,
    api_key: str,
    model: str = "openai/gpt-image-2",
    base_url: str = "https://openrouter.ai/api/v1",
    retry_policy: RetryPolicy | None = None,
) -> ImageGenerationService:
    return ImageGenerationService(
        OpenRouterImageBackend(api_key=api_key, model=model, base_url=base_url),
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
        services = (self._image, self._background, self._music)
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

    async def run_recipe_stage(
        self, recipe_id: str, stage_name: str, context: StageContext
    ) -> Sequence[str]:
        del context
        raise NotImplementedError(
            f"recipe stage {recipe_id}/{stage_name} requires a composed recipe executor"
        )


def create_headless_runtime(
    config: StageGenConfig,
    *,
    image_service: ImageGenerationService | None = None,
    background_service: BackgroundRemovalService | None = None,
    music_service: MusicGenerationService | None = None,
) -> DefaultHeadlessRuntime:
    return DefaultHeadlessRuntime(
        config,
        image_service=image_service,
        background_service=background_service,
        music_service=music_service,
    )


def _create_scrolling_preview_executor(
    *,
    image_service: ImageGenerationService,
    structured_service: StructuredGenerationService[object],
    background_service: BackgroundRemovalService | None,
) -> RecipeExecutor:
    from stage_gen.recipes.scrolling_preview.executor import ScrollingPreviewExecutor

    executor = ScrollingPreviewExecutor(
        image_service=image_service,
        structured_service=structured_service,
        background_service=background_service,
    )
    return _CallableRecipeExecutor(executor.run_scrolling_preview_stage)


def _create_dialogue_scene_executor(
    *,
    image_service: ImageGenerationService,
    structured_service: StructuredGenerationService[object],
    background_service: BackgroundRemovalService | None,
) -> RecipeExecutor:
    from stage_gen.recipes.dialogue_scene.executor import (
        DialogueExecutorContext,
        DialogueSceneExecutor,
    )

    return DialogueSceneExecutor(
        DialogueExecutorContext(
            structured=structured_service,
            images=image_service,
            background=background_service,
        )
    )


_RECIPE_EXECUTOR_FACTORIES: dict[str, _RecipeExecutorFactory] = {
    "dialogue-scene": _create_dialogue_scene_executor,
    "scrolling-preview": _create_scrolling_preview_executor,
}


def create_default_runtime(
    config: StageGenConfig,
    recipe_id: str = "scrolling-preview",
) -> _ComposedHeadlessRuntime:
    """Compose concrete provider services with the selected recipe executor."""

    try:
        executor_factory = _RECIPE_EXECUTOR_FACTORIES[recipe_id]
    except KeyError as error:
        raise ValueError(f"no recipe executor registered for recipe: {recipe_id}") from error

    api_key = config.open_router_api_key
    if api_key is None:
        raise RuntimeError("OPENROUTER_API_KEY is required to compose the generation runtime")
    openrouter_url = config.open_router_base_url or "https://openrouter.ai/api/v1"
    if config.transparency_mode is TransparencyMode.NATIVE:
        if config.openai_api_key is None:
            raise RuntimeError("OPENAI_API_KEY is required for native image generation")
        image_service = create_openai_image_service(
            api_key=config.openai_api_key,
            model=config.openai_image_model,
            base_url=config.openai_base_url or "https://api.openai.com/v1",
            images_per_minute=config.openai_image_ipm,
        )
        if not image_service.supports_native_alpha:
            raise RuntimeError("configured OpenAI image model is not verified for native alpha")
    else:
        image_service = create_image_service(
            api_key=api_key, model=config.image_model, base_url=openrouter_url
        )
    structured_service = create_structured_service(
        api_key=api_key, model=config.text_model, base_url=openrouter_url
    )
    background_service = (
        create_background_removal_service(
            api_key=config.fal_key,
            model=config.background_removal_model,
            base_url=config.fal_base_url or "https://fal.run",
        )
        if config.fal_key is not None
        else None
    )
    music_service = create_music_service(
        api_key=api_key,
        model=config.music_model,
        base_url=openrouter_url,
    )
    standalone_runtime = create_headless_runtime(
        config,
        image_service=image_service,
        background_service=background_service,
        music_service=music_service,
    )
    standalone = cast("HeadlessRuntime", standalone_runtime)
    recipe_executor = executor_factory(
        image_service=image_service,
        structured_service=structured_service,
        background_service=background_service,
    )
    return _ComposedHeadlessRuntime(
        standalone,
        {recipe_id: recipe_executor},
        standalone_resource=standalone_runtime,
        resources=(structured_service,),
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
