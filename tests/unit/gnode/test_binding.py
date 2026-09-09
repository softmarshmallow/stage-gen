from __future__ import annotations

import pytest

from gnode import Binding, BindingTable, CapabilityError, ModelRef


def test_model_reference_keeps_the_vendor_namespace_with_the_model() -> None:
    """The route is the suffix; a vendor prefix stays part of the model id."""

    direct = ModelRef.parse("gpt-image-2.5-sunburst@openai")
    assert (direct.model, direct.provider) == ("gpt-image-2.5-sunburst", "openai")

    routed = ModelRef.parse("openai/gpt-image-2.5-sunburst@openrouter")
    assert (routed.model, routed.provider) == (
        "openai/gpt-image-2.5-sunburst",
        "openrouter",
    )

    nested = ModelRef.parse("fal-ai/birefnet/v2@fal")
    assert (nested.model, nested.provider) == ("fal-ai/birefnet/v2", "fal")

    assert str(routed) == "openai/gpt-image-2.5-sunburst@openrouter"


def test_model_reference_rejects_a_bare_identifier() -> None:
    with pytest.raises(ValueError, match="model@provider"):
        ModelRef.parse("gpt-image-2.5-sunburst")


def _image_binding(*, provider: str, features: frozenset[str]) -> Binding:
    return Binding(
        operation="image_generation",
        model=ModelRef(model="gpt-image-2.5-sunburst", provider=provider),
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
                model=ModelRef(model="gpt-image-2.5-sunburst", provider="openai"),
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
            model=ModelRef(model="gpt-image-2.5-sunburst", provider="openai"),
            resource_id="local",
            estimated_duration_seconds=0.0,
            estimated_cost_low_usd=0.0,
            estimated_cost_high_usd=0.0,
        )


def _video_binding(*, limits: tuple[tuple[str, float], ...]) -> Binding:
    return Binding(
        operation="video_generation",
        model=ModelRef(model="google/gemini-omni-flash/v1.1", provider="fal"),
        features=frozenset({"reference_images"}),
        limits=limits,
        resource_id="video",
        estimated_duration_seconds=120.0,
        estimated_cost_low_usd=0.30,
        estimated_cost_high_usd=1.50,
    )


def test_a_route_ceiling_is_declared_on_the_route_and_refused_while_planning() -> None:
    """How long a clip a model will make is a fact about that route.

    Declaring it here rather than in the modality is what lets one authored
    document plan against a route with a different ceiling without an edit.
    """

    table = BindingTable([_video_binding(limits=(("clip_seconds_max", 10.0),))])

    assert (
        table.require_within(
            "video_generation", "clip_seconds_max", 10.0, subject="the opening shot"
        ).model.provider
        == "fal"
    )

    with pytest.raises(CapabilityError, match="the opening shot asks for 18"):
        table.require_within(
            "video_generation", "clip_seconds_max", 18.0, subject="the opening shot"
        )


def test_an_undeclared_ceiling_is_refused_rather_than_waved_through() -> None:
    """Fail-closed: forgetting the limit is a planning failure, not a 422 after spend."""

    table = BindingTable([_video_binding(limits=())])
    with pytest.raises(CapabilityError, match="declares no clip_seconds_max"):
        table.require_within("video_generation", "clip_seconds_max", 4.0, subject="a shot")


def test_a_route_declares_each_ceiling_once_and_positively() -> None:
    with pytest.raises(ValueError, match="each limit at most once"):
        _video_binding(limits=(("clip_seconds_max", 10.0), ("clip_seconds_max", 12.0)))
    with pytest.raises(ValueError, match="positive finite"):
        _video_binding(limits=(("clip_seconds_max", 0.0),))
    with pytest.raises(ValueError, match="positive finite"):
        _video_binding(limits=(("clip_seconds_max", float("inf")),))


def test_a_missing_feature_still_refuses_before_a_ceiling_is_read() -> None:
    table = BindingTable([_video_binding(limits=(("clip_seconds_max", 10.0),))])
    with pytest.raises(CapabilityError, match="alpha_matte"):
        table.require_within(
            "video_generation", "clip_seconds_max", 4.0, subject="a shot", features=("alpha_matte",)
        )


def test_a_route_that_counts_in_steps_refuses_a_value_between_them() -> None:
    """A ceiling is not the only shape a route's arithmetic takes.

    Learned by spending: a route that counts whole seconds was handed 4.5, the adapter
    truncated it to 4, the answer came back four seconds long, and the caller's length
    gate refused it against the 4.5 nobody had actually asked for - six times, at full
    price. The step is declared where the ceiling is, and refused in the same place.
    """

    table = BindingTable(
        [_video_binding(limits=(("clip_seconds_max", 10.0), ("clip_seconds_step", 1.0)))]
    )
    binding = table.require("video_generation")
    binding.aligned("clip_seconds_step", 5.0, subject="a shot")

    with pytest.raises(CapabilityError, match=r"asks for 4\.5 .* in steps of 1"):
        binding.aligned("clip_seconds_step", 4.5, subject="a shot")
    with pytest.raises(CapabilityError, match="declares no clip_seconds_step"):
        _video_binding(limits=()).aligned("clip_seconds_step", 5.0, subject="a shot")
