"""Offline snapshots and diffs for application-owned model routing policy.

This module is deliberately a reader of sealed plans.  It does not load host
configuration, inspect credentials, discover provider models, construct an
adapter, or make a network request.  A release engineer can therefore review a
model-policy migration and its cache blast radius before authorizing any spend.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from collections.abc import Mapping, Sequence
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Self, cast
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from gnode import (
    SHA256_PATTERN,
    Graph,
    PersistedContractModel,
    RouteCatalog,
    WorkloadPolicyV1,
)

MODEL_POLICY_SNAPSHOT_KIND = "stage-gen-model-policy-snapshot-v1"
MODEL_POLICY_DIFF_KIND = "stage-gen-model-policy-diff-v1"
ACTIVE_MODEL_POLICY_SNAPSHOT = "model_policy_snapshot.json"
_SENSITIVE_KEY = re.compile(
    r"(?:^|_)(?:api_key|authorization|auth|bearer|credential|credentials|headers?|"
    r"password|secret|token)(?:_|$)",
    re.IGNORECASE,
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _validate_snapshot_options(value: object, *, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int, float)):
        return
    if isinstance(value, list):
        for index, nested in enumerate(value):
            _validate_snapshot_options(nested, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            if _SENSITIVE_KEY.search(key):
                raise ValueError(f"{path} must not contain credential-bearing keys")
            _validate_snapshot_options(nested, path=f"{path}.{key}")
        return
    raise ValueError(f"{path} must contain only JSON values")


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


class ModelPolicyBindingSnapshotV1(PersistedContractModel):
    """One deduplicated resolved workload carried by a canonical recipe plan."""

    binding_ref: str = Field(pattern=SHA256_PATTERN)
    route_id: str
    policy_id: str
    provider: str
    model: str
    output_fingerprint: str = Field(pattern=SHA256_PATTERN)
    required_features: tuple[str, ...] = ()
    required_limits: tuple[tuple[str, float], ...] = ()
    required_exact_size: dict[str, int] | None = None
    effective_output_options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("effective_output_options")
    @classmethod
    def validate_effective_output_options(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_snapshot_options(value, path="effective_output_options")
        return value


class ModelPolicyNodeSnapshotV1(PersistedContractModel):
    """Compact identity record sufficient to price and explain cache movement."""

    node_id: str
    operation: str
    depends_on: tuple[str, ...]
    cache_depends_on: tuple[str, ...]
    structural_fingerprint: str = Field(pattern=SHA256_PATTERN)
    consumer_structure_fingerprint: str = Field(pattern=SHA256_PATTERN)
    cache_key: str = Field(pattern=SHA256_PATTERN)
    estimated_cost_low_usd: float = Field(ge=0.0)
    estimated_cost_high_usd: float = Field(ge=0.0)
    binding_ref: str | None = Field(default=None, pattern=SHA256_PATTERN)


class ModelPolicyResourceSnapshotV1(PersistedContractModel):
    resource_id: str
    max_in_flight: int | None = Field(default=None, ge=1)
    requests_per_minute: int | None = Field(default=None, ge=1)
    rate_limit_owner: Literal["scheduler", "provider_adapter", "none"]


class ModelPolicyRecipeSnapshotV1(PersistedContractModel):
    """One canonical recipe fixture planned entirely offline."""

    recipe_id: str
    fixture_ref: str
    graph_kind: str
    graph_schema_version: int = Field(ge=1)
    graph_sha256: str = Field(pattern=SHA256_PATTERN)
    topology_sha256: str = Field(pattern=SHA256_PATTERN)
    terminal_node_id: str
    resources: tuple[ModelPolicyResourceSnapshotV1, ...]
    operation_counts: dict[str, int]
    estimated_cost_low_usd: float = Field(ge=0.0)
    estimated_cost_high_usd: float = Field(ge=0.0)
    bindings: tuple[ModelPolicyBindingSnapshotV1, ...]
    nodes: tuple[ModelPolicyNodeSnapshotV1, ...]

    @field_validator("nodes")
    @classmethod
    def validate_unique_nodes(
        cls, value: tuple[ModelPolicyNodeSnapshotV1, ...]
    ) -> tuple[ModelPolicyNodeSnapshotV1, ...]:
        node_ids = [node.node_id for node in value]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("recipe snapshot node ids must be unique")
        return value

    @model_validator(mode="after")
    def validate_binding_references(self) -> Self:
        binding_refs = [binding.binding_ref for binding in self.bindings]
        if len(binding_refs) != len(set(binding_refs)):
            raise ValueError("recipe snapshot binding references must be unique")
        known = set(binding_refs)
        missing = sorted(
            {
                node.binding_ref
                for node in self.nodes
                if node.binding_ref is not None and node.binding_ref not in known
            }
        )
        if missing:
            raise ValueError("recipe snapshot nodes reference missing bindings")
        return self


class GeneratedModelPolicyFileSnapshotV1(PersistedContractModel):
    """Read-only generator comparison plus the exact file bytes it inspected."""

    check_id: str
    path: str
    expected_state_sha256: str = Field(pattern=SHA256_PATTERN)
    observed_state_sha256: str = Field(pattern=SHA256_PATTERN)
    file_sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("path")
    @classmethod
    def validate_portable_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            not value
            or "\\" in value
            or path.is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("generated model-policy path must be a portable relative path")
        return value

    @property
    def stale(self) -> bool:
        return self.expected_state_sha256 != self.observed_state_sha256


class ModelPolicySnapshotV1(PersistedContractModel):
    """Executable application snapshot used as the base of an offline diff."""

    schema_version: Literal[1] = 1
    kind: Literal["stage-gen-model-policy-snapshot-v1"] = "stage-gen-model-policy-snapshot-v1"
    routes: tuple[ModelRouteSnapshotV1, ...]
    policies: tuple[ModelPolicySelectionSnapshotV1, ...]
    recipes: tuple[ModelPolicyRecipeSnapshotV1, ...]
    generated_files: tuple[GeneratedModelPolicyFileSnapshotV1, ...] = ()

    @model_validator(mode="after")
    def validate_unique_keys(self) -> Self:
        for label, values in (
            ("route ids", [route.route_id for route in self.routes]),
            ("policy selections", [policy.key for policy in self.policies]),
            ("recipe ids", [recipe.recipe_id for recipe in self.recipes]),
            ("generated-file checks", [entry.check_id for entry in self.generated_files]),
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


def recipe_snapshot(
    recipe_id: str,
    fixture_ref: str,
    graph: Graph,
) -> ModelPolicyRecipeSnapshotV1:
    """Project one already-sealed graph into the compact maintenance contract."""

    bindings = tuple(
        ModelPolicyBindingSnapshotV1(
            binding_ref=route.binding_ref,
            route_id=route.route_id,
            policy_id=route.policy_id,
            provider=route.provider,
            model=route.model,
            output_fingerprint=route.output_fingerprint,
            required_features=route.required_features,
            required_limits=route.required_limits,
            required_exact_size=(
                None
                if route.required_exact_size is None
                else route.required_exact_size.model_dump(mode="json")
            ),
            effective_output_options=route.effective_output_options,
        )
        for route in graph.resolved_routes
    )
    nodes: list[ModelPolicyNodeSnapshotV1] = []
    for node in graph.nodes:
        structural = {
            "node_id": node.node_id,
            "type_id": node.type_id,
            "domain": node.domain,
            "depends_on": list(node.depends_on),
            "barrier_only": list(node.barrier_only),
            "operation": node.operation,
            "resource_id": node.resource_id,
            "retry_owner": node.retry_owner.value,
            "max_attempts": node.max_attempts,
            "ports": [
                {
                    "port_id": port.port_id,
                    "artifact_ref": port.artifact_ref,
                    "kind": port.kind,
                }
                for port in node.ports
            ],
        }
        consumer_structure = {
            key: value for key, value in structural.items() if key != "resource_id"
        }
        nodes.append(
            ModelPolicyNodeSnapshotV1(
                node_id=node.node_id,
                operation=node.operation,
                depends_on=node.depends_on,
                cache_depends_on=tuple(
                    dependency
                    for dependency in node.depends_on
                    if dependency not in node.barrier_only
                ),
                structural_fingerprint=_sha256(structural),
                consumer_structure_fingerprint=_sha256(consumer_structure),
                cache_key=node.cache_key,
                estimated_cost_low_usd=node.estimated_cost_low_usd,
                estimated_cost_high_usd=node.estimated_cost_high_usd,
                binding_ref=node.binding_ref,
            )
        )
    return ModelPolicyRecipeSnapshotV1(
        recipe_id=recipe_id,
        fixture_ref=fixture_ref,
        graph_kind=graph.kind,
        graph_schema_version=graph.schema_version,
        graph_sha256=graph.graph_sha256,
        topology_sha256=graph.topology_sha256,
        terminal_node_id=graph.terminal_node_id,
        resources=tuple(
            ModelPolicyResourceSnapshotV1.model_validate(resource.model_dump(mode="json"))
            for resource in graph.resources
        ),
        operation_counts=graph.operation_counts(),
        estimated_cost_low_usd=round(sum(node.estimated_cost_low_usd for node in graph.nodes), 6),
        estimated_cost_high_usd=round(sum(node.estimated_cost_high_usd for node in graph.nodes), 6),
        bindings=bindings,
        nodes=tuple(nodes),
    )


def build_model_policy_snapshot(
    *,
    catalog: RouteCatalog,
    policy_selections: Mapping[str, Mapping[str, WorkloadPolicyV1]],
    recipes: Sequence[tuple[str, str, Graph]],
    generated_files: Sequence[GeneratedModelPolicyFileSnapshotV1] = (),
) -> ModelPolicySnapshotV1:
    """Build a deterministic snapshot from already-offline application inputs."""

    return ModelPolicySnapshotV1(
        routes=route_snapshots(catalog),
        policies=policy_snapshots(policy_selections),
        recipes=tuple(
            recipe_snapshot(recipe_id, fixture_ref, graph)
            for recipe_id, fixture_ref, graph in sorted(recipes)
        ),
        generated_files=tuple(sorted(generated_files, key=lambda entry: entry.check_id)),
    )


def load_model_policy_snapshot(path: Path) -> ModelPolicySnapshotV1:
    """Load one strict snapshot from a caller-selected local path."""

    return ModelPolicySnapshotV1.model_validate_json(path.read_text(encoding="utf-8"))


def load_active_model_policy_snapshot() -> ModelPolicySnapshotV1:
    """Load the application-owned snapshot packaged beside this module."""

    resource = files("stage_gen").joinpath(ACTIVE_MODEL_POLICY_SNAPSHOT)
    return ModelPolicySnapshotV1.model_validate_json(resource.read_text(encoding="utf-8"))


def find_model_policy_repository_root(start: Path | None = None) -> Path | None:
    """Find a source checkout for live stale-file checks, or return ``None`` in a wheel."""

    origin = (start or Path.cwd()).resolve()
    for candidate in (origin, *origin.parents):
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "src/stage_gen" / ACTIVE_MODEL_POLICY_SNAPSHOT
        ).is_file():
            return candidate
    return None


def render_model_policy_snapshot(snapshot: ModelPolicySnapshotV1) -> str:
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


def stale_generated_files(
    snapshot: ModelPolicySnapshotV1,
    *,
    repository_root: Path | None = None,
) -> list[dict[str, object]]:
    """Report generator mismatch or post-snapshot edits without rewriting files."""

    stale: list[dict[str, object]] = []
    resolved_root = repository_root.resolve() if repository_root is not None else None
    for entry in snapshot.generated_files:
        reasons: list[str] = []
        if entry.stale:
            reasons.append("generated_state_mismatch")
        if repository_root is not None:
            path = repository_root / entry.path
            if not path.is_file():
                reasons.append("missing")
            else:
                resolved = path.resolve()
                assert resolved_root is not None
                if path.is_symlink() or not resolved.is_relative_to(resolved_root):
                    reasons.append("unsafe_path")
                elif hashlib.sha256(path.read_bytes()).hexdigest() != entry.file_sha256:
                    reasons.append("modified_since_snapshot")
        if reasons:
            stale.append({"check_id": entry.check_id, "path": entry.path, "reasons": reasons})
    return stale


def model_route_report(
    snapshot: ModelPolicySnapshotV1,
    *,
    repository_root: Path | None = None,
) -> dict[str, object]:
    """Human/tool-readable active routes and policies, without graph node bulk."""

    return {
        "schema_version": 1,
        "kind": "stage-gen-model-routes-report-v1",
        "routes": [route.model_dump(mode="json") for route in snapshot.routes],
        "policies": [policy.model_dump(mode="json") for policy in snapshot.policies],
        "recipes": [
            {
                "recipe_id": recipe.recipe_id,
                "fixture_ref": recipe.fixture_ref,
                "node_count": len(recipe.nodes),
                "operation_counts": recipe.operation_counts,
                "estimated_cost_low_usd": recipe.estimated_cost_low_usd,
                "estimated_cost_high_usd": recipe.estimated_cost_high_usd,
                "topology_sha256": recipe.topology_sha256,
                "graph_sha256": recipe.graph_sha256,
            }
            for recipe in snapshot.recipes
        ],
        "capability_gaps": _capability_gaps(snapshot, snapshot.recipes),
        "stale_generated_files": stale_generated_files(snapshot, repository_root=repository_root),
    }


def _changed_fields(base: PersistedContractModel, current: PersistedContractModel) -> list[str]:
    before = base.model_dump(mode="json")
    after = current.model_dump(mode="json")
    return sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))


def _field_deltas(
    base: PersistedContractModel, current: PersistedContractModel
) -> dict[str, dict[str, object]]:
    before = base.model_dump(mode="json")
    after = current.model_dump(mode="json")
    return {
        key: {"base": before.get(key), "current": after.get(key)}
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    }


def _indexed[T](values: Sequence[T], key: str) -> dict[str, T]:
    return {str(getattr(value, key)): value for value in values}


def _map_delta(base: Mapping[str, int], current: Mapping[str, int]) -> dict[str, dict[str, int]]:
    return {
        key: {
            "base": base.get(key, 0),
            "current": current.get(key, 0),
            "delta": current.get(key, 0) - base.get(key, 0),
        }
        for key in sorted(set(base) | set(current))
        if base.get(key, 0) != current.get(key, 0)
    }


def _descendants(
    seeds: set[str],
    base_nodes: Mapping[str, ModelPolicyNodeSnapshotV1],
    current_nodes: Mapping[str, ModelPolicyNodeSnapshotV1],
) -> list[str]:
    dependents: dict[str, set[str]] = {}
    for node in (*base_nodes.values(), *current_nodes.values()):
        for dependency in node.cache_depends_on:
            dependents.setdefault(dependency, set()).add(node.node_id)
    seen = set(seeds)
    queue = deque(sorted(seeds))
    while queue:
        for node_id in sorted(dependents.get(queue.popleft(), ())):
            if node_id not in seen:
                seen.add(node_id)
                queue.append(node_id)
    return sorted(seen - seeds)


def _option_changes(
    recipe_id: str,
    node_id: str,
    base: Mapping[str, Any],
    current: Mapping[str, Any],
) -> list[dict[str, object]]:
    return [
        {
            "recipe_id": recipe_id,
            "node_id": node_id,
            "option": option,
            "base_present": option in base,
            "current_present": option in current,
            "base": base.get(option),
            "current": current.get(option),
        }
        for option in sorted(set(base) | set(current))
        if base.get(option) != current.get(option) or (option in base) != (option in current)
    ]


def _route_deltas(
    base: ModelPolicySnapshotV1, current: ModelPolicySnapshotV1
) -> list[dict[str, object]]:
    before = _indexed(base.routes, "route_id")
    after = _indexed(current.routes, "route_id")
    deltas: list[dict[str, object]] = []
    for route_id in sorted(set(before) | set(after)):
        if route_id not in before:
            deltas.append(
                {
                    "route_id": route_id,
                    "change": "added",
                    "current": after[route_id].model_dump(mode="json"),
                }
            )
        elif route_id not in after:
            deltas.append(
                {
                    "route_id": route_id,
                    "change": "removed",
                    "base": before[route_id].model_dump(mode="json"),
                }
            )
        else:
            changed = _changed_fields(before[route_id], after[route_id])
            if changed:
                removed = sorted(set(before[route_id].features) - set(after[route_id].features))
                added = sorted(set(after[route_id].features) - set(before[route_id].features))
                deltas.append(
                    {
                        "route_id": route_id,
                        "change": "changed",
                        "changed_fields": changed,
                        "field_deltas": _field_deltas(before[route_id], after[route_id]),
                        "features_added": added,
                        "features_removed": removed,
                    }
                )
    return deltas


def _policy_deltas(
    base: ModelPolicySnapshotV1, current: ModelPolicySnapshotV1
) -> list[dict[str, object]]:
    before = {policy.key: policy for policy in base.policies}
    after = {policy.key: policy for policy in current.policies}
    deltas: list[dict[str, object]] = []
    for key in sorted(set(before) | set(after)):
        if key not in before:
            deltas.append(
                {
                    "policy": key,
                    "change": "added",
                    "current": after[key].model_dump(mode="json"),
                }
            )
        elif key not in after:
            deltas.append(
                {
                    "policy": key,
                    "change": "removed",
                    "base": before[key].model_dump(mode="json"),
                }
            )
        else:
            changed = _changed_fields(before[key], after[key])
            if changed:
                deltas.append(
                    {
                        "policy": key,
                        "change": "changed",
                        "changed_fields": changed,
                        "field_deltas": _field_deltas(before[key], after[key]),
                    }
                )
    return deltas


def _resource_deltas(
    base: Sequence[ModelPolicyResourceSnapshotV1],
    current: Sequence[ModelPolicyResourceSnapshotV1],
) -> list[dict[str, object]]:
    before = _indexed(base, "resource_id")
    after = _indexed(current, "resource_id")
    deltas: list[dict[str, object]] = []
    for resource_id in sorted(set(before) | set(after)):
        if resource_id not in before:
            deltas.append(
                {
                    "resource_id": resource_id,
                    "change": "added",
                    "current": after[resource_id].model_dump(mode="json"),
                }
            )
        elif resource_id not in after:
            deltas.append(
                {
                    "resource_id": resource_id,
                    "change": "removed",
                    "base": before[resource_id].model_dump(mode="json"),
                }
            )
        else:
            changed = _changed_fields(before[resource_id], after[resource_id])
            if changed:
                deltas.append(
                    {
                        "resource_id": resource_id,
                        "change": "changed",
                        "changed_fields": changed,
                        "field_deltas": _field_deltas(before[resource_id], after[resource_id]),
                    }
                )
    return deltas


def _constraint_failures(route: ModelRouteSnapshotV1, size: Mapping[str, int]) -> list[str]:
    constraints = route.exact_size_constraints
    if constraints is None:
        return ["route declares no exact_size_constraints"]
    width = size["width"]
    height = size["height"]
    failures: list[str] = []
    allowed = constraints.get("allowed_sizes")
    if allowed is not None and size not in allowed:
        failures.append(f"size {width}x{height} is not allowed")
    if width % int(constraints.get("width_multiple", 1)):
        failures.append("width multiple")
    if height % int(constraints.get("height_multiple", 1)):
        failures.append("height multiple")
    area = width * height
    min_area = constraints.get("min_area")
    max_area = constraints.get("max_area")
    max_edge = constraints.get("max_edge")
    max_aspect = constraints.get("max_aspect_ratio")
    if min_area is not None and area < int(min_area):
        failures.append("minimum area")
    if max_area is not None and area > int(max_area):
        failures.append("maximum area")
    if max_edge is not None and max(width, height) > int(max_edge):
        failures.append("maximum edge")
    if max_aspect is not None and max(width, height) / min(width, height) > float(max_aspect):
        failures.append("maximum aspect ratio")
    return failures


def _binding_route_failures(
    binding: ModelPolicyBindingSnapshotV1,
    route: ModelRouteSnapshotV1,
) -> list[str]:
    reasons: list[str] = []
    missing = sorted(set(binding.required_features) - set(route.features))
    if missing:
        reasons.append("missing features: " + ", ".join(missing))
    limits = dict(route.limits)
    for name, required in binding.required_limits:
        if name not in limits:
            reasons.append(f"missing limit: {name}")
        elif limits[name] < required:
            reasons.append(f"limit below requirement: {name}")
    if binding.required_exact_size is not None:
        reasons.extend(_constraint_failures(route, binding.required_exact_size))
    return reasons


def _capability_gaps(
    snapshot: ModelPolicySnapshotV1,
    recipes: Sequence[ModelPolicyRecipeSnapshotV1],
) -> list[dict[str, object]]:
    routes = _indexed(snapshot.routes, "route_id")
    gaps: list[dict[str, object]] = []
    for recipe in recipes:
        bindings = _indexed(recipe.bindings, "binding_ref")
        for node in recipe.nodes:
            if node.binding_ref is None:
                continue
            binding = bindings[node.binding_ref]
            route = routes.get(binding.route_id)
            reasons: list[str] = []
            if route is None:
                reasons.append("selected route is missing")
            else:
                reasons.extend(_binding_route_failures(binding, route))
            if reasons:
                gaps.append(
                    {
                        "recipe_id": recipe.recipe_id,
                        "node_id": node.node_id,
                        "route_id": binding.route_id,
                        "reasons": reasons,
                    }
                )
    return gaps


def image_provider_capability_gaps(
    snapshot: ModelPolicySnapshotV1,
    *,
    image_provider: str,
    recipe_id: str | None = None,
) -> list[dict[str, object]]:
    """Preflight every planned image workload against one provider selection.

    This path deliberately reads the already-sealed workload requirements rather
    than asking recipe planners to resolve them. An unsupported provider can
    therefore report every refusing node instead of aborting at the first one.
    Normal graph planning remains fail-closed and is used only after this
    preflight finds no gaps.
    """

    selected_policies = {
        policy.policy_id: policy
        for policy in snapshot.policies
        if policy.selection == image_provider
    }
    available_selections = sorted({policy.selection for policy in snapshot.policies})
    if not selected_policies:
        raise ValueError(
            f"unknown model-policy provider selection {image_provider!r}; available: "
            + ", ".join(available_selections)
        )
    available_recipes = sorted(recipe.recipe_id for recipe in snapshot.recipes)
    if recipe_id is not None and recipe_id not in available_recipes:
        raise ValueError(
            f"unknown model-policy recipe {recipe_id!r}; available: " + ", ".join(available_recipes)
        )

    routes = _indexed(snapshot.routes, "route_id")
    gaps: list[dict[str, object]] = []
    for recipe in snapshot.recipes:
        if recipe_id is not None and recipe.recipe_id != recipe_id:
            continue
        bindings = _indexed(recipe.bindings, "binding_ref")
        for node in recipe.nodes:
            if node.binding_ref is None:
                continue
            binding = bindings[node.binding_ref]
            policy = selected_policies.get(binding.policy_id)
            route_id = None if policy is None else policy.route_id
            route = None if route_id is None else routes.get(route_id)
            reasons: list[str] = []
            if policy is None:
                reasons.append(f"provider selection declares no policy: {binding.policy_id}")
            elif route is None:
                reasons.append("selected route is missing")
            else:
                if route.provider != image_provider:
                    reasons.append(
                        f"selected route provider is {route.provider}, not {image_provider}"
                    )
                if route.product_id != policy.product_id:
                    reasons.append("selected route serves a different product")
                if route.operation != node.operation:
                    reasons.append(
                        f"selected route operation is {route.operation}, not {node.operation}"
                    )
                expected_variant = binding.effective_output_options.get("operation_variant")
                if (
                    isinstance(expected_variant, str)
                    and route.operation_variant != expected_variant
                ):
                    reasons.append(
                        "selected route operation variant is "
                        f"{route.operation_variant}, not {expected_variant}"
                    )
                reasons.extend(_binding_route_failures(binding, route))
            if reasons:
                gaps.append(
                    {
                        "recipe_id": recipe.recipe_id,
                        "node_id": node.node_id,
                        "route_id": route_id,
                        "reasons": reasons,
                    }
                )
    return gaps


def _canary_classes(
    route_deltas: Sequence[Mapping[str, object]],
    recipe_deltas: Sequence[Mapping[str, object]],
    current_recipes: Mapping[str, ModelPolicyRecipeSnapshotV1],
) -> list[str]:
    classes: set[str] = set()
    output_material_fields = {
        "product_id",
        "operation",
        "operation_variant",
        "modality_spec_version",
        "provider",
        "model",
        "surface",
        "endpoint",
        "adapter_id",
        "adapter_behavior_version",
        "features",
        "limits",
        "exact_size_constraints",
        "behavior_fingerprint",
        "contract_fingerprint",
    }
    changed_route_ids = {
        str(delta["route_id"])
        for delta in route_deltas
        if delta.get("change") != "changed"
        or bool(output_material_fields & set(cast(Sequence[str], delta.get("changed_fields", ()))))
    }
    behavior_fields = {
        "provider",
        "model",
        "surface",
        "endpoint",
        "adapter_id",
        "adapter_behavior_version",
        "behavior_fingerprint",
    }
    if any(
        delta.get("change") != "changed"
        or bool(behavior_fields & set(cast(Sequence[str], delta.get("changed_fields", ()))))
        for delta in route_deltas
    ):
        classes.add("route_endpoint_smoke")
    if any(
        "exact_size_constraints" in cast(Sequence[object], delta.get("changed_fields", ()))
        for delta in route_deltas
    ):
        classes.add("exact_size_constraint_boundary")
    for delta in recipe_deltas:
        recipe = current_recipes.get(str(delta["recipe_id"]))
        if recipe is None:
            continue
        bindings = _indexed(recipe.bindings, "binding_ref")
        direct = set(cast(Sequence[str], delta.get("direct_nodes", ())))
        opaque_count = 0
        exact_areas: list[int] = []
        for node in recipe.nodes:
            binding = None if node.binding_ref is None else bindings.get(node.binding_ref)
            if binding is None:
                continue
            if node.node_id not in direct and binding.route_id not in changed_route_ids:
                continue
            options = binding.effective_output_options
            background = options.get("background")
            variant = options.get("operation_variant")
            if background == "transparent" and variant == "generation":
                classes.add("transparent_generation")
            if background == "transparent" and variant == "edit":
                classes.add("transparent_reference_edit")
            if options.get("mask_present") is True:
                classes.add("masked_edit_seam")
            if background == "opaque":
                opaque_count += 1
                classes.add("opaque_output")
            if binding.required_exact_size is not None:
                exact_areas.append(
                    binding.required_exact_size["width"] * binding.required_exact_size["height"]
                )
        if opaque_count >= 10:
            classes.add("opaque_high_fanout_canvas")
        if exact_areas:
            classes.add("constraint_heavy_atlas_or_cutout")
            classes.add("largest_active_canvas")
    return sorted(classes)


def _same_spec_policy_switches(
    base: ModelPolicySnapshotV1,
    current: ModelPolicySnapshotV1,
    policy_deltas: Sequence[Mapping[str, object]],
) -> bool:
    before_policies = {policy.key: policy for policy in base.policies}
    after_policies = {policy.key: policy for policy in current.policies}
    before_routes = _indexed(base.routes, "route_id")
    after_routes = _indexed(current.routes, "route_id")
    for delta in policy_deltas:
        if delta.get("change") != "changed":
            return False
        key = str(delta["policy"])
        before_policy = before_policies[key]
        after_policy = after_policies[key]
        before_route = before_routes.get(before_policy.route_id)
        after_route = after_routes.get(after_policy.route_id)
        if before_route is None or after_route is None:
            return False
        if (
            before_route.product_id,
            before_route.operation,
            before_route.operation_variant,
            before_route.modality_spec_version,
        ) != (
            after_route.product_id,
            after_route.operation,
            after_route.operation_variant,
            after_route.modality_spec_version,
        ):
            return False
    return True


def _same_spec_direct_bindings(
    base: ModelPolicySnapshotV1,
    current: ModelPolicySnapshotV1,
    recipe_deltas: Sequence[Mapping[str, object]],
) -> bool:
    before_recipes = _indexed(base.recipes, "recipe_id")
    after_recipes = _indexed(current.recipes, "recipe_id")
    before_routes = _indexed(base.routes, "route_id")
    after_routes = _indexed(current.routes, "route_id")
    for delta in recipe_deltas:
        if delta.get("change") != "changed":
            continue
        recipe_id = str(delta["recipe_id"])
        before = before_recipes[recipe_id]
        after = after_recipes[recipe_id]
        before_nodes = _indexed(before.nodes, "node_id")
        after_nodes = _indexed(after.nodes, "node_id")
        before_bindings = _indexed(before.bindings, "binding_ref")
        after_bindings = _indexed(after.bindings, "binding_ref")
        for node_id in cast(Sequence[str], delta.get("direct_nodes", ())):
            before_ref = before_nodes[node_id].binding_ref
            after_ref = after_nodes[node_id].binding_ref
            if before_ref is None or after_ref is None:
                return False
            before_route = before_routes[before_bindings[before_ref].route_id]
            after_route = after_routes[after_bindings[after_ref].route_id]
            if (
                before_route.product_id,
                before_route.operation,
                before_route.operation_variant,
                before_route.modality_spec_version,
            ) != (
                after_route.product_id,
                after_route.operation,
                after_route.operation_variant,
                after_route.modality_spec_version,
            ):
                return False
    return True


def diff_model_policy_snapshots(
    base: ModelPolicySnapshotV1,
    current: ModelPolicySnapshotV1,
    *,
    recipe_id: str | None = None,
    repository_root: Path | None = None,
    additional_capability_gaps: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Compare policy snapshots and classify structural and cache blast radius."""

    before_recipes = _indexed(base.recipes, "recipe_id")
    after_recipes = _indexed(current.recipes, "recipe_id")
    available = sorted(set(before_recipes) | set(after_recipes))
    if recipe_id is not None and recipe_id not in available:
        raise ValueError(
            f"unknown model-policy recipe {recipe_id!r}; available: {', '.join(available)}"
        )
    selected_ids = [recipe_id] if recipe_id is not None else available
    recipe_deltas: list[dict[str, object]] = []
    option_changes: list[dict[str, object]] = []
    for selected in selected_ids:
        before = before_recipes.get(selected)
        after = after_recipes.get(selected)
        if before is None:
            recipe_deltas.append({"recipe_id": selected, "change": "added"})
            continue
        if after is None:
            recipe_deltas.append({"recipe_id": selected, "change": "removed"})
            continue
        before_nodes = _indexed(before.nodes, "node_id")
        after_nodes = _indexed(after.nodes, "node_id")
        before_bindings = _indexed(before.bindings, "binding_ref")
        after_bindings = _indexed(after.bindings, "binding_ref")
        added_nodes = sorted(set(after_nodes) - set(before_nodes))
        removed_nodes = sorted(set(before_nodes) - set(after_nodes))
        structurally_changed = sorted(
            node_id
            for node_id in set(before_nodes) & set(after_nodes)
            if before_nodes[node_id].structural_fingerprint
            != after_nodes[node_id].structural_fingerprint
        )
        consumer_structure_changed = sorted(
            node_id
            for node_id in set(before_nodes) & set(after_nodes)
            if before_nodes[node_id].consumer_structure_fingerprint
            != after_nodes[node_id].consumer_structure_fingerprint
        )
        route_resource_only_nodes = sorted(
            set(structurally_changed) - set(consumer_structure_changed)
        )
        direct_nodes = sorted(
            node_id
            for node_id in set(before_nodes) & set(after_nodes)
            if before_nodes[node_id].binding_ref != after_nodes[node_id].binding_ref
            and (
                before_nodes[node_id].binding_ref is not None
                or after_nodes[node_id].binding_ref is not None
            )
        )
        content_identity_changes = sorted(
            node_id
            for node_id in set(before_nodes) & set(after_nodes)
            if before_nodes[node_id].cache_key != after_nodes[node_id].cache_key
        )
        content_identity_deltas = [
            {
                "node_id": node_id,
                "base_cache_key": before_nodes[node_id].cache_key,
                "current_cache_key": after_nodes[node_id].cache_key,
            }
            for node_id in content_identity_changes
        ]
        downstream_cache_rekeys = sorted(
            set(_descendants(set(direct_nodes), before_nodes, after_nodes))
            & set(content_identity_changes)
        )
        for node_id in direct_nodes:
            before_ref = before_nodes[node_id].binding_ref
            after_ref = after_nodes[node_id].binding_ref
            before_options = (
                {} if before_ref is None else before_bindings[before_ref].effective_output_options
            )
            after_options = (
                {} if after_ref is None else after_bindings[after_ref].effective_output_options
            )
            option_changes.extend(
                _option_changes(
                    selected,
                    node_id,
                    before_options,
                    after_options,
                )
            )
        operation_delta = _map_delta(before.operation_counts, after.operation_counts)
        cost_delta = {
            "low_usd": round(after.estimated_cost_low_usd - before.estimated_cost_low_usd, 6),
            "high_usd": round(after.estimated_cost_high_usd - before.estimated_cost_high_usd, 6),
        }
        resources_changed = before.resources != after.resources
        resource_deltas = _resource_deltas(before.resources, after.resources)
        if (
            added_nodes
            or removed_nodes
            or structurally_changed
            or direct_nodes
            or content_identity_changes
            or operation_delta
            or any(cost_delta.values())
            or resources_changed
            or before.graph_sha256 != after.graph_sha256
        ):
            recipe_deltas.append(
                {
                    "recipe_id": selected,
                    "change": "changed",
                    "direct_nodes": direct_nodes,
                    "downstream_cache_rekeys": downstream_cache_rekeys,
                    "content_identity_changes": content_identity_changes,
                    "content_identity_deltas": content_identity_deltas,
                    "structural": {
                        "topology_changed": before.topology_sha256 != after.topology_sha256,
                        "base_topology_sha256": before.topology_sha256,
                        "current_topology_sha256": after.topology_sha256,
                        "resources_changed": resources_changed,
                        "resource_deltas": resource_deltas,
                        "nodes_added": added_nodes,
                        "nodes_removed": removed_nodes,
                        "nodes_changed": structurally_changed,
                        "consumer_nodes_changed": consumer_structure_changed,
                        "route_resource_only_nodes": route_resource_only_nodes,
                    },
                    "operation_count_deltas": operation_delta,
                    "cost_deltas": cost_delta,
                }
            )

    route_deltas = _route_deltas(base, current)
    policy_deltas = _policy_deltas(base, current)
    selected_current = [
        recipe for recipe in current.recipes if recipe_id is None or recipe.recipe_id == recipe_id
    ]
    gaps = _capability_gaps(current, selected_current)
    seen_gaps = {_canonical_bytes(gap) for gap in gaps}
    for additional in additional_capability_gaps:
        if recipe_id is not None and additional.get("recipe_id") != recipe_id:
            continue
        gap = dict(additional)
        encoded = _canonical_bytes(gap)
        if encoded not in seen_gaps:
            seen_gaps.add(encoded)
            gaps.append(gap)
    gaps.sort(
        key=lambda gap: (
            str(gap.get("recipe_id", "")),
            str(gap.get("node_id", "")),
            str(gap.get("route_id", "")),
        )
    )
    consumer_structure_changes = False
    for delta in recipe_deltas:
        if delta.get("change") != "changed":
            consumer_structure_changes = True
            break
        structural = cast(Mapping[str, object], delta.get("structural", {}))
        if any(
            bool(structural.get(key))
            for key in ("nodes_added", "nodes_removed", "consumer_nodes_changed")
        ):
            consumer_structure_changes = True
            break
    has_direct_binding_change = any(
        delta.get("change") == "changed" and bool(delta.get("direct_nodes"))
        for delta in recipe_deltas
    )
    same_spec_route_change = bool(
        route_deltas or policy_deltas or has_direct_binding_change
    ) and all(
        (
            not consumer_structure_changes,
            not gaps,
            not policy_deltas or _same_spec_policy_switches(base, current, policy_deltas),
            _same_spec_direct_bindings(base, current, recipe_deltas),
        )
    )
    report: dict[str, object] = {
        "schema_version": 1,
        "kind": MODEL_POLICY_DIFF_KIND,
        "recipe_filter": recipe_id,
        "route_deltas": route_deltas,
        "policy_deltas": policy_deltas,
        "capability_gaps": gaps,
        "effective_option_deltas": option_changes,
        "recipe_deltas": recipe_deltas,
        "required_live_canary_classes": _canary_classes(route_deltas, recipe_deltas, after_recipes),
        "consumer_source_changes": {
            "catalog_or_policy_only": same_spec_route_change,
            "same_spec_route_change": same_spec_route_change,
            "recipes": False if same_spec_route_change else None,
            "components": False if same_spec_route_change else None,
            "modalities": False if same_spec_route_change else None,
            "orchestration_factories": False if same_spec_route_change else None,
        },
        "stale_generated_files": stale_generated_files(current, repository_root=repository_root),
    }
    report["has_changes"] = any(
        report[key]
        for key in (
            "route_deltas",
            "policy_deltas",
            "capability_gaps",
            "effective_option_deltas",
            "recipe_deltas",
            "stale_generated_files",
        )
    )
    return report


__all__ = [
    "ACTIVE_MODEL_POLICY_SNAPSHOT",
    "GeneratedModelPolicyFileSnapshotV1",
    "MODEL_POLICY_DIFF_KIND",
    "MODEL_POLICY_SNAPSHOT_KIND",
    "ModelPolicyNodeSnapshotV1",
    "ModelPolicyRecipeSnapshotV1",
    "ModelPolicyResourceSnapshotV1",
    "ModelPolicySelectionSnapshotV1",
    "ModelPolicySnapshotV1",
    "ModelRouteSnapshotV1",
    "build_model_policy_snapshot",
    "diff_model_policy_snapshots",
    "find_model_policy_repository_root",
    "image_provider_capability_gaps",
    "load_active_model_policy_snapshot",
    "load_model_policy_snapshot",
    "model_route_report",
    "policy_snapshots",
    "recipe_snapshot",
    "render_model_policy_snapshot",
    "route_snapshots",
    "stale_generated_files",
]
