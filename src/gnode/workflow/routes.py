"""Routes a workflow may use: which model serves a capability, what it costs, what it can do.

A route is ``model@provider`` serving one capability (``image.generate``). It carries the
features the provider supports for it (``image_input``, ``mask``, ``alpha`` ...), its price
per call or per unit of length, and its pacing. The catalog is assembled from the
providers gnode ships and is checked offline: a step whose route is unknown, lacks a
required feature, or shares an underlying model with a step it must be independent of is
refused while planning, before anything is spent.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from gnode.workflow.values import digest_of

PriceUnit = Literal["call", "1k_chars", "second"]


class RouteError(ValueError):
    """A route the catalog cannot serve as asked."""


@dataclass(frozen=True, slots=True)
class RoutePrice:
    """What one call costs: a range per call, or per thousand characters or per second."""

    low_usd: float
    high_usd: float
    unit: PriceUnit = "call"
    #: For a length-priced route, the most units one call can carry (its worst case).
    max_units: float | None = None
    #: The setting whose value picks the price, such as a video's ``resolution``. Each tier
    #: is a ``(low_usd, high_usd)`` range in the price's unit; ``low_usd`` and ``high_usd``
    #: span them all, and price a call whose setting the plan does not know yet.
    by: str | None = None
    tiers: Mapping[str, tuple[float, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.low_usd < 0 or self.high_usd < self.low_usd:
            raise RouteError("a price is a non-negative range, low to high")
        if self.unit != "call" and (self.max_units is None or self.max_units <= 0):
            raise RouteError("a length-priced route declares the most units one call carries")
        if (self.by is None) != (not self.tiers):
            raise RouteError("a tiered price names the setting it is priced by, and its tiers")
        for name, (low, high) in self.tiers.items():
            if not self.low_usd <= low <= high <= self.high_usd:
                raise RouteError(f"price tier {name} lies outside the route's range")

    def per_call(self, units: float | None, tier: str | None = None) -> tuple[float, float]:
        """The range for one call; ``units`` is the call's length and ``tier`` the value of
        the setting it is priced by, each when the plan knows it."""

        low_unit, high_unit = self.tiers.get(tier or "", (self.low_usd, self.high_usd))
        if self.unit == "call":
            return low_unit, high_unit
        assert self.max_units is not None
        known = units if units is not None else self.max_units
        divisor = 1_000.0 if self.unit == "1k_chars" else 1.0
        high = high_unit * min(known, self.max_units) / divisor
        low = low_unit * (known / divisor if units is not None else 0.0)
        return round(low, 6), round(high, 6)


@dataclass(frozen=True, slots=True)
class Route:
    """One ``model@provider`` serving one capability."""

    capability: str
    model: str
    provider: str
    price: RoutePrice
    features: frozenset[str] = frozenset()
    concurrency: int | None = None
    requests_per_minute: int | None = None
    #: Settings that change what the route returns; part of every step identity it serves.
    contract: Mapping[str, Any] = field(default_factory=dict)

    @property
    def route_id(self) -> str:
        return f"{self.model}@{self.provider}"

    @property
    def underlying_model(self) -> str:
        """The model behind any provider: ``vendor/name`` and ``name`` are the same model."""

        return self.model.rsplit("/", 1)[-1].lower()

    def cost(self, request: Mapping[str, Any]) -> tuple[float, float]:
        """What one call with these settings may cost, low to high."""

        tier = request.get(self.price.by) if self.price.by is not None else None
        return self.price.per_call(units_of(self, request), tier if isinstance(tier, str) else None)

    @property
    def fingerprint(self) -> str:
        return digest_of(
            {
                "capability": self.capability,
                "model": self.model,
                "provider": self.provider,
                "contract": dict(self.contract),
            }
        )


def units_of(route: Route, values: Mapping[str, Any]) -> float | None:
    """A call's length when its route is priced by length: characters, or seconds."""

    if route.price.unit == "1k_chars":
        text = values.get("text")
        if isinstance(text, str):
            return float(len(text))
        limit = values.get("max_chars")
        return float(limit) if isinstance(limit, int | float) else None
    if route.price.unit == "second":
        for name in ("duration", "duration_s"):
            value = values.get(name)
            if isinstance(value, int | float) and not isinstance(value, bool):
                return float(value)
    return None


def parse_route_id(value: str) -> tuple[str, str]:
    model, separator, provider = value.rpartition("@")
    if not separator or not model or not provider:
        raise RouteError(f"a route is model@provider, not {value!r}")
    return model, provider


class RouteTable:
    """Every route gnode can call, by capability."""

    def __init__(self, routes: Iterable[Route] = ()) -> None:
        self._routes: dict[str, dict[str, Route]] = {}
        for route in routes:
            by_id = self._routes.setdefault(route.capability, {})
            if route.route_id in by_id:
                raise RouteError(f"{route.route_id} is declared twice for {route.capability}")
            by_id[route.route_id] = route

    def capabilities(self) -> list[str]:
        return sorted(self._routes)

    def routes(self, capability: str) -> list[Route]:
        return [self._routes[capability][key] for key in sorted(self._routes.get(capability, {}))]

    def resolve(self, capability: str, route_id: str) -> Route:
        parse_route_id(route_id)
        found = self._routes.get(capability, {}).get(route_id)
        if found is None:
            known = ", ".join(sorted(self._routes.get(capability, {}))) or "none"
            raise RouteError(f"no route {route_id} serves {capability} (known routes: {known})")
        return found

    def merged(self, other: RouteTable) -> RouteTable:
        return RouteTable([*self._all(), *other._all()])

    def _all(self) -> list[Route]:
        return [route for by_id in self._routes.values() for route in by_id.values()]


def route_table_from_document(document: Mapping[str, Any]) -> RouteTable:
    """Read a ``gnode: routes/v1`` document: a list of routes with prices and features."""

    if document.get("gnode") != "routes/v1":
        raise RouteError("a route catalog starts with gnode: routes/v1")
    routes: list[Route] = []
    for entry in document.get("routes", []):
        model, provider = parse_route_id(entry["route"])
        price = entry["price"]
        routes.append(
            Route(
                capability=entry["capability"],
                model=model,
                provider=provider,
                price=RoutePrice(
                    low_usd=float(price.get("low_usd", price.get("usd", 0.0))),
                    high_usd=float(price.get("high_usd", price.get("usd", 0.0))),
                    unit=price.get("unit", "call"),
                    max_units=price.get("max_units"),
                    by=price.get("by"),
                    tiers={
                        str(name): (float(tier["low_usd"]), float(tier["high_usd"]))
                        for name, tier in price.get("tiers", {}).items()
                    },
                ),
                features=frozenset(entry.get("features", ())),
                concurrency=entry.get("concurrency"),
                requests_per_minute=entry.get("requests_per_minute"),
                contract=dict(entry.get("contract", {})),
            )
        )
    return RouteTable(routes)
