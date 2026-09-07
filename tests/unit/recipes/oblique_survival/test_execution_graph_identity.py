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

2026-09-06  The interface joins the props scope and above: nine nodes, the
            shared game_ui triplet (generate, gate, review) over the panel frame,
            the button sheet and the preview icon grid, planned when the package
            authors a ``ui.toml``. Three images and three structured reviews per
            scope from ``props`` up; ``minimal`` is untouched, and its topology
            digest proves it. Every other node's key holds (``test_cache_keys``).

2026-09-07  The pointer joins the interface: three more nodes from ``props`` up,
            the same triplet over the optional ``cursor_set`` role Ember Hollow's
            ``ui.toml`` declares (``game-ui-v5``). One image and one structured
            review per scope from ``props`` up; ``minimal`` is untouched again.

2026-09-07  The world places nothing the player cannot act on (decision 0060):
            the litter sheet, the standing-plant sheet and its winter look, and
            the inert fern clump leave every scope — eleven nodes from ``full``
            (three images, one of them a paintover; the rest local). The forage
            adopt and validate move with the sheet's new per-cell sizes, the
            layout with its object list, the lock with the package text. Zero
            provider operations re-bill (``test_cache_keys`` shows no image key
            moved); the three family judgements re-run because their sheets
            lost members. The manifest port and record now name the kind from
            ``manifest.MANIFEST_KIND`` (``oblique-survival-manifest-v2``: one
            sheet of ground pieces, each cell sized) instead of a literal, which
            is the second move of every topology digest in one day.

2026-09-07  The shell joins the props scope and above: thirteen nodes, the shared
            game_shell triplet (draw, gate, review) over the four plates Ember
            Hollow's ``shell.toml`` declares — three opening shots, the title
            backdrop and the title emblem. Four images and four structured
            reviews per scope from ``props`` up; ``minimal`` is untouched and its
            topology digest proves it, the third time that split has held. The
            loading backdrop is bound to the winter season look the run already
            draws, so it costs nothing and plans no node. Only ``source-lock``
            and ``package-manifest`` move a cache key (the package text grew a
            document); no paid node re-bills, which ``test_cache_keys`` shows.

2026-09-07  The opening is filmed. Its three shots are clips rather than stills, so
            three image nodes leave every scope from ``props`` up and three video
            nodes arrive, and the family's node count rises by two per scope: a
            clip is a four-node chain (film, gate, publish, review) where a still
            is three. ``minimal`` is untouched again.

2026-09-07  Video is promoted, and every topology digest moves without a single
            node moving with it: the node counts are the same 64, 199, 249 and
            291, and what changed is the binding table, which gained the clip
            route and therefore a resource the scheduler gates on. ``minimal``
            moving is the proof - it plans no shell and no clip at all, so a
            digest that shifted there can only have come from the route list.
            Ember Hollow authors no clip shot, so the family costs nothing here;
            a document that declares one plans four nodes for it and one video
            operation, and a shot longer than the route's declared ceiling is
            refused while planning rather than counted.
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
        node_count=64,
        topology_sha256="f22f834f204bee5004f72766651607f57ac9889c7d7bc803174a2d5597a04092",
        operations={
            "local": 38,
            "image_generation": 21,
            "tool_loop": 5,
            "structured_generation": 0,
            "music_generation": 0,
            "sound_effect_generation": 0,
            "video_generation": 0,
        },
    ),
    "props": ScopeIdentity(
        node_count=202,
        topology_sha256="8193f32c43d5b8da20e0db427ec4d9624bc3173da260e0797584d34f08ceb87a",
        operations={
            "local": 102,
            "image_generation": 75,
            "tool_loop": 11,
            "structured_generation": 11,
            "music_generation": 0,
            "sound_effect_generation": 0,
            "video_generation": 3,
        },
    ),
    "actors": ScopeIdentity(
        node_count=252,
        topology_sha256="f17686374c644d1f08fa08e18cffa694317a455ce90771ae52bee810e2a457ec",
        operations={
            "local": 126,
            "image_generation": 96,
            "tool_loop": 11,
            "structured_generation": 16,
            "music_generation": 0,
            "sound_effect_generation": 0,
            "video_generation": 3,
        },
    ),
    "full": ScopeIdentity(
        node_count=294,
        topology_sha256="2296dcdbf01fa6b5048c788e7e877a397c3b2b5dc1bc58f74c1a2aebd9ee1b90",
        operations={
            "local": 157,
            "image_generation": 103,
            "tool_loop": 11,
            "structured_generation": 17,
            "music_generation": 0,
            "sound_effect_generation": 3,
            "video_generation": 3,
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
