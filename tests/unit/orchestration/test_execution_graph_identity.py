"""Pinned identity for the prepared-game plan.

The engine may move; the graph a package plans to may not. These digests were
captured before the engine was extracted into ``gnode`` and must only ever
change when the recipe deliberately changes what it plans — never as a side
effect of moving code, renaming a symbol, or re-declaring a provider route.
"""

from __future__ import annotations

from pathlib import Path

from gnode import LOCAL_OPERATION
from stage_gen.config import StageGenConfig
from stage_gen.orchestration.execution_graph import ExecutionGraph, OperationKind
from stage_gen.recipes.scrolling_preview.package_executor import PreparedPackageExecutor

REPOSITORY_ROOT = Path(__file__).parents[3]
BELLWEATHER = REPOSITORY_ROOT / "library/games/bellweather"

BELLWEATHER_NODE_COUNT = 221
BELLWEATHER_GRAPH_SHA256 = "d7487ec53683cf4942fac4b2afca31a1c27632f07d1247af828e2ad7aedd9567"
BELLWEATHER_TOPOLOGY_SHA256 = "bbca9d958ba295b5b5e662cd0caeb320bdf9719f2b8f0944f08908ad4f55d169"


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

    assert graph.kind == "prepared-game-execution-graph-v1"
    assert graph.recipe == "scrolling-preview"
    assert graph.game_id == "bellweather"
    assert graph.identity_header()["recipe"] == "scrolling-preview"
    assert graph.view_header() == {"recipe": "scrolling-preview", "game_id": "bellweather"}
    assert graph.annotator_key() == "scrolling-preview"

    assert ExecutionGraph.TRACE_EVENT_KIND == "prepared-game-execution-event-v1"
    assert ExecutionGraph.RUN_SUMMARY_KIND == "prepared-game-execution-summary-v1"
    assert ExecutionGraph.PROJECTION_KIND == "prepared-game-execution-projection-v1"
    assert ExecutionGraph.VIEW_KIND == "prepared-game-execution-view-v1"

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
