"""Model bindings: which route serves an operation, and what that route can do.

Three levels are kept apart deliberately.

* **Capability** — the operation a node declares it needs. Stable, engine-side
  vocabulary owned by the consumer's node types.
* **Feature** — a capability's optional behaviour, such as returning a
  transparent background. Declared per binding, because two routes to the same
  model do not always offer the same ones.
* **Limit** — a capability's declared numeric ceiling on one route, such as the
  longest clip a video model will make. The same consumer-named vocabulary as a
  feature, in numbers rather than booleans, so a per-model bound is declared
  where the model is chosen instead of hard-coded into a modality or branched on
  inside an adapter. Refused offline, before any spend.
* **Binding** — one concrete route, written ``model@provider``. Time-sensitive
  configuration, not architecture.

``model@provider`` is used rather than ``provider/model`` because a model
identifier already carries its own namespace and that namespace belongs to
whoever routes it: ``gpt-image-2@openai`` and ``openai/gpt-image-2@openrouter``
are the same model reached two ways, and a leading ``vendor/`` cannot say which
of the two is meant. The two halves are persisted as separate ``provider`` and
``model`` fields, so this form is a surface for configuration and display only —
no record's identity depends on it.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from gnode.graph import LOCAL_OPERATION, Resource

_PROVIDER_PATTERN = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


class CapabilityError(ValueError):
    """Raised at plan time when no binding can serve a required capability.

    Refusing here keeps the failure free: nothing has been requested from a
    provider yet, so a missing feature costs a message instead of a call.
    """


@dataclass(frozen=True, slots=True)
class ModelRef:
    """One route to one model, written ``model@provider``."""

    model: str
    provider: str

    def __post_init__(self) -> None:
        if not _MODEL_PATTERN.fullmatch(self.model):
            raise ValueError(f"invalid model identifier: {self.model!r}")
        if not _PROVIDER_PATTERN.fullmatch(self.provider):
            raise ValueError(f"invalid provider identifier: {self.provider!r}")

    @classmethod
    def parse(cls, value: str) -> ModelRef:
        """Read ``model@provider``; the model keeps any vendor prefix it carries."""

        model, separator, provider = value.rpartition("@")
        if not separator:
            raise ValueError(f"model reference must be model@provider: {value!r}")
        return cls(model=model, provider=provider)

    def __str__(self) -> str:
        return f"{self.model}@{self.provider}"


@dataclass(frozen=True, slots=True)
class Binding:
    """What one operation costs, how fast it may be called, and what it supports."""

    operation: str
    model: ModelRef
    resource_id: str
    estimated_duration_seconds: float
    estimated_cost_low_usd: float
    estimated_cost_high_usd: float
    features: frozenset[str] = field(default_factory=frozenset)
    #: Named numeric ceilings this route declares, as ``(name, value)`` pairs.
    #: A tuple rather than a set of pairs because a set would happily hold both
    #: ``("clip_seconds_max", 10.0)`` and ``("clip_seconds_max", 12.0)`` and
    #: leave the reader to iteration order.
    limits: tuple[tuple[str, float], ...] = ()
    max_in_flight: int | None = None
    requests_per_minute: int | None = None
    rate_limit_owner: Literal["scheduler", "provider_adapter", "none"] = "none"
    #: ISO date this route's contract was last checked against its provider.
    #: Hosted capabilities drift; an old date is a prompt to re-verify, not a gate.
    verified_on: str | None = None

    def __post_init__(self) -> None:
        if self.operation == LOCAL_OPERATION:
            raise ValueError("local operations run without a provider route")
        if self.estimated_cost_high_usd < self.estimated_cost_low_usd:
            raise ValueError("estimated high cost must not be below estimated low cost")
        names = [name for name, _ in self.limits]
        if len(names) != len(set(names)):
            raise ValueError("a binding declares each limit at most once")
        for name, value in self.limits:
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"limit {name!r} must be a positive finite number")

    def limit(self, name: str) -> float | None:
        """The ceiling this route declares under ``name``, or ``None`` if it declares none."""

        for declared, value in self.limits:
            if declared == name:
                return value
        return None

    def within(self, name: str, value: float, *, subject: str) -> None:
        """Refuse offline unless this route's declared ceiling can carry ``value``.

        Fail-closed on purpose. An undeclared ceiling is refused rather than
        waved through, so forgetting the ``limits=`` entry on a new route is a
        loud planning failure instead of a provider rejection after the plan has
        already been paid for.
        """

        ceiling = self.limit(name)
        if ceiling is None:
            raise CapabilityError(
                f"{self.model} declares no {name} for {self.operation}, so {subject} "
                f"cannot be planned; measure the route and declare it"
            )
        if value > ceiling:
            raise CapabilityError(
                f"{subject} asks for {value:g} but {self.model} declares "
                f"{name} {ceiling:g} for {self.operation}"
            )

    def aligned(self, name: str, value: float, *, subject: str) -> None:
        """Refuse offline unless ``value`` is a whole multiple of a declared step.

        A ceiling is not the only shape a route's arithmetic takes: a video route that
        counts seconds cannot be handed four and a half of them. Fail-closed like
        ``within``, for the same reason.
        """

        step = self.limit(name)
        if step is None:
            raise CapabilityError(
                f"{self.model} declares no {name} for {self.operation}, so {subject} "
                f"cannot be planned; measure the route and declare it"
            )
        if abs(value / step - round(value / step)) > 1e-9:
            raise CapabilityError(
                f"{subject} asks for {value:g} but {self.model} takes {self.operation} "
                f"in steps of {step:g}"
            )

    def resource(self) -> Resource:
        return Resource(
            resource_id=self.resource_id,
            max_in_flight=self.max_in_flight,
            requests_per_minute=self.requests_per_minute,
            rate_limit_owner=self.rate_limit_owner,
        )


class BindingTable:
    """Every provider route one plan is allowed to use, declared in one place."""

    def __init__(self, bindings: Sequence[Binding]) -> None:
        operations = [binding.operation for binding in bindings]
        if len(operations) != len(set(operations)):
            raise ValueError("a binding table declares at most one route per operation")
        self._bindings = tuple(bindings)
        self._by_operation = {binding.operation: binding for binding in bindings}

    def __iter__(self) -> Iterable[Binding]:
        return iter(self._bindings)

    @property
    def bindings(self) -> tuple[Binding, ...]:
        return self._bindings

    def resources(self) -> tuple[Resource, ...]:
        return tuple(binding.resource() for binding in self._bindings)

    def require(self, operation: str, *features: str) -> Binding:
        """Resolve one operation, refusing offline when a feature is unavailable."""

        binding = self._by_operation.get(operation)
        if binding is None:
            raise CapabilityError(f"no binding declares the {operation} capability")
        missing = sorted(feature for feature in features if feature not in binding.features)
        if missing:
            raise CapabilityError(
                f"{binding.model} does not declare {', '.join(missing)} "
                f"for {operation}; bind a route that does"
            )
        return binding

    def require_within(
        self, operation: str, name: str, value: float, *, subject: str, features: Sequence[str] = ()
    ) -> Binding:
        """Resolve one operation and refuse offline when its declared ceiling is too low."""

        binding = self.require(operation, *features)
        binding.within(name, value, subject=subject)
        return binding


__all__ = [
    "Binding",
    "BindingTable",
    "CapabilityError",
    "ModelRef",
]
