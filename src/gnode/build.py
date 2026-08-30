"""One graph builder for every recipe: typed construction, cache keys, barriers.

Every recipe used to carry a private builder that wired dependency order,
cache keys, and binding resolution the same way. This is that builder, once,
consuming ``NodeType`` declarations: a provider type resolves its route and
features against the binding table offline (a missing feature is refused
before any spend), a local type runs on the local resource, and the cache
contract version comes from the type instead of a per-family constant.

A subgraph template is a parameterized expansion — a callable that adds a
cluster of typed nodes through this builder. ``within_template`` stamps every
node added inside it with the template's identity, so an instantiated cluster
stays visible as one construct in the plan and the viewer, while the
parameters that make each instance different (the measured residue of an
asset type) stay in the nodes' digests and cards.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from gnode.binding import BindingTable
from gnode.graph import (
    Node,
    NodeCard,
    Port,
    Resource,
    RetryOwner,
    build_node_cache_key,
)
from gnode.node_types import NodeType

DEFAULT_LOCAL_DURATION_SECONDS = 0.25


class GraphBuilder:
    """Accumulate typed nodes in dependency order for one sealed graph."""

    def __init__(
        self,
        *,
        profile: BindingTable,
        local_resource_id: str = "local",
        local_max_in_flight: int | None = None,
    ) -> None:
        self._profile = profile
        self._local_resource_id = local_resource_id
        self._local_max_in_flight = local_max_in_flight
        self._nodes: list[Node] = []
        self._by_id: dict[str, Node] = {}
        self._template_stack: list[str] = []

    @property
    def nodes(self) -> tuple[Node, ...]:
        return tuple(self._nodes)

    def node(self, node_id: str) -> Node:
        return self._by_id[node_id]

    def resources(self) -> tuple[Resource, ...]:
        """The local resource plus every route the profile declares.

        Declared, not merely used: a zero-node resource stays visible, and the
        scheduler's exact-match rule keeps run configuration honest.
        """

        resources = [
            Resource(
                resource_id=self._local_resource_id,
                max_in_flight=self._local_max_in_flight,
                rate_limit_owner="none",
            )
        ]
        resources.extend(binding.resource() for binding in self._profile.bindings)
        return tuple(resources)

    @contextmanager
    def within_template(self, template_id: str) -> Iterator[None]:
        """Stamp every node added inside with the template instance's identity."""

        self._template_stack.append(template_id)
        try:
            yield
        finally:
            self._template_stack.pop()

    def add(
        self,
        node_type: NodeType,
        node_id: str,
        *,
        domain: str,
        description: str,
        params: dict[str, str] | None = None,
        depends_on: Sequence[str] = (),
        cache_depends_on: Sequence[str] | None = None,
        input_digests: Sequence[str] = (),
        ports: Sequence[Port] = (),
        card: NodeCard | None = None,
        duration_seconds: float | None = None,
    ) -> Node:
        """Add one instance of a type; dependencies must already be added.

        ``cache_depends_on`` selects which dependencies contribute cache
        lineage; the rest become barrier edges — ordering without identity.
        ``None`` means every dependency carries lineage.
        """

        if node_id in self._by_id:
            raise ValueError(f"duplicate graph node: {node_id}")
        lineage = tuple(depends_on) if cache_depends_on is None else tuple(cache_depends_on)
        unknown_lineage = sorted(set(lineage) - set(depends_on))
        if unknown_lineage:
            raise ValueError(
                f"cache lineage of {node_id} must be declared dependencies: "
                + ", ".join(unknown_lineage)
            )
        for dependency in (*depends_on, *lineage):
            if dependency not in self._by_id:
                raise ValueError(f"graph dependency must be added first: {node_id}->{dependency}")
        dependency_cache_keys = [self._by_id[dependency].cache_key for dependency in lineage]
        barrier_only = tuple(
            dependency for dependency in depends_on if dependency not in set(lineage)
        )

        if node_type.is_local:
            provider: str | None = None
            model: str | None = None
            resource_id = self._local_resource_id
            retry_owner = RetryOwner.NONE
            duration = (
                DEFAULT_LOCAL_DURATION_SECONDS if duration_seconds is None else duration_seconds
            )
            cost_low = 0.0
            cost_high = 0.0
        else:
            binding = self._profile.require(node_type.operation, *node_type.features)
            provider = binding.model.provider
            model = binding.model.model
            resource_id = binding.resource_id
            retry_owner = RetryOwner.COMPONENT
            duration = (
                binding.estimated_duration_seconds if duration_seconds is None else duration_seconds
            )
            cost_low = binding.estimated_cost_low_usd
            cost_high = binding.estimated_cost_high_usd

        digests = tuple(dict.fromkeys(input_digests))
        node = Node(
            node_id=node_id,
            type_id=node_type.type_id,
            domain=domain,
            description=description,
            params=dict(params or {}),
            depends_on=tuple(depends_on),
            barrier_only=barrier_only,
            operation=node_type.operation,
            resource_id=resource_id,
            provider=provider,
            model=model,
            retry_owner=retry_owner,
            max_attempts=node_type.policy.max_attempts,
            input_sha256=digests,
            cache_key=build_node_cache_key(
                node_id=node_id,
                type_id=node_type.type_id,
                operation=node_type.operation,
                provider=provider,
                model=model,
                input_sha256=digests,
                dependency_cache_keys=dependency_cache_keys,
                contract_version=node_type.contract_version,
            ),
            ports=tuple(ports),
            card=card,
            template_id=self._template_stack[-1] if self._template_stack else None,
            estimated_duration_seconds=float(duration),
            estimated_cost_low_usd=cost_low,
            estimated_cost_high_usd=cost_high,
        )
        self._nodes.append(node)
        self._by_id[node_id] = node
        return node


__all__ = ["DEFAULT_LOCAL_DURATION_SECONDS", "GraphBuilder"]
