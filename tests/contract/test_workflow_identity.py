"""Every identity a code move must not change, recomputed from code against one golden.

The golden holds values only, so moving a module changes the writer's imports and never
the fixture. A failure names what moved and what it costs; re-pin a section with
``scripts/write_workflow_identity.py --only SECTION`` only when that cost is the intent.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.write_workflow_identity import (
    CACHE_KEY_PLANS,
    GOLDEN_PATH,
    INPUTS_PATH,
    SECTIONS,
    differences,
)
from tests.support.cache_key_golden import assert_cache_keys_match

GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

#: What a change to each value-only section costs; cache_keys price themselves per node.
COSTS = {
    "movie_sprite_sources": "moves paid movie-sprite generate/finish keys",
    "portrait_implementation": "prepared portrait runs can no longer be resumed or verified",
    "character_frozen_set": (
        "a character_3d member changed: supported mode needs a paid qualification cohort, "
        "not a carry-over"
    ),
    "identities": (
        "a persisted identity moved: runs, caches and consumers that read it back stop matching"
    ),
}


@pytest.fixture(autouse=True)
def _no_stage_gen_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(os.environ):
        if name.startswith("STAGE_GEN_"):
            monkeypatch.delenv(name)


def test_the_golden_pins_every_section_and_plan() -> None:
    assert set(GOLDEN) == set(SECTIONS) == {*COSTS, "cache_keys"}
    assert set(GOLDEN["cache_keys"]) == set(CACHE_KEY_PLANS)


def test_input_bytes_are_small_constants() -> None:
    assert INPUTS_PATH.stat().st_size < 256 * 1024
    assert set(json.loads(INPUTS_PATH.read_text(encoding="utf-8"))) == {
        "looping-parallax",
        "movie-sprite-generate",
        "storefront",
    }


@pytest.mark.parametrize("section", sorted(COSTS))
def test_section_is_pinned(section: str, tmp_path: Path) -> None:
    moved = differences(GOLDEN[section], SECTIONS[section](tmp_path), section)
    assert not moved, "\n".join(
        [
            f"{section} moved: {COSTS[section]}",
            *moved,
            f"  rewrite with scripts/write_workflow_identity.py --only {section} "
            "only if that is the intent",
        ]
    )


@pytest.mark.parametrize("name", sorted(CACHE_KEY_PLANS))
def test_cache_keys_are_pinned(name: str, tmp_path: Path) -> None:
    assert_cache_keys_match(
        CACHE_KEY_PLANS[name](tmp_path),
        GOLDEN["cache_keys"][name],
        label=f"workflow-identity.json cache_keys.{name}",
    )
