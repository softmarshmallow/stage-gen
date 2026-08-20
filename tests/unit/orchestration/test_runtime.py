from __future__ import annotations

from pathlib import Path

import pytest

import stage_gen.orchestration.runtime as runtime_module
from stage_gen.capabilities import CapabilityArtifactResult, remove_background
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
from stage_gen.reliability import RetryPolicy


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
        model = "openai/gpt-5.6"
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
