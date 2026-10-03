"""Stage Gen's ``music.generate``, ``sound.generate`` and ``speech.generate`` routes."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from gnode import CallRefused, Route, Store
from stage_gen.config import StageGenConfig
from stage_gen.orchestration.gnode_plugin import (
    agent_routes,
    audio_routes,
    music_job,
    sound_job,
    speech_job,
)

MP3 = b"ID3" + b"\x00" * 64


class FakeService:
    def __init__(self, **settings: Any) -> None:
        self.settings = settings
        self.requests: list[Any] = []

    async def generate(self, request: Any) -> Any:
        self.requests.append(request)
        return SimpleNamespace(data=MP3, attempts=1)


def _config() -> StageGenConfig:
    return StageGenConfig(open_router_api_key="or-test", elevenlabs_api_key="el-test")


def _route(capability: str) -> Route:
    return next(route for route in audio_routes(_config()) if route.capability == capability)


def _factory(made: list[FakeService]) -> Any:
    def build(**settings: Any) -> FakeService:
        service = FakeService(**settings)
        made.append(service)
        return service

    return build


async def test_each_audio_call_sends_its_settings_and_returns_its_clip(tmp_path: Path) -> None:
    store, made = Store(tmp_path), list[FakeService]()
    config = _config()

    music = await music_job(config, store, factory=_factory(made))(
        _route("music.generate"), {"prompt": "a calm loop"}, 1
    )
    sound = await sound_job(config, store, factory=_factory(made))(
        _route("sound.generate"),
        {"prompt": "a clank", "duration": 0.8, "prompt_influence": 0.6, "loop": False},
        1,
    )
    speech = await speech_job(config, store, factory=_factory(made))(
        _route("speech.generate"),
        {"text": "Go!", "voice": "voice-123", "stability": 0.5, "language_code": "en"},
        1,
    )

    for record in (music, sound, speech):
        assert store.file_path(record.files["audio"].digest).read_bytes() == MP3
        assert record.files["audio"].kind == "audio/mpeg"
    assert made[0].settings["model"] == "google/lyria-3-pro-preview"
    assert made[0].requests[0].prompt == "a calm loop"
    clip = made[1].requests[0]
    assert (clip.duration_seconds, clip.prompt_influence, clip.loop) == (0.8, 0.6, False)
    line = made[2].requests[0]
    assert (line.text, line.voice, line.stability, line.language_code) == (
        "Go!",
        "voice-123",
        0.5,
        "en",
    )


async def test_a_call_without_its_key_or_text_is_refused_before_it_leaves(tmp_path: Path) -> None:
    store, made = Store(tmp_path), list[FakeService]()
    keyless = StageGenConfig()
    with pytest.raises(CallRefused, match="ELEVENLABS_API_KEY"):
        await sound_job(keyless, store, factory=_factory(made))(
            _route("sound.generate"), {"prompt": "a clank"}, 1
        )
    with pytest.raises(CallRefused, match="provider voice"):
        await speech_job(_config(), store, factory=_factory(made))(
            _route("speech.generate"), {"text": "Go!"}, 1
        )
    with pytest.raises(CallRefused, match="a number"):
        await sound_job(_config(), store, factory=_factory(made))(
            _route("sound.generate"), {"prompt": "a clank", "duration": "long"}, 1
        )
    assert made == []


def test_the_text_model_answers_agent_turns_beside_the_vision_judge() -> None:
    routes = {route.route_id: route for route in agent_routes(_config())}
    assert set(routes) == {"openai/gpt-6-astra@openrouter", "openai/gpt-5.6-sol@openrouter"}
    assert "request_policy" not in routes["openai/gpt-5.6-sol@openrouter"].contract
