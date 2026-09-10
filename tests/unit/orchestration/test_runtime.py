from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from gnode import (
    BackgroundRemovalRequest,
    ImageGenerationRequest,
    MusicGenerationRequest,
    StructuredGenerationRequest,
    StructuredOutputSchema,
)
from stage_gen.capabilities import (
    CapabilityArtifactResult,
    HeadlessRuntime,
    generate_image_artifact,
    remove_background,
)
from stage_gen.components.audio_normalization import (
    AudioNormalizationRequest,
)
from stage_gen.config import ConfigError, StageGenConfig, TransparencyMode
from stage_gen.image_product import ImageProvider
from stage_gen.model_routes import (
    FAL_IMAGE_GENERATION_ROUTE_ID,
    OPENAI_IMAGE_GENERATION_ROUTE_ID,
    OPENROUTER_IMAGE_GENERATION_ROUTE_ID,
)
from stage_gen.orchestration.runtime import DefaultHeadlessRuntime


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config",
    [
        StageGenConfig(
            transparency_mode=TransparencyMode.NATIVE,
            open_router_api_key="openrouter-only",
        ),
        StageGenConfig(
            transparency_mode=TransparencyMode.CHROMA,
            image_provider_override=ImageProvider.OPENAI,
            openai_api_key="openai-only",
        ),
        StageGenConfig(
            image_provider_override=ImageProvider.FAL,
            fal_key="fal-only",
        ),
    ],
)
async def test_standalone_image_admission_uses_selected_opaque_route_credential(
    config: StageGenConfig,
    tmp_path: Path,
) -> None:
    class FakeStandaloneRuntime:
        async def generate_image(
            self,
            *,
            prompt: str,
            output_path: str,
            aspect_ratio: str,
            reference_paths: Sequence[str],
        ) -> CapabilityArtifactResult:
            assert prompt == "A neutral icon."
            assert aspect_ratio == "1:1"
            assert reference_paths == ()
            return CapabilityArtifactResult(
                artifact_path=output_path,
                provenance_path=f"{output_path}.meta.json",
                media_type="image/png",
                bytes=17,
                attempts=1,
            )

    result = await generate_image_artifact(
        prompt="A neutral icon.",
        output_path=str(tmp_path / "output.png"),
        config=config,
        runtime=cast(HeadlessRuntime, FakeStandaloneRuntime()),
    )

    assert result.media_type == "image/png"


@pytest.mark.asyncio
async def test_standalone_image_admission_refuses_missing_selected_provider_credential(
    tmp_path: Path,
) -> None:
    class UncalledRuntime:
        async def generate_image(
            self,
            *,
            prompt: str,
            output_path: str,
            aspect_ratio: str,
            reference_paths: Sequence[str],
        ) -> CapabilityArtifactResult:
            raise AssertionError("runtime must not run before route credential admission")

    with pytest.raises(ConfigError) as exc_info:
        await generate_image_artifact(
            prompt="A neutral icon.",
            output_path=str(tmp_path / "output.png"),
            config=StageGenConfig(
                transparency_mode=TransparencyMode.NATIVE,
                openai_api_key="unselected-openai-key",
            ),
            runtime=cast(HeadlessRuntime, UncalledRuntime()),
        )

    assert exc_info.value.missing == ("OPENROUTER_API_KEY",)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "aspect_ratio", "route_id"),
    [
        (StageGenConfig(), "1:1", OPENROUTER_IMAGE_GENERATION_ROUTE_ID),
        (StageGenConfig(), "16:9", OPENAI_IMAGE_GENERATION_ROUTE_ID),
        (
            StageGenConfig(image_provider_override=ImageProvider.FAL),
            "16:9",
            FAL_IMAGE_GENERATION_ROUTE_ID,
        ),
    ],
)
async def test_headless_image_generation_resolves_exact_opaque_route(
    config: StageGenConfig,
    aspect_ratio: str,
    route_id: str,
    tmp_path: Path,
) -> None:
    requests: list[ImageGenerationRequest] = []

    class CapturingImageService:
        async def generate(self, request: ImageGenerationRequest) -> SimpleNamespace:
            requests.append(request)
            return SimpleNamespace(
                data=b"synthetic-image",
                media_type="image/png",
                provenance_path=str(tmp_path / "output.png.meta.json"),
                attempts=1,
            )

        async def aclose(self) -> None:
            return None

    runtime = DefaultHeadlessRuntime(
        config,
        image_service=CapturingImageService(),  # type: ignore[arg-type]
    )
    try:
        result = await runtime.generate_image(
            prompt="A neutral icon.",
            output_path=str(tmp_path / "output.png"),
            aspect_ratio=aspect_ratio,
            reference_paths=(),
        )
    finally:
        await runtime.aclose()

    assert result.media_type == "image/png"
    assert len(requests) == 1
    assert requests[0].quality == "max"
    assert requests[0].background == "opaque"
    assert requests[0].resolved_binding is not None
    assert requests[0].resolved_binding.route.route_id == route_id
