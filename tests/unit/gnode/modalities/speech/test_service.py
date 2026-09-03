"""The speech retry owner: signature floor, caller validation, provenance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar, Literal

import pytest

from gnode import (
    BinaryArtifact,
    ProviderResponseMetadata,
    ProviderSpeech,
    RetryPolicy,
    SpeechGenerationRequest,
    SpeechGenerationService,
)
from stage_gen.identity import SPEECH_GENERATION_COMPONENT, STAGE_GEN_TOOL

MP3 = b"ID3\x04\x00\x00" + b"\x00" * 64


class _ScriptedBackend:
    spec_version: ClassVar[Literal[1]] = 1
    provider = "scripted"
    model = "scripted-tts"
    secrets: tuple[str, ...] = ("hush",)

    def __init__(self, responses: list[bytes]) -> None:
        self._responses = responses
        self.requests: list[SpeechGenerationRequest] = []
        self.closed = False

    async def generate_once(self, request: SpeechGenerationRequest) -> ProviderSpeech:
        self.requests.append(request)
        data = self._responses.pop(0)
        return ProviderSpeech(
            data=data,
            media_type="audio/mpeg",
            source_shape="binary",
            response_metadata=ProviderResponseMetadata(
                request_id="tts-1", usage={"character_cost": 23}
            ),
        )

    async def aclose(self) -> None:
        self.closed = True


def _service(backend: _ScriptedBackend) -> SpeechGenerationService:
    return SpeechGenerationService(
        backend,
        component=SPEECH_GENERATION_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )


def test_request_bounds_are_the_route_bounds() -> None:
    with pytest.raises(ValueError, match="text must be non-empty"):
        SpeechGenerationRequest(text="  ", voice="v", artifact_path="x.mp3")
    with pytest.raises(ValueError, match="5000"):
        SpeechGenerationRequest(text="a" * 5001, voice="v", artifact_path="x.mp3")
    with pytest.raises(ValueError, match="voice must be non-empty"):
        SpeechGenerationRequest(text="hi", voice=" ", artifact_path="x.mp3")
    with pytest.raises(ValueError, match="between 0 and 1"):
        SpeechGenerationRequest(text="hi", voice="v", artifact_path="x.mp3", stability=1.5)
    with pytest.raises(ValueError, match="language_code"):
        SpeechGenerationRequest(text="hi", voice="v", artifact_path="x.mp3", language_code="")
    with pytest.raises(ValueError, match="output_format"):
        SpeechGenerationRequest(text="hi", voice="v", artifact_path="x.mp3", output_format="wav")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_generate_persists_the_verbatim_text_and_route_parameters(tmp_path: Path) -> None:
    backend = _ScriptedBackend([MP3])
    facts: list[int] = []

    def validate(artifact: BinaryArtifact) -> dict[str, object]:
        facts.append(len(artifact.data))
        return {"peak_dbfs": -1.2, "clipped": False}

    result = await _service(backend).generate(
        SpeechGenerationRequest(
            text="[excited] いくよっ!",
            voice="voice-7",
            artifact_path=tmp_path / "go.mp3",
            stability=0.5,
            language_code="ja",
            metadata={"effect_id": "go"},
            validate=validate,
        )
    )

    assert result.data == MP3
    assert result.attempts == 1
    assert facts == [len(MP3)]
    sidecar = json.loads((tmp_path / "go.mp3.meta.json").read_text())
    # The annotation is part of the prompt, verbatim: nothing strips or adds a tag.
    assert sidecar["prompt"] == "[excited] いくよっ!"
    assert sidecar["seed"] is None
    assert sidecar["params"] == {
        "voice": "voice-7",
        "output_format": "mp3",
        "validated": True,
        "stability": 0.5,
        "language_code": "ja",
        "metadata": {"effect_id": "go"},
    }
    assert sidecar["validation"]["peak_dbfs"] == -1.2
    assert sidecar["validation"]["source_shape"] == "binary"
    assert sidecar["response"]["usage"] == {"character_cost": 23}
    assert sidecar["component"]["name"] == "@stage-gen/speech-generation"
    assert "hush" not in (tmp_path / "go.mp3.meta.json").read_text()


@pytest.mark.asyncio
async def test_optional_parameters_stay_out_of_provenance_when_absent(tmp_path: Path) -> None:
    backend = _ScriptedBackend([MP3])
    await _service(backend).generate(
        SpeechGenerationRequest(text="hi", voice="v", artifact_path=tmp_path / "hi.mp3")
    )
    sidecar = json.loads((tmp_path / "hi.mp3.meta.json").read_text())
    assert sidecar["params"] == {"voice": "v", "output_format": "mp3", "validated": False}


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
            raise ValueError("spoken line runs 7.7s against an authored ceiling of 3.0s")
        return {"peak_dbfs": -0.9, "clipped": False}

    result = await _service(backend).generate(
        SpeechGenerationRequest(
            text="go", voice="v", artifact_path=tmp_path / "go.mp3", validate=validate
        )
    )

    # Attempt one fails the mp3 signature, attempt two the caller's length gate,
    # attempt three ships. Only the shipped bytes ever reach disk.
    assert result.attempts == 3
    assert (tmp_path / "go.mp3").read_bytes() == MP3
    assert json.loads((tmp_path / "go.mp3.meta.json").read_text())["attempts"] == 3


@pytest.mark.asyncio
async def test_the_owner_stops_at_six_attempts(tmp_path: Path) -> None:
    backend = _ScriptedBackend([b"not audio"] * 7)

    with pytest.raises(Exception, match="attempt"):
        await _service(backend).generate(
            SpeechGenerationRequest(text="go", voice="v", artifact_path=tmp_path / "go.mp3")
        )

    assert len(backend.requests) == 6
    assert not (tmp_path / "go.mp3").exists()
