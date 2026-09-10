from __future__ import annotations

import json
from enum import StrEnum
from typing import Literal

import pytest
from pydantic import ValidationError

from gnode import (
    GraphBuilder,
    ModelRef,
    NodePolicy,
    NodeType,
    RouteCatalog,
    RouteContractV1,
    ViewArchetype,
    WorkloadPolicyV1,
    WorkloadRequestV1,
    seal_graph,
)
from stage_gen.recipes.graph_document import RecipeGraph


class _Operations(StrEnum):
    IMAGE_GENERATION = "image_generation"


class _VersionedGraph(RecipeGraph):
    OPERATIONS = _Operations
    CURRENT_SCHEMA_VERSION = 2
    CURRENT_KIND = "versioned-test-execution-graph-v2"
    LEGACY_GRAPH_IDENTITIES = frozenset({(1, "versioned-test-execution-graph-v1")})
    ROUTED_OPERATIONS = frozenset({_Operations.IMAGE_GENERATION.value})

    schema_version: Literal[1, 2]
    kind: Literal[
        "versioned-test-execution-graph-v1",
        "versioned-test-execution-graph-v2",
    ]
    recipe: Literal["versioned-test"]


_IMAGE_TYPE = NodeType(
    type_id="test/image.generate",
    title="Generate image",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    contract_version="test-image-v1",
    policy=NodePolicy(max_attempts=3),
)


def _builder() -> GraphBuilder:
    route = RouteContractV1(
        route_id="test.image.generation",
        product_id="test-image",
        operation="image_generation",
        operation_variant="generation",
        model=ModelRef(model="test-image-v1", provider="test-provider"),
        modality_spec_version="image-generation-v1",
        surface="test-api",
        endpoint="https://provider.test/v1/images",
        adapter_id="test-image-adapter",
        adapter_behavior_version="1",
        features=frozenset(),
        resource_id="test-image",
        estimated_duration_seconds=1,
        estimated_cost_low_usd=0,
        estimated_cost_high_usd=0,
        rate_limit_owner="none",
    )
    policy = WorkloadPolicyV1(
        policy_id="test.image",
        policy_version="1",
        product_id=route.product_id,
        route_id=route.route_id,
    )
    builder = GraphBuilder(
        route_catalog=RouteCatalog((route,)),
        workload_policies={policy.policy_id: policy},
    )
    builder.add(
        _IMAGE_TYPE,
        "image.generate",
        domain="test",
        description="Generate an image",
        input_digests=("a" * 64,),
        workload=WorkloadRequestV1(
            policy_id=policy.policy_id,
            operation=route.operation,
            modality_spec_version=route.modality_spec_version,
            required_features=frozenset(),
            output_options={"operation_variant": "generation"},
        ),
    )
    return builder


def test_new_seals_write_v2_and_legacy_v1_records_remain_byte_shaped() -> None:
    builder = _builder()
    current = _VersionedGraph.seal(
        resources=builder.resources(),
        resolved_routes=builder.resolved_routes(),
        nodes=builder.nodes,
        terminal_node_id="image.generate",
    )

    assert (current.schema_version, current.kind) == (
        2,
        "versioned-test-execution-graph-v2",
    )
    assert current.resolved_routes
    assert current.node("image.generate").binding_ref is not None

    legacy_node = current.node("image.generate").model_copy(update={"binding_ref": None})
    legacy = seal_graph(
        _VersionedGraph,
        resources=current.resources,
        nodes=(legacy_node,),
        terminal_node_id=legacy_node.node_id,
        schema_version=1,
        kind="versioned-test-execution-graph-v1",
        recipe="versioned-test",
    )
    payload = legacy.model_dump(mode="json")

    assert "resolved_routes" not in payload
    assert "binding_ref" not in payload["nodes"][0]
    assert _VersionedGraph.model_validate_json(json.dumps(payload)) == legacy


def test_identity_discriminator_refuses_mixed_or_route_bearing_legacy_records() -> None:
    builder = _builder()
    node = builder.nodes[0]

    with pytest.raises(ValidationError, match="current or legacy identity pair"):
        seal_graph(
            _VersionedGraph,
            resources=builder.resources(),
            resolved_routes=builder.resolved_routes(),
            nodes=builder.nodes,
            terminal_node_id=node.node_id,
            schema_version=1,
            kind="versioned-test-execution-graph-v2",
            recipe="versioned-test",
        )

    with pytest.raises(ValidationError, match=r"legacy.*cannot carry resolved routes"):
        seal_graph(
            _VersionedGraph,
            resources=builder.resources(),
            resolved_routes=builder.resolved_routes(),
            nodes=builder.nodes,
            terminal_node_id=node.node_id,
            schema_version=1,
            kind="versioned-test-execution-graph-v1",
            recipe="versioned-test",
        )


def test_current_identity_refuses_unbound_routed_nodes() -> None:
    builder = _builder()
    node = builder.nodes[0].model_copy(update={"binding_ref": None})

    with pytest.raises(ValidationError, match="require resolved route bindings"):
        seal_graph(
            _VersionedGraph,
            resources=builder.resources(),
            nodes=(node,),
            terminal_node_id=node.node_id,
            schema_version=2,
            kind="versioned-test-execution-graph-v2",
            recipe="versioned-test",
        )
