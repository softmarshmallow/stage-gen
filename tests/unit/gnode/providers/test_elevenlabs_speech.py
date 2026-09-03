from __future__ import annotations

import json

import httpx
import pytest

from gnode import SpeechGenerationRequest
from gnode.providers.elevenlabs import ElevenLabsSpeechBackend

MP3 = b"\xff\xfb\x90\x00" + b"\x00" * 32


def _request(**overrides: object) -> SpeechGenerationRequest:
    fields: dict[str, object] = {
        "text": "[excited] いくよっ!",
        "voice": "voice-7",
        "artifact_path": "go.mp3",
    }
    fields.update(overrides)
    return SpeechGenerationRequest(**fields)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_generate_once_posts_the_route_shape_and_reads_the_charge() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            content=MP3,
            headers={
                "content-type": "audio/mpeg",
                "request-id": "req-9",
                "character-cost": "23",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = ElevenLabsSpeechBackend(api_key="secret", client=client)
        generated = await backend.generate_once(_request(stability=0.5, language_code="ja"))

    assert generated.data == MP3
    assert generated.media_type == "audio/mpeg"
    assert generated.source_shape == "binary"
    assert generated.response_metadata.request_id == "req-9"
    assert generated.response_metadata.usage == {"character_cost": 23}
    assert captured["url"] == (
        "https://api.elevenlabs.io/v1/text-to-speech/voice-7?output_format=mp3_44100_192"
    )
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["xi-api-key"] == "secret"
    assert headers["accept"] == "audio/mpeg"
    assert captured["body"] == {
        "text": "[excited] いくよっ!",
        "model_id": "eleven_v3",
        "voice_settings": {"stability": 0.5},
        "language_code": "ja",
    }


@pytest.mark.asyncio
async def test_absent_settings_are_not_sent() -> None:
    """v3 accepts stability alone; an omitted one leaves the provider default in force."""

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, content=MP3, headers={"content-type": "audio/mpeg"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = ElevenLabsSpeechBackend(api_key="secret", client=client)
        generated = await backend.generate_once(_request())

    assert captured["body"] == {"text": "[excited] いくよっ!", "model_id": "eleven_v3"}
    assert generated.response_metadata.usage is None


@pytest.mark.asyncio
async def test_a_provider_error_is_raised_with_the_key_redacted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "voice not found: secret"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = ElevenLabsSpeechBackend(api_key="secret", client=client)
        with pytest.raises(Exception) as caught:
            await backend.generate_once(_request())

    assert "secret" not in str(caught.value)


@pytest.mark.asyncio
async def test_non_audio_bytes_are_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not audio", headers={"content-type": "audio/mpeg"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = ElevenLabsSpeechBackend(api_key="secret", client=client)
        with pytest.raises(ValueError):
            await backend.generate_once(_request())


def test_constructor_refuses_empty_identity() -> None:
    with pytest.raises(ValueError, match="api_key"):
        ElevenLabsSpeechBackend(api_key=" ")
    with pytest.raises(ValueError, match="model"):
        ElevenLabsSpeechBackend(api_key="k", model=" ")
