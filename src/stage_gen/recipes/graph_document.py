"""The execution-graph document every recipe seals.

A recipe's graph is the engine's ``Graph`` plus a header binding it to one authored
package. Five recipes declared that header five times, each re-stating the four derived
document kinds and the run-view version by hand - and twice a recipe bumped the view
version alongside its own graph version, which made every one of its runs invisible to
the run viewer while the document shape had not moved at all. Here the base owns what
is uniform: the derived kinds follow from the recipe name, the view version is the
engine's, and a subclass declares only what is its own.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Any, ClassVar, Self, get_args

from gnode import Graph, Node, Resource, seal_graph


def _literal_of(cls: type[Graph], field: str) -> Any:
    annotation = cls.model_fields[field].annotation
    values = get_args(annotation)
    if len(values) != 1:
        raise TypeError(f"{cls.__name__}.{field} must be a one-value Literal; got {annotation!r}")
    return values[0]


class RecipeGraph(Graph):
    """One recipe's plan of record, bound to the authored input that produced it.

    A subclass pins ``schema_version``, ``kind`` and ``recipe`` as one-value ``Literal``
    fields - the identity table reads them there - and names its operation vocabulary.
    ``VIEW_FIELDS`` are the header fields copied onto the run view; ``IDENTITY_FIELDS``
    are the ones that also participate in topology identity, which is almost none: a
    field that changes what the graph draws moves ``graph_sha256`` through the nodes,
    while the topology digest should move only when the shape of the graph does.
    """

    OPERATIONS: ClassVar[type[StrEnum]]
    VIEW_FIELDS: ClassVar[tuple[str, ...]] = ()
    IDENTITY_FIELDS: ClassVar[tuple[str, ...]] = ()

    recipe: str

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        recipe = _literal_of(cls, "recipe")
        cls.TRACE_EVENT_KIND = f"{recipe}-execution-event-v1"
        cls.RUN_SUMMARY_KIND = f"{recipe}-execution-summary-v1"
        cls.PROJECTION_KIND = f"{recipe}-execution-projection-v1"
        cls.VIEW_KIND = f"{recipe}-execution-view-v1"

    @classmethod
    def seal(
        cls,
        *,
        resources: Sequence[Resource],
        nodes: Sequence[Node],
        terminal_node_id: str,
        **header: object,
    ) -> Self:
        """Seal a graph of this class; the pinned literals fill themselves in."""

        return seal_graph(
            cls,
            resources=resources,
            nodes=nodes,
            terminal_node_id=terminal_node_id,
            schema_version=_literal_of(cls, "schema_version"),
            kind=_literal_of(cls, "kind"),
            recipe=_literal_of(cls, "recipe"),
            **header,
        )

    def identity_header(self) -> dict[str, object]:
        header = {**super().identity_header(), "recipe": self.recipe}
        for field in self.IDENTITY_FIELDS:
            header[field] = getattr(self, field)
        return header

    def annotator_key(self) -> str:
        return self.recipe

    def view_header(self) -> dict[str, object]:
        header: dict[str, object] = {"recipe": self.recipe}
        for field in self.VIEW_FIELDS:
            header[field] = getattr(self, field)
        return header

    def operation_vocabulary(self) -> tuple[str, ...]:
        """Every declared operation, so a zero count stays visible."""

        return tuple(operation.value for operation in self.OPERATIONS)


__all__ = ["RecipeGraph"]
