"""Prepared-game execution documents: this application's asset-graph vocabulary.

The engine owns topology, scheduling, trace, and identity. This module owns what
is specific to prepared-game generation: which operations exist, and which header
fields bind a graph to one game package.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from gnode import SHA256_PATTERN
from stage_gen.recipes.graph_document import RecipeGraph

EXECUTION_GRAPH_SCHEMA_VERSION = 2
EXECUTION_GRAPH_KIND = "sideview-platformer-execution-graph-v2"
EXECUTION_TRACE_SCHEMA_VERSION = 1


class OperationKind(StrEnum):
    """The capabilities this application's nodes are allowed to use."""

    LOCAL = "local"
    IMAGE_GENERATION = "image_generation"
    STRUCTURED_GENERATION = "structured_generation"
    MUSIC_GENERATION = "music_generation"


class ExecutionGraph(RecipeGraph):
    """One prepared-game plan of record, bound to the package that produced it."""

    OPERATIONS = OperationKind
    VIEW_FIELDS = ("game_id",)
    CURRENT_SCHEMA_VERSION = EXECUTION_GRAPH_SCHEMA_VERSION
    CURRENT_KIND = EXECUTION_GRAPH_KIND
    LEGACY_GRAPH_IDENTITIES = frozenset({(1, "sideview-platformer-execution-graph-v1")})
    ROUTED_OPERATIONS = frozenset({OperationKind.IMAGE_GENERATION.value})

    schema_version: Literal[1, 2]
    kind: Literal[
        "sideview-platformer-execution-graph-v1",
        "sideview-platformer-execution-graph-v2",
    ]
    recipe: Literal["sideview-platformer"]
    game_id: str
    package_sha256: str = Field(pattern=SHA256_PATTERN)


__all__ = [
    "EXECUTION_GRAPH_SCHEMA_VERSION",
    "EXECUTION_GRAPH_KIND",
    "EXECUTION_TRACE_SCHEMA_VERSION",
    "ExecutionGraph",
    "OperationKind",
]
