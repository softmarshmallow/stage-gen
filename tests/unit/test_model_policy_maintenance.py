"""The model-policy snapshot: every route and every policy selection, offline and sorted."""

from __future__ import annotations

import pytest

from stage_gen.image_product import ImageProvider
from stage_gen.model_policy_maintenance import (
    ModelPolicySnapshotV2,
    ModelRouteSnapshotV1,
    build_model_policy_snapshot,
    load_active_model_policy_snapshot,
    render_model_policy_snapshot,
)
from stage_gen.model_routes import IMAGE_ROUTE_CATALOG, image_workload_policies


def _snapshot() -> ModelPolicySnapshotV2:
    return build_model_policy_snapshot(
        catalog=IMAGE_ROUTE_CATALOG,
        policy_selections={
            "default": image_workload_policies(),
            **{provider.value: image_workload_policies(provider) for provider in ImageProvider},
        },
    )


def test_the_snapshot_is_deterministic_and_sorted() -> None:
    first, second = _snapshot(), _snapshot()
    assert render_model_policy_snapshot(first) == render_model_policy_snapshot(second)
    route_ids = [route.route_id for route in first.routes]
    assert route_ids == sorted(route_ids)
    selections = [(policy.selection, policy.policy_id) for policy in first.policies]
    assert selections == sorted(selections)
    assert {policy.route_id for policy in first.policies} <= set(route_ids)


@pytest.mark.parametrize(
    ("endpoint", "message"),
    [
        ("https://:443/images", r"non-secret HTTP\(S\) URL"),
        ("https://user:secret@provider.example.test/images", r"non-secret HTTP\(S\) URL"),
        ("https://provider.example.test:bad/images", "valid network port"),
        ("https://provider.example.test:99999/images", "valid network port"),
    ],
)
def test_a_route_snapshot_refuses_unusable_endpoints(endpoint: str, message: str) -> None:
    payload = _snapshot().routes[0].model_dump(mode="json")
    payload["endpoint"] = endpoint

    with pytest.raises(ValueError, match=message):
        ModelRouteSnapshotV1.model_validate(payload)


def test_route_ids_and_policy_selections_are_unique() -> None:
    snapshot = _snapshot()
    with pytest.raises(ValueError, match="route ids must be unique"):
        ModelPolicySnapshotV2(routes=snapshot.routes * 2, policies=snapshot.policies)
    with pytest.raises(ValueError, match="policy selections must be unique"):
        ModelPolicySnapshotV2(routes=snapshot.routes, policies=snapshot.policies * 2)


def test_the_packaged_snapshot_reads_back_as_written() -> None:
    packaged = load_active_model_policy_snapshot()
    assert packaged.kind == "stage-gen-model-policy-snapshot-v2"
    assert ModelPolicySnapshotV2.model_validate_json(render_model_policy_snapshot(packaged)) == (
        packaged
    )
