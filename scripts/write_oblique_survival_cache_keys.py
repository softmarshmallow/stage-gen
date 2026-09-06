#!/usr/bin/env python3
"""Check or rewrite the oblique-survival cache-key golden.

Every provider node's cache key is what a run is billed against: a key that moved
is a picture that will be drawn again. The golden holds one key per node per
scope for the committed package, so a change that moves one is a diff a reviewer
reads and prices rather than a surprise on the next run.

    uv run python scripts/write_oblique_survival_cache_keys.py          # check
    uv run python scripts/write_oblique_survival_cache_keys.py --write  # rewrite

Rewriting is a decision, not a fix. Read the diff first: the test that fails
against this file names every moved node and estimates what redrawing them costs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stage_gen.config import StageGenConfig
from stage_gen.recipes.oblique_survival.survival_executor import ObliqueSurvivalExecutor
from stage_gen.recipes.oblique_survival.survival_types import SCOPES

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPOSITORY_ROOT / "library/games/ember-hollow"
GOLDEN = REPOSITORY_ROOT / "tests/contract/fixtures/oblique_survival/ember-hollow.cache-keys.json"


def cache_keys() -> dict[str, dict[str, str]]:
    """One ``node_id -> cache_key`` map per scope, planned offline from the package."""

    executor = ObliqueSurvivalExecutor(StageGenConfig())
    keys: dict[str, dict[str, str]] = {}
    for scope in SCOPES:
        graph = executor.plan(PACKAGE, scope).graph
        keys[scope] = {node.node_id: node.cache_key for node in graph.nodes}
    return keys


def render() -> str:
    return json.dumps(cache_keys(), indent=1, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="rewrite the golden")
    args = parser.parse_args()
    rendered = render()
    relative = GOLDEN.relative_to(REPOSITORY_ROOT)
    if args.write:
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(rendered, encoding="utf-8")
        print(f"wrote {relative}")
        return 0
    if not GOLDEN.exists() or GOLDEN.read_text(encoding="utf-8") != rendered:
        print(f"{relative} is stale; read the diff, then run with --write")
        return 1
    print(f"{relative} is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
