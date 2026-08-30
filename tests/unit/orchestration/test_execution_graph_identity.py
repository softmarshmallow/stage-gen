"""Pinned identity for the prepared-game plan.

The engine may move; the graph a package plans to may not. These digests must
only ever change when the recipe deliberately changes what it plans — never as
a side effect of moving code, renaming a symbol, or re-declaring a provider
route. Re-pinned 2026-08-31 for the node-ABI schema bump (typed nodes, ports,
and the taxonomy-aligned persisted vocabulary), which changed every digest by
design in one coordinated move.
"""

from __future__ import annotations

from pathlib import Path

from gnode import LOCAL_OPERATION
from stage_gen.config import StageGenConfig
from stage_gen.orchestration.execution_graph import ExecutionGraph, OperationKind
from stage_gen.recipes.sideview_platformer.package_executor import PreparedPackageExecutor
from stage_gen.recipes.sideview_platformer.package_types import platformer_type_index

REPOSITORY_ROOT = Path(__file__).parents[3]
BELLWEATHER = REPOSITORY_ROOT / "library/games/bellweather"

BELLWEATHER_NODE_COUNT = 221
BELLWEATHER_GRAPH_SHA256 = "fbdcbcef65f5484be59e2094dfdb367b7ee43a12de262f3a8b8da42e962ae49c"
BELLWEATHER_TOPOLOGY_SHA256 = "0c85fcc8d415a20670601f819112150a1dd78aec163aa1756b9169679d450164"


def _bellweather_graph() -> ExecutionGraph:
    return PreparedPackageExecutor(StageGenConfig()).plan(BELLWEATHER).graph


def test_planning_bellweather_reproduces_its_pinned_identity() -> None:
    graph = _bellweather_graph()

    assert len(graph.nodes) == BELLWEATHER_NODE_COUNT
    assert graph.graph_sha256 == BELLWEATHER_GRAPH_SHA256
    assert graph.topology_sha256 == BELLWEATHER_TOPOLOGY_SHA256


def test_the_plan_document_keeps_its_declared_vocabulary() -> None:
    """Header, document kinds, and operation counts stay this application's."""

    graph = _bellweather_graph()

    assert graph.kind == "sideview-platformer-execution-graph-v1"
    assert graph.recipe == "sideview-platformer"
    assert graph.game_id == "bellweather"
    assert graph.identity_header()["recipe"] == "sideview-platformer"
    assert graph.view_header() == {"recipe": "sideview-platformer", "game_id": "bellweather"}
    assert graph.annotator_key() == "sideview-platformer"

    assert ExecutionGraph.TRACE_EVENT_KIND == "sideview-platformer-execution-event-v1"
    assert ExecutionGraph.RUN_SUMMARY_KIND == "sideview-platformer-execution-summary-v1"
    assert ExecutionGraph.PROJECTION_KIND == "sideview-platformer-execution-projection-v1"
    assert ExecutionGraph.VIEW_KIND == "sideview-platformer-execution-view-v1"

    # Every declared operation is reported, so a zero count stays visible.
    counts = graph.operation_counts()
    assert set(counts) == {operation.value for operation in OperationKind}
    assert LOCAL_OPERATION in counts
    assert sum(counts.values()) == BELLWEATHER_NODE_COUNT
    assert LOCAL_OPERATION not in graph.provider_operation_vocabulary()


def test_local_nodes_are_the_ones_without_a_provider_route() -> None:
    graph = _bellweather_graph()

    for node in graph.nodes:
        assert node.is_local == (node.provider is None)
        assert node.is_local == (node.operation == LOCAL_OPERATION)


def test_every_node_declares_a_registered_type_with_matching_policy() -> None:
    """The plan and the type census agree: no orphan type ids, no policy drift."""

    graph = _bellweather_graph()
    types = platformer_type_index()

    for node in graph.nodes:
        declared = types[node.type_id]
        assert node.operation == declared.operation
        assert node.max_attempts == declared.policy.max_attempts
        assert node.ports, f"{node.node_id} declares no ports"
