from __future__ import annotations

from pathlib import Path

import pytest

from gnode import SoundEffectGenerationRequest
from stage_gen.components.sound_effect import admit_sound_effect_bytes
from stage_gen.media import assert_audio_signature, probe_audio
from stage_gen.orchestration import create_sound_effect_service

from ._contracts import assert_persisted_artifact
from .conftest import ElevenLabsLiveSettings

pytestmark = [pytest.mark.live, pytest.mark.asyncio]


async def test_sound_effect_generation_live_smoke(
    tmp_path: Path, elevenlabs_settings: ElevenLabsLiveSettings
) -> None:
    """One short foley draw, admitted on level, never post-processed.

    The prompt follows docs/spec/model-eleven-text-to-sound-v2.md: an event
    with its material, nothing else. Whether it sounds right is a listening
    verdict and is not asserted here.
    """

    output = tmp_path / "door.mp3"
    async with create_sound_effect_service(
        api_key=elevenlabs_settings.api_key,
        model=elevenlabs_settings.model,
        base_url=elevenlabs_settings.base_url,
    ) as service:
        result = await service.generate(
            SoundEffectGenerationRequest(
                prompt="wooden door opens",
                artifact_path=output,
                duration_seconds=0.8,
                metadata={"live_smoke": True},
                timeout_seconds=elevenlabs_settings.timeout_seconds,
                validate=lambda artifact: admit_sound_effect_bytes(artifact.data),
            )
        )
    data, provenance = assert_persisted_artifact(
        output,
        result.provenance_path,
        provider="elevenlabs",
        model=elevenlabs_settings.model,
    )
    assert data == result.data
    assert_audio_signature(data, result.media_type)
    assert result.attempts == provenance.attempts
    assert provenance.validation["signature"] == "matched"
    assert provenance.validation["clipped"] is False
    assert provenance.params["duration_seconds"] == 0.8
    assert provenance.component.name == "@stage-gen/sound-effect-generation"
    probe = await probe_audio(output)
    assert abs(probe.duration_seconds - 0.8) <= 0.15
