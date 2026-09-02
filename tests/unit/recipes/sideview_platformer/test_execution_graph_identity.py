"""Pinned identity for the prepared-game plan.

The engine may move; the graph a package plans to may not. These digests must
only ever change when the recipe deliberately changes what it plans — never as
a side effect of moving code, renaming a symbol, or re-declaring a provider
route. Re-pinned 2026-08-31 for the node-ABI schema bump (typed nodes, ports,
and the taxonomy-aligned persisted vocabulary), which changed every digest by
design in one coordinated move.

Re-pinned again 2026-08-31: the node card gained ``authored_inputs`` so that a
package member a node is handed can never be invisible in the plan. Bellweather
plans exactly the same work — the topology digest below is unchanged, and no
cache key moved, because the card is not part of one — but every card now
carries the field, so the document digest moves with it. This recipe declares
no authored inputs yet; wiring its reference images through the new field is a
deliberate later change that will move this digest again.

Re-pinned 2026-09-01 after the shared Bellweather container gained the required
runner audio member and optional runner soundtrack. Platformer topology and
operation count remain unchanged; the plan document binds the package closure,
so its graph digest moves with those newly captured authored members.

Re-pinned 2026-09-02 for ``alpha-component-repack-v3``. The fused-component fallback now
requires one higher-alpha principal core in every expected source lattice slot. The local repack
cache identity changed deliberately while provider operations and topology stayed fixed.

Re-pinned again 2026-09-02 for ``runner-gameplay-v3``. Bellweather's runner member re-authored
its gameplay closure - the collision box split away from what a contact costs, and a vitals
gauge arrived, and the container's own revision moved with it - and the plan document binds the
whole package closure, so the platformer's graph digest moves with a sibling member it does not
read. Topology, node count, and operation counts are all unchanged, which is the same shape as
the 2026-09-01 re-pin above.
"""

from __future__ import annotations

from pathlib import Path

from gnode import LOCAL_OPERATION
from stage_gen.config import StageGenConfig
from stage_gen.recipes.sideview_platformer.execution_graph import ExecutionGraph, OperationKind
from stage_gen.recipes.sideview_platformer.package_executor import PreparedPackageExecutor
from stage_gen.recipes.sideview_platformer.package_types import platformer_type_index

REPOSITORY_ROOT = Path(__file__).parents[4]
BELLWEATHER = REPOSITORY_ROOT / "library/games/bellweather"

BELLWEATHER_NODE_COUNT = 221
BELLWEATHER_GRAPH_SHA256 = "d2d550ccbfa695c8dcd3f8d3bee72a669653c0842cd035e836afa4e085c543e4"
BELLWEATHER_TOPOLOGY_SHA256 = "2cf9fc619702263ac2954e9e28bc22f47227735d1eadbf08d58ebe5573c36c2d"


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
