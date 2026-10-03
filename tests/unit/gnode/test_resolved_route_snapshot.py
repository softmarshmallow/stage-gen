from __future__ import annotations

import json
from dataclasses import replace

import pytest
from pydantic import ValidationError

from gnode import (
    ExactSize2DV1,
    ExactSizeConstraints2DV1,
    ModelRef,
    ResolvedRouteSnapshotV1,
    RouteCatalog,
    RouteContractV1,
    WorkloadPolicyV1,
    WorkloadRequestV1,
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


def _snapshot(*, route: RouteContractV1 | None = None) -> ResolvedRouteSnapshotV1:
    selected = route or _route()
    policy = WorkloadPolicyV1(
        policy_id="hero-image",
        policy_version="1",
        product_id="gpt-image-2.5-sunburst",
        route_id=selected.route_id,
    )
    return RouteCatalog([selected]).resolve(_workload(), policy).to_snapshot()


def test_snapshot_round_trips_and_rehydrates_exact_dispatch_identity() -> None:
    snapshot = _snapshot()

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
    assert ResolvedRouteSnapshotV1.model_validate_json(snapshot.model_dump_json()) == snapshot


def test_snapshot_round_trips_a_strict_exact_size_allowlist() -> None:
    allowed_size = ExactSize2DV1(width=1024, height=1024)
    route = replace(
        _route(),
        exact_size_constraints=ExactSizeConstraints2DV1(
            allowed_sizes=(allowed_size,),
        ),
    )
    snapshot = _snapshot(route=route)

    assert snapshot.supported_exact_size_constraints is not None
    assert snapshot.supported_exact_size_constraints.allowed_sizes == (allowed_size,)
    assert snapshot.to_resolved_binding().to_snapshot() == snapshot


def test_price_pacing_and_verification_do_not_change_the_binding() -> None:
    changed = _route(
        duration=120.0,
        cost_low=0.05,
        cost_high=0.25,
        requests_per_minute=60,
        verified_on="2026-10-01",
    )
    assert _snapshot(route=changed).binding_ref == _snapshot().binding_ref


def test_snapshot_refuses_tampered_behavior_options_and_reference() -> None:
    payload = _snapshot().model_dump(mode="json")

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
    payload = _snapshot().model_dump(mode="json")

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
    payload = _snapshot().model_dump(mode="json")

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
