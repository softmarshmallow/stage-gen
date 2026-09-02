"""The sound-effect retry owner: signature floor, caller validation, provenance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar, Literal

import pytest

from gnode import (
    BinaryArtifact,
    ProviderResponseMetadata,
    ProviderSoundEffect,
    RetryPolicy,
    SoundEffectGenerationRequest,
    SoundEffectGenerationService,
)
from stage_gen.identity import SOUND_EFFECT_GENERATION_COMPONENT, STAGE_GEN_TOOL

MP3 = b"ID3\x04\x00\x00" + b"\x00" * 64


class _ScriptedBackend:
    spec_version: ClassVar[Literal[1]] = 1
    provider = "scripted"
    model = "scripted-sfx"
    secrets: tuple[str, ...] = ("hush",)

    def __init__(self, responses: list[bytes]) -> None:
        self._responses = responses
        self.requests: list[SoundEffectGenerationRequest] = []
        self.closed = False

    async def generate_once(self, request: SoundEffectGenerationRequest) -> ProviderSoundEffect:
        self.requests.append(request)
        data = self._responses.pop(0)
        return ProviderSoundEffect(
            data=data,
            media_type="audio/mpeg",
            source_shape="binary",
            response_metadata=ProviderResponseMetadata(
                request_id="sfx-1", usage={"character_cost": 11}
            ),
        )

    async def aclose(self) -> None:
        self.closed = True


def _service(backend: _ScriptedBackend) -> SoundEffectGenerationService:
    return SoundEffectGenerationService(
        backend,
        component=SOUND_EFFECT_GENERATION_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )


def test_request_bounds_are_the_route_bounds() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        SoundEffectGenerationRequest(prompt="  ", artifact_path="x.mp3")
    with pytest.raises(ValueError, match="450"):
        SoundEffectGenerationRequest(prompt="a" * 451, artifact_path="x.mp3")
    with pytest.raises(ValueError, match=r"between 0\.5 and 30"):
        SoundEffectGenerationRequest(prompt="door", artifact_path="x.mp3", duration_seconds=0.4)
    with pytest.raises(ValueError, match="between 0 and 1"):
        SoundEffectGenerationRequest(prompt="door", artifact_path="x.mp3", prompt_influence=1.5)
    with pytest.raises(ValueError, match="output_format"):
        SoundEffectGenerationRequest(prompt="door", artifact_path="x.mp3", output_format="wav")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_generate_persists_the_verbatim_prompt_and_route_parameters(tmp_path: Path) -> None:
    backend = _ScriptedBackend([MP3])
    facts: list[int] = []

    def validate(artifact: BinaryArtifact) -> dict[str, object]:
        facts.append(len(artifact.data))
        return {"peak_dbfs": -6.5, "clipped": False}

    result = await _service(backend).generate(
        SoundEffectGenerationRequest(
            prompt="wooden door opens",
            artifact_path=tmp_path / "door.mp3",
            duration_seconds=0.6,
            prompt_influence=0.3,
            metadata={"effect_id": "door"},
            validate=validate,
        )
    )

    assert result.data == MP3
    assert result.attempts == 1
    assert facts == [len(MP3)]
    sidecar = json.loads((tmp_path / "door.mp3.meta.json").read_text())
    assert sidecar["prompt"] == "wooden door opens"
    assert sidecar["params"] == {
        "output_format": "mp3",
        "loop": False,
        "duration_seconds": 0.6,
        "prompt_influence": 0.3,
        "validated": True,
        "metadata": {"effect_id": "door"},
    }
    assert sidecar["validation"]["peak_dbfs"] == -6.5
    assert sidecar["validation"]["source_shape"] == "binary"
    assert sidecar["response"]["usage"] == {"character_cost": 11}
    assert sidecar["component"]["name"] == "@stage-gen/sound-effect-generation"
    assert "hush" not in (tmp_path / "door.mp3.meta.json").read_text()


@pytest.mark.asyncio
async def test_a_refused_draw_is_retried_inside_the_owner_and_never_persisted(
    tmp_path: Path,
) -> None:
    backend = _ScriptedBackend([b"RIFF\x00\x00\x00\x00WAVE", MP3, MP3])
    seen = 0

    def validate(artifact: BinaryArtifact) -> dict[str, object]:
        nonlocal seen
        seen += 1
        if seen == 1:
            raise ValueError("generated sound effect peaks at -44.2 dBFS: effectively silent")
        return {"peak_dbfs": -9.0, "clipped": False}

    result = await _service(backend).generate(
        SoundEffectGenerationRequest(
            prompt="hit", artifact_path=tmp_path / "hit.mp3", validate=validate
        )
    )

    # Attempt one fails the mp3 signature, attempt two the caller's level gate,
    # attempt three ships. Only the shipped bytes ever reach disk.
    assert result.attempts == 3
    assert (tmp_path / "hit.mp3").read_bytes() == MP3
    assert json.loads((tmp_path / "hit.mp3.meta.json").read_text())["attempts"] == 3


@pytest.mark.asyncio
async def test_the_owner_stops_at_six_attempts(tmp_path: Path) -> None:
    backend = _ScriptedBackend([b"not audio"] * 7)

    with pytest.raises(Exception, match="attempt"):
        await _service(backend).generate(
            SoundEffectGenerationRequest(prompt="hit", artifact_path=tmp_path / "hit.mp3")
        )

    assert len(backend.requests) == 6
    assert not (tmp_path / "hit.mp3").exists()
