"""The packaged snapshot of Stage Gen's model routes and the policies that select them.

A reader of the route catalog and the workload policies only: it loads no host
configuration, inspects no credential, discovers no provider model, constructs no adapter
and makes no network request. ``scripts/write_model_policy_snapshot.py`` writes it, and a
reviewer reads the diff of ``model_policy_snapshot.json`` before a route, price or policy
change is authorized.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from importlib.resources import files
from typing import Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from gnode import (
    SHA256_PATTERN,
    PersistedContractModel,
    RouteCatalog,
    WorkloadPolicyV1,
)

MODEL_POLICY_SNAPSHOT_KIND = "stage-gen-model-policy-snapshot-v2"
ACTIVE_MODEL_POLICY_SNAPSHOT = "model_policy_snapshot.json"


class ModelRouteSnapshotV1(PersistedContractModel):
    """One registered provider route, including identity and planning metadata."""

    route_id: str
    product_id: str
    operation: str
    operation_variant: str
    modality_spec_version: str
    provider: str
    model: str
    surface: str
    endpoint: str
    adapter_id: str
    adapter_behavior_version: str
    resource_id: str
    features: tuple[str, ...]
    limits: tuple[tuple[str, float], ...]
    exact_size_constraints: dict[str, Any] | None = None
    estimated_duration_seconds: float = Field(ge=0.0)
    estimated_cost_low_usd: float = Field(ge=0.0)
    estimated_cost_high_usd: float = Field(ge=0.0)
    max_in_flight: int | None = Field(default=None, ge=1)
    requests_per_minute: int | None = Field(default=None, ge=1)
    rate_limit_owner: Literal["scheduler", "provider_adapter", "none"]
    verified_on: str | None = None
    evidence_ref: str | None = None
    behavior_fingerprint: str = Field(pattern=SHA256_PATTERN)
    contract_fingerprint: str = Field(pattern=SHA256_PATTERN)

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("snapshot route endpoint must be a non-secret HTTP(S) URL")
        try:
            _ = parsed.port
        except ValueError as error:
            raise ValueError("snapshot route endpoint must use a valid network port") from error
        return value


class ModelPolicySelectionSnapshotV1(PersistedContractModel):
    """One checked-in policy under the default or a scalar provider selection."""

    selection: str
    policy_id: str
    policy_version: str
    product_id: str
    route_id: str

    @property
    def key(self) -> str:
        return f"{self.selection}:{self.policy_id}"


class ModelPolicySnapshotV2(PersistedContractModel):
    """Every registered route and every policy selection, in a deterministic order."""

    schema_version: Literal[2] = 2
    kind: Literal["stage-gen-model-policy-snapshot-v2"] = "stage-gen-model-policy-snapshot-v2"
    routes: tuple[ModelRouteSnapshotV1, ...]
    policies: tuple[ModelPolicySelectionSnapshotV1, ...]

    @model_validator(mode="after")
    def validate_unique_keys(self) -> Self:
        for label, values in (
            ("route ids", [route.route_id for route in self.routes]),
            ("policy selections", [policy.key for policy in self.policies]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"model policy snapshot {label} must be unique")
        return self


def route_snapshots(catalog: RouteCatalog) -> tuple[ModelRouteSnapshotV1, ...]:
    """Project a route catalog without touching an adapter or provider."""

    return tuple(
        ModelRouteSnapshotV1(
            route_id=route.route_id,
            product_id=route.product_id,
            operation=route.operation,
            operation_variant=route.operation_variant,
            modality_spec_version=route.modality_spec_version,
            provider=route.model.provider,
            model=route.model.model,
            surface=route.surface,
            endpoint=route.endpoint,
            adapter_id=route.adapter_id,
            adapter_behavior_version=route.adapter_behavior_version,
            resource_id=route.resource_id,
            features=tuple(sorted(route.features)),
            limits=route.limits,
            exact_size_constraints=(
                None
                if route.exact_size_constraints is None
                else route.exact_size_constraints.model_dump(mode="json")
            ),
            estimated_duration_seconds=route.estimated_duration_seconds,
            estimated_cost_low_usd=route.estimated_cost_low_usd,
            estimated_cost_high_usd=route.estimated_cost_high_usd,
            max_in_flight=route.max_in_flight,
            requests_per_minute=route.requests_per_minute,
            rate_limit_owner=route.rate_limit_owner,
            verified_on=route.verified_on,
            evidence_ref=route.evidence_ref,
            behavior_fingerprint=route.behavior_fingerprint,
            contract_fingerprint=route.contract_fingerprint,
        )
        for route in sorted(catalog.routes, key=lambda route: route.route_id)
    )


def policy_snapshots(
    selections: Mapping[str, Mapping[str, WorkloadPolicyV1]],
) -> tuple[ModelPolicySelectionSnapshotV1, ...]:
    """Project default and provider-selected policies into one deterministic table."""

    return tuple(
        ModelPolicySelectionSnapshotV1(
            selection=selection,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            product_id=policy.product_id,
            route_id=policy.route_id,
        )
        for selection, policies in sorted(selections.items())
        for policy in sorted(policies.values(), key=lambda value: value.policy_id)
    )


def build_model_policy_snapshot(
    *,
    catalog: RouteCatalog,
    policy_selections: Mapping[str, Mapping[str, WorkloadPolicyV1]],
) -> ModelPolicySnapshotV2:
    """Build a deterministic snapshot from the offline route catalog and policies."""

    return ModelPolicySnapshotV2(
        routes=route_snapshots(catalog),
        policies=policy_snapshots(policy_selections),
    )


def load_active_model_policy_snapshot() -> ModelPolicySnapshotV2:
    """Load the application-owned snapshot packaged beside this module."""

    resource = files("stage_gen").joinpath(ACTIVE_MODEL_POLICY_SNAPSHOT)
    return ModelPolicySnapshotV2.model_validate_json(resource.read_text(encoding="utf-8"))


def render_model_policy_snapshot(snapshot: ModelPolicySnapshotV2) -> str:
    return (
        json.dumps(
            snapshot.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


__all__ = [
    "ACTIVE_MODEL_POLICY_SNAPSHOT",
    "MODEL_POLICY_SNAPSHOT_KIND",
    "ModelPolicySelectionSnapshotV1",
    "ModelPolicySnapshotV2",
    "ModelRouteSnapshotV1",
    "build_model_policy_snapshot",
    "load_active_model_policy_snapshot",
    "policy_snapshots",
    "render_model_policy_snapshot",
    "route_snapshots",
]
