"""Prepared-game execution documents: this application's asset-graph vocabulary.

The engine owns topology, scheduling, trace, and identity. This module owns what
is specific to prepared-game generation: which operations exist, what the run's
documents are called, and which header fields bind a graph to one game package.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import ClassVar, Literal

from pydantic import Field

from gnode import SHA256_PATTERN, Graph, Node, Resource, seal_graph

EXECUTION_GRAPH_SCHEMA_VERSION = 1
EXECUTION_TRACE_SCHEMA_VERSION = 1


class OperationKind(StrEnum):
    """The capabilities this application's nodes are allowed to use."""

    LOCAL = "local"
    IMAGE_GENERATION = "image_generation"
    STRUCTURED_GENERATION = "structured_generation"
    MUSIC_GENERATION = "music_generation"


class ExecutionGraph(Graph):
    """One prepared-game plan of record, bound to the package that produced it."""

    TRACE_SCHEMA_VERSION: ClassVar[int] = EXECUTION_TRACE_SCHEMA_VERSION
    TRACE_EVENT_KIND: ClassVar[str] = "prepared-game-execution-event-v1"
    RUN_SUMMARY_KIND: ClassVar[str] = "prepared-game-execution-summary-v1"
    PROJECTION_KIND: ClassVar[str] = "prepared-game-execution-projection-v1"
    VIEW_KIND: ClassVar[str] = "prepared-game-execution-view-v1"
    VIEW_SCHEMA_VERSION: ClassVar[int] = 2

    schema_version: Literal[1]
    kind: Literal["prepared-game-execution-graph-v1"]
    recipe: Literal["scrolling-preview"]
    game_id: str
    package_sha256: str = Field(pattern=SHA256_PATTERN)

    def identity_header(self) -> dict[str, object]:
        return {**super().identity_header(), "recipe": self.recipe}

    def annotator_key(self) -> str:
        return self.recipe

    def view_header(self) -> dict[str, object]:
        return {"recipe": self.recipe, "game_id": self.game_id}

    def operation_vocabulary(self) -> tuple[str, ...]:
        """Report every declared operation, so a zero count stays visible."""

        return tuple(operation.value for operation in OperationKind)


def finalize_execution_graph(
    *,
    game_id: str,
    package_sha256: str,
    resources: Sequence[Resource],
    nodes: Sequence[Node],
    terminal_node_id: str,
) -> ExecutionGraph:
    return seal_graph(
        ExecutionGraph,
        resources=resources,
        nodes=nodes,
        terminal_node_id=terminal_node_id,
        schema_version=EXECUTION_GRAPH_SCHEMA_VERSION,
        kind="prepared-game-execution-graph-v1",
        recipe="scrolling-preview",
        game_id=game_id,
        package_sha256=package_sha256,
    )


__all__ = [
    "EXECUTION_GRAPH_SCHEMA_VERSION",
    "EXECUTION_TRACE_SCHEMA_VERSION",
    "ExecutionGraph",
    "OperationKind",
    "finalize_execution_graph",
]
