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
from stage_gen.recipes.oblique_survival.survival_graph import oblique_survival_graph_profile
from stage_gen.recipes.pointclick_room.room_graph import room_graph_profile
from stage_gen.recipes.sideview_platformer.package_graph import package_graph_profile
from stage_gen.recipes.sideview_runner.runner_graph import runner_graph_profile
from stage_gen.recipes.storefront.storefront_graph import storefront_graph_profile
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


def test_the_storefront_opaque_route_binds_the_model_it_calls() -> None:
    profile = storefront_graph_profile(CONFIG)
    image = next(b for b in profile.bindings if b.operation == "image_generation")
    services = RunServices(CONFIG)
    try:
        service = services.opaque_image()
        assert _backend_model(service) == image.model.model
        assert image.model.provider == "openrouter"
        assert image.model.model == "openai/gpt-image-2.5-sunburst"
    finally:
        asyncio.run(services.aclose())


def test_default_image_bindings_have_no_gpt_image_2_route() -> None:
    profiles = [profile(CONFIG) for _, profile in PROFILES]
    profiles.extend(
        (
            storefront_graph_profile(CONFIG),
            universe_graph_profile(CONFIG, images=True),
        )
    )
    image_bindings = [
        binding
        for profile in profiles
        for binding in profile.bindings
        if binding.operation == "image_generation"
    ]
    assert image_bindings
    assert {str(binding.model) for binding in image_bindings} <= {
        "gpt-image-2.5-sunburst@openai",
        "openai/gpt-image-2.5-sunburst@openrouter",
    }


@pytest.mark.parametrize(("recipe", "profile"), PROFILES)
def test_direct_image_profiles_refuse_unverified_model_overrides(
    recipe: str, profile: Callable[[StageGenConfig], BindingTable]
) -> None:
    with pytest.raises(ValueError, match=r"GPT Image 2\.5 Sunburst"):
        profile(CONFIG.model_copy(update={"openai_image_model": "gpt-image-2"}))


@pytest.mark.parametrize(
    "profile",
    (
        lambda config: storefront_graph_profile(config),
        lambda config: universe_graph_profile(config, images=True),
    ),
)
def test_opaque_recipe_profiles_refuse_unverified_model_overrides(
    profile: Callable[[StageGenConfig], BindingTable],
) -> None:
    with pytest.raises(ValueError, match=r"GPT Image 2\.5 Sunburst"):
        profile(CONFIG.model_copy(update={"image_model": "openai/gpt-image-2"}))
