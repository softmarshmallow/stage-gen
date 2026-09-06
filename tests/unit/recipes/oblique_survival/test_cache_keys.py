"""The committed cache-key golden: what a run of Ember Hollow would be billed.

A key that moved is a picture that will be drawn again, so the golden holds one
``node_id -> cache_key`` map per scope and the assertion below names and prices
whatever moved. Rewrite it with ``scripts/write_oblique_survival_cache_keys.py
--write``, and only after reading the diff.

Two claims the reuse story rests on live here, because the spike proved them
against paid runs on one machine and this file proves them against committed
bytes on every machine:

* a node the scope ladder shares has one key in every scope, or a narrow run's
  artifacts are paid for a second time by the wide one that follows it;
* an authored edit moves exactly the keys that read it, and no others.

Changelog
---------
2026-09-06  First pin, when the recipe was promoted out of the spike. Compared
            node by node against the key map dumped from the spike before the
            move (the Freeze phase's oracle, whose ``full`` scope is the paid
            run ``full-v66``): every one of the 768 nodes across the four scopes
            holds the key the spike gave it, except ``source-lock`` and
            ``package-manifest`` in each scope. Those two moved because the
            authored package's text had to change -- the document kinds were
            re-versioned to the repository's identity grammar and every take is
            now declared by digest -- and ``source_digest`` is a function of
            that text. Both are local nodes with no provider, every other node
            takes the lock as a barrier rather than as lineage, and so the paid
            run still restores at zero provider operations.
2026-09-06  Nine keys added per scope from ``props`` up, the shared game_ui
            triplet over three sheet roles, when ``ui.toml`` joined the package;
            ``source-lock`` and ``package-manifest`` moved with the source digest.
            No other key moved: the interface is new spend, not a redraw.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Final

import pytest

from gnode import LOCAL_OPERATION
from stage_gen.config import StageGenConfig
from stage_gen.recipes.oblique_survival.models import Package
from stage_gen.recipes.oblique_survival.survival_graph import ObliqueSurvivalGraph, build_graph
from stage_gen.recipes.oblique_survival.survival_request import load_package
from stage_gen.recipes.oblique_survival.survival_types import SCOPES
from tests.unit.recipes._cache_key_golden import assert_cache_keys_match

REPOSITORY_ROOT: Final = Path(__file__).parents[4]
PACKAGE: Final = REPOSITORY_ROOT / "library/games/ember-hollow"
GOLDEN_PATH: Final = (
    REPOSITORY_ROOT / "tests/contract/fixtures/oblique_survival/ember-hollow.cache-keys.json"
)

#: What the four scopes plan for the committed package. A count here moves only
#: when the recipe deliberately plans more or fewer nodes.
SCOPE_NODE_COUNTS: Final = {"minimal": 71, "props": 194, "actors": 244, "full": 286}

#: A biome's brief is read by its own plate, by the sheet the ground review is
#: judged from, and by the manifest that measures what was published. Nothing
#: else, which is why re-briefing one plate is a cheap decision.
GROUND_CLAUSE_READERS: Final = frozenset(
    {
        "ground-forest-floor-adopt",
        "ground-forest-floor-canonicalize",
        "review-ground-sheet",
        "review-ground-judge",
        "package-manifest",
    }
)


@pytest.fixture(scope="module")
def package() -> Package:
    return load_package(PACKAGE)


@pytest.fixture(scope="module")
def golden() -> dict[str, dict[str, str]]:
    loaded = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return {scope: dict(keys) for scope, keys in loaded.items()}


def _graph(package: Package, scope: str) -> ObliqueSurvivalGraph:
    return build_graph(StageGenConfig(), package, scope)


def test_the_golden_holds_for_every_scope(
    package: Package, golden: dict[str, dict[str, str]]
) -> None:
    """The whole regression guard for provider spend, in one assertion per scope."""

    assert sorted(golden) == sorted(SCOPES)
    for scope in SCOPES:
        assert_cache_keys_match(
            _graph(package, scope), golden[scope], label=f"{GOLDEN_PATH.name}[{scope}]"
        )


def test_every_scope_plans_the_node_count_the_golden_records(
    golden: dict[str, dict[str, str]],
) -> None:
    for scope, count in SCOPE_NODE_COUNTS.items():
        assert len(golden[scope]) == count, scope


def test_a_node_the_ladder_shares_has_one_key_in_every_scope(
    golden: dict[str, dict[str, str]],
) -> None:
    """This is what makes a narrow run pay for the wide one instead of being redrawn.

    The terminal manifest is the single exception: it depends on every node in
    its own graph, so a wider scope legitimately gives it a wider identity.
    """

    narrow = golden["minimal"]
    for scope in ("props", "actors", "full"):
        wider = golden[scope]
        assert set(narrow) <= set(wider), f"{scope} dropped nodes a narrower scope had"
        moved = [
            node_id
            for node_id, key in narrow.items()
            if node_id != "package-manifest" and wider[node_id] != key
        ]
        assert moved == [], f"{scope} moved: {moved}"


def test_re_briefing_one_ground_plate_moves_exactly_the_keys_that_read_it(
    package: Package, golden: dict[str, dict[str, str]]
) -> None:
    """An edit is priced by what it moves, and the price is read off this diff.

    The spike proved this against two paid runs it happened to have on disk. The
    claim is the same and the evidence is now committed: re-brief the forest
    floor and exactly its own plate, the sheet the ground review is judged from,
    that review, and the manifest move -- one provider operation, not a redraw
    of the wood.
    """

    biomes = list(package.biomes)
    index = next(i for i, biome in enumerate(biomes) if biome.biome_id == "forest_floor")
    biomes[index] = replace(biomes[index], prompt=biomes[index].prompt + " Brighter.")
    graph = _graph(replace(package, biomes=tuple(biomes)), "full")

    before = golden["full"]
    after = {node.node_id: node.cache_key for node in graph.nodes}
    assert set(after) == set(before), "re-briefing a plate added or dropped a node"
    moved = {node_id for node_id, key in before.items() if after[node_id] != key}
    assert moved == GROUND_CLAUSE_READERS, sorted(moved ^ GROUND_CLAUSE_READERS)

    billed = [
        node_id for node_id in sorted(moved) if graph.node(node_id).operation != LOCAL_OPERATION
    ]
    assert billed == ["review-ground-judge"], billed


def test_the_golden_carries_no_key_from_a_node_the_recipe_does_not_plan(
    package: Package, golden: dict[str, dict[str, str]]
) -> None:
    """A golden is only a guard while every line in it still names something."""

    for scope in SCOPES:
        planned = {node.node_id for node in _graph(package, scope).nodes}
        assert set(golden[scope]) == planned, scope
