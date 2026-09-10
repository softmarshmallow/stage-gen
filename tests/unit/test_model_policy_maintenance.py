from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

import pytest

from gnode import (
    ExactSize2DV1,
    ExactSizeConstraints2DV1,
    Graph,
    GraphBuilder,
    ModelRef,
    NodeType,
    RouteCatalog,
    RouteContractV1,
    ViewArchetype,
    WorkloadPolicyV1,
    WorkloadRequestV1,
    seal_graph,
)
from stage_gen.model_policy_maintenance import (
    GeneratedModelPolicyFileSnapshotV1,
    ModelPolicySnapshotV1,
    ModelRouteSnapshotV1,
    build_model_policy_snapshot,
    diff_model_policy_snapshots,
    image_provider_capability_gaps,
    model_route_report,
    stale_generated_files,
)

_INPUT = "a" * 64

IMAGE = NodeType(
    type_id="test/image.generate",
    title="Generate test image",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    contract_version="test-image-v1",
)
VALIDATE = NodeType(
    type_id="test/image.validate",
    title="Validate test image",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="test-validate-v1",
)
PACKAGE = NodeType(
    type_id="test/package",
    title="Package test image",
    archetype=ViewArchetype.PACKAGE,
    operation="local",
    contract_version="test-package-v1",
)


def _route(
    provider: str,
    *,
    route_id: str | None = None,
    estimated_cost_low_usd: float = 0.2,
    estimated_cost_high_usd: float = 0.3,
    max_in_flight: int | None = None,
    extra_features: frozenset[str] = frozenset(),
) -> RouteContractV1:
    return RouteContractV1(
        route_id=route_id or f"image.sunburst.{provider}.generation",
        product_id="gpt-image-2.5-sunburst",
        operation="image_generation",
        operation_variant="generation",
        model=ModelRef(model=f"{provider}/sunburst", provider=provider),
        modality_spec_version="image-generation-v1",
        surface=f"{provider}-images",
        endpoint=f"https://{provider}.example.test/images",
        adapter_id=f"gnode-{provider}-image-v1",
        adapter_behavior_version="1",
        resource_id=f"{provider}-image",
        features=frozenset(
            {"exact_size", "maximum_quality", "png_output", "transparent_background"}
        )
        | extra_features,
        exact_size_constraints=ExactSizeConstraints2DV1(width_multiple=16, height_multiple=16),
        estimated_duration_seconds=10.0,
        estimated_cost_low_usd=estimated_cost_low_usd,
        estimated_cost_high_usd=estimated_cost_high_usd,
        max_in_flight=max_in_flight,
        rate_limit_owner="none",
    )


def _policy(route: RouteContractV1) -> WorkloadPolicyV1:
    return WorkloadPolicyV1(
        policy_id="image.transparent.generation",
        policy_version="1",
        product_id=route.product_id,
        route_id=route.route_id,
    )


def _graph(
    route: RouteContractV1,
    policy: WorkloadPolicyV1,
    *,
    quality: str = "max",
) -> Graph:
    builder = GraphBuilder(
        route_catalog=RouteCatalog((route,)),
        workload_policies={policy.policy_id: policy},
    )
    builder.add(
        IMAGE,
        "hero-generate",
        domain="hero",
        description="Generate the hero",
        input_digests=(_INPUT,),
        workload=WorkloadRequestV1(
            policy_id=policy.policy_id,
            operation="image_generation",
            modality_spec_version="image-generation-v1",
            required_features=frozenset(
                {"exact_size", "maximum_quality", "png_output", "transparent_background"}
            ),
            exact_size=ExactSize2DV1(width=1536, height=1024),
            output_options={
                "background": "transparent",
                "operation_variant": "generation",
                "quality": quality,
                "size": "1536x1024",
            },
        ),
    )
    builder.add(
        VALIDATE,
        "hero-validate",
        domain="hero",
        description="Validate the hero",
        depends_on=("hero-generate",),
    )
    builder.add(
        PACKAGE,
        "package",
        domain="package",
        description="Package the hero",
        depends_on=("hero-validate",),
    )
    return seal_graph(
        Graph,
        schema_version=1,
        kind="test-model-policy-graph-v1",
        resources=builder.resources(),
        resolved_routes=builder.resolved_routes(),
        nodes=builder.nodes,
        terminal_node_id="package",
    )


def _snapshot(
    provider: str,
    *,
    quality: str = "max",
    route_id: str | None = None,
    estimated_cost_low_usd: float = 0.2,
    estimated_cost_high_usd: float = 0.3,
    max_in_flight: int | None = None,
    extra_features: frozenset[str] = frozenset(),
) -> ModelPolicySnapshotV1:
    route = _route(
        provider,
        route_id=route_id,
        estimated_cost_low_usd=estimated_cost_low_usd,
        estimated_cost_high_usd=estimated_cost_high_usd,
        max_in_flight=max_in_flight,
        extra_features=extra_features,
    )
    policy = _policy(route)
    return build_model_policy_snapshot(
        catalog=RouteCatalog((route,)),
        policy_selections={"default": {policy.policy_id: policy}},
        recipes=(("test_recipe", "fixtures/test", _graph(route, policy, quality=quality)),),
    )


@pytest.mark.parametrize(
    ("endpoint", "message"),
    [
        ("https://:443/images", r"non-secret HTTP\(S\) URL"),
        ("https://provider.example.test:bad/images", "valid network port"),
        ("https://provider.example.test:99999/images", "valid network port"),
    ],
)
def test_model_route_snapshot_refuses_unusable_endpoints(
    endpoint: str,
    message: str,
) -> None:
    payload = _snapshot("provider_a").routes[0].model_dump(mode="json")
    payload["endpoint"] = endpoint

    with pytest.raises(ValueError, match=message):
        ModelRouteSnapshotV1.model_validate(payload)


def test_same_spec_provider_switch_is_policy_only_and_prices_cache_rekeys() -> None:
    report = cast(
        dict[str, Any],
        diff_model_policy_snapshots(_snapshot("provider_a"), _snapshot("provider_b")),
    )

    assert report["has_changes"] is True
    assert report["capability_gaps"] == []
    assert report["effective_option_deltas"] == []
    assert report["consumer_source_changes"] == {
        "catalog_or_policy_only": True,
        "same_spec_route_change": True,
        "recipes": False,
        "components": False,
        "modalities": False,
        "orchestration_factories": False,
    }
    [recipe] = cast(list[dict[str, Any]], report["recipe_deltas"])
    assert recipe["direct_nodes"] == ["hero-generate"]
    assert recipe["downstream_cache_rekeys"] == ["hero-validate", "package"]
    structural = recipe["structural"]
    assert structural["topology_changed"] is True
    assert structural["base_topology_sha256"] != structural["current_topology_sha256"]
    assert structural["resources_changed"] is True
    assert [delta["change"] for delta in structural["resource_deltas"]] == [
        "removed",
        "added",
    ]
    assert structural["nodes_added"] == []
    assert structural["nodes_removed"] == []
    assert structural["nodes_changed"] == ["hero-generate"]
    assert structural["consumer_nodes_changed"] == []
    assert structural["route_resource_only_nodes"] == ["hero-generate"]
    assert recipe["operation_count_deltas"] == {}
    assert recipe["cost_deltas"] == {"low_usd": 0.0, "high_usd": 0.0}
    assert report["required_live_canary_classes"] == [
        "constraint_heavy_atlas_or_cutout",
        "largest_active_canvas",
        "route_endpoint_smoke",
        "transparent_generation",
    ]


def test_same_route_id_successor_model_remains_catalog_only() -> None:
    route_id = "image.sunburst.selected.generation"
    report = cast(
        dict[str, Any],
        diff_model_policy_snapshots(
            _snapshot("provider_a", route_id=route_id),
            _snapshot("provider_b", route_id=route_id),
        ),
    )

    assert report["policy_deltas"] == []
    [route_delta] = cast(list[dict[str, Any]], report["route_deltas"])
    assert route_delta["change"] == "changed"
    assert route_delta["field_deltas"]["model"] == {
        "base": "provider_a/sunburst",
        "current": "provider_b/sunburst",
    }
    assert report["consumer_source_changes"] == {
        "catalog_or_policy_only": True,
        "same_spec_route_change": True,
        "recipes": False,
        "components": False,
        "modalities": False,
        "orchestration_factories": False,
    }


def test_capability_gap_is_reported_per_planned_node() -> None:
    current = _snapshot("provider_b")
    route = current.routes[0].model_copy(
        update={
            "features": tuple(
                feature
                for feature in current.routes[0].features
                if feature != "transparent_background"
            )
        }
    )
    invalid = current.model_copy(update={"routes": (route,)})

    report = cast(dict[str, Any], diff_model_policy_snapshots(_snapshot("provider_a"), invalid))

    assert report["capability_gaps"] == [
        {
            "recipe_id": "test_recipe",
            "node_id": "hero-generate",
            "route_id": "image.sunburst.provider_b.generation",
            "reasons": ["missing features: transparent_background"],
        }
    ]
    consumer_changes = cast(dict[str, object], report["consumer_source_changes"])
    assert consumer_changes["same_spec_route_change"] is False


def test_provider_preflight_accumulates_every_refusing_node() -> None:
    active = _snapshot("provider_a")
    candidate = _snapshot("provider_b")
    candidate_route = candidate.routes[0].model_copy(
        update={
            "features": tuple(
                feature
                for feature in candidate.routes[0].features
                if feature != "transparent_background"
            )
        }
    )
    candidate_policy = candidate.policies[0].model_copy(update={"selection": "provider_b"})
    second_recipe = active.recipes[0].model_copy(update={"recipe_id": "test_recipe_two"})
    snapshot = active.model_copy(
        update={
            "routes": (*active.routes, candidate_route),
            "policies": (*active.policies, candidate_policy),
            "recipes": (*active.recipes, second_recipe),
        }
    )

    gaps = image_provider_capability_gaps(snapshot, image_provider="provider_b")

    assert [(gap["recipe_id"], gap["node_id"]) for gap in gaps] == [
        ("test_recipe", "hero-generate"),
        ("test_recipe_two", "hero-generate"),
    ]
    assert all(gap["route_id"] == candidate_route.route_id for gap in gaps)
    assert all(gap["reasons"] == ["missing features: transparent_background"] for gap in gaps)
    assert image_provider_capability_gaps(
        snapshot,
        image_provider="provider_b",
        recipe_id="test_recipe_two",
    ) == [gaps[1]]


def test_effective_option_change_reports_exact_before_and_after_values() -> None:
    report = cast(
        dict[str, Any],
        diff_model_policy_snapshots(
            _snapshot("provider_a", quality="max"),
            _snapshot("provider_a", quality="high"),
        ),
    )

    assert report["route_deltas"] == []
    assert report["policy_deltas"] == []
    assert report["effective_option_deltas"] == [
        {
            "recipe_id": "test_recipe",
            "node_id": "hero-generate",
            "option": "quality",
            "base_present": True,
            "current_present": True,
            "base": "max",
            "current": "high",
        }
    ]
    [recipe] = cast(list[dict[str, Any]], report["recipe_deltas"])
    assert recipe["direct_nodes"] == ["hero-generate"]
    assert recipe["content_identity_changes"] == [
        "hero-generate",
        "hero-validate",
        "package",
    ]


def test_cost_only_change_is_priced_without_cache_rekeys_or_live_canaries() -> None:
    report = cast(
        dict[str, Any],
        diff_model_policy_snapshots(
            _snapshot("provider_a"),
            _snapshot(
                "provider_a",
                estimated_cost_low_usd=0.25,
                estimated_cost_high_usd=0.4,
            ),
        ),
    )

    [route_delta] = cast(list[dict[str, Any]], report["route_deltas"])
    assert route_delta["changed_fields"] == [
        "estimated_cost_high_usd",
        "estimated_cost_low_usd",
    ]
    [recipe] = cast(list[dict[str, Any]], report["recipe_deltas"])
    assert recipe["direct_nodes"] == []
    assert recipe["downstream_cache_rekeys"] == []
    assert recipe["content_identity_changes"] == []
    assert recipe["operation_count_deltas"] == {}
    assert recipe["cost_deltas"] == {"low_usd": 0.05, "high_usd": 0.1}
    assert report["required_live_canary_classes"] == []


def test_resource_only_change_is_separate_from_content_identity() -> None:
    report = cast(
        dict[str, Any],
        diff_model_policy_snapshots(
            _snapshot("provider_a", max_in_flight=1),
            _snapshot("provider_a", max_in_flight=3),
        ),
    )

    [recipe] = cast(list[dict[str, Any]], report["recipe_deltas"])
    assert recipe["direct_nodes"] == []
    assert recipe["downstream_cache_rekeys"] == []
    assert recipe["content_identity_changes"] == []
    assert recipe["structural"]["topology_changed"] is True
    assert recipe["structural"]["resources_changed"] is True
    assert recipe["structural"]["resource_deltas"] == [
        {
            "resource_id": "provider_a-image",
            "change": "changed",
            "changed_fields": ["max_in_flight"],
            "field_deltas": {"max_in_flight": {"base": 1, "current": 3}},
        }
    ]
    assert recipe["structural"]["nodes_changed"] == []
    assert recipe["structural"]["consumer_nodes_changed"] == []
    assert report["required_live_canary_classes"] == []


def test_capability_metadata_change_does_not_invent_downstream_cache_rekeys() -> None:
    report = cast(
        dict[str, Any],
        diff_model_policy_snapshots(
            _snapshot("provider_a"),
            _snapshot("provider_a", extra_features=frozenset({"reference_image"})),
        ),
    )

    [recipe] = cast(list[dict[str, Any]], report["recipe_deltas"])
    assert recipe["direct_nodes"] == ["hero-generate"]
    assert recipe["content_identity_changes"] == []
    assert recipe["downstream_cache_rekeys"] == []


def test_route_report_is_compact_and_stale_checks_never_rewrite(tmp_path: Path) -> None:
    generated = tmp_path / "generated.json"
    generated.write_text("{}\n", encoding="utf-8")
    file_sha256 = hashlib.sha256(generated.read_bytes()).hexdigest()
    check = GeneratedModelPolicyFileSnapshotV1(
        check_id="graph_contract",
        path="generated.json",
        expected_state_sha256="b" * 64,
        observed_state_sha256="b" * 64,
        file_sha256=file_sha256,
    )
    snapshot = _snapshot("provider_a").model_copy(update={"generated_files": (check,)})

    assert stale_generated_files(snapshot, repository_root=tmp_path) == []
    before = generated.read_bytes()
    generated.write_text('{"changed":true}\n', encoding="utf-8")
    changed = generated.read_bytes()
    assert stale_generated_files(snapshot, repository_root=tmp_path) == [
        {
            "check_id": "graph_contract",
            "path": "generated.json",
            "reasons": ["modified_since_snapshot"],
        }
    ]
    report = cast(dict[str, Any], model_route_report(snapshot, repository_root=tmp_path))
    assert "nodes" not in report["recipes"][0]
    assert changed != before
    assert generated.read_bytes() == changed
