from __future__ import annotations

import asyncio
import base64
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from gnode import ImageGenerationRequest, ImageReference
from stage_gen.media import NATIVE_ALPHA_OPAQUE_THRESHOLD, inspect_image
from stage_gen.providers.openai import OpenAIImageBackend

from .conftest import OpenAILiveSettings

pytestmark = [pytest.mark.live, pytest.mark.asyncio]


@pytest.mark.parametrize("with_reference", [False, True])
async def test_openai_gpt_image_2_returns_nontrivial_native_alpha(
    tmp_path: Path,
    openai_settings: OpenAILiveSettings,
    with_reference: bool,
) -> None:
    output = tmp_path / ("native-edit.png" if with_reference else "native-generation.png")
    references = (_reference_image(),) if with_reference else ()
    backend = OpenAIImageBackend(
        api_key=openai_settings.api_key,
        model=openai_settings.image_model,
        base_url=openai_settings.base_url,
    )
    try:
        async with asyncio.timeout(openai_settings.timeout_seconds):
            result = await backend.generate_once(
                ImageGenerationRequest(
                    prompt=(
                        "Create one original small blue enamel game token, centered and fully "
                        "isolated. Preserve a generous empty transparent border. No ground, "
                        "shadow, frame, text, scenery, or background."
                    ),
                    artifact_path=output,
                    input_references=references,
                    aspect_ratio="1:1",
                    quality="high",
                    background="transparent",
                    output_format="png",
                    moderation="low",
                    metadata={"live_smoke": True, "with_reference": with_reference},
                )
            )
    finally:
        await backend.aclose()

    await asyncio.to_thread(output.write_bytes, result.data)
    facts = inspect_image(result.data, expected_media_type="image/png")
    assert facts.has_alpha
    with Image.open(BytesIO(result.data)) as opened:
        opened.load()
        alpha = opened.convert("RGBA").getchannel("A").tobytes()
    transparent = sum(value < 255 for value in alpha)
    visible = sum(value > 0 for value in alpha)
    assert transparent > 0
    assert visible > 0
    assert min(alpha) == 0
    assert max(alpha) >= NATIVE_ALPHA_OPAQUE_THRESHOLD

    assert result.media_type == "image/png"
    assert result.applied_params is not None
    assert result.applied_params["background"] == "transparent"
    assert result.applied_params["output_format"] == "png"
    assert result.applied_params["quality"] == "high"
    assert result.applied_params["operation"] == ("edit" if with_reference else "generation")
    if with_reference:
        assert "moderation" not in result.applied_params
    else:
        assert result.applied_params["moderation"] == "low"


def _reference_image() -> ImageReference:
    image = Image.new("RGB", (64, 64), (238, 244, 252))
    for x in range(16, 48):
        for y in range(16, 48):
            image.putpixel((x, y), (38, 112, 210))
    output = BytesIO()
    image.save(output, format="PNG", compress_level=9, optimize=False)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return ImageReference(
        url=f"data:image/png;base64,{encoded}",
        provenance_ref="fixture:openai-native-alpha-reference-v1",
    )
