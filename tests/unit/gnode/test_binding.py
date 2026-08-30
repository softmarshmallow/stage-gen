from __future__ import annotations

import pytest

from gnode import Binding, BindingTable, CapabilityError, ModelRef


def test_model_reference_keeps_the_vendor_namespace_with_the_model() -> None:
    """The route is the suffix; a vendor prefix stays part of the model id."""

    direct = ModelRef.parse("gpt-image-2@openai")
    assert (direct.model, direct.provider) == ("gpt-image-2", "openai")

    routed = ModelRef.parse("openai/gpt-image-2@openrouter")
    assert (routed.model, routed.provider) == ("openai/gpt-image-2", "openrouter")

    nested = ModelRef.parse("fal-ai/birefnet/v2@fal")
    assert (nested.model, nested.provider) == ("fal-ai/birefnet/v2", "fal")

    assert str(routed) == "openai/gpt-image-2@openrouter"


def test_model_reference_rejects_a_bare_identifier() -> None:
    with pytest.raises(ValueError, match="model@provider"):
        ModelRef.parse("gpt-image-2")


def _image_binding(*, provider: str, features: frozenset[str]) -> Binding:
    return Binding(
        operation="image_generation",
        model=ModelRef(model="gpt-image-2", provider=provider),
        features=features,
        resource_id="image",
        estimated_duration_seconds=120.0,
        estimated_cost_low_usd=0.04,
        estimated_cost_high_usd=0.20,
    )


def test_a_route_missing_a_declared_feature_is_refused_while_planning() -> None:
    """The same model on a route without transparency fails before any spend."""

    table = BindingTable(
        [_image_binding(provider="openrouter", features=frozenset({"reference_images"}))]
    )

    with pytest.raises(CapabilityError, match="transparent_background"):
        table.require("image_generation", "transparent_background")

    assert table.require("image_generation", "reference_images").model.provider == "openrouter"


def test_an_undeclared_capability_is_refused_by_name() -> None:
    table = BindingTable([])
    with pytest.raises(CapabilityError, match="music_generation"):
        table.require("music_generation")


def test_a_table_declares_at_most_one_route_per_capability() -> None:
    with pytest.raises(ValueError, match="at most one route"):
        BindingTable(
            [
                _image_binding(provider="openai", features=frozenset()),
                _image_binding(provider="openrouter", features=frozenset()),
            ]
        )


def test_bindings_declare_the_resources_the_scheduler_gates_on() -> None:
    table = BindingTable(
        [
            Binding(
                operation="image_generation",
                model=ModelRef(model="gpt-image-2", provider="openai"),
                resource_id="openai-image",
                estimated_duration_seconds=120.0,
                estimated_cost_low_usd=0.04,
                estimated_cost_high_usd=0.20,
                requests_per_minute=150,
                rate_limit_owner="provider_adapter",
            )
        ]
    )

    resource = table.resources()[0]
    assert resource.resource_id == "openai-image"
    assert resource.requests_per_minute == 150
    assert resource.rate_limit_owner == "provider_adapter"


def test_a_local_operation_cannot_be_bound_to_a_provider() -> None:
    with pytest.raises(ValueError, match="without a provider route"):
        Binding(
            operation="local",
            model=ModelRef(model="gpt-image-2", provider="openai"),
            resource_id="local",
            estimated_duration_seconds=0.0,
            estimated_cost_low_usd=0.0,
            estimated_cost_high_usd=0.0,
        )
