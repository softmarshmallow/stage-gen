from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from gnode import (
    MusicGenerationRequest,
    MusicGenerationService,
    RetryPolicy,
)
from gnode.providers.openrouter import OpenRouterMusicBackend
from stage_gen.identity import MUSIC_GENERATION_COMPONENT, STAGE_GEN_TOOL

from ..._helpers import wav_bytes


@pytest.mark.asyncio
async def test_music_assembles_sse_audio_and_persists_provenance(tmp_path: Path) -> None:
    audio = wav_bytes()
    encoded = base64.b64encode(audio).decode()
    midpoint = len(encoded) // 2
    midpoint -= midpoint % 4
    events = [
        {"choices": [{"delta": {"audio": {"data": encoded[:midpoint], "format": "wav"}}}]},
        {
            "choices": [{"delta": {"audio": {"data": encoded[midpoint:]}, "content": "done"}}],
            "usage": {"tokens": 3},
        },
    ]
    stream = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
    body: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body.update(json.loads(request.content))
        return httpx.Response(
            200,
            text=stream,
            headers={"content-type": "text/event-stream", "x-request-id": "music-1"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await MusicGenerationService(
            OpenRouterMusicBackend(api_key="secret", client=client),
            component=MUSIC_GENERATION_COMPONENT,
            tool=STAGE_GEN_TOOL,
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ).generate(
            MusicGenerationRequest(
                prompt="original instrumental test loop",
                artifact_path=tmp_path / "theme.wav",
                output_format="wav",
            )
        )
    assert result.data == audio
    assert result.text == "done"
    assert body["modalities"] == ["text", "audio"]
    assert body["stream"] is True
    sidecar = json.loads((tmp_path / "theme.wav.meta.json").read_text())
    assert sidecar["validation"]["source_shape"] == "sse"
    assert sidecar["response"]["usage"] == {"tokens": 3}


@pytest.mark.asyncio
async def test_music_retries_empty_invalid_and_provider_native_steps_audio(
    tmp_path: Path,
) -> None:
    calls = 0
    audio = wav_bytes()

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, content=b"")
        payload: dict[str, object]
        if calls == 2:
            payload = {"choices": [{"message": {"audio": {"data": "AAAA", "format": "wav"}}}]}
        else:
            payload = {
                "steps": [
                    {
                        "type": "model_output",
                        "content": [
                            {"type": "text", "text": "structure"},
                            {
                                "type": "audio",
                                "data": base64.b64encode(audio).decode(),
                                "media_type": "audio/wav",
                            },
                        ],
                    }
                ]
            }
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await MusicGenerationService(
            OpenRouterMusicBackend(api_key="secret", client=client),
            component=MUSIC_GENERATION_COMPONENT,
            tool=STAGE_GEN_TOOL,
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ).generate(
            MusicGenerationRequest(
                prompt="original loop",
                artifact_path=tmp_path / "out.wav",
                output_format="wav",
            )
        )
    assert calls == result.attempts == 3
    assert result.text == "structure"
