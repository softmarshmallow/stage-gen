from __future__ import annotations

from dataclasses import replace

import pytest

from gnode import (
    Binding,
    BindingTable,
    GraphBuilder,
    ModelRef,
    NodePolicy,
    NodeType,
    NodeTypeError,
    RouteCatalog,
    RouteContractV1,
    RouteResolutionError,
    ViewArchetype,
    WorkloadPolicyV1,
    WorkloadRequestV1,
)

_INPUT_DIGEST = "a" * 64

IMAGE_TYPE = NodeType(
    type_id="asset/image.generate",
    title="Generate image",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    contract_version="image-v1",
    features=("legacy_required",),
    policy=NodePolicy(max_attempts=3),
)

LOCAL_TYPE = NodeType(
    type_id="asset/image.validate",
    title="Validate image",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="image-validation-v1",
)


def _legacy_profile() -> BindingTable:
    return BindingTable(
        [
            Binding(
                operation="image_generation",
                model=ModelRef(model="gpt-image-2.5-sunburst", provider="openai"),
                resource_id="legacy-openai-image",
                estimated_duration_seconds=120.0,
                estimated_cost_low_usd=0.04,
                estimated_cost_high_usd=0.20,
                features=frozenset({"legacy_required"}),
            )
        ]
    )


def _route(
    *,
    route_id: str = "gpt-image-2.5-sunburst/fal/queue",
    provider: str = "fal",
    model: str = "fal-ai/gpt-image-2.5-sunburst",
    endpoint: str = "https://queue.fal.test/fal-ai/gpt-image-2.5-sunburst",
    surface: str = "queue_api",
    features: frozenset[str] = frozenset({"transparent_background"}),
    resource_id: str = "fal-image",
    duration: float = 90.0,
    cost_low: float = 0.03,
    cost_high: float = 0.19,
    requests_per_minute: int | None = 120,
    verified_on: str = "2026-09-10",
) -> RouteContractV1:
    return RouteContractV1(
        route_id=route_id,
        product_id="gpt-image-2.5-sunburst",
        operation="image_generation",
        operation_variant="generate",
        model=ModelRef(model=model, provider=provider),
        modality_spec_version="image-generation-v1",
        surface=surface,
        endpoint=endpoint,
        adapter_id=f"gnode.providers.{provider}.image",
        adapter_behavior_version="1",
        features=features,
        resource_id=resource_id,
        estimated_duration_seconds=duration,
        estimated_cost_low_usd=cost_low,
        estimated_cost_high_usd=cost_high,
        requests_per_minute=requests_per_minute,
        rate_limit_owner=("provider_adapter" if requests_per_minute else "none"),
        verified_on=verified_on,
        evidence_ref=f"provider-contract:{provider}",
    )


def _policy(route_id: str, *, policy_id: str = "hero-image") -> WorkloadPolicyV1:
    return WorkloadPolicyV1(
        policy_id=policy_id,
        policy_version="1",
        product_id="gpt-image-2.5-sunburst",
        route_id=route_id,
    )


def _workload(
    *,
    policy_id: str = "hero-image",
    features: frozenset[str] = frozenset({"transparent_background"}),
    background: str = "transparent",
) -> WorkloadRequestV1:
    return WorkloadRequestV1(
        policy_id=policy_id,
        operation="image_generation",
        modality_spec_version="image-generation-v1",
        required_features=features,
        output_options={"background": background, "quality": "sunburst"},
    )


def _add_image(
    builder: GraphBuilder,
    *,
    node_id: str = "hero.generate",
    workload: WorkloadRequestV1 | None = None,
) -> None:
    builder.add(
        IMAGE_TYPE,
        node_id,
        domain="image",
        description="Generate a hero image",
        input_digests=(_INPUT_DIGEST,),
        workload=workload,
    )


def test_legacy_one_binding_plan_and_cache_are_unchanged() -> None:
    unused_route = _route()
    builder = GraphBuilder(
        profile=_legacy_profile(),
        route_catalog=RouteCatalog([unused_route]),
        workload_policies={"hero-image": _policy(unused_route.route_id)},
    )

    _add_image(builder)
    node = builder.node("hero.generate")

    assert node.provider == "openai"
    assert node.model == "gpt-image-2.5-sunburst"
    assert node.input_sha256 == (_INPUT_DIGEST,)
    assert node.binding_ref is None
    assert node.cache_key == "ae38684f28c40af2adae70a5bfc8bf1d600f8118c26f227b350545cfe7f69cbb"
    assert [resource.resource_id for resource in builder.resources()] == [
        "local",
        "legacy-openai-image",
    ]
    assert builder.resolved_bindings == ()
    assert builder.resolved_routes() == ()


def test_catalog_workload_resolves_exact_route_and_binds_output_identity() -> None:
    route = _route()
    builder = GraphBuilder(
        route_catalog=RouteCatalog([route]),
        workload_policies={"hero-image": _policy(route.route_id)},
    )

    _add_image(builder, workload=_workload())
    node = builder.node("hero.generate")
    resolved = builder.resolved_binding(node.node_id)

    assert node.provider == "fal"
    assert node.model == "fal-ai/gpt-image-2.5-sunburst"
    assert node.input_sha256 == (_INPUT_DIGEST, resolved.output_fingerprint)
    assert node.binding_ref == resolved.to_snapshot().binding_ref
    assert builder.resolved_bindings == (resolved,)
    assert builder.resolved_routes() == (resolved.to_snapshot(),)
    assert [resource.resource_id for resource in builder.resources()] == ["local", "fal-image"]


def test_catalog_features_are_instance_requirements_not_legacy_type_features() -> None:
    """Adding a model capability must not require editing the NodeType."""

    route = _route(features=frozenset({"new_provider_capability"}))
    builder = GraphBuilder(
        route_catalog=RouteCatalog([route]),
        workload_policies={"hero-image": _policy(route.route_id)},
    )
    workload = _workload(features=frozenset({"new_provider_capability"}))

    _add_image(builder, workload=workload)

    assert builder.node("hero.generate").provider == "fal"
    assert IMAGE_TYPE.features == ("legacy_required",)


def test_selected_unsupported_route_refuses_without_mutating_the_plan() -> None:
    fal = _route()
    openrouter = _route(
        route_id="gpt-image-2.5-sunburst/openrouter/chat",
        provider="openrouter",
        model="openai/gpt-image-2.5-sunburst",
        endpoint="https://openrouter.test/api/v1/chat/completions",
        surface="chat_completions",
        features=frozenset(),
        resource_id="openrouter-image",
    )
    builder = GraphBuilder(
        route_catalog=RouteCatalog([fal, openrouter]),
        workload_policies={"hero-image": _policy(openrouter.route_id)},
    )

    with pytest.raises(RouteResolutionError, match="missing features transparent_background"):
        _add_image(builder, workload=_workload())

    assert builder.nodes == ()
    assert [resource.resource_id for resource in builder.resources()] == ["local"]


def test_two_instances_of_one_type_can_use_distinct_capabilities_and_routes() -> None:
    transparent_route = _route()
    opaque_route = _route(
        route_id="gpt-image-2.5-sunburst/openrouter/chat",
        provider="openrouter",
        model="openai/gpt-image-2.5-sunburst",
        endpoint="https://openrouter.test/api/v1/chat/completions",
        surface="chat_completions",
        features=frozenset(),
        resource_id="openrouter-image",
    )
    builder = GraphBuilder(
        route_catalog=RouteCatalog([transparent_route, opaque_route]),
        workload_policies={
            "hero-image": _policy(transparent_route.route_id),
            "background-image": _policy(opaque_route.route_id, policy_id="background-image"),
        },
    )

    _add_image(builder, node_id="hero.generate", workload=_workload())
    _add_image(
        builder,
        node_id="background.generate",
        workload=_workload(
            policy_id="background-image",
            features=frozenset(),
            background="opaque",
        ),
    )

    assert builder.node("hero.generate").provider == "fal"
    assert builder.node("background.generate").provider == "openrouter"
    assert [resource.resource_id for resource in builder.resources()] == [
        "local",
        "fal-image",
        "openrouter-image",
    ]


def _catalog_node(route: RouteContractV1, workload: WorkloadRequestV1) -> GraphBuilder:
    builder = GraphBuilder(
        route_catalog=RouteCatalog([route]),
        workload_policies={
            workload.policy_id: _policy(route.route_id, policy_id=workload.policy_id)
        },
    )
    _add_image(builder, workload=workload)
    return builder


def test_endpoint_and_output_options_change_cache_but_operational_metadata_does_not() -> None:
    route = _route()
    base = _catalog_node(route, _workload())
    endpoint_change = _catalog_node(
        replace(route, endpoint="https://queue.fal.test/fal-ai/gpt-image-2.5-sunburst/v2"),
        _workload(),
    )
    output_change = _catalog_node(
        route,
        _workload(features=frozenset(), background="opaque"),
    )
    operational_change = _catalog_node(
        replace(
            route,
            resource_id="fal-image-new-pacing",
            estimated_duration_seconds=999.0,
            estimated_cost_low_usd=8.0,
            estimated_cost_high_usd=9.0,
            requests_per_minute=2,
            verified_on="2030-01-01",
            evidence_ref="new-evidence",
        ),
        _workload(),
    )

    base_node = base.node("hero.generate")
    assert endpoint_change.node("hero.generate").cache_key != base_node.cache_key
    assert output_change.node("hero.generate").cache_key != base_node.cache_key
    assert operational_change.node("hero.generate").cache_key == base_node.cache_key
    assert operational_change.node("hero.generate").estimated_cost_high_usd == 9.0


def test_catalog_planning_refuses_missing_policy_or_operation_mismatch() -> None:
    route = _route()
    without_policy = GraphBuilder(route_catalog=RouteCatalog([route]))
    with pytest.raises(RouteResolutionError, match="no workload policy"):
        _add_image(without_policy, workload=_workload())

    wrong_operation = replace(_workload(), operation="image_edit")
    with_policy = GraphBuilder(
        route_catalog=RouteCatalog([route]),
        workload_policies={"hero-image": _policy(route.route_id)},
    )
    with pytest.raises(NodeTypeError, match="does not match node type"):
        _add_image(with_policy, workload=wrong_operation)


def test_local_nodes_refuse_provider_workloads() -> None:
    route = _route()
    builder = GraphBuilder(
        route_catalog=RouteCatalog([route]),
        workload_policies={"hero-image": _policy(route.route_id)},
    )

    with pytest.raises(ValueError, match=r"local node .* provider workload"):
        builder.add(
            LOCAL_TYPE,
            "hero.validate",
            domain="image",
            description="Validate a hero image",
            workload=_workload(),
        )


def test_builder_requires_a_legacy_profile_or_route_catalog() -> None:
    with pytest.raises(ValueError, match="binding profile or route catalog"):
        GraphBuilder()
