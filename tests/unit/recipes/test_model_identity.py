"""The model a cache key records is the model the call is made with (D11).

A node's ``model`` comes from the recipe profile's binding table; the request goes to
the service ``RunServices`` composes. Both read the config, and this is the test that
keeps them reading the same field: a profile that binds ``config.text_model`` while
the run composes a service on some other default would key every artifact on a model
that never generated it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from gnode import BindingTable
from stage_gen.config import StageGenConfig
from stage_gen.recipes.dialogue_scene.scene_graph import dialogue_graph_profile
from stage_gen.recipes.executor import RunServices
from stage_gen.recipes.pointclick_room.room_graph import room_graph_profile
from stage_gen.recipes.sideview_platformer.package_graph import package_graph_profile
from stage_gen.recipes.sideview_runner.runner_graph import runner_graph_profile
from stage_gen.recipes.universe.universe_graph import GALLERY_IMAGE_ROUTE, universe_graph_profile

CONFIG = StageGenConfig(
    openai_api_key="openai",
    open_router_api_key="openrouter",
    fal_key="fal",
    elevenlabs_api_key="elevenlabs",
)

#: Which ``RunServices`` accessor serves each bound operation.
SERVICE_FOR_OPERATION: dict[str, Callable[[RunServices], object]] = {
    "image_generation": lambda services: services.image(),
    "structured_generation": lambda services: services.structured(),
    "tool_loop": lambda services: services.tool_loop(),
    "music_generation": lambda services: services.music(),
    "background_removal": lambda services: services.background_removal(),
    "sound_effect_generation": lambda services: services.sound_effect(),
    "speech_generation": lambda services: services.speech(),
}

PROFILES: tuple[tuple[str, Callable[[StageGenConfig], BindingTable]], ...] = (
    ("sideview-platformer", package_graph_profile),
    ("sideview-runner", runner_graph_profile),
    ("pointclick-room", room_graph_profile),
    ("dialogue-scene", dialogue_graph_profile),
)


def _backend_model(service: object) -> str:
    backend = service._backend  # type: ignore[attr-defined]
    return str(backend.model)


@pytest.mark.parametrize(("recipe", "profile"), PROFILES)
def test_every_bound_model_is_the_model_the_run_calls(
    recipe: str, profile: Callable[[StageGenConfig], BindingTable]
) -> None:
    services = RunServices(CONFIG)
    try:
        for binding in profile(CONFIG).bindings:
            service = SERVICE_FOR_OPERATION[binding.operation](services)
            assert _backend_model(service) == binding.model.model.lstrip("/"), (
                f"{recipe}: {binding.operation} keys on {binding.model.model!r} but calls "
                f"{_backend_model(service)!r}"
            )
    finally:
        asyncio.run(services.aclose())


def test_the_universe_gallery_route_binds_the_model_it_calls() -> None:
    profile = universe_graph_profile(CONFIG, images=True)
    image = next(b for b in profile.bindings if b.operation == "image_generation")
    service = GALLERY_IMAGE_ROUTE.service(CONFIG)
    try:
        assert _backend_model(service) == image.model.model
        assert image.model.provider == GALLERY_IMAGE_ROUTE.provider
    finally:
        asyncio.run(service.aclose())
