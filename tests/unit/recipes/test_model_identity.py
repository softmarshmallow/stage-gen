"""Planned route identity is the provider/model identity the run can call (D11)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from bellweather_pipeline.package_graph import package_graph_profile
from ember_hollow_pipeline.survival_graph import oblique_survival_graph_profile
from gnode import BindingTable
from iron_petal_unit_pipeline.runner_graph import runner_graph_profile
from stage_gen.config import StageGenConfig
from stage_gen.image_product import ImageProvider
from stage_gen.model_routes import (
    FAL_SUNBURST_MODEL,
    OPENAI_SUNBURST_MODEL,
    OPENROUTER_SUNBURST_MODEL,
    SUNBURST_PRODUCT_ID,
    configured_image_route_catalog,
)
from stage_gen.recipes.executor import RunServices
from stage_gen.recipes.storefront.storefront_graph import storefront_graph_profile
from stage_gen.recipes.universe.universe_graph import universe_graph_profile
from the_grain_pipeline.dialogue_scene.scene_graph import dialogue_graph_profile
from the_grain_pipeline.pointclick_room.room_graph import room_graph_profile

CONFIG = StageGenConfig(
    openai_api_key="openai",
    open_router_api_key="openrouter",
    fal_key="fal",
    elevenlabs_api_key="elevenlabs",
)

#: Which ``RunServices`` accessor serves each bound operation.
SERVICE_FOR_OPERATION: dict[str, Callable[[RunServices], object]] = {
    "structured_generation": lambda services: services.structured(),
    "tool_loop": lambda services: services.tool_loop(),
    "music_generation": lambda services: services.music(),
    "background_removal": lambda services: services.background_removal(),
    "video_generation": lambda services: services.video(),
    "sound_effect_generation": lambda services: services.sound_effect(),
    "speech_generation": lambda services: services.speech(),
}

PROFILES: tuple[tuple[str, Callable[[StageGenConfig], BindingTable]], ...] = (
    ("sideview-platformer", package_graph_profile),
    ("sideview-runner", runner_graph_profile),
    ("pointclick-room", room_graph_profile),
    ("dialogue-scene", dialogue_graph_profile),
    ("oblique-survival", oblique_survival_graph_profile),
    ("storefront", storefront_graph_profile),
    ("universe", lambda config: universe_graph_profile(config, images=True)),
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


def test_image_runtime_is_request_routed_instead_of_bound_to_an_ambient_provider() -> None:
    services = RunServices(CONFIG)
    try:
        image = services.image()
        assert services.opaque_image() is image
        assert image.provider == "routed"
        assert image.model == SUNBURST_PRODUCT_ID
    finally:
        asyncio.run(services.aclose())


def test_registered_image_routes_are_sunburst_only_and_provider_exact() -> None:
    catalog = configured_image_route_catalog(CONFIG)
    expected_models = {
        ImageProvider.OPENAI.value: OPENAI_SUNBURST_MODEL,
        ImageProvider.FAL.value: FAL_SUNBURST_MODEL,
        ImageProvider.OPENROUTER.value: OPENROUTER_SUNBURST_MODEL,
    }
    assert catalog.routes
    assert {route.product_id for route in catalog.routes} == {SUNBURST_PRODUCT_ID}
    assert {route.model.provider for route in catalog.routes} == set(expected_models)
    for route in catalog.routes:
        assert route.model.model == expected_models[route.model.provider]
