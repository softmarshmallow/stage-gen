"""The persisted records gnode's run views, routes and ledger share.

Patterns every identifier is held to; the resource a route paces; the route snapshot a
binding is resolved to; the output ports and static card a run view shows for each step;
an artifact as a record names it; and the error a refused step carries.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from gnode.contracts.artifacts import SHA256_PATTERN, PersistedContractModel
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


class NodeArtifact(PersistedContractModel):
    artifact_ref: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    bytes: int = Field(ge=0)


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
