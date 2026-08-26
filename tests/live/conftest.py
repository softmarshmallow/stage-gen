from __future__ import annotations

import os
from dataclasses import dataclass, field

import pytest

from stage_gen.config import StageGenConfig, load_config

_LIVE_FLAG = "STAGE_GEN_RUN_LIVE"


@dataclass(frozen=True, slots=True)
class OpenRouterLiveSettings:
    api_key: str = field(repr=False)
    base_url: str
    image_model: str
    text_model: str
    music_model: str
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class OpenAILiveSettings:
    api_key: str = field(repr=False)
    base_url: str
    image_model: str
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class FalLiveSettings:
    api_key: str = field(repr=False)
    base_url: str
    model: str
    timeout_seconds: float


@pytest.fixture(scope="session", autouse=True)
def live_opt_in() -> None:
    if os.environ.get(_LIVE_FLAG) != "1":
        pytest.skip(f"set {_LIVE_FLAG}=1 to run provider-backed smoke tests")


@pytest.fixture(scope="session")
def live_config(live_opt_in: None) -> StageGenConfig:
    del live_opt_in
    return load_config()


@pytest.fixture(scope="session")
def openrouter_settings(live_config: StageGenConfig) -> OpenRouterLiveSettings:
    api_key = live_config.open_router_api_key
    if api_key is None:
        pytest.skip("OPENROUTER_API_KEY is required for this live smoke test")
    return OpenRouterLiveSettings(
        api_key=api_key,
        base_url=live_config.open_router_base_url or "https://openrouter.ai/api/v1",
        image_model=live_config.image_model,
        text_model=live_config.text_model,
        music_model=live_config.music_model,
        timeout_seconds=live_config.capability_timeout_s,
    )


@pytest.fixture(scope="session")
def openai_settings(live_config: StageGenConfig) -> OpenAILiveSettings:
    api_key = live_config.openai_api_key
    if api_key is None:
        pytest.skip("OPENAI_API_KEY is required for this live smoke test")
    return OpenAILiveSettings(
        api_key=api_key,
        base_url=live_config.openai_base_url or "https://api.openai.com/v1",
        image_model=live_config.openai_image_model,
        timeout_seconds=live_config.capability_timeout_s,
    )


@pytest.fixture(scope="session")
def fal_settings(live_config: StageGenConfig) -> FalLiveSettings:
    api_key = live_config.fal_key
    if api_key is None:
        pytest.skip("FAL_KEY is required for this live smoke test")
    return FalLiveSettings(
        api_key=api_key,
        base_url=live_config.fal_base_url or "https://fal.run",
        model=live_config.background_removal_model,
        timeout_seconds=live_config.capability_timeout_s,
    )
