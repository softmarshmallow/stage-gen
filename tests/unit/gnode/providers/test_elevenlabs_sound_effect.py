from __future__ import annotations

import json

import httpx
import pytest

from gnode import SoundEffectGenerationRequest
from gnode.providers.elevenlabs import ElevenLabsSoundEffectBackend

MP3 = b"\xff\xfb\x90\x00" + b"\x00" * 32


def _request(**overrides: object) -> SoundEffectGenerationRequest:
    fields: dict[str, object] = {"prompt": "wooden door opens", "artifact_path": "door.mp3"}
    fields.update(overrides)
    return SoundEffectGenerationRequest(**fields)  # type: ignore[arg-type]


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
                "request-id": "req-7",
                "character-cost": "11",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = ElevenLabsSoundEffectBackend(api_key="secret", client=client)
        generated = await backend.generate_once(
            _request(duration_seconds=0.6, prompt_influence=0.3)
        )

    assert generated.data == MP3
    assert generated.media_type == "audio/mpeg"
    assert generated.source_shape == "binary"
    assert generated.response_metadata.request_id == "req-7"
    assert generated.response_metadata.usage == {"character_cost": 11}
    assert captured["url"] == (
        "https://api.elevenlabs.io/v1/sound-generation?output_format=mp3_44100_192"
    )
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["xi-api-key"] == "secret"
    assert captured["body"] == {
        "text": "wooden door opens",
        "model_id": "eleven_text_to_sound_v2",
        "loop": False,
        "duration_seconds": 0.6,
        "prompt_influence": 0.3,
    }


@pytest.mark.asyncio
async def test_unset_parameters_are_omitted_so_the_provider_default_applies() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, content=MP3, headers={"content-type": "audio/mpeg"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await ElevenLabsSoundEffectBackend(api_key="secret", client=client).generate_once(
            _request()
        )

    assert captured["body"] == {
        "text": "wooden door opens",
        "model_id": "eleven_text_to_sound_v2",
        "loop": False,
    }


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(429, json={"detail": {"message": "secret quota"}}), "HTTP 429"),
        (httpx.Response(200, content=b"", headers={"content-type": "audio/mpeg"}), "no audio"),
        (
            httpx.Response(200, content=b"not audio", headers={"content-type": "audio/mpeg"}),
            "do not match",
        ),
        (
            httpx.Response(200, content=MP3, headers={"content-type": "audio/wav"}),
            "received audio/wav",
        ),
    ],
)
@pytest.mark.asyncio
async def test_a_bad_response_raises_without_leaking_the_key(
    response: httpx.Response, message: str
) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: response)) as client:
        backend = ElevenLabsSoundEffectBackend(api_key="secret", client=client)
        with pytest.raises(ValueError, match=message) as captured:
            await backend.generate_once(_request())
    assert "secret" not in str(captured.value)


def test_constructor_refuses_blank_identity() -> None:
    with pytest.raises(ValueError, match="api_key"):
        ElevenLabsSoundEffectBackend(api_key=" ")
    with pytest.raises(ValueError, match="model"):
        ElevenLabsSoundEffectBackend(api_key="secret", model=" ")
