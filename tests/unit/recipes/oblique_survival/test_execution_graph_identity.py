"""Pinned identity for the four scopes planned against the committed package.

A digest here moves only when the recipe deliberately changes what it plans, and
a scope's node count and topology are the coarse shape of that: what a node is
worth is pinned in ``test_cache_keys.py`` beside this file. Record why, in this
docstring, whenever one is re-pinned.

Changelog
---------
2026-09-06  First pin, when the recipe was promoted out of the spike. The four
            scopes are the ladder the recipe is built around: minimal proves the
            oblique clause over six props, props adds the rest of the standing
            world, actors adds the cast, and full adds the audio, the weather and
            the seasons. The full scope's operation counts are the ones the paid
            run ``full-v66`` recorded: 152 local, 101 images, 12 tool loops, 9
            structured judgements, 3 sound effects, no music (both tracks adopt
            an auditioned take).

            Every topology digest is NEW against that run, and deliberately so.
            The promoted graph's identity header carries only the scope where the
            spike's carried more, and the resource ids were renamed; both ride the
            topology digest and neither is a cache-key input, so not one provider
            node's key moved with them. That is exactly what the split between
            this file and ``test_cache_keys.py`` is for.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from stage_gen.config import StageGenConfig
from stage_gen.recipes.oblique_survival.survival_executor import ObliqueSurvivalExecutor
from stage_gen.recipes.oblique_survival.survival_graph import (
    OBLIQUE_SURVIVAL_GRAPH_SCHEMA_VERSION,
    ObliqueSurvivalGraph,
)
from stage_gen.recipes.oblique_survival.survival_types import SCOPES
from stage_gen.recipes.oblique_survival.survival_view import OBLIQUE_SURVIVAL_VIEW_KIND

REPOSITORY_ROOT: Final = Path(__file__).parents[4]
PACKAGE: Final = REPOSITORY_ROOT / "library/games/ember-hollow"


@dataclass(frozen=True, slots=True)
class ScopeIdentity:
    """What one scope plans: how many nodes, in what shape, spending what."""

    node_count: int
    topology_sha256: str
    operations: dict[str, int]


IDENTITIES: Final = {
    "minimal": ScopeIdentity(
        node_count=71,
        topology_sha256="c51f9850cd50d6dbc0d178c60edfef7dd350326dad91d5b914851771b00538eb",
        operations={
            "local": 43,
            "image_generation": 22,
            "tool_loop": 6,
            "structured_generation": 0,
            "music_generation": 0,
            "sound_effect_generation": 0,
        },
    ),
    "props": ScopeIdentity(
        node_count=185,
        topology_sha256="5aa780cf86378d0175c3345716ea8f2435e3e4ccc0099bee080a9a77eb8feb17",
        operations={
            "local": 97,
            "image_generation": 73,
            "tool_loop": 12,
            "structured_generation": 3,
            "music_generation": 0,
            "sound_effect_generation": 0,
        },
    ),
    "actors": ScopeIdentity(
        node_count=235,
        topology_sha256="edd75f1623fc8dce589210b9b120971a54cb0e456cb0fe78b19a966d2433e255",
        operations={
            "local": 121,
            "image_generation": 94,
            "tool_loop": 12,
            "structured_generation": 8,
            "music_generation": 0,
            "sound_effect_generation": 0,
        },
    ),
    "full": ScopeIdentity(
        node_count=277,
        topology_sha256="df7e69d900ddf28e70d74920057e892f9f7e7de30e761376a2defd7b5c5c5a64",
        operations={
            "local": 152,
            "image_generation": 101,
            "tool_loop": 12,
            "structured_generation": 9,
            "music_generation": 0,
            "sound_effect_generation": 3,
        },
    ),
}


def _plan(scope: str) -> ObliqueSurvivalGraph:
    return ObliqueSurvivalExecutor(StageGenConfig()).plan(PACKAGE, scope).graph


def test_planning_every_scope_reproduces_its_pinned_identity() -> None:
    assert sorted(IDENTITIES) == sorted(SCOPES)
    for scope, identity in IDENTITIES.items():
        graph = _plan(scope)
        assert graph.scope == scope
        assert len(graph.nodes) == identity.node_count, scope
        assert graph.topology_sha256 == identity.topology_sha256, scope
        assert graph.operation_counts() == identity.operations, scope


def test_planning_twice_plans_the_same_graph() -> None:
    """Planning is a pure function of the package, or a plan could not be a price."""

    for scope in SCOPES:
        first, second = _plan(scope), _plan(scope)
        assert first.graph_sha256 == second.graph_sha256, scope
        assert first.topology_sha256 == second.topology_sha256, scope


def test_the_ladder_only_ever_adds_nodes() -> None:
    previous: set[str] = set()
    for scope in SCOPES:
        planned = {node.node_id for node in _plan(scope).nodes}
        assert previous <= planned, f"{scope} dropped nodes a narrower scope had"
        previous = planned


def test_every_plan_keeps_the_recipe_vocabulary_it_declares() -> None:
    for scope in SCOPES:
        graph = _plan(scope)
        assert graph.schema_version == OBLIQUE_SURVIVAL_GRAPH_SCHEMA_VERSION
        assert graph.kind == "oblique-survival-execution-graph-v1"
        assert graph.recipe == "oblique-survival"
        assert graph.TRACE_EVENT_KIND == "oblique-survival-execution-event-v1"
        assert graph.RUN_SUMMARY_KIND == "oblique-survival-execution-summary-v1"
        assert graph.PROJECTION_KIND == "oblique-survival-execution-projection-v1"
        assert graph.VIEW_KIND == OBLIQUE_SURVIVAL_VIEW_KIND
        assert graph.annotator_key() == "oblique-survival"
        assert graph.presentation_profile == "elevated_oblique_perspective_ground_plane_v1"
        assert graph.terminal_node_id == "package-manifest"
        assert sum(graph.operation_counts().values()) == len(graph.nodes)
        assert set(graph.operation_counts()) == set(graph.operation_vocabulary())


def test_no_plan_can_assert_its_own_publication() -> None:
    for scope in SCOPES:
        assert _plan(scope).publication_authorized is False
