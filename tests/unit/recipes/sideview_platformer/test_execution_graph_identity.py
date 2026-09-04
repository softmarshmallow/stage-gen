"""Bellweather's planned graph is pinned, and a moved node is named.

Two things are pinned. The topology digest and the node count say the graph
has the same shape; they move rarely and a move is worth a sentence. The
cache-key golden - ``bellweather.cache-keys.json``, one line per node - says
which nodes would re-bill; when it moves, the diff of the golden file names
the nodes, and the failure message counts the provider operations among them.

That replaces a single whole-graph digest that conflated four independent
facts (topology, node identity, cache keys, authored bytes) and was re-pinned
in twelve commits over three days, each with a hand-written paragraph saying
which of the four had moved. Now the diff says so.
"""

from __future__ import annotations

from pathlib import Path

from gnode import LOCAL_OPERATION
from stage_gen.config import StageGenConfig
from stage_gen.recipes.sideview_platformer.execution_graph import ExecutionGraph, OperationKind
from stage_gen.recipes.sideview_platformer.package_executor import PreparedPackageExecutor
from stage_gen.recipes.sideview_platformer.package_types import platformer_type_index
from tests.unit.recipes._cache_key_golden import assert_cache_keys_match_golden

REPOSITORY_ROOT = Path(__file__).parents[4]
BELLWEATHER = REPOSITORY_ROOT / "library/games/bellweather"
BELLWEATHER_CACHE_KEYS = Path(__file__).with_name("bellweather.cache-keys.json")

BELLWEATHER_NODE_COUNT = 230
# Re-pinned when the manifest gained per-block versions (C-R3): the terminal node\'s port
# kind is the manifest identity, so the topology moved with it. No cache key moved.
# Re-pinned again when the soundtrack family moved to its component (D8): the pair's
# type ids and the admission's port kind are the family's; both nodes keep this
# recipe's cache identity. No cache key moved.
# Re-pinned when the motion-rebase family moved to `sideview_actor` (D8): the pair's type
# ids, the port order and the verification's port are the family's; both nodes keep this
# recipe's cache identity. No cache key moved.
# Re-pinned when the manifest root lost its four unread fields (C6): the root kind moved to
# v12, and the terminal port kind is the manifest identity. No cache key moved.
# Re-pinned when the inventory-panel family moved to `game_ui` (B7): the triplet's type ids
# are the family's; all three keep this recipe's cache identity. No cache key moved.
BELLWEATHER_TOPOLOGY_SHA256 = "e66804985e78d4a49bd9025c9734d471563db8913db8e0b6e73a84db809e67c8"


def _bellweather_graph() -> ExecutionGraph:
    return PreparedPackageExecutor(StageGenConfig()).plan(BELLWEATHER).graph


def test_planning_bellweather_reproduces_its_pinned_identity() -> None:
    graph = _bellweather_graph()

    assert len(graph.nodes) == BELLWEATHER_NODE_COUNT
    assert graph.topology_sha256 == BELLWEATHER_TOPOLOGY_SHA256


def test_planning_bellweather_reproduces_its_cache_key_golden() -> None:
    assert_cache_keys_match_golden(_bellweather_graph(), BELLWEATHER_CACHE_KEYS)


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
