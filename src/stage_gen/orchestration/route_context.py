"""Task-local access to the exact route sealed on the node being dispatched."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from gnode import Graph, Node, ResolvedBindingV1

_CURRENT_RESOLVED_BINDING: ContextVar[ResolvedBindingV1 | None] = ContextVar(
    "stage_gen_current_resolved_binding",
    default=None,
)


@contextmanager
def node_route_context(graph: Graph, node: Node) -> Iterator[None]:
    """Expose this planned node's binding only within its async dispatch task."""

    binding = (
        None if node.binding_ref is None else graph.resolved_route_for(node).to_resolved_binding()
    )
    token = _CURRENT_RESOLVED_BINDING.set(binding)
    try:
        yield
    finally:
        _CURRENT_RESOLVED_BINDING.reset(token)


def current_resolved_binding() -> ResolvedBindingV1 | None:
    """Return the dispatch task's sealed binding, never a process-global default."""

    return _CURRENT_RESOLVED_BINDING.get()


__all__ = ["current_resolved_binding", "node_route_context"]
