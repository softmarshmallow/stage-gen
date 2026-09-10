"""Asset-graph topology: typed nodes, declared resources, and content identity."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol, Self, cast
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from gnode.contracts.artifacts import SHA256_PATTERN, PersistedContractModel
from gnode.reliability import atomic_write_json
from gnode.route_constraints import ExactSize2DV1, ExactSizeConstraints2DV1

if TYPE_CHECKING:
    from gnode.routes import ResolvedBindingV1

NODE_ID_PATTERN = r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$"
OPERATION_PATTERN = r"^[a-z0-9]+(?:_[a-z0-9]+)*$"
#: Persisted type identifier: a taxonomy path with an optional ``.step`` suffix,
#: e.g. ``2d/sideview/platformer/map_layer.generate``. Never a module path.
TYPE_ID_PATTERN = r"^[a-z0-9_]+(?:/[a-z0-9_]+)*(?:\.[a-z0-9_]+)?$"
PORT_ID_PATTERN = r"^[a-z0-9]+(?:_[a-z0-9]+)*$"
PAYLOAD_KIND_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
LOCAL_OPERATION = "local"
_ROUTE_IDENTIFIER_PATTERN = r"^[a-z0-9]+(?:[._/-][a-z0-9]+)*$"
_PROVIDER_PATTERN = r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$"
_MODEL_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._/-]*$"
_OPTION_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_SENSITIVE_OPTION_KEY_PATTERN = re.compile(
    r"(?:^|_)(?:api_key|authorization|auth|bearer|credential|credentials|headers?|"
    r"password|secret|token)(?:_|$)",
    re.IGNORECASE,
)


def _route_fingerprint(kind: str, value: Mapping[str, object]) -> str:
    """Hash a canonical route payload without changing legacy graph hashing."""

    encoded = json.dumps(
        {"kind": kind, **value},
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_route_options(value: object, *, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must contain only finite JSON numbers")
        return
    if isinstance(value, list):
        for index, nested in enumerate(value):
            _validate_route_options(nested, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str) or not _OPTION_NAME_PATTERN.fullmatch(key):
                raise ValueError(f"{path} keys must use lower_snake_case")
            if _SENSITIVE_OPTION_KEY_PATTERN.search(key):
                raise ValueError(f"{path} must not contain credential-bearing keys")
            _validate_route_options(nested, path=f"{path}.{key}")
        return
    raise ValueError(f"{path} must contain only canonical JSON values")


def _validate_route_endpoint(value: str) -> str:
    if not value.strip() or value != value.strip():
        raise ValueError("route endpoint must be a non-empty trimmed string")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("route endpoint must be a non-secret HTTP(S) endpoint")
    if not parsed.netloc or parsed.username is not None or parsed.password is not None:
        raise ValueError("route endpoint must be a non-secret HTTP(S) endpoint")
    if parsed.query or parsed.fragment:
        raise ValueError("route endpoint must not contain a query or fragment")
    return value


class RetryOwner(StrEnum):
    NONE = "none"
    COMPONENT = "component"


class CacheDisposition(StrEnum):
    HIT = "hit"
    MISS = "miss"
    BYPASS = "bypass"


class NodeStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class Resource(PersistedContractModel):
    resource_id: str = Field(pattern=NODE_ID_PATTERN, max_length=96)
    max_in_flight: int | None = Field(default=None, ge=1, le=1_024)
    requests_per_minute: int | None = Field(default=None, ge=1)
    rate_limit_owner: Literal["scheduler", "provider_adapter", "none"]

    @model_validator(mode="after")
    def validate_rate_owner(self) -> Resource:
        if self.requests_per_minute is None and self.rate_limit_owner != "none":
            raise ValueError("rate-limited resources require requests_per_minute")
        if self.requests_per_minute is not None and self.rate_limit_owner == "none":
            raise ValueError("requests_per_minute requires a rate-limit owner")
        return self


class ResolvedRouteSnapshotV1(PersistedContractModel):
    """Strict plan-time record of one exact, capability-admitted provider route.

    The snapshot is deliberately free of prices, pacing, credentials, and
    verification evidence. Those facts may govern scheduling or display, but
    they neither describe material output behavior nor belong in portable plan
    provenance.
    """

    schema_version: Literal[1] = 1
    binding_ref: str = Field(pattern=SHA256_PATTERN)
    policy_id: str = Field(pattern=_ROUTE_IDENTIFIER_PATTERN, max_length=192)
    policy_version: str = Field(min_length=1, max_length=96)
    product_id: str = Field(pattern=_ROUTE_IDENTIFIER_PATTERN, max_length=192)
    route_id: str = Field(pattern=_ROUTE_IDENTIFIER_PATTERN, max_length=192)
    route_contract_fingerprint: str = Field(pattern=SHA256_PATTERN)
    behavior_fingerprint: str = Field(pattern=SHA256_PATTERN)
    output_fingerprint: str = Field(pattern=SHA256_PATTERN)
    operation: str = Field(pattern=OPERATION_PATTERN, max_length=64)
    operation_variant: str = Field(pattern=_ROUTE_IDENTIFIER_PATTERN, max_length=96)
    modality_spec_version: str = Field(min_length=1, max_length=96)
    provider: str = Field(pattern=_PROVIDER_PATTERN, max_length=96)
    model: str = Field(pattern=_MODEL_PATTERN, max_length=192)
    surface: str = Field(pattern=_ROUTE_IDENTIFIER_PATTERN, max_length=96)
    endpoint: str = Field(min_length=1, max_length=2_048)
    adapter_id: str = Field(pattern=_ROUTE_IDENTIFIER_PATTERN, max_length=192)
    adapter_behavior_version: str = Field(min_length=1, max_length=96)
    resource_id: str = Field(pattern=NODE_ID_PATTERN, max_length=96)
    supported_features: tuple[str, ...] = ()
    supported_limits: tuple[tuple[str, float], ...] = ()
    supported_exact_size_constraints: ExactSizeConstraints2DV1 | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    required_features: tuple[str, ...] = ()
    required_limits: tuple[tuple[str, float], ...] = ()
    required_exact_size: ExactSize2DV1 | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    effective_output_options: dict[str, object] = Field(default_factory=dict)

    @field_validator(
        "policy_version",
        "modality_spec_version",
        "adapter_behavior_version",
    )
    @classmethod
    def validate_trimmed_versions(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("route versions must be trimmed strings")
        return value

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        return _validate_route_endpoint(value)

    @field_validator("supported_features", "required_features")
    @classmethod
    def validate_features(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for feature in value:
            if not _OPTION_NAME_PATTERN.fullmatch(feature):
                raise ValueError("route features must use lower_snake_case")
        if value != tuple(sorted(set(value))):
            raise ValueError("route features must be unique and sorted")
        return value

    @field_validator("supported_limits", "required_limits")
    @classmethod
    def validate_limits(cls, value: tuple[tuple[str, float], ...]) -> tuple[tuple[str, float], ...]:
        names = tuple(name for name, _ in value)
        if names != tuple(sorted(set(names))):
            raise ValueError("route limits must be unique and sorted by name")
        for name, limit in value:
            if not _OPTION_NAME_PATTERN.fullmatch(name):
                raise ValueError("route limit names must use lower_snake_case")
            if isinstance(limit, bool) or not math.isfinite(limit) or limit <= 0:
                raise ValueError("route limits must be positive finite numbers")
        return value

    @field_validator("effective_output_options")
    @classmethod
    def validate_output_options(cls, value: dict[str, object]) -> dict[str, object]:
        _validate_route_options(value, path="effective_output_options")
        return value

    @classmethod
    def create(
        cls,
        *,
        policy_id: str,
        policy_version: str,
        product_id: str,
        route_id: str,
        route_contract_fingerprint: str,
        behavior_fingerprint: str,
        output_fingerprint: str,
        operation: str,
        operation_variant: str,
        modality_spec_version: str,
        provider: str,
        model: str,
        surface: str,
        endpoint: str,
        adapter_id: str,
        adapter_behavior_version: str,
        resource_id: str,
        supported_features: tuple[str, ...],
        supported_limits: tuple[tuple[str, float], ...],
        required_features: tuple[str, ...],
        required_limits: tuple[tuple[str, float], ...],
        effective_output_options: dict[str, object],
        supported_exact_size_constraints: ExactSizeConstraints2DV1 | None = None,
        required_exact_size: ExactSize2DV1 | None = None,
    ) -> Self:
        """Seal a validated snapshot and derive its exact plan reference."""

        payload: dict[str, object] = {
            "schema_version": 1,
            "policy_id": policy_id,
            "policy_version": policy_version,
            "product_id": product_id,
            "route_id": route_id,
            "route_contract_fingerprint": route_contract_fingerprint,
            "behavior_fingerprint": behavior_fingerprint,
            "output_fingerprint": output_fingerprint,
            "operation": operation,
            "operation_variant": operation_variant,
            "modality_spec_version": modality_spec_version,
            "provider": provider,
            "model": model,
            "surface": surface,
            "endpoint": endpoint,
            "adapter_id": adapter_id,
            "adapter_behavior_version": adapter_behavior_version,
            "resource_id": resource_id,
            "supported_features": supported_features,
            "supported_limits": supported_limits,
            "required_features": required_features,
            "required_limits": required_limits,
            "effective_output_options": effective_output_options,
        }
        if supported_exact_size_constraints is not None:
            payload["supported_exact_size_constraints"] = (
                supported_exact_size_constraints.model_dump(mode="python")
            )
        if required_exact_size is not None:
            payload["required_exact_size"] = required_exact_size.model_dump(mode="python")
        binding_ref = _route_fingerprint("gnode-resolved-route-snapshot-ref-v1", payload)
        return cls.model_validate({"binding_ref": binding_ref, **payload})

    def expected_binding_ref(self) -> str:
        payload = self.model_dump(mode="json", exclude={"binding_ref"})
        return _route_fingerprint("gnode-resolved-route-snapshot-ref-v1", payload)

    def to_resolved_binding(self) -> ResolvedBindingV1:
        """Rehydrate dispatch identity, using neutral values for omitted operations data."""

        from gnode.binding import ModelRef
        from gnode.routes import (
            ResolvedBindingV1,
            RouteContractV1,
            WorkloadPolicyV1,
            WorkloadRequestV1,
        )

        route = RouteContractV1(
            route_id=self.route_id,
            product_id=self.product_id,
            operation=self.operation,
            operation_variant=self.operation_variant,
            model=ModelRef(model=self.model, provider=self.provider),
            modality_spec_version=self.modality_spec_version,
            surface=self.surface,
            endpoint=self.endpoint,
            adapter_id=self.adapter_id,
            adapter_behavior_version=self.adapter_behavior_version,
            features=frozenset(self.supported_features),
            limits=self.supported_limits,
            exact_size_constraints=self.supported_exact_size_constraints,
            resource_id=self.resource_id,
            estimated_duration_seconds=0.0,
            estimated_cost_low_usd=0.0,
            estimated_cost_high_usd=0.0,
        )
        request = WorkloadRequestV1(
            policy_id=self.policy_id,
            operation=self.operation,
            modality_spec_version=self.modality_spec_version,
            required_features=frozenset(self.required_features),
            required_limits=self.required_limits,
            exact_size=self.required_exact_size,
            output_options=self.effective_output_options,
        )
        policy = WorkloadPolicyV1(
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            product_id=self.product_id,
            route_id=self.route_id,
        )
        resolved = ResolvedBindingV1(route=route, request=request, policy=policy)
        if resolved.to_snapshot() != self:
            raise ValueError("resolved route snapshot cannot reproduce its exact binding")
        return resolved

    def assert_integrity(self) -> None:
        """Refuse any internally inconsistent or tampered snapshot fields."""

        missing_features = sorted(set(self.required_features) - set(self.supported_features))
        if missing_features:
            raise ValueError(
                "resolved route snapshot requires unsupported features: "
                + ", ".join(missing_features)
            )
        supported_limits = dict(self.supported_limits)
        for name, requested in self.required_limits:
            ceiling = supported_limits.get(name)
            if ceiling is None:
                raise ValueError(f"resolved route snapshot requires undeclared limit {name}")
            if requested > ceiling:
                raise ValueError(
                    f"resolved route snapshot requires {name} {requested:g} above "
                    f"supported {ceiling:g}"
                )
        if self.required_exact_size is not None:
            if self.supported_exact_size_constraints is None:
                raise ValueError(
                    "resolved route snapshot requires undeclared exact size constraints"
                )
            size_failures = self.supported_exact_size_constraints.failures(self.required_exact_size)
            if size_failures:
                raise ValueError(
                    "resolved route snapshot requires unsupported exact size: "
                    + "; ".join(size_failures)
                )

        expected_behavior = _route_fingerprint(
            "gnode-route-behavior-v1",
            {
                "operation": self.operation,
                "operation_variant": self.operation_variant,
                "modality_spec_version": self.modality_spec_version,
                "model": {"model": self.model, "provider": self.provider},
                "surface": self.surface,
                "endpoint": self.endpoint,
                "adapter_id": self.adapter_id,
                "adapter_behavior_version": self.adapter_behavior_version,
            },
        )
        if self.behavior_fingerprint != expected_behavior:
            raise ValueError("resolved route snapshot behavior fingerprint is stale")

        contract_payload: dict[str, object] = {
            "behavior_fingerprint": self.behavior_fingerprint,
            "features": list(self.supported_features),
            "limits": [list(limit) for limit in self.supported_limits],
        }
        if self.supported_exact_size_constraints is not None:
            contract_payload["exact_size_constraints"] = (
                self.supported_exact_size_constraints.model_dump(mode="json")
            )
        expected_contract = _route_fingerprint("gnode-route-contract-v1", contract_payload)
        if self.route_contract_fingerprint != expected_contract:
            raise ValueError("resolved route snapshot contract fingerprint is stale")

        expected_output = _route_fingerprint(
            "gnode-route-output-v1",
            {
                "behavior_fingerprint": self.behavior_fingerprint,
                "output_options": self.effective_output_options,
            },
        )
        if self.output_fingerprint != expected_output:
            raise ValueError("resolved route snapshot output fingerprint is stale")
        if self.binding_ref != self.expected_binding_ref():
            raise ValueError("resolved route snapshot binding_ref is stale")

    @model_validator(mode="after")
    def validate_integrity(self) -> ResolvedRouteSnapshotV1:
        self.assert_integrity()
        return self


class Port(PersistedContractModel):
    """One declared output: an artifact address plus the typed record it carries.

    ``kind`` names the payload contract (an application-owned persisted
    vocabulary such as ``map-terrain-v1``); ``sidecar_ref`` keeps the
    provenance sidecar visibly paired with its artifact instead of appearing
    as a second undifferentiated output.
    """

    port_id: str = Field(pattern=PORT_ID_PATTERN, max_length=64)
    artifact_ref: str = Field(min_length=1, max_length=512)
    kind: str = Field(pattern=PAYLOAD_KIND_PATTERN, max_length=96)
    sidecar_ref: str | None = Field(default=None, max_length=512)


class PortRef(PersistedContractModel):
    """An edge endpoint: one named port on one node."""

    node_id: str = Field(pattern=NODE_ID_PATTERN, max_length=192)
    port_id: str = Field(pattern=PORT_ID_PATTERN, max_length=64)


class AuthoredInput(PersistedContractModel):
    """One input a node consumes that no upstream node produced.

    An authored input comes from the package the run was asked to build — a
    reference image, a template, a document the author put there. It carries
    the digest that binds it, so the plan states which exact bytes the node
    will be handed instead of leaving them implicit in an opaque cache key.
    """

    label: str = Field(pattern=NODE_ID_PATTERN, max_length=96)
    ref: str = Field(min_length=1, max_length=512)
    sha256: str = Field(pattern=SHA256_PATTERN)


class NodeCard(PersistedContractModel):
    """The definition a renderer shows for a node: what it is told, statically.

    ``prompt`` is the instruction text as known at plan time; ``template_ref``
    names a packaged template resource when composition is runtime-bound;
    ``reference_inputs`` point at the derived inputs (upstream ports) the node
    consumes at run time; ``authored_inputs`` name the package members it is
    handed that nothing upstream produced. A reader sees the static, derived,
    and authored halves of the definition side by side without reading handler
    code — an input that reaches a provider is never invisible in the plan.
    """

    prompt: str | None = Field(default=None, min_length=1, max_length=20_000)
    template_ref: str | None = Field(default=None, max_length=192)
    schema_name: str | None = Field(default=None, max_length=96)
    reference_inputs: tuple[PortRef, ...] = ()
    authored_inputs: tuple[AuthoredInput, ...] = ()


class Node(PersistedContractModel):
    """A planned operation instance with dependencies, route, and output ports.

    Construction validates fields; ``Graph`` validates references and DAG structure.
    ``NodeHandler`` supplies execution and artifact acceptance. Input digests and
    the cache key describe identity, not proof of valid reusable files.
    """

    node_id: str = Field(pattern=NODE_ID_PATTERN, max_length=192)
    type_id: str = Field(pattern=TYPE_ID_PATTERN, max_length=192)
    domain: str = Field(pattern=NODE_ID_PATTERN, max_length=96)
    description: str = Field(min_length=1, max_length=512)
    params: dict[str, str] = Field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    #: The subset of ``depends_on`` that orders execution without contributing
    #: cache lineage — a barrier edge, rendered distinctly from lineage.
    barrier_only: tuple[str, ...] = ()
    operation: str = Field(pattern=OPERATION_PATTERN, max_length=64)
    resource_id: str = Field(pattern=NODE_ID_PATTERN, max_length=96)
    provider: str | None = Field(default=None, max_length=96)
    model: str | None = Field(default=None, max_length=192)
    binding_ref: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
        exclude_if=lambda value: value is None,
    )
    retry_owner: RetryOwner
    max_attempts: int = Field(ge=1, le=6)
    input_sha256: tuple[str, ...] = ()
    cache_key: str = Field(pattern=SHA256_PATTERN)
    ports: tuple[Port, ...] = ()
    card: NodeCard | None = None
    #: Which subgraph template instance emitted this node, when one did.
    template_id: str | None = Field(default=None, max_length=192)
    estimated_duration_seconds: float = Field(ge=0.0)
    estimated_cost_low_usd: float = Field(ge=0.0)
    estimated_cost_high_usd: float = Field(ge=0.0)

    @field_validator("depends_on")
    @classmethod
    def validate_dependencies(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("execution node dependencies must be unique")
        return value

    @field_validator("ports")
    @classmethod
    def validate_ports(cls, value: tuple[Port, ...]) -> tuple[Port, ...]:
        port_ids = [port.port_id for port in value]
        if len(port_ids) != len(set(port_ids)):
            raise ValueError("execution node ports must be unique")
        refs = [port.artifact_ref for port in value] + [
            port.sidecar_ref for port in value if port.sidecar_ref is not None
        ]
        if len(refs) != len(set(refs)):
            raise ValueError("execution node port artifact refs must be unique")
        return value

    def port(self, port_id: str) -> Port:
        for port in self.ports:
            if port.port_id == port_id:
                return port
        raise KeyError(f"{self.node_id} declares no port {port_id}")

    def declared_artifact_refs(self) -> set[str]:
        refs = {port.artifact_ref for port in self.ports}
        refs.update(port.sidecar_ref for port in self.ports if port.sidecar_ref is not None)
        return refs

    @field_validator("input_sha256")
    @classmethod
    def validate_input_digests(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("execution node input digests must be unique")
        for digest in value:
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError("execution node input digests must be SHA-256 values")
        return value

    @property
    def is_local(self) -> bool:
        """A node is local when its operation runs without a provider route."""

        return self.operation == LOCAL_OPERATION

    @model_validator(mode="after")
    def validate_operation_ownership(self) -> Node:
        stray = sorted(set(self.barrier_only) - set(self.depends_on))
        if stray:
            raise ValueError(
                "execution node barrier edges must be declared dependencies: " + ", ".join(stray)
            )
        if len(self.barrier_only) != len(set(self.barrier_only)):
            raise ValueError("execution node barrier edges must be unique")
        if self.is_local:
            if self.provider is not None or self.model is not None:
                raise ValueError("local execution nodes must not declare provider models")
            if self.binding_ref is not None:
                raise ValueError("local execution nodes must not declare provider bindings")
            if self.retry_owner is not RetryOwner.NONE or self.max_attempts != 1:
                raise ValueError("local execution nodes must not own provider retries")
        else:
            if not self.provider or not self.model:
                raise ValueError("provider execution nodes require provider and model")
            if self.retry_owner is not RetryOwner.COMPONENT:
                raise ValueError("provider retries must be owned by the component")
        if self.estimated_cost_high_usd < self.estimated_cost_low_usd:
            raise ValueError("estimated high cost must not be below estimated low cost")
        return self


class Graph(PersistedContractModel):
    """One sealed asset graph.

    A consumer subclasses this to add its own header fields and to pin ``kind``;
    everything below the header is the engine's. The document kinds stamped on
    derived records are class attributes so a consumer keeps its own vocabulary
    without the engine knowing anything about it.
    """

    TRACE_SCHEMA_VERSION: ClassVar[int] = 1
    TRACE_EVENT_KIND: ClassVar[str] = "gnode-node-event-v1"
    RUN_SUMMARY_KIND: ClassVar[str] = "gnode-run-summary-v1"
    PROJECTION_KIND: ClassVar[str] = "gnode-projection-v1"
    VIEW_KIND: ClassVar[str] = "gnode-run-view-v1"
    VIEW_SCHEMA_VERSION: ClassVar[int] = 3

    schema_version: int = Field(ge=1)
    kind: str = Field(min_length=1, max_length=96)
    resources: tuple[Resource, ...]
    resolved_routes: tuple[ResolvedRouteSnapshotV1, ...] = Field(
        default=(),
        exclude_if=lambda value: not value,
    )
    nodes: tuple[Node, ...]
    terminal_node_id: str
    topology_sha256: str = Field(pattern=SHA256_PATTERN)
    graph_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_graph(self) -> Graph:
        binding_refs = [snapshot.binding_ref for snapshot in self.resolved_routes]
        if len(binding_refs) != len(set(binding_refs)):
            raise ValueError("execution graph resolved routes must be unique")
        for snapshot in self.resolved_routes:
            snapshot.assert_integrity()
        routes_by_ref = {snapshot.binding_ref: snapshot for snapshot in self.resolved_routes}

        resource_ids = [resource.resource_id for resource in self.resources]
        if len(resource_ids) != len(set(resource_ids)):
            raise ValueError("execution graph resources must be unique")
        node_ids = [node.node_id for node in self.nodes]
        if not node_ids or len(node_ids) != len(set(node_ids)):
            raise ValueError("execution graph nodes must be non-empty and unique")
        known = set(node_ids)
        if self.terminal_node_id not in known:
            raise ValueError("execution graph terminal node is undeclared")
        for node in self.nodes:
            if node.node_id in node.depends_on:
                raise ValueError("execution graph nodes must not depend on themselves")
            unknown = sorted(set(node.depends_on) - known)
            if unknown:
                raise ValueError(
                    f"execution node {node.node_id} has undeclared dependencies: "
                    + ", ".join(unknown)
                )
            if node.resource_id not in resource_ids:
                raise ValueError(f"execution node {node.node_id} uses an undeclared resource")
            if node.binding_ref is not None:
                resolved_route = routes_by_ref.get(node.binding_ref)
                if resolved_route is None:
                    raise ValueError(
                        f"execution node {node.node_id} references an undeclared binding"
                    )
                mismatches: list[str] = []
                if node.operation != resolved_route.operation:
                    mismatches.append("operation")
                if node.provider != resolved_route.provider:
                    mismatches.append("provider")
                if node.model != resolved_route.model:
                    mismatches.append("model")
                if node.resource_id != resolved_route.resource_id:
                    mismatches.append("resource_id")
                if resolved_route.output_fingerprint not in node.input_sha256:
                    mismatches.append("output_fingerprint")
                if mismatches:
                    raise ValueError(
                        f"execution node {node.node_id} disagrees with binding "
                        f"{node.binding_ref}: " + ", ".join(mismatches)
                    )
        used_binding_refs = {
            node.binding_ref for node in self.nodes if node.binding_ref is not None
        }
        unused_binding_refs = sorted(set(binding_refs) - used_binding_refs)
        if unused_binding_refs:
            raise ValueError(
                "execution graph carries unused resolved routes: " + ", ".join(unused_binding_refs)
            )
        topological_node_ids(self.nodes)
        descendants = dependency_ancestors(self.terminal_node_id, self.nodes)
        orphaned = sorted(known - descendants - {self.terminal_node_id})
        if orphaned:
            raise ValueError(
                "execution graph contains nodes outside terminal closure: " + ", ".join(orphaned)
            )
        if self.topology_sha256 != topology_sha256(self):
            raise ValueError("execution graph topology_sha256 is stale")
        if self.graph_sha256 != graph_sha256_of(self):
            raise ValueError("execution graph graph_sha256 is stale")
        return self

    def node(self, node_id: str) -> Node:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        raise KeyError(node_id)

    def resolved_route(self, binding_ref: str) -> ResolvedRouteSnapshotV1:
        for snapshot in self.resolved_routes:
            if snapshot.binding_ref == binding_ref:
                return snapshot
        raise KeyError(binding_ref)

    def resolved_route_for(self, node: Node | str) -> ResolvedRouteSnapshotV1:
        """Resolve the exact persisted route snapshot carried by one graph node."""

        planned = self.node(node) if isinstance(node, str) else self.node(node.node_id)
        if not isinstance(node, str) and planned != node:
            raise ValueError(f"node {node.node_id} is not the graph's planned node")
        if planned.binding_ref is None:
            raise KeyError(f"node has no resolved route binding: {planned.node_id}")
        return self.resolved_route(planned.binding_ref)

    def identity_header(self) -> dict[str, object]:
        """Header fields that participate in topology identity.

        A consumer overrides this to add its own; the values must be JSON
        scalars so the digest stays stable across processes.
        """

        return {"schema_version": self.schema_version, "kind": self.kind}

    def annotator_key(self) -> str:
        """Which artifact-annotator family this graph's nodes belong to."""

        return self.kind

    def view_header(self) -> dict[str, object]:
        """Consumer header fields copied onto this graph's derived run view."""

        return {}

    def operation_vocabulary(self) -> tuple[str, ...]:
        """Operations reported in counts, including those with no node.

        The default reports exactly what the graph contains. A consumer with a
        closed vocabulary overrides this so a zero count stays visible.
        """

        return tuple(sorted({node.operation for node in self.nodes}))

    def operation_counts(self) -> dict[str, int]:
        return {
            operation: sum(node.operation == operation for node in self.nodes)
            for operation in self.operation_vocabulary()
        }

    def provider_operation_vocabulary(self) -> tuple[str, ...]:
        return tuple(
            operation for operation in self.operation_vocabulary() if operation != LOCAL_OPERATION
        )


def topology_sha256(graph: Graph) -> str:
    identity = {
        **graph.identity_header(),
        "resources": [
            {
                "resource_id": resource.resource_id,
                "max_in_flight": resource.max_in_flight,
                "requests_per_minute": resource.requests_per_minute,
                "rate_limit_owner": resource.rate_limit_owner,
            }
            for resource in graph.resources
        ],
        "nodes": [
            {
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
            for node in graph.nodes
        ],
        "terminal_node_id": graph.terminal_node_id,
    }
    return _sha256_json(identity)


def graph_sha256_of(graph: Graph) -> str:
    value = graph.model_dump(mode="json", exclude={"graph_sha256", "topology_sha256"})
    return _sha256_json(value)


def seal_graph[GraphT: Graph](
    graph_type: type[GraphT],
    *,
    resources: Sequence[Resource],
    nodes: Sequence[Node],
    terminal_node_id: str,
    resolved_routes: Sequence[ResolvedRouteSnapshotV1] = (),
    **header: object,
) -> GraphT:
    """Compute both digests and return one validated graph.

    Topology identity is sealed first so a moved node stays distinguishable
    from a changed input; content identity then covers the whole document.
    """

    payload: dict[str, Any] = {
        "resources": tuple(resources),
        "resolved_routes": tuple(resolved_routes),
        "nodes": tuple(nodes),
        "terminal_node_id": terminal_node_id,
        "topology_sha256": "0" * 64,
        "graph_sha256": "0" * 64,
        **header,
    }
    incomplete = cast(GraphT, graph_type.model_construct(**payload))
    with_topology = incomplete.model_copy(update={"topology_sha256": topology_sha256(incomplete)})
    sealed = with_topology.model_copy(update={"graph_sha256": graph_sha256_of(with_topology)})
    return graph_type.model_validate(sealed.model_dump())


class NodeArtifact(PersistedContractModel):
    artifact_ref: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    bytes: int = Field(ge=0)


@dataclass(frozen=True, slots=True)
class NodeExecutionResult:
    cache: CacheDisposition
    attempts: int
    provider_operations: int
    artifacts: tuple[NodeArtifact, ...] = ()
    known_cost_usd: float | None = None

    def __post_init__(self) -> None:
        if self.attempts < 1 or self.attempts > 6:
            raise ValueError("node execution attempts must be between one and six")
        if self.provider_operations < 0:
            raise ValueError("node provider operation count must be non-negative")
        if self.known_cost_usd is not None and self.known_cost_usd < 0:
            raise ValueError("known node cost must be non-negative")


class NodeExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        attempts: int = 1,
        provider_operations: int = 0,
        known_cost_usd: float | None = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.provider_operations = provider_operations
        self.known_cost_usd = known_cost_usd


@dataclass(frozen=True, slots=True)
class NodeExecutionContext:
    """Run identity and successful direct-dependency results, including barriers."""

    invocation_id: str
    graph_sha256: str
    dependency_results: Mapping[str, NodeExecutionResult]


class NodeHandler(Protocol):
    """Execute a ready node and return only after artifact acceptance and persistence.

    Own cache validation and dispatch to local operations or retry-owning services.
    The scheduler calls at most once per selected node and trusts artifact validation.
    Report attempts, provider operations, and known cost; ``NodeExecutionError``
    preserves those fields on failure. Downstream handlers receive only successful
    dependency results.
    """

    async def __call__(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult: ...


def dependency_ancestors(node_id: str, nodes: Sequence[Node]) -> set[str]:
    dependencies = {node.node_id: set(node.depends_on) for node in nodes}
    ancestors: set[str] = set()
    frontier = list(dependencies[node_id])
    while frontier:
        dependency = frontier.pop()
        if dependency in ancestors:
            continue
        ancestors.add(dependency)
        frontier.extend(dependencies[dependency])
    return ancestors


def node_closure(
    graph: Graph,
    target_node_ids: Sequence[str] | None,
) -> tuple[Node, ...]:
    if target_node_ids is None:
        return graph.nodes
    targets = tuple(dict.fromkeys(target_node_ids))
    if not targets:
        raise ValueError("target_node_ids must not be empty")
    known = {node.node_id for node in graph.nodes}
    unknown = sorted(set(targets) - known)
    if unknown:
        raise ValueError("execution targets are undeclared: " + ", ".join(unknown))
    selected = set(targets)
    for target in targets:
        selected.update(dependency_ancestors(target, graph.nodes))
    return tuple(node for node in graph.nodes if node.node_id in selected)


def topological_node_ids(nodes: Sequence[Node]) -> tuple[str, ...]:
    dependencies = {node.node_id: set(node.depends_on) for node in nodes}
    unresolved = set(dependencies)
    resolved: list[str] = []
    while unresolved:
        resolved_set = set(resolved)
        ready = [
            node.node_id
            for node in nodes
            if node.node_id in unresolved and dependencies[node.node_id] <= resolved_set
        ]
        if not ready:
            raise ValueError("execution graph dependencies contain a cycle")
        resolved.extend(ready)
        unresolved.difference_update(ready)
    return tuple(resolved)


def _sha256_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_node_cache_key(
    *,
    node_id: str,
    type_id: str,
    operation: str,
    provider: str | None,
    model: str | None,
    input_sha256: Sequence[str],
    dependency_cache_keys: Sequence[str],
    contract_version: str,
) -> str:
    return _sha256_json(
        {
            "node_id": node_id,
            "type_id": type_id,
            "operation": str(operation),
            "provider": provider,
            "model": model,
            "input_sha256": sorted(input_sha256),
            "dependency_cache_keys": list(dependency_cache_keys),
            "contract_version": contract_version,
        }
    )


def dependency_port(
    graph: Graph,
    node: Node,
    *,
    kind: str,
    port_id: str | None = None,
    from_node: str | None = None,
) -> tuple[Node, Port]:
    """Resolve one typed input: the upstream port a node consumes.

    This is how a handler locates what an edge carries — by the payload's
    declared ``kind`` (and optionally the producing node or port name) —
    instead of re-deriving a path convention the producer never promised.
    Exactly one dependency port must match.
    """

    candidates: list[tuple[Node, Port]] = []
    for dependency_id in node.depends_on:
        if from_node is not None and dependency_id != from_node:
            continue
        producer = graph.node(dependency_id)
        for port in producer.ports:
            if port.kind != kind:
                continue
            if port_id is not None and port.port_id != port_id:
                continue
            candidates.append((producer, port))
    if not candidates:
        raise KeyError(f"{node.node_id} has no dependency port of kind {kind}")
    if len(candidates) > 1:
        producers = ", ".join(f"{producer.node_id}:{port.port_id}" for producer, port in candidates)
        raise KeyError(f"{node.node_id} has ambiguous dependency ports of kind {kind}: {producers}")
    return candidates[0]


def write_graph(path: Path, graph: Graph) -> None:
    """Persist one sealed graph as this run's plan of record."""

    atomic_write_json(path, graph.model_dump(mode="json"))
