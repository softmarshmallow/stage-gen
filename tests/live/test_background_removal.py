from __future__ import annotations

import base64
from pathlib import Path

import pytest

from stage_gen.components import BackgroundRemovalRequest, ImageGenerationRequest
from stage_gen.media import inspect_image
from stage_gen.orchestration import create_background_removal_service, create_image_service

from ._contracts import assert_persisted_artifact
from .conftest import FalLiveSettings, OpenRouterLiveSettings

pytestmark = [pytest.mark.live, pytest.mark.asyncio]


async def test_background_removal_live_smoke(
    tmp_path: Path,
    openrouter_settings: OpenRouterLiveSettings,
    fal_settings: FalLiveSettings,
) -> None:
    source_path = tmp_path / "fresh-source.asset"
    async with create_image_service(
        api_key=openrouter_settings.api_key,
        model=openrouter_settings.image_model,
        base_url=openrouter_settings.base_url,
    ) as image_service:
        source = await image_service.generate(
            ImageGenerationRequest(
                prompt="Create an original, brand-neutral red circle on a plain white background.",
                artifact_path=source_path,
                aspect_ratio="1:1",
                quality="low",
                background="opaque",
                metadata={"live_smoke": "background-source"},
                timeout_seconds=openrouter_settings.timeout_seconds,
            )
        )
    inspect_image(source.data, expected_media_type=source.media_type)
    source_url = f"data:{source.media_type};base64," + base64.b64encode(source.data).decode("ascii")
    output = tmp_path / "removed.png"
    async with create_background_removal_service(
        api_key=fal_settings.api_key,
        model=fal_settings.model,
        base_url=fal_settings.base_url,
    ) as service:
        result = await service.remove(
            BackgroundRemovalRequest(
                image_url=source_url,
                artifact_path=output,
                output_format="png",
                metadata={"live_smoke": True},
                timeout_seconds=fal_settings.timeout_seconds,
            )
        )
    data, provenance = assert_persisted_artifact(
        output,
        result.provenance_path,
        provider="fal",
        model=fal_settings.model,
    )
    inspect_image(data, expected_media_type=result.media_type)
    assert result.attempts == provenance.attempts
    assert provenance.inputs[0].source == "content"
    assert provenance.params["metadata"] == {"live_smoke": True}
    assert provenance.validation["signature"] == "matched"
    assert provenance.component.name == "@stage-gen/background-removal"
