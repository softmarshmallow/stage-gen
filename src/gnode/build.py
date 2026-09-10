"""Typed graph construction with offline bindings, cache lineage, and barriers.

Subgraph templates are callables that add clusters of nodes. ``within_template``
stamps their identity for the plan and viewer; instance-specific inputs remain
in each node's digests and cards.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager

from gnode.binding import BindingTable
from gnode.graph import (
    Node,
    NodeCard,
    Port,
    ResolvedRouteSnapshotV1,
    Resource,
    RetryOwner,
    build_node_cache_key,
)
from gnode.node_types import NodeType
from gnode.routes import (
    ResolvedBindingV1,
    RouteCatalog,
    RouteResolutionError,
    WorkloadPolicyV1,
    WorkloadRequestV1,
)

DEFAULT_LOCAL_DURATION_SECONDS = 0.25


class GraphBuilder:
    """Plan typed nodes using legacy bindings or exact catalog workloads.

    Pass ``nodes`` and ``resources()`` to ``seal_graph`` when ready. Construction
    resolves provider routes offline; it does not execute nodes or persist files.
    """

    def __init__(
        self,
        *,
        profile: BindingTable | None = None,
        route_catalog: RouteCatalog | None = None,
        workload_policies: Mapping[str, WorkloadPolicyV1] | None = None,
        local_resource_id: str = "local",
        local_max_in_flight: int | None = None,
    ) -> None:
        if profile is None and route_catalog is None:
            raise ValueError("graph builder requires a binding profile or route catalog")
        if route_catalog is None and workload_policies:
            raise ValueError("workload policies require a route catalog")
        policies = dict(workload_policies or {})
        mismatched_policy_ids = sorted(
            key for key, policy in policies.items() if key != policy.policy_id
        )
        if mismatched_policy_ids:
            raise ValueError(
                "workload policy mapping keys must match policy_id: "
                + ", ".join(mismatched_policy_ids)
            )
        self._profile = profile
        self._route_catalog = route_catalog
        self._workload_policies = policies
        self._local_resource_id = local_resource_id
        self._local_max_in_flight = local_max_in_flight
        self._nodes: list[Node] = []
        self._by_id: dict[str, Node] = {}
        self._resolved_by_node_id: dict[str, ResolvedBindingV1] = {}
        self._resolved_routes_by_ref: dict[str, ResolvedRouteSnapshotV1] = {}
        self._template_stack: list[str] = []

    @property
    def nodes(self) -> tuple[Node, ...]:
        return tuple(self._nodes)

    def node(self, node_id: str) -> Node:
        return self._by_id[node_id]

    @property
    def resolved_bindings(self) -> tuple[ResolvedBindingV1, ...]:
        """Catalog resolutions in node insertion order; legacy nodes are absent."""

        return tuple(
            self._resolved_by_node_id[node.node_id]
            for node in self._nodes
            if node.node_id in self._resolved_by_node_id
        )

    def resolved_binding(self, node_id: str) -> ResolvedBindingV1:
        """Return catalog resolution metadata for one opt-in node."""

        try:
            return self._resolved_by_node_id[node_id]
        except KeyError as error:
            raise KeyError(f"node has no catalog-resolved binding: {node_id}") from error

    def resolved_routes(self) -> tuple[ResolvedRouteSnapshotV1, ...]:
        """Deduplicated snapshots for the exact catalog routes nodes actually use."""

        return tuple(
            self._resolved_routes_by_ref[binding_ref]
            for binding_ref in sorted(self._resolved_routes_by_ref)
        )

    def resources(self) -> tuple[Resource, ...]:
        """The local resource plus legacy declarations and used catalog routes.

        Legacy profile resources remain declared even when unused, preserving
        v1 graph output. Catalog registration alone has no plan effect, so only
        routes resolved by a node contribute their resource.
        """

        resources = [
            Resource(
                resource_id=self._local_resource_id,
                max_in_flight=self._local_max_in_flight,
                rate_limit_owner="none",
            )
        ]
        if self._profile is not None:
            resources.extend(binding.resource() for binding in self._profile.bindings)

        used_catalog_resources = sorted(
            (resolved.route.resource() for resolved in self.resolved_bindings),
            key=lambda resource: resource.resource_id,
        )
        for resource in used_catalog_resources:
            matching = [
                declared for declared in resources if declared.resource_id == resource.resource_id
            ]
            if matching:
                if any(declared != resource for declared in matching):
                    raise ValueError(
                        f"resource {resource.resource_id} has conflicting route declarations"
                    )
                continue
            resources.append(resource)
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
        workload: WorkloadRequestV1 | None = None,
        ports: Sequence[Port] = (),
        card: NodeCard | None = None,
        duration_seconds: float | None = None,
    ) -> Node:
        """Return and retain a planned node; dependencies must already be added.

        Provider types without ``workload`` retain v1 binding-profile behavior.
        A workload opts into the catalog and its exact application policy; no
        alternate route is tried when that selection is absent or unsupported.
        Local types use the local resource. ``duration_seconds`` overrides the
        default local estimate or the resolved route's estimate.

        ``cache_depends_on`` selects a subset of ``depends_on`` for cache lineage.
        ``None`` includes all; an empty sequence makes all edges ordering barriers.
        Cache identity includes node/type IDs, route, operation, contract version,
        input digests, and dependency cache keys. Parameters and presentation
        metadata are not hashed directly: include output-affecting configuration
        in ``input_digests``. Catalog workloads add their endpoint-aware output
        fingerprint automatically. Duplicate input digests are removed in order.

        Raises:
            CapabilityError: No binding supports the operation or its features.
            ValueError: Duplicate ID, missing dependency, invalid cache dependency
                subset, or invalid node fields.
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

        resolved: ResolvedBindingV1 | None = None
        if node_type.is_local:
            if workload is not None:
                raise ValueError(f"local node {node_id} cannot declare a provider workload")
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
            if workload is None:
                if self._profile is None:
                    raise RouteResolutionError(
                        f"provider node {node_id} requires an explicit catalog workload"
                    )
                binding = self._profile.require(node_type.operation, *node_type.features)
            else:
                if self._route_catalog is None:
                    raise RouteResolutionError(
                        f"provider node {node_id} declares a workload without a route catalog"
                    )
                policy = self._workload_policies.get(workload.policy_id)
                if policy is None:
                    raise RouteResolutionError(
                        f"no workload policy is registered as {workload.policy_id}"
                    )
                node_type.validate_workload_operation(workload.operation)
                resolved = self._route_catalog.resolve(workload, policy)
                binding = resolved.to_binding()
            provider = binding.model.provider
            model = binding.model.model
            resource_id = binding.resource_id
            retry_owner = RetryOwner.COMPONENT
            duration = (
                binding.estimated_duration_seconds if duration_seconds is None else duration_seconds
            )
            cost_low = binding.estimated_cost_low_usd
            cost_high = binding.estimated_cost_high_usd

        route_snapshot = None if resolved is None else resolved.to_snapshot()
        if route_snapshot is not None:
            existing = self._resolved_routes_by_ref.get(route_snapshot.binding_ref)
            if existing is not None and existing != route_snapshot:
                raise ValueError(
                    f"resolved route binding reference collision: {route_snapshot.binding_ref}"
                )

        route_digests = (
            tuple(input_digests)
            if resolved is None
            else (*input_digests, resolved.output_fingerprint)
        )
        digests = tuple(dict.fromkeys(route_digests))
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
            binding_ref=(None if route_snapshot is None else route_snapshot.binding_ref),
            retry_owner=retry_owner,
            max_attempts=node_type.policy.max_attempts,
            input_sha256=digests,
            cache_key=build_node_cache_key(
                node_id=node_id,
                type_id=node_type.cache_identity,
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
        if resolved is not None:
            self._resolved_by_node_id[node_id] = resolved
        if route_snapshot is not None:
            self._resolved_routes_by_ref[route_snapshot.binding_ref] = route_snapshot
        return node


__all__ = ["DEFAULT_LOCAL_DURATION_SECONDS", "GraphBuilder"]
