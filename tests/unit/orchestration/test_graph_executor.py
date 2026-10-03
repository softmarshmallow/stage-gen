"""The executor base: a run's services close together, a missing credential refuses first."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from stage_gen.config import CapabilityName, ConfigError, StageGenConfig
from stage_gen.orchestration.services import RunServices


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
    assert {
        type(image).__name__,
        type(structured).__name__,
        type(music).__name__,
    } == {
        "RoutedImageGenerationService",
        "StructuredGenerationService",
        "MusicGenerationService",
    }
    assert services.image() is image
    assert image.provider == "routed"
    assert image.model == "gpt-image-2.5-sunburst"
    asyncio.run(services.aclose())


def test_image_capability_credentials_require_an_exact_resolved_route() -> None:
    from the_grain_pipeline.pointclick_room.room_executor import PointClickRoomExecutor

    executor = PointClickRoomExecutor(StageGenConfig(open_router_api_key="openrouter"))
    with pytest.raises(ValueError, match="exact resolved route"):
        executor.require(
            CapabilityName.NATIVE_IMAGE_GENERATION, CapabilityName.STRUCTURED_GENERATION
        )


def test_route_credentials_are_scoped_to_the_selected_target_closure() -> None:
    from stage_gen.image_product import ImageProvider
    from the_grain_pipeline.pointclick_room.room_executor import PointClickRoomExecutor

    executor = PointClickRoomExecutor(
        StageGenConfig(
            open_router_api_key="openrouter",
            image_provider_override=ImageProvider.FAL,
        )
    )
    plan = executor.plan(Path("godot/games/the_grain/inputs/rooms/window"))
    by_id = {node.node_id: node for node in plan.graph.nodes}

    def local_closure(node_id: str) -> bool:
        node = by_id[node_id]
        return node.is_local and all(local_closure(parent) for parent in node.depends_on)

    local = tuple(node_id for node_id in by_id if local_closure(node_id))
    assert local

    executor.require_route_credentials(plan.graph, target_node_ids=local)
    with pytest.raises(ConfigError, match="FAL_KEY"):
        executor.require_route_credentials(plan.graph)
