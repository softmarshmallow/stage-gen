"""Iron Petal's planned graph is pinned the way Bellweather's is.

The topology digest is also embedded in ``docs/spec/game/runner.md`` by the
graph-contract writer; this test is the one that names a moved node.
"""

from __future__ import annotations

from pathlib import Path

from stage_gen.config import StageGenConfig
from stage_gen_legacy.recipes.sideview_runner.runner_executor import SideviewRunnerExecutor
from tests.unit.recipes._cache_key_golden import assert_cache_keys_match_golden

REPOSITORY_ROOT = Path(__file__).parents[4]
IRON_PETAL = REPOSITORY_ROOT / "godot/legacy/inputs/iron-petal-unit"
IRON_PETAL_CACHE_KEYS = Path(__file__).with_name("iron-petal-unit.cache-keys.json")

IRON_PETAL_NODE_COUNT = 109
# Re-pinned when the manifest gained per-block versions (C-R3): the terminal node\'s port
# kind is the manifest identity, so the topology moved with it. No cache key moved.
# Re-pinned again when the soundtrack family moved to its component (D8): the pair's
# type ids are the family's, the generate node keeps this recipe's cache identity and
# contract, and the two admissions converged on the family's record - three local keys
# moved (both admissions and the manifest that depends on them), no provider key.
# Re-pinned when the motion-rebase family moved to `sideview_actor` (D8): the pair's type
# ids are the family's; both nodes keep this recipe's cache identity and contracts. No
# cache key moved.
# Re-pinned when the layer family moved to `sideview_layers` (D8): the four type ids and
# the port kinds are the family's; the paid nodes keep this recipe's cache identity and
# contracts, and the three admissions converged on the family's - three local keys moved
# (and the manifest downstream), no provider key.
# The GPT Image 2.5 Sunburst/max migration deliberately moved 84 of 109 keys:
# all 39 image operations, seven structured and two tool-loop consumers, and 36
# local descendants. Topology and the other 25 keys are unchanged.
# Re-pinned for capability-first image routing: all 39 image nodes now seal exact route and
# output-option identity, and their cache descendants move with that intentional provenance.
# Re-pinned when generic exact-size admission refused to claim that OpenRouter accepts the
# runner's custom production canvases. Those nodes now bind the checked OpenAI route.
IRON_PETAL_TOPOLOGY_SHA256 = "f634afc9c267d21b68e091c09eebaeafcae85b5b713ac3fa3b2a63b4105f6ff9"


def test_planning_iron_petal_reproduces_its_pinned_identity() -> None:
    graph = SideviewRunnerExecutor(StageGenConfig()).plan(IRON_PETAL).graph

    assert len(graph.nodes) == IRON_PETAL_NODE_COUNT
    assert graph.topology_sha256 == IRON_PETAL_TOPOLOGY_SHA256
    assert_cache_keys_match_golden(graph, IRON_PETAL_CACHE_KEYS)
