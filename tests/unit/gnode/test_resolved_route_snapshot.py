from __future__ import annotations

import json
from dataclasses import replace

import pytest
from pydantic import ValidationError

from gnode import (
    ExactSize2DV1,
    ExactSizeConstraints2DV1,
    Graph,
    GraphBuilder,
    ModelRef,
    Node,
    NodePolicy,
    NodeType,
    ResolvedRouteSnapshotV1,
    Resource,
    RouteCatalog,
    RouteContractV1,
    ViewArchetype,
    WorkloadPolicyV1,
    WorkloadRequestV1,
    graph_sha256_of,
    seal_graph,
    topology_sha256,
)

_INPUT_DIGEST = "a" * 64

IMAGE_TYPE = NodeType(
    type_id="asset/image.generate",
    title="Generate image",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    contract_version="image-v1",
    policy=NodePolicy(max_attempts=3),
)


def _route(
    *,
    endpoint: str = "https://queue.fal.test/fal-ai/gpt-image-2.5-sunburst",
    duration: float = 90.0,
    cost_low: float = 0.03,
    cost_high: float = 0.19,
    requests_per_minute: int | None = 120,
    verified_on: str = "2026-09-10",
) -> RouteContractV1:
    return RouteContractV1(
        route_id="gpt-image-2.5-sunburst/fal/queue",
        product_id="gpt-image-2.5-sunburst",
        operation="image_generation",
        operation_variant="generation",
        model=ModelRef(model="fal-ai/gpt-image-2.5-sunburst", provider="fal"),
        modality_spec_version="image-generation-v1",
        surface="queue_api",
        endpoint=endpoint,
        adapter_id="gnode.providers.fal.image",
        adapter_behavior_version="1",
        features=frozenset({"maximum_quality", "png_output", "transparent_background"}),
        limits=(("reference_images_max", 16.0),),
        exact_size_constraints=ExactSizeConstraints2DV1(
            width_multiple=16,
            height_multiple=16,
            min_area=655_360,
            max_area=8_294_400,
            max_edge=3_840,
            max_aspect_ratio=3.0,
        ),
        resource_id="fal-image",
        estimated_duration_seconds=duration,
        estimated_cost_low_usd=cost_low,
        estimated_cost_high_usd=cost_high,
        requests_per_minute=requests_per_minute,
        rate_limit_owner=("provider_adapter" if requests_per_minute else "none"),
        verified_on=verified_on,
        evidence_ref="provider-contract:fal",
    )


def _workload(*, policy_id: str = "hero-image") -> WorkloadRequestV1:
    return WorkloadRequestV1(
        policy_id=policy_id,
        operation="image_generation",
        modality_spec_version="image-generation-v1",
        required_features=frozenset({"maximum_quality", "png_output", "transparent_background"}),
        exact_size=ExactSize2DV1(width=1024, height=1024),
        output_options={
            "background": "transparent",
            "operation_variant": "generation",
            "output_format": "png",
            "quality": "sunburst",
            "size": "1024x1024",
        },
    )


def _builder(
    *,
    route: RouteContractV1 | None = None,
    policy_id: str = "hero-image",
    policy_version: str = "1",
) -> GraphBuilder:
    selected = route or _route()
    policy = WorkloadPolicyV1(
        policy_id=policy_id,
        policy_version=policy_version,
        product_id="gpt-image-2.5-sunburst",
        route_id=selected.route_id,
    )
    return GraphBuilder(
        route_catalog=RouteCatalog([selected]),
        workload_policies={policy_id: policy},
    )


def _add_image(
    builder: GraphBuilder,
    *,
    node_id: str = "hero.generate",
    depends_on: tuple[str, ...] = (),
    policy_id: str = "hero-image",
) -> Node:
    return builder.add(
        IMAGE_TYPE,
        node_id,
        domain="image",
        description="Generate a hero image",
        depends_on=depends_on,
        input_digests=(_INPUT_DIGEST,),
        workload=_workload(policy_id=policy_id),
    )


def _seal(builder: GraphBuilder, *, terminal_node_id: str = "hero.generate") -> Graph:
    return seal_graph(
        Graph,
        resources=builder.resources(),
        resolved_routes=builder.resolved_routes(),
        nodes=builder.nodes,
        terminal_node_id=terminal_node_id,
        schema_version=1,
        kind="test-graph-v1",
    )


def test_snapshot_round_trips_and_rehydrates_exact_dispatch_identity() -> None:
    builder = _builder()
    node = _add_image(builder)
    graph = _seal(builder)

    snapshot = graph.resolved_route_for(node)
    assert graph.resolved_route_for(node.node_id) is snapshot
    assert graph.resolved_route(snapshot.binding_ref) is snapshot
    assert snapshot.endpoint == "https://queue.fal.test/fal-ai/gpt-image-2.5-sunburst"
    assert snapshot.required_features == (
        "maximum_quality",
        "png_output",
        "transparent_background",
    )
    assert snapshot.effective_output_options["background"] == "transparent"
    assert snapshot.required_exact_size == ExactSize2DV1(width=1024, height=1024)
    assert snapshot.supported_exact_size_constraints == ExactSizeConstraints2DV1(
        width_multiple=16,
        height_multiple=16,
        min_area=655_360,
        max_area=8_294_400,
        max_edge=3_840,
        max_aspect_ratio=3.0,
    )
    assert snapshot.output_fingerprint in node.input_sha256

    forbidden = {
        "estimated_duration_seconds",
        "estimated_cost_low_usd",
        "estimated_cost_high_usd",
        "max_in_flight",
        "requests_per_minute",
        "rate_limit_owner",
        "verified_on",
        "evidence_ref",
        "credentials",
    }
    assert forbidden.isdisjoint(snapshot.model_dump())

    restored = snapshot.to_resolved_binding()
    assert restored.route.route_id == snapshot.route_id
    assert restored.route.model.provider == snapshot.provider
    assert restored.route.exact_size_constraints == snapshot.supported_exact_size_constraints
    assert restored.request.exact_size == snapshot.required_exact_size
    assert restored.request.output_options["quality"] == "sunburst"
    assert restored.policy.policy_version == snapshot.policy_version
    assert restored.to_snapshot() == snapshot

    reparsed = Graph.model_validate_json(graph.model_dump_json())
    assert reparsed == graph
    assert reparsed.graph_sha256 == graph.graph_sha256
    assert reparsed.topology_sha256 == graph.topology_sha256


def test_snapshot_round_trips_a_strict_exact_size_allowlist() -> None:
    allowed_size = ExactSize2DV1(width=1024, height=1024)
    route = replace(
        _route(),
        exact_size_constraints=ExactSizeConstraints2DV1(
            allowed_sizes=(allowed_size,),
        ),
    )
    builder = _builder(route=route)
    node = _add_image(builder)
    graph = _seal(builder)

    snapshot = graph.resolved_route_for(node)
    assert snapshot.supported_exact_size_constraints is not None
    assert snapshot.supported_exact_size_constraints.allowed_sizes == (allowed_size,)
    assert Graph.model_validate_json(graph.model_dump_json()) == graph
    assert snapshot.to_resolved_binding().to_snapshot() == snapshot


def test_builder_deduplicates_only_identical_used_snapshots() -> None:
    builder = _builder()
    first = _add_image(builder)
    second = _add_image(
        builder,
        node_id="hero-variant.generate",
        depends_on=(first.node_id,),
    )

    assert first.binding_ref == second.binding_ref
    assert len(builder.resolved_routes()) == 1
    graph = _seal(builder, terminal_node_id=second.node_id)
    assert len(graph.resolved_routes) == 1


def test_inactive_registered_routes_never_enter_the_plan() -> None:
    selected = _route()
    inactive = replace(
        selected,
        route_id="gpt-image-2.5-sunburst/openai/images",
        model=ModelRef(model="gpt-image-2.5-sunburst", provider="openai"),
        surface="images_api",
        endpoint="https://api.openai.test/v1/images/generations",
        adapter_id="gnode.providers.openai.image",
        resource_id="openai-image",
    )
    policy = WorkloadPolicyV1(
        policy_id="hero-image",
        policy_version="1",
        product_id=selected.product_id,
        route_id=selected.route_id,
    )
    builder = GraphBuilder(
        route_catalog=RouteCatalog([inactive, selected]),
        workload_policies={policy.policy_id: policy},
    )
    _add_image(builder)

    assert [snapshot.route_id for snapshot in builder.resolved_routes()] == [selected.route_id]
    assert [resource.resource_id for resource in builder.resources()] == ["local", "fal-image"]


@pytest.mark.parametrize(
    ("policy_id", "policy_version"),
    [("alternate-hero-image", "1"), ("hero-image", "2")],
)
def test_policy_alias_or_revision_changes_plan_ref_but_not_artifact_cache(
    policy_id: str, policy_version: str
) -> None:
    base_builder = _builder()
    base_node = _add_image(base_builder)
    changed_builder = _builder(policy_id=policy_id, policy_version=policy_version)
    changed_node = _add_image(changed_builder, policy_id=policy_id)

    assert changed_node.cache_key == base_node.cache_key
    assert changed_node.binding_ref != base_node.binding_ref
    assert (
        changed_builder.resolved_routes()[0].output_fingerprint
        == base_builder.resolved_routes()[0].output_fingerprint
    )


def test_price_pacing_and_verification_do_not_change_ref_or_artifact_cache() -> None:
    base_builder = _builder()
    base_node = _add_image(base_builder)
    changed_route = replace(
        _route(),
        estimated_duration_seconds=999.0,
        estimated_cost_low_usd=8.0,
        estimated_cost_high_usd=9.0,
        requests_per_minute=2,
        verified_on="2030-01-01",
        evidence_ref="new-evidence",
    )
    changed_builder = _builder(route=changed_route)
    changed_node = _add_image(changed_builder)

    assert changed_node.cache_key == base_node.cache_key
    assert changed_node.binding_ref == base_node.binding_ref
    assert changed_builder.resolved_routes() == base_builder.resolved_routes()


def test_exact_size_constraint_change_rekeys_plan_but_not_artifact_cache() -> None:
    base_builder = _builder()
    base_node = _add_image(base_builder)
    changed_route = replace(
        _route(),
        exact_size_constraints=ExactSizeConstraints2DV1(
            width_multiple=16,
            height_multiple=16,
            min_area=655_360,
            max_area=8_294_400,
            max_edge=4_096,
            max_aspect_ratio=3.0,
        ),
    )
    changed_builder = _builder(route=changed_route)
    changed_node = _add_image(changed_builder)

    assert changed_node.cache_key == base_node.cache_key
    assert changed_node.binding_ref != base_node.binding_ref
    assert (
        changed_builder.resolved_routes()[0].behavior_fingerprint
        == base_builder.resolved_routes()[0].behavior_fingerprint
    )
    assert (
        changed_builder.resolved_routes()[0].output_fingerprint
        == base_builder.resolved_routes()[0].output_fingerprint
    )


def test_snapshot_refuses_tampered_behavior_options_and_reference() -> None:
    builder = _builder()
    _add_image(builder)
    payload = builder.resolved_routes()[0].model_dump(mode="json")

    changed_endpoint = {**payload, "endpoint": "https://queue.fal.test/another-route"}
    with pytest.raises(ValidationError, match="behavior fingerprint is stale"):
        ResolvedRouteSnapshotV1.model_validate_json(json.dumps(changed_endpoint))

    changed_options = {
        **payload,
        "effective_output_options": {
            **payload["effective_output_options"],
            "background": "opaque",
        },
    }
    with pytest.raises(ValidationError, match="output fingerprint is stale"):
        ResolvedRouteSnapshotV1.model_validate_json(json.dumps(changed_options))

    changed_ref = {**payload, "binding_ref": "0" * 64}
    with pytest.raises(ValidationError, match="binding_ref is stale"):
        ResolvedRouteSnapshotV1.model_validate_json(json.dumps(changed_ref))


def test_snapshot_refuses_tampered_exact_size_capability_or_requirement() -> None:
    builder = _builder()
    _add_image(builder)
    payload = builder.resolved_routes()[0].model_dump(mode="json")

    changed_constraints = {
        **payload,
        "supported_exact_size_constraints": {
            **payload["supported_exact_size_constraints"],
            "max_edge": 4_096,
        },
    }
    with pytest.raises(ValidationError, match="contract fingerprint is stale"):
        ResolvedRouteSnapshotV1.model_validate_json(json.dumps(changed_constraints))

    unsupported_requirement = {
        **payload,
        "required_exact_size": {"width": 640, "height": 360},
    }
    with pytest.raises(ValidationError, match="requires unsupported exact size"):
        ResolvedRouteSnapshotV1.model_validate_json(json.dumps(unsupported_requirement))


def test_snapshot_refuses_credentials_in_endpoint_or_output_options() -> None:
    builder = _builder()
    _add_image(builder)
    payload = builder.resolved_routes()[0].model_dump(mode="json")

    secret_endpoint = {
        **payload,
        "endpoint": "https://user:secret@queue.fal.test/route",
    }
    with pytest.raises(ValidationError, match=r"non-secret HTTP\(S\) endpoint"):
        ResolvedRouteSnapshotV1.model_validate_json(json.dumps(secret_endpoint))

    for endpoint in ("file:///private/provider", "/relative/provider", "ftp://provider.test"):
        with pytest.raises(ValidationError, match=r"non-secret HTTP\(S\) endpoint"):
            ResolvedRouteSnapshotV1.model_validate({**payload, "endpoint": endpoint})

    secret_options = {
        **payload,
        "effective_output_options": {"api_key": "not-portable"},
    }
    with pytest.raises(ValidationError, match="credential-bearing keys"):
        ResolvedRouteSnapshotV1.model_validate_json(json.dumps(secret_options))


@pytest.mark.parametrize(
    ("change", "value", "pattern"),
    [
        ("operation", "image_edit", "operation"),
        ("provider", "openrouter", "provider"),
        ("model", "another-model", "model"),
        ("resource_id", "another-image", "resource_id"),
        ("input_sha256", (_INPUT_DIGEST,), "output_fingerprint"),
    ],
)
def test_graph_refuses_node_binding_mismatches(change: str, value: object, pattern: str) -> None:
    builder = _builder()
    node = _add_image(builder)
    changed_node = node.model_copy(update={change: value})
    resources = list(builder.resources())
    if change == "resource_id":
        resources.append(Resource(resource_id="another-image", rate_limit_owner="none"))

    with pytest.raises(ValidationError, match=pattern):
        seal_graph(
            Graph,
            resources=resources,
            resolved_routes=builder.resolved_routes(),
            nodes=(changed_node,),
            terminal_node_id=changed_node.node_id,
            schema_version=1,
            kind="test-graph-v1",
        )


def test_graph_refuses_dangling_duplicate_and_unused_snapshots() -> None:
    builder = _builder()
    node = _add_image(builder)
    snapshot = builder.resolved_routes()[0]

    dangling = node.model_copy(update={"binding_ref": "0" * 64})
    with pytest.raises(ValidationError, match="references an undeclared binding"):
        seal_graph(
            Graph,
            resources=builder.resources(),
            resolved_routes=(snapshot,),
            nodes=(dangling,),
            terminal_node_id=dangling.node_id,
            schema_version=1,
            kind="test-graph-v1",
        )

    with pytest.raises(ValidationError, match="resolved routes must be unique"):
        seal_graph(
            Graph,
            resources=builder.resources(),
            resolved_routes=(snapshot, snapshot),
            nodes=(node,),
            terminal_node_id=node.node_id,
            schema_version=1,
            kind="test-graph-v1",
        )

    alternate_builder = _builder(policy_version="2")
    _add_image(alternate_builder)
    unused = alternate_builder.resolved_routes()[0]
    with pytest.raises(ValidationError, match="unused resolved routes"):
        seal_graph(
            Graph,
            resources=builder.resources(),
            resolved_routes=(snapshot, unused),
            nodes=(node,),
            terminal_node_id=node.node_id,
            schema_version=1,
            kind="test-graph-v1",
        )


def test_old_graph_json_keeps_its_exact_serialized_shape_and_hashes() -> None:
    old_record = {
        "schema_version": 1,
        "kind": "test-graph-v1",
        "resources": [
            {
                "resource_id": "local",
                "max_in_flight": None,
                "requests_per_minute": None,
                "rate_limit_owner": "none",
            },
            {
                "resource_id": "legacy-image",
                "max_in_flight": None,
                "requests_per_minute": None,
                "rate_limit_owner": "none",
            },
        ],
        "nodes": [
            {
                "node_id": "hero.generate",
                "type_id": "asset/image.generate",
                "domain": "image",
                "description": "Generate a hero image",
                "params": {},
                "depends_on": [],
                "barrier_only": [],
                "operation": "image_generation",
                "resource_id": "legacy-image",
                "provider": "openai",
                "model": "legacy-model",
                "retry_owner": "component",
                "max_attempts": 3,
                "input_sha256": [_INPUT_DIGEST],
                "cache_key": "b4f8ef5a956475b0119e68b777c4283a491daf7f007eba4475979d3d33b75e57",
                "ports": [],
                "card": None,
                "template_id": None,
                "estimated_duration_seconds": 10.0,
                "estimated_cost_low_usd": 0.1,
                "estimated_cost_high_usd": 0.2,
            }
        ],
        "terminal_node_id": "hero.generate",
        "topology_sha256": "9707669e3adfaf257534fb96fded2ff368cd87e0863b0436b0377f231a6ebba9",
        "graph_sha256": "2d4562db630d67d82a38bf6cd5317e4d36e205400ee2f44f495a6073cde50e74",
    }

    graph = Graph.model_validate_json(json.dumps(old_record))

    assert graph.resolved_routes == ()
    assert graph.node("hero.generate").binding_ref is None
    assert graph.topology_sha256 == topology_sha256(graph)
    assert graph.graph_sha256 == graph_sha256_of(graph)
    assert graph.model_dump(mode="json") == old_record
