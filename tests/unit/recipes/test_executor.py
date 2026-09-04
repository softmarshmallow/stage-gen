"""The executor base: a run's services close together, a missing credential refuses first."""

from __future__ import annotations

import asyncio

import pytest

from stage_gen.config import CapabilityName, ConfigError, StageGenConfig
from stage_gen.recipes.executor import RunServices


class _Service:
    def __init__(self, log: list[str], name: str) -> None:
        self._log = log
        self._name = name

    async def aclose(self) -> None:
        self._log.append(self._name)


def test_run_services_close_in_reverse_order_of_opening() -> None:
    log: list[str] = []

    async def scenario() -> None:
        async with RunServices(StageGenConfig()) as services:
            services.adopt(_Service(log, "first"))
            services.adopt(_Service(log, "second"))
        assert log == ["second", "first"]
        # A second close is a no-op: the list was drained.
        await services.aclose()
        assert log == ["second", "first"]

    asyncio.run(scenario())


def test_run_services_close_even_when_the_run_raises() -> None:
    log: list[str] = []

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="boom"):
            async with RunServices(StageGenConfig()) as services:
                services.adopt(_Service(log, "only"))
                raise RuntimeError("boom")

    asyncio.run(scenario())
    assert log == ["only"]


def test_configured_services_compose_from_the_config_alone() -> None:
    config = StageGenConfig(openai_api_key="openai", open_router_api_key="openrouter")
    services = RunServices(config)
    image = services.image()
    structured = services.structured()
    music = services.music()
    assert {type(image).__name__, type(structured).__name__, type(music).__name__} == {
        "ImageGenerationService",
        "StructuredGenerationService",
        "MusicGenerationService",
    }
    asyncio.run(services.aclose())


def test_a_missing_credential_is_a_value_error_naming_the_variable() -> None:
    from stage_gen.recipes.pointclick_room.room_executor import PointClickRoomExecutor

    executor = PointClickRoomExecutor(StageGenConfig(open_router_api_key="openrouter"))
    with pytest.raises(ConfigError, match="OPENAI_API_KEY") as raised:
        executor.require(
            CapabilityName.NATIVE_IMAGE_GENERATION, CapabilityName.STRUCTURED_GENERATION
        )
    assert isinstance(raised.value, ValueError)
    assert raised.value.missing == ("OPENAI_API_KEY",)
