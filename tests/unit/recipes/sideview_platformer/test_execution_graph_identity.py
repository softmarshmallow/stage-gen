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

Re-pinned once more the same day when that runner member was retired outright. It was the
vehicle the runner genre was built against before Iron Petal existed - a sprinting restyle of
the platformer's own Wayfarer, reusing the same cover, referenced by no scenario, map, or
gameplay member on the platformer side. Iron Petal is the canonical runner game now, so
bellweather is a platformer package again and its closure shrinks by the whole ``runner/``
prefix. Platformer topology and operation counts are still untouched; only the closure the
document binds is smaller.

Re-pinned 2026-09-02 for ``game-ui-v2``. Two nine-slice atlas roles (``panel_frame`` and a
four-state ``button_rect`` sheet) join the UI domain as one generic typed triplet fanned out over
the role: six nodes, two image and two structured operations, two local admissions. Topology,
node count, and the UI cache identities all changed by design; the atlas image key hashes the
role's geometry record rather than template bytes, so a rasterizer change cannot re-bill it.

Re-pinned once more the same day for ``prepared-ui-atlas-validation-v2``: the atlas validate node
gained its own identity so a richer record (the measured ornament-free ``safe_rect``) re-runs the
local gate over cached sheets without touching the image key. Topology unchanged; the graph digest
moves with the two validate cache identities.

Re-pinned 2026-09-02 when the atlas triplet moved to its own home. Three other genres wanted the
same two roles, so the nodes now carry the component's taxonomy path (``2d/ui/atlas.*``) instead
of this recipe's, and the prompt they send is composed at plan time onto the card rather than in
the handler. A cache key hashes the type id, so the six UI atlas keys move and Bellweather re-bills
its two sheets exactly once; the topology digest moves with the renamed types, and every other
node in the plan is untouched.

Re-pinned 2026-09-02 for Bellweather's gameplay member at revision 5: the package now names the
``melee_sweep_v1`` weapon class and the ``arcade_v1`` number scale, both closed names the consumer
turns into numbers, and roughly doubles each hunting zone's population with a shorter respawn, so
no image or structured operation moves and topology is unchanged. The plan
document binds the whole closure, so the graph digest moves with the authored bytes. The working
tree this was pinned against also carried the ``game-ui-v3`` bump to ``ui.toml``; the digest
captures both, and lands or re-pins with that change.

Re-pinned once more the same day when the mob content model gained its optional ``aggression``
name and the manifest projection began carrying it. No authored byte moved, no operation moved;
the plan document's package projection did.
Re-pinned 2026-09-03 for ``game-ui-v4``: the preview icon set joins the UI domain as a third
role of the same shared triplet — one image, one local admission, one structured review — so the
node count rises by three and topology moves with the fan-out. The icon role is a fixed glyph grid
the document may only restyle; the two nine-slice roles' cache identities are untouched, because a
role's key hashes its own direction and geometry rather than the document as a whole.
Re-pinned 2026-09-03 again when Crowncrag Road's terrain request went from 96x16 to 56x24 (walk
surface row 21) with a brief that asks for storeys. The terrain table is the terrain node's own
identity, so that node and the local composite and review behind it moved; no layer, ground,
climbable, or portal image identity did, and the node count is unchanged.
Re-pinned 2026-09-03 a third time for a topology fix the reshape exposed: ground validation
composes its evidence over generated occupancy but declared no edge to the terrain node, so a
cache-cold run scheduled it before terrain.json existed. The edge moves ground-validate's
lineage and the topology digest; no provider node's identity moved.

Re-pinned 2026-09-03 a fourth time for ``map-terrain-design-v2``: the recipe now fences the
floor to a one-tile relief around the walk-surface datum instead of a free 1..8 depth, so the
level's interest hangs above the ground as floating decks, and the grammar gained ``shelves``,
the word that stacks decks over one column range. Neither lives in the authored terrain table,
so a cached design composed under the old rule and vocabulary would otherwise be reused
unexamined; the contract version is how both reach identity.
Re-pinned 2026-09-03 a fifth time for ``map-terrain-design-v3``: shelves are held to a validated
standing-room width, because the first v2 design took the advisory schema minimum of four
tiles for every deck. Same two nodes move; topology and image identities hold.
Re-pinned 2026-09-03 a sixth time for ``map-terrain-design-v4`` together with Crowncrag Road's
own reshape from 56x24 to 56x14 (walk surface row 11). The v3 map was too tall to read and each
shelves chunk was one narrow stack, so a shelves tier is now a lane of decks rather than a single
deck and the grid was shortened to the storeys it actually needs. The map document and the
contract version both feed the terrain node's key, so the same two nodes move.
Only the two terrain nodes and their dependants move; topology and every image identity hold.
Re-pinned 2026-09-03 a seventh time for authoring alone: the road's three spawn zones now name
``terrain_and_decks``, so their creatures stand on the storeys over the bank as well as on it.
That is a gameplay-document edit, so package resolve, gameplay validation, and the manifest move
and nothing else does -- no terrain, layer, ground, climbable, or portal identity, and no
provider node at all.
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

BELLWEATHER_NODE_COUNT = 230
BELLWEATHER_GRAPH_SHA256 = "96f601880d7a455fcacb808af2bfaed8dfcbd2fbf18f83d92ce05461ef84722c"
BELLWEATHER_TOPOLOGY_SHA256 = "819c43338c5e6305746a4aaca59a1ee52ab712f09b073a36ff8504b1d839bc87"


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
