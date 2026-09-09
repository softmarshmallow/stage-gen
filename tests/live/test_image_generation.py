from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from gnode import ImageGenerationRequest, ImageReference
from stage_gen.media import data_url, inspect_image
from stage_gen.orchestration import create_image_service

from ._contracts import assert_persisted_artifact
from .conftest import OpenRouterLiveSettings

pytestmark = [pytest.mark.live, pytest.mark.asyncio]


async def test_image_generation_live_smoke(
    tmp_path: Path, openrouter_settings: OpenRouterLiveSettings
) -> None:
    output = tmp_path / "image.asset"
    reference_bytes = _reference_png()
    async with create_image_service(
        api_key=openrouter_settings.api_key,
        model=openrouter_settings.image_model,
        base_url=openrouter_settings.base_url,
    ) as service:
        result = await service.generate(
            ImageGenerationRequest(
                prompt=(
                    "Create an original wide atmospheric environment study informed by the "
                    "supplied reference, without text or logos."
                ),
                artifact_path=output,
                input_references=(
                    ImageReference(
                        url=data_url(reference_bytes, "image/png"),
                        provenance_ref="fixture:openrouter-sunburst-reference-v1",
                    ),
                ),
                size="2560x1440",
                quality="max",
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
    assert (facts.width, facts.height) == (2560, 1440)
    assert result.attempts == provenance.attempts
    assert provenance.validation["signature"] == "matched"
    assert provenance.params["quality"] == "max"
    assert provenance.component.name == "@stage-gen/image-generation"


def _reference_png() -> bytes:
    image = Image.new("RGB", (64, 64), (225, 236, 248))
    for x in range(16, 48):
        for y in range(16, 48):
            image.putpixel((x, y), (32, 96, 176))
    output = BytesIO()
    image.save(output, format="PNG", compress_level=9, optimize=False)
    return output.getvalue()
