from __future__ import annotations

from pathlib import Path

import pytest

from gnode import ImageGenerationRequest
from stage_gen.media import inspect_image
from stage_gen.orchestration import create_image_service

from ._contracts import assert_persisted_artifact
from .conftest import OpenRouterLiveSettings

pytestmark = [pytest.mark.live, pytest.mark.asyncio]


async def test_image_generation_live_smoke(
    tmp_path: Path, openrouter_settings: OpenRouterLiveSettings
) -> None:
    output = tmp_path / "image.asset"
    async with create_image_service(
        api_key=openrouter_settings.api_key,
        model=openrouter_settings.image_model,
        base_url=openrouter_settings.base_url,
    ) as service:
        result = await service.generate(
            ImageGenerationRequest(
                prompt="Create an original, brand-neutral red circle on a plain white background.",
                artifact_path=output,
                aspect_ratio="1:1",
                quality="low",
                background="opaque",
                metadata={"live_smoke": True},
                timeout_seconds=openrouter_settings.timeout_seconds,
            )
        )
    data, provenance = assert_persisted_artifact(
        output,
        result.provenance_path,
        provider="openrouter",
        model=openrouter_settings.image_model,
    )
    facts = inspect_image(data, expected_media_type=result.media_type)
    assert facts.width > 0 and facts.height > 0
    assert result.attempts == provenance.attempts
    assert provenance.validation["signature"] == "matched"
    assert provenance.params["quality"] == "low"
    assert provenance.component.name == "@stage-gen/image-generation"
