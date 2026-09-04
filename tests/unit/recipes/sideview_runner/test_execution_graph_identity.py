"""Iron Petal's planned graph is pinned the way Bellweather's is.

The topology digest is also embedded in ``docs/spec/game/runner.md`` by the
graph-contract writer; this test is the one that names a moved node.
"""

from __future__ import annotations

from pathlib import Path

from stage_gen.config import StageGenConfig
from stage_gen.recipes.sideview_runner.runner_executor import SideviewRunnerExecutor
from tests.unit.recipes._cache_key_golden import assert_cache_keys_match_golden

REPOSITORY_ROOT = Path(__file__).parents[4]
IRON_PETAL = REPOSITORY_ROOT / "library/games/iron-petal-unit"
IRON_PETAL_CACHE_KEYS = Path(__file__).with_name("iron-petal-unit.cache-keys.json")

IRON_PETAL_NODE_COUNT = 109
IRON_PETAL_TOPOLOGY_SHA256 = "c3be1f81d692cc3d2100e7b3955d76565c7d923031b404de60d77af401fd69e4"


def test_planning_iron_petal_reproduces_its_pinned_identity() -> None:
    graph = SideviewRunnerExecutor(StageGenConfig()).plan(IRON_PETAL).graph

    assert len(graph.nodes) == IRON_PETAL_NODE_COUNT
    assert graph.topology_sha256 == IRON_PETAL_TOPOLOGY_SHA256
    assert_cache_keys_match_golden(graph, IRON_PETAL_CACHE_KEYS)
