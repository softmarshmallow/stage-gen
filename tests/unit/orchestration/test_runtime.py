from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

import stage_gen.orchestration.runtime as runtime_module
from gnode import RetryPolicy
from stage_gen.capabilities import CapabilityArtifactResult, HeadlessRuntime, remove_background
from stage_gen.components.background_removal import BackgroundRemovalRequest
from stage_gen.components.image_generation import ImageGenerationRequest
from stage_gen.components.music_generation import (
    AudioNormalizationRequest,
    MusicGenerationRequest,
)
from stage_gen.components.structured_generation import (
    ProviderStructuredOutput,
    StructuredGenerationRequest,
    StructuredGenerationService,
    StructuredOutputSchema,
)
from stage_gen.config import StageGenConfig
from stage_gen.orchestration.service import GenerateRequest, generate
from stage_gen.recipes.base import StageContext


def test_component_requests_reject_invalid_runtime_values() -> None:
    with pytest.raises(ValueError, match="temperature"):
        StructuredGenerationRequest(
            prompt="audit",
            artifact_path="x.json",
            schema=StructuredOutputSchema(name="x", json_schema={}),
            parse=lambda value: value,
            temperature=True,
        )
    with pytest.raises(ValueError, match="positive finite"):
        ImageGenerationRequest(
            prompt="audit",
            artifact_path="x.png",
            timeout_seconds=float("nan"),
        )
    with pytest.raises(ValueError, match="output_format"):
        BackgroundRemovalRequest(
            image_url="https://example.test/x.png",
            artifact_path="x.png",
            output_format="jpeg",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="top_p"):
        MusicGenerationRequest(
            prompt="audit",
            artifact_path="x.mp3",
            top_p=True,
        )
    with pytest.raises(ValueError, match="target_integrated_lufs"):
        AudioNormalizationRequest(
            source_path="raw.mp3",
            source_provenance_path="raw.mp3.meta.json",
            artifact_path="out.mp3",
            target_integrated_lufs=float("inf"),
        )
    with pytest.raises(ValueError, match="timeout_seconds"):
        AudioNormalizationRequest(
            source_path="raw.mp3",
            source_provenance_path="raw.mp3.meta.json",
            artifact_path="out.mp3",
            timeout_seconds=0,
        )


async def test_composed_runtime_dispatches_by_recipe_and_forwards_resume_controls(
    tmp_path: Path,
) -> None:
    class RecordingExecutor:
        def __init__(self) -> None:
            self.stage_name: str | None = None
            self.context: StageContext | None = None

        async def run_stage(self, stage_name: str, context: StageContext) -> tuple[str, ...]:
            self.stage_name = stage_name
            self.context = context
            return ("unchanged-artifact",)

    class Closable:
        async def aclose(self) -> None:
            pass

    executor = RecordingExecutor()
    context = StageContext(
        input={"forceStages": ["expressions"], "resume": True},
        tag="resume-tag",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode="chroma"),
    )
    runtime = runtime_module._ComposedHeadlessRuntime(
        cast("HeadlessRuntime", object()),
        {"dialogue-scene": executor},
        standalone_resource=Closable(),
    )

    result = await runtime.run_recipe_stage("dialogue-scene", "expressions", context)

    assert result == ("unchanged-artifact",)
    assert executor.stage_name == "expressions"
    assert executor.context is context
    assert executor.context.input == {"forceStages": ["expressions"], "resume": True}


async def test_composed_runtime_rejects_an_unknown_recipe_executor(tmp_path: Path) -> None:
    class Closable:
        async def aclose(self) -> None:
            pass

    runtime = runtime_module._ComposedHeadlessRuntime(
        cast("HeadlessRuntime", object()),
        {},
        standalone_resource=Closable(),
    )
    context = StageContext(
        input={},
        tag="unknown-tag",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode="chroma"),
    )

    with pytest.raises(ValueError, match="no recipe executor registered for recipe: missing"):
        await runtime.run_recipe_stage("missing", "prepare", context)


async def test_composed_runtime_closes_every_owned_resource_after_first_error() -> None:
    class Closable:
        def __init__(self, error: str | None = None) -> None:
            self.error = error
            self.close_calls = 0

        async def aclose(self) -> None:
            self.close_calls += 1
            if self.error is not None:
                raise RuntimeError(self.error)

    standalone = Closable("standalone close failed")
    structured = Closable()
    supplemental = Closable("supplemental close failed")
    runtime = runtime_module._ComposedHeadlessRuntime(
        cast("HeadlessRuntime", object()),
        {},
        standalone_resource=standalone,
        resources=(structured, supplemental),
    )

    with pytest.raises(RuntimeError, match="standalone close failed"):
        await runtime.aclose()

    assert standalone.close_calls == 1
    assert structured.close_calls == 1
    assert supplemental.close_calls == 1


def test_default_runtime_rejects_unknown_executor_before_provider_composition() -> None:
    with pytest.raises(ValueError, match="no recipe executor registered for recipe: missing"):
        runtime_module.create_default_runtime(StageGenConfig(), "missing")


async def test_default_runtime_selects_the_dialogue_executor_factory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeClosableService:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    image = FakeClosableService()
    structured = FakeClosableService()
    music = FakeClosableService()
    monkeypatch.setattr(runtime_module, "create_image_service", lambda **_kwargs: image)
    monkeypatch.setattr(runtime_module, "create_structured_service", lambda **_kwargs: structured)
    monkeypatch.setattr(runtime_module, "create_music_service", lambda **_kwargs: music)
    runtime = runtime_module.create_default_runtime(
        StageGenConfig(
            out_dir=tmp_path,
            open_router_api_key="offline",
            transparency_mode="chroma",
        ),
        "dialogue-scene",
    )
    context = StageContext(
        input={},
        tag="dialogue-tag",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode="chroma"),
        runtime=runtime,
    )

    try:
        with pytest.raises(ValueError, match="unknown dialogue-scene stage: unknown"):
            await runtime.run_recipe_stage("dialogue-scene", "unknown", context)
    finally:
        await runtime.aclose()

    assert image.closed
    assert structured.closed
    assert music.closed


@pytest.mark.asyncio
async def test_fal_only_standalone_background_removal_needs_no_openrouter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeStandaloneRuntime:
        def __init__(self) -> None:
            self.closed = False

        async def remove_background(
            self, *, input_path: str, output_path: str
        ) -> CapabilityArtifactResult:
            assert input_path == str(tmp_path / "input.png")
            assert output_path == str(tmp_path / "output.png")
            return CapabilityArtifactResult(
                artifact_path=output_path,
                provenance_path=f"{output_path}.meta.json",
                media_type="image/png",
                bytes=17,
                attempts=1,
            )

        async def aclose(self) -> None:
            self.closed = True

    fake = FakeStandaloneRuntime()

    def create_runtime(_config: StageGenConfig) -> FakeStandaloneRuntime:
        return fake

    monkeypatch.setattr(
        "stage_gen.orchestration.runtime.create_headless_runtime",
        create_runtime,
    )
    result = await remove_background(
        input_path=str(tmp_path / "input.png"),
        output_path=str(tmp_path / "output.png"),
        config=StageGenConfig(fal_key="fal-only", open_router_api_key=None),
    )
    assert result.media_type == "image/png"
    assert fake.closed


async def test_owned_runtime_closes_structured_backend_after_themed_compiler_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FailingStructuredBackend:
        provider = "fake-structured"
        model = "text-model"
        secrets: tuple[str, ...] = ()

        def __init__(self) -> None:
            self.calls = 0
            self.closed = False

        async def generate_once(
            self, _request: StructuredGenerationRequest[object]
        ) -> ProviderStructuredOutput:
            self.calls += 1
            raise RuntimeError("compiler unavailable")

        async def aclose(self) -> None:
            self.closed = True

    class FakeClosableService:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    backend = FailingStructuredBackend()
    structured = StructuredGenerationService[object](
        backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    image = FakeClosableService()
    music = FakeClosableService()
    monkeypatch.setattr(runtime_module, "create_structured_service", lambda **_kwargs: structured)
    monkeypatch.setattr(runtime_module, "create_image_service", lambda **_kwargs: image)
    monkeypatch.setattr(runtime_module, "create_music_service", lambda **_kwargs: music)

    summary = await generate(
        GenerateRequest(
            input={"prompt": "moonlit ruins", "theme": {"hostile_action": 3}},
            transparency_mode="chroma",
        ),
        StageGenConfig(
            out_dir=tmp_path,
            open_router_api_key="offline",
            transparency_mode="chroma",
        ),
        log=lambda _message: None,
    )

    assert summary.failed_stage == "theme-compile"
    assert backend.calls == 6
    assert backend.closed
    assert image.closed
    assert music.closed
