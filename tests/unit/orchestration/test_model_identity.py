"""Planned route identity is the provider/model identity the run can call (D11)."""

from __future__ import annotations

from stage_gen.config import StageGenConfig
from stage_gen.image_product import ImageProvider
from stage_gen.model_routes import (
    FAL_SUNBURST_MODEL,
    OPENAI_SUNBURST_MODEL,
    OPENROUTER_SUNBURST_MODEL,
    SUNBURST_PRODUCT_ID,
    configured_image_route_catalog,
)

CONFIG = StageGenConfig(
    openai_api_key="openai",
    open_router_api_key="openrouter",
    fal_key="fal",
    elevenlabs_api_key="elevenlabs",
)


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
