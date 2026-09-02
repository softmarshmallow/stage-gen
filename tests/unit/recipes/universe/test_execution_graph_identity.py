"""Pinned identity for both universe graphs planned against the committed fixture.

A digest here moves only when the recipe deliberately changes what it plans.
Record why, in this docstring, whenever one is re-pinned.

Changelog
---------
2026-09-03  First pin, when the recipe was promoted out of the spike.
            Semantic: 6 nodes. Gallery: 42 nodes over the fixture's 8 entities
            (one global direction, five nodes per entity, one terminal close).
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

FIXTURE = Path("library/games/lantern_ferry")
ADMITTED = Path("tests/contract/fixtures/universe/lantern_ferry.admitted-universe.json")

SEMANTIC_NODE_COUNT = 6
SEMANTIC_GRAPH_SHA256 = "dd6f0be572608404eb0dd6bf5db0d961bcd6889625e53fbbd16809bfac9c2001"
SEMANTIC_TOPOLOGY_SHA256 = "ef67f5dfad878dd308ce7a481b0f68cdf53b6626355dd186c42e29d6b9831e22"

GALLERY_NODE_COUNT = 42
GALLERY_GRAPH_SHA256 = "369b3409624c0626010ed9d2f798122426f32368e82f70159bda92a0c2031e33"
GALLERY_TOPOLOGY_SHA256 = "3cdc982dcad3f7bd6b0433bb50c5e61097559e6768fb02eb63d2d41799c2d62c"


def _semantic() -> UniverseGraph:
    resolved = resolve_universe_source(read_universe_document(FIXTURE), root=FIXTURE)
    return build_universe_semantic_graph(
        resolved, profile=universe_graph_profile(StageGenConfig(), images=False)
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
        profile=universe_graph_profile(StageGenConfig(), images=True),
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
        assert graph.kind == "universe-execution-graph-v1"
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
