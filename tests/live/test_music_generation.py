from __future__ import annotations

from pathlib import Path

import pytest

from stage_gen.components import MusicGenerationRequest
from stage_gen.media import assert_audio_signature
from stage_gen.orchestration import create_music_service

from ._contracts import assert_persisted_artifact
from .conftest import OpenRouterLiveSettings

pytestmark = [pytest.mark.live, pytest.mark.asyncio]


async def test_music_generation_live_smoke(
    tmp_path: Path, openrouter_settings: OpenRouterLiveSettings
) -> None:
    output = tmp_path / "music.mp3"
    async with create_music_service(
        api_key=openrouter_settings.api_key,
        model=openrouter_settings.music_model,
        base_url=openrouter_settings.base_url,
    ) as service:
        result = await service.generate(
            MusicGenerationRequest(
                prompt="Create an original, brand-neutral short instrumental chime.",
                artifact_path=output,
                output_format="mp3",
                metadata={"live_smoke": True},
                timeout_seconds=openrouter_settings.timeout_seconds,
            )
        )
    data, provenance = assert_persisted_artifact(
        output,
        result.provenance_path,
        provider="openrouter",
        model=openrouter_settings.music_model,
    )
    assert data == result.data
    assert_audio_signature(data, result.media_type)
    assert result.attempts == provenance.attempts
    assert provenance.validation["signature"] == "matched"
    assert provenance.params["output_format"] == "mp3"
    assert provenance.component.name == "@stage-gen/music-generation"
