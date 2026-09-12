"""Pinned identity for both universe graphs planned against the committed fixture.

A digest here moves only when the recipe deliberately changes what it plans.
Record why, in this docstring, whenever one is re-pinned.

Changelog
---------
2026-09-03  First pin, when the recipe was promoted out of the spike.
            Semantic: 6 nodes. Gallery: 42 nodes over the fixture's 8 entities
            (one global direction, five nodes per entity, one terminal close).
2026-09-03  Both graph digests re-pinned after an adversarial review found three
            things outside node identity that decide what a node produces: the
            requested pixel size and the two proxy long edges, and the medium's
            forbidden-direction vocabulary and display name. All four now ride
            input digests. No node was added or removed, so both topology
            digests are unchanged — which is the point of the split.
2026-09-09  Gallery only re-pinned for the GPT Image 2.5 Sunburst/max route.
            The semantic graph and both topology digests are unchanged.
2026-09-09  Gallery only re-pinned again after exact current-canvas canaries
            calibrated its OpenRouter image planning range. Topology is unchanged.
2026-09-10  Gallery re-pinned when each image node moved from a legacy model
            row to a capability-admitted exact route snapshot. The node count is
            unchanged; topology now records each node's binding reference.
2026-09-10  Gallery graph identity re-pinned once more when route snapshots gained
            generic exact-size constraints. Output and topology identity stay fixed;
            the persisted capability evidence becomes stricter.
2026-09-10  Gallery graph identity re-pinned when reference-conditioned image
            bindings began sealing their concrete data-URL delivery capability.
            Node count and topology remain unchanged.
"""

from __future__ import annotations

from pathlib import Path

from stage_gen.config import StageGenConfig
from stage_gen.recipes.universe.universe_graph import (
    UniverseGraph,
    build_universe_gallery_graph,
    build_universe_semantic_graph,
    universe_graph_profile,
)
from stage_gen.recipes.universe.universe_request import (
    admitted_universe_from_document,
    read_universe_document,
    resolve_sample_ledger,
    resolve_universe_source,
)
from stage_gen.recipes.universe.universe_view import UNIVERSE_VIEW_KIND

FIXTURE = Path("src/stage_gen/recipes/universe/examples/lantern_ferry")
ADMITTED = Path("tests/contract/fixtures/universe/lantern_ferry.admitted-universe.json")
CONFIG = StageGenConfig()

SEMANTIC_NODE_COUNT = 6
SEMANTIC_GRAPH_SHA256 = "581db57e5c1145e590e935c360f82f9f8df86085563639437121341ab96be563"
SEMANTIC_TOPOLOGY_SHA256 = "e135e32f015b8418165a50fb0211ae81f0262a3c4656f810d05130fb59464027"

GALLERY_NODE_COUNT = 42
GALLERY_GRAPH_SHA256 = "5ecfaf3a65370277325e59f0c8e0a45d9cab40390febee553822dcd9d4297be9"
GALLERY_TOPOLOGY_SHA256 = "504d8dac5ee971ddf7eb600c5c3f7390c9d84b03f883df4ed3e42ffa5a54025d"


def _semantic() -> UniverseGraph:
    resolved = resolve_universe_source(read_universe_document(FIXTURE), root=FIXTURE)
    return build_universe_semantic_graph(
        resolved, profile=universe_graph_profile(CONFIG, images=False)
    )


def _gallery() -> UniverseGraph:
    resolved = resolve_universe_source(read_universe_document(FIXTURE), root=FIXTURE)
    admitted = admitted_universe_from_document(ADMITTED, poster_sha256=resolved.poster_sha256)
    samples = resolve_sample_ledger(
        universe_id=admitted.universe_id, entity_ids=admitted.entity_ids()
    )
    return build_universe_gallery_graph(
        resolved,
        admitted,
        samples=samples,
        config=CONFIG,
        profile=universe_graph_profile(CONFIG, images=True),
    )


def test_planning_the_semantic_phase_reproduces_its_pinned_identity() -> None:
    graph = _semantic()
    assert len(graph.nodes) == SEMANTIC_NODE_COUNT
    assert graph.graph_sha256 == SEMANTIC_GRAPH_SHA256
    assert graph.topology_sha256 == SEMANTIC_TOPOLOGY_SHA256


def test_planning_the_gallery_phase_reproduces_its_pinned_identity() -> None:
    graph = _gallery()
    assert len(graph.nodes) == GALLERY_NODE_COUNT
    assert graph.graph_sha256 == GALLERY_GRAPH_SHA256
    assert graph.topology_sha256 == GALLERY_TOPOLOGY_SHA256


def test_both_plans_keep_the_recipe_vocabulary_they_declare() -> None:
    for graph in (_semantic(), _gallery()):
        assert graph.kind == "universe-execution-graph-v2"
        assert graph.recipe == "universe"
        assert graph.TRACE_EVENT_KIND == "universe-execution-event-v1"
        assert graph.RUN_SUMMARY_KIND == "universe-execution-summary-v1"
        assert graph.PROJECTION_KIND == "universe-execution-projection-v1"
        assert graph.VIEW_KIND == UNIVERSE_VIEW_KIND
        assert graph.annotator_key() == "universe"
        assert sum(graph.operation_counts().values()) == len(graph.nodes)
        assert set(graph.operation_counts()) == set(graph.operation_vocabulary())


def test_neither_plan_can_assert_its_own_publication() -> None:
    for graph in (_semantic(), _gallery()):
        assert graph.publication_authorized is False
