"""Provider-neutral route catalog and deterministic offline resolution.

The catalog describes routes a host application is willing to plan against. It
does not discover providers, inspect credentials, construct adapters, or choose
the cheapest or newest route. A workload policy names one exact route; the
resolver merely proves that route serves the requested product and capability.

Modality-specific code owns the meaning and normalization of output options.
Ring 0 treats those options as canonical JSON values and binds their bytes into
an output fingerprint without interpreting them.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from types import MappingProxyType
from typing import Literal
from urllib.parse import urlsplit

from gnode.binding import Binding, CapabilityError, ModelRef
from gnode.graph import (
    LOCAL_OPERATION,
    NODE_ID_PATTERN,
    ResolvedRouteSnapshotV1,
    Resource,
    _route_fingerprint,
)
from gnode.route_constraints import ExactSize2DV1, ExactSizeConstraints2DV1

_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9]+(?:[._/-][a-z0-9]+)*$")
_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_RESOURCE_PATTERN = re.compile(NODE_ID_PATTERN)


class RouteCatalogError(ValueError):
    """A catalog is internally ambiguous or contains duplicate identities."""


class RouteResolutionError(CapabilityError):
    """An exact workload policy cannot be admitted by the offline catalog."""


def _require_identifier(value: str, label: str) -> str:
    if value != value.strip() or not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase route identifier")
    return value


def _require_name(value: str, label: str) -> str:
    if value != value.strip() or not _NAME_PATTERN.fullmatch(value):
        raise ValueError(f"{label} must be a lower_snake_case name")
    return value


def _require_version(value: str, label: str) -> str:
    if not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")
    return value


def _require_endpoint(value: str) -> str:
    if not value.strip() or value != value.strip():
        raise ValueError("route endpoint must be a non-empty trimmed string")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("route endpoint must be a non-secret HTTP(S) endpoint")
    if (
        not parsed.netloc
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("route endpoint must be a non-secret HTTP(S) endpoint")
    try:
        _ = parsed.port
    except ValueError as error:
        raise ValueError("route endpoint must use a valid network port") from error
    if parsed.query or parsed.fragment:
        raise ValueError("route endpoint must not contain a query or fragment")
    return value


def _require_resource_id(value: str) -> str:
    if value != value.strip() or not _RESOURCE_PATTERN.fullmatch(value):
        raise ValueError("resource_id must be a lowercase graph resource identifier")
    return value


def _validate_limits(
    limits: Sequence[tuple[str, float]], *, label: str
) -> tuple[tuple[str, float], ...]:
    names = [name for name, _ in limits]
    if len(names) != len(set(names)):
        raise ValueError(f"{label} declares each limit at most once")
    normalized: list[tuple[str, float]] = []
    for name, value in limits:
        _require_name(name, f"{label} limit")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{label} limit {name!r} must be a positive finite number")
        numeric = float(value)
        if not math.isfinite(numeric) or numeric <= 0:
            raise ValueError(f"{label} limit {name!r} must be a positive finite number")
        normalized.append((name, numeric))
    return tuple(sorted(normalized))


def _freeze_json(value: object, *, path: str) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must contain only finite JSON numbers")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for raw_key, nested in value.items():
            if not isinstance(raw_key, str):
                raise ValueError(f"{path} keys must be strings")
            key = _require_name(raw_key, f"{path} key")
            normalized[key] = _freeze_json(nested, path=f"{path}.{key}")
        return MappingProxyType(dict(sorted(normalized.items())))
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json(nested, path=f"{path}[{index}]") for index, nested in enumerate(value)
        )
    raise ValueError(f"{path} must contain only canonical JSON values")


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        items: list[tuple[str, object]] = []
        for raw_key, nested in value.items():
            if not isinstance(raw_key, str):
                raise TypeError("canonical JSON mapping keys must be strings")
            items.append((raw_key, nested))
        return {key: _plain_json(nested) for key, nested in sorted(items)}
    if isinstance(value, tuple):
        return [_plain_json(nested) for nested in value]
    return value


def _fingerprint(kind: str, value: Mapping[str, object]) -> str:
    plain = _plain_json(value)
    if not isinstance(plain, dict):
        raise TypeError("fingerprint payload must be a mapping")
    return _route_fingerprint(kind, plain)


def _capability_failures(route: RouteContractV1, request: WorkloadRequestV1) -> tuple[str, ...]:
    failures: list[str] = []
    missing_features = sorted(request.required_features - route.features)
    if missing_features:
        failures.append("missing features " + ", ".join(missing_features))
    for name, requested in request.required_limits:
        ceiling = route.limit(name)
        if ceiling is None:
            failures.append(f"declares no {name}")
        elif requested > ceiling:
            failures.append(f"{name} {ceiling:g} is below requested {requested:g}")
    if request.exact_size is not None:
        if route.exact_size_constraints is None:
            failures.append("declares no exact_size_constraints")
        else:
            failures.extend(route.exact_size_constraints.failures(request.exact_size))
    return tuple(failures)


@dataclass(frozen=True, slots=True)
class RouteContractV1:
    """One application-registered route to one provider model and API surface.

    Capability facts and behavior identity are separated from operational
    metadata. Prices, verification dates, and pacing are retained for planning
    and display, but cannot select a route and do not enter output identity.
    """

    route_id: str
    product_id: str
    operation: str
    model: ModelRef
    modality_spec_version: str
    surface: str
    endpoint: str
    adapter_id: str
    adapter_behavior_version: str
    resource_id: str
    estimated_duration_seconds: float
    estimated_cost_low_usd: float
    estimated_cost_high_usd: float
    operation_variant: str = "default"
    features: frozenset[str] = field(default_factory=frozenset)
    limits: tuple[tuple[str, float], ...] = ()
    exact_size_constraints: ExactSizeConstraints2DV1 | None = None
    max_in_flight: int | None = None
    requests_per_minute: int | None = None
    rate_limit_owner: Literal["scheduler", "provider_adapter", "none"] = "none"
    verified_on: str | None = None
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.route_id, "route_id")
        _require_identifier(self.product_id, "product_id")
        _require_name(self.operation, "operation")
        if self.operation == LOCAL_OPERATION:
            raise ValueError("local operations run without a provider route")
        _require_version(self.modality_spec_version, "modality_spec_version")
        _require_identifier(self.surface, "surface")
        _require_endpoint(self.endpoint)
        _require_identifier(self.adapter_id, "adapter_id")
        _require_version(self.adapter_behavior_version, "adapter_behavior_version")
        _require_identifier(self.operation_variant, "operation_variant")
        _require_resource_id(self.resource_id)
        object.__setattr__(self, "features", frozenset(self.features))
        for feature in self.features:
            _require_name(feature, "route feature")
        object.__setattr__(self, "limits", _validate_limits(self.limits, label="route"))
        if self.exact_size_constraints is not None and not isinstance(
            self.exact_size_constraints, ExactSizeConstraints2DV1
        ):
            raise ValueError(
                "exact_size_constraints must be ExactSizeConstraints2DV1 when declared"
            )
        for estimate, label in (
            (self.estimated_duration_seconds, "estimated_duration_seconds"),
            (self.estimated_cost_low_usd, "estimated_cost_low_usd"),
            (self.estimated_cost_high_usd, "estimated_cost_high_usd"),
        ):
            if (
                isinstance(estimate, bool)
                or not isinstance(estimate, (int, float))
                or not math.isfinite(estimate)
                or estimate < 0
            ):
                raise ValueError(f"{label} must be a non-negative finite number")
        if self.estimated_cost_high_usd < self.estimated_cost_low_usd:
            raise ValueError("estimated high cost must not be below estimated low cost")
        for value, label in (
            (self.max_in_flight, "max_in_flight"),
            (self.requests_per_minute, "requests_per_minute"),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
            ):
                raise ValueError(f"{label} must be a positive integer when declared")
        if self.rate_limit_owner not in {"scheduler", "provider_adapter", "none"}:
            raise ValueError("rate_limit_owner is not recognized")
        if self.verified_on is not None:
            try:
                date.fromisoformat(self.verified_on)
            except ValueError as error:
                raise ValueError("verified_on must be an ISO calendar date") from error
        if self.evidence_ref is not None and (
            not self.evidence_ref.strip() or self.evidence_ref != self.evidence_ref.strip()
        ):
            raise ValueError("evidence_ref must be a non-empty trimmed string")

    def limit(self, name: str) -> float | None:
        for declared, value in self.limits:
            if declared == name:
                return value
        return None

    def resource(self) -> Resource:
        return Resource(
            resource_id=self.resource_id,
            max_in_flight=self.max_in_flight,
            requests_per_minute=self.requests_per_minute,
            rate_limit_owner=self.rate_limit_owner,
        )

    def to_binding(self) -> Binding:
        """Flatten this resolved route into the v1 binding fields."""

        return Binding(
            operation=self.operation,
            model=self.model,
            resource_id=self.resource_id,
            estimated_duration_seconds=self.estimated_duration_seconds,
            estimated_cost_low_usd=self.estimated_cost_low_usd,
            estimated_cost_high_usd=self.estimated_cost_high_usd,
            features=self.features,
            limits=self.limits,
            max_in_flight=self.max_in_flight,
            requests_per_minute=self.requests_per_minute,
            rate_limit_owner=self.rate_limit_owner,
            verified_on=self.verified_on,
        )

    @property
    def behavior_fingerprint(self) -> str:
        """Identity of material provider behavior, excluding operational metadata."""

        return _fingerprint(
            "gnode-route-behavior-v1",
            {
                "operation": self.operation,
                "operation_variant": self.operation_variant,
                "modality_spec_version": self.modality_spec_version,
                "model": {"model": self.model.model, "provider": self.model.provider},
                "surface": self.surface,
                "endpoint": self.endpoint,
                "adapter_id": self.adapter_id,
                "adapter_behavior_version": self.adapter_behavior_version,
            },
        )

    @property
    def contract_fingerprint(self) -> str:
        """Behavior and capability facts, excluding price, pacing, and verification."""

        capability_payload: dict[str, object] = {
            "behavior_fingerprint": self.behavior_fingerprint,
            "features": sorted(self.features),
            "limits": [[name, value] for name, value in self.limits],
        }
        if self.exact_size_constraints is not None:
            capability_payload["exact_size_constraints"] = self.exact_size_constraints.model_dump(
                mode="json"
            )
        return _fingerprint(
            "gnode-route-contract-v1",
            capability_payload,
        )

    def material_identity(self) -> tuple[str, ...]:
        """Fields whose duplication under two route IDs would be ambiguous."""

        return (
            self.product_id,
            self.operation,
            self.operation_variant,
            self.modality_spec_version,
            self.model.provider,
            self.model.model,
            self.surface,
            self.endpoint,
            self.adapter_id,
            self.adapter_behavior_version,
        )


@dataclass(frozen=True, slots=True)
class WorkloadRequestV1:
    """One node instance's exact, modality-normalized route requirements."""

    policy_id: str
    operation: str
    modality_spec_version: str
    required_features: frozenset[str] = field(default_factory=frozenset)
    required_limits: tuple[tuple[str, float], ...] = ()
    exact_size: ExactSize2DV1 | None = None
    output_options: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_identifier(self.policy_id, "policy_id")
        _require_name(self.operation, "operation")
        if self.operation == LOCAL_OPERATION:
            raise ValueError("local operations do not resolve provider workloads")
        _require_version(self.modality_spec_version, "modality_spec_version")
        object.__setattr__(self, "required_features", frozenset(self.required_features))
        for feature in self.required_features:
            _require_name(feature, "required feature")
        object.__setattr__(
            self,
            "required_limits",
            _validate_limits(self.required_limits, label="workload"),
        )
        if self.exact_size is not None and not isinstance(self.exact_size, ExactSize2DV1):
            raise ValueError("exact_size must be ExactSize2DV1 when declared")
        frozen = _freeze_json(self.output_options, path="output_options")
        if not isinstance(frozen, Mapping):
            raise ValueError("output_options must be a mapping")
        object.__setattr__(self, "output_options", frozen)


@dataclass(frozen=True, slots=True)
class WorkloadPolicyV1:
    """An explicit product and exact route selection owned by the host application."""

    policy_id: str
    policy_version: str
    product_id: str
    route_id: str

    def __post_init__(self) -> None:
        _require_identifier(self.policy_id, "policy_id")
        _require_version(self.policy_version, "policy_version")
        _require_identifier(self.product_id, "product_id")
        _require_identifier(self.route_id, "route_id")


@dataclass(frozen=True, slots=True)
class ResolvedBindingV1:
    """The one route admitted for a workload, with deterministic identity digests."""

    route: RouteContractV1
    request: WorkloadRequestV1
    policy: WorkloadPolicyV1
    route_contract_fingerprint: str = field(init=False)
    behavior_fingerprint: str = field(init=False)
    output_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if self.request.policy_id != self.policy.policy_id:
            raise RouteResolutionError(
                f"workload policy mismatch: request names {self.request.policy_id}, "
                f"policy is {self.policy.policy_id}"
            )
        if self.route.route_id != self.policy.route_id:
            raise RouteResolutionError(
                f"policy {self.policy.policy_id} selects route {self.policy.route_id}, "
                f"not supplied route {self.route.route_id}"
            )
        if self.route.product_id != self.policy.product_id:
            raise RouteResolutionError(
                f"route {self.route.route_id} serves product {self.route.product_id}, "
                f"not policy product {self.policy.product_id}"
            )
        if self.route.operation != self.request.operation:
            raise RouteResolutionError(
                f"route {self.route.route_id} serves operation {self.route.operation}, "
                f"not workload operation {self.request.operation}"
            )
        if self.route.modality_spec_version != self.request.modality_spec_version:
            raise RouteResolutionError(
                f"route {self.route.route_id} serves modality spec "
                f"{self.route.modality_spec_version}, not workload modality spec "
                f"{self.request.modality_spec_version}"
            )
        capability_failures = _capability_failures(self.route, self.request)
        if capability_failures:
            raise RouteResolutionError(
                f"selected route {self.route.route_id} is unsupported: "
                + "; ".join(capability_failures)
            )
        object.__setattr__(self, "route_contract_fingerprint", self.route.contract_fingerprint)
        object.__setattr__(self, "behavior_fingerprint", self.route.behavior_fingerprint)
        object.__setattr__(
            self,
            "output_fingerprint",
            _fingerprint(
                "gnode-route-output-v1",
                {
                    "behavior_fingerprint": self.route.behavior_fingerprint,
                    "output_options": self.request.output_options,
                },
            ),
        )

    def to_binding(self) -> Binding:
        return self.route.to_binding()

    def to_snapshot(self) -> ResolvedRouteSnapshotV1:
        """Seal the portable, non-operational record referenced by a graph node."""

        output_options = _plain_json(self.request.output_options)
        if not isinstance(output_options, dict):
            raise TypeError("resolved output options must be a mapping")
        return ResolvedRouteSnapshotV1.create(
            policy_id=self.policy.policy_id,
            policy_version=self.policy.policy_version,
            product_id=self.policy.product_id,
            route_id=self.route.route_id,
            route_contract_fingerprint=self.route_contract_fingerprint,
            behavior_fingerprint=self.behavior_fingerprint,
            output_fingerprint=self.output_fingerprint,
            operation=self.route.operation,
            operation_variant=self.route.operation_variant,
            modality_spec_version=self.route.modality_spec_version,
            provider=self.route.model.provider,
            model=self.route.model.model,
            surface=self.route.surface,
            endpoint=self.route.endpoint,
            adapter_id=self.route.adapter_id,
            adapter_behavior_version=self.route.adapter_behavior_version,
            resource_id=self.route.resource_id,
            supported_features=tuple(sorted(self.route.features)),
            supported_limits=self.route.limits,
            supported_exact_size_constraints=self.route.exact_size_constraints,
            required_features=tuple(sorted(self.request.required_features)),
            required_limits=self.request.required_limits,
            required_exact_size=self.request.exact_size,
            effective_output_options=output_options,
        )


class RouteCatalog:
    """Immutable route facts resolved only through an exact workload policy."""

    def __init__(self, routes: Sequence[RouteContractV1]) -> None:
        grouped_ids: dict[str, list[RouteContractV1]] = {}
        grouped_material: dict[tuple[str, ...], list[RouteContractV1]] = {}
        for route in routes:
            grouped_ids.setdefault(route.route_id, []).append(route)
            grouped_material.setdefault(route.material_identity(), []).append(route)

        duplicate_ids = sorted(
            route_id for route_id, group in grouped_ids.items() if len(group) > 1
        )
        if duplicate_ids:
            raise RouteCatalogError(
                "route catalog declares route ids more than once: " + ", ".join(duplicate_ids)
            )
        ambiguous = sorted(
            tuple(sorted(route.route_id for route in group))
            for group in grouped_material.values()
            if len(group) > 1
        )
        if ambiguous:
            raise RouteCatalogError(
                "route catalog assigns one material route multiple ids: " + ", ".join(ambiguous[0])
            )

        self._routes = tuple(sorted(routes, key=lambda route: route.route_id))
        self._by_id = {route.route_id: route for route in self._routes}

    def __iter__(self) -> Iterable[RouteContractV1]:
        return iter(self._routes)

    @property
    def routes(self) -> tuple[RouteContractV1, ...]:
        return self._routes

    def route(self, route_id: str) -> RouteContractV1:
        try:
            return self._by_id[route_id]
        except KeyError as error:
            raise RouteResolutionError(f"unregistered route: {route_id}") from error

    def resolve(self, request: WorkloadRequestV1, policy: WorkloadPolicyV1) -> ResolvedBindingV1:
        """Admit the policy's one route or refuse; never cascade to another route."""

        if request.policy_id != policy.policy_id:
            raise RouteResolutionError(
                f"workload policy mismatch: request names {request.policy_id}, "
                f"policy is {policy.policy_id}"
            )

        product_routes = tuple(
            route
            for route in self._routes
            if route.product_id == policy.product_id
            and route.operation == request.operation
            and route.modality_spec_version == request.modality_spec_version
        )
        if not product_routes:
            raise RouteResolutionError(
                f"no route declares product {policy.product_id} for {request.operation} "
                f"at modality spec {request.modality_spec_version}"
            )

        capable_route_ids = {
            route.route_id for route in product_routes if not _capability_failures(route, request)
        }

        selected = self._by_id.get(policy.route_id)
        if selected is None:
            raise RouteResolutionError(
                f"policy {policy.policy_id} selects unregistered route {policy.route_id}"
            )
        if selected not in product_routes:
            raise RouteResolutionError(
                f"route {selected.route_id} does not serve product {policy.product_id} "
                f"for {request.operation} at modality spec {request.modality_spec_version}"
            )

        if selected.route_id not in capable_route_ids:
            raise RouteResolutionError(
                f"selected route {selected.route_id} is unsupported: "
                + "; ".join(_capability_failures(selected, request))
            )

        return ResolvedBindingV1(route=selected, request=request, policy=policy)


__all__ = [
    "ResolvedBindingV1",
    "RouteCatalog",
    "RouteCatalogError",
    "RouteContractV1",
    "RouteResolutionError",
    "WorkloadPolicyV1",
    "WorkloadRequestV1",
]
