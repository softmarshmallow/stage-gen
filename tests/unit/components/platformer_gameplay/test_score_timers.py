"""The two additive blocks a minigame authors and a story game leaves out (C5)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from stage_gen.components.platformer_gameplay.models import ScorePolicy, TimerEntry, TimersPolicy
from stage_gen.recipes.manifest_blocks import present_blocks
from stage_gen.recipes.sideview_platformer.prepared_manifest import (
    PLATFORMER_MANIFEST_BLOCK_VERSIONS,
    _score_block,
    _timers_block,
)


def test_a_score_names_closed_events_with_bounded_points() -> None:
    policy = ScorePolicy.model_validate({"awards": {"mob_defeated": 100, "item_collected": 10}})
    assert policy.display == "hud"
    with pytest.raises(ValidationError):
        ScorePolicy.model_validate({"awards": {"treasure_found": 5}})
    with pytest.raises(ValidationError, match="between 1 and 1000000"):
        ScorePolicy.model_validate({"awards": {"mob_defeated": 0}})
    with pytest.raises(ValidationError):
        ScorePolicy.model_validate({"awards": {}})


def test_timers_are_unique_and_end_the_session() -> None:
    timers = TimersPolicy.model_validate(
        {"entries": [{"timer_id": "run", "seconds": 90, "on_end": "session_ended"}]}
    )
    assert timers.entries[0] == TimerEntry(
        timer_id="run", seconds=90, on_end="session_ended", display="hud"
    )
    with pytest.raises(ValidationError, match="timer_id"):
        TimersPolicy.model_validate(
            {
                "entries": [
                    {"timer_id": "run", "seconds": 90, "on_end": "session_ended"},
                    {"timer_id": "run", "seconds": 30, "on_end": "session_ended"},
                ]
            }
        )
    with pytest.raises(ValidationError):
        TimersPolicy.model_validate(
            {"entries": [{"timer_id": "run", "seconds": 0, "on_end": "session_ended"}]}
        )


def test_the_blocks_are_published_only_when_authored() -> None:
    quiet = SimpleNamespace(
        package=SimpleNamespace(gameplay=SimpleNamespace(score=None, timers=None))
    )
    assert _score_block(quiet) is None and _timers_block(quiet) is None  # type: ignore[arg-type]
    every_block_quiet = dict.fromkeys(PLATFORMER_MANIFEST_BLOCK_VERSIONS)
    table = present_blocks(PLATFORMER_MANIFEST_BLOCK_VERSIONS, every_block_quiet)
    assert "score" not in table and "timers" not in table
    authored = SimpleNamespace(
        package=SimpleNamespace(
            gameplay=SimpleNamespace(
                score=ScorePolicy.model_validate({"awards": {"wave_cleared": 500}}),
                timers=TimersPolicy.model_validate(
                    {"entries": [{"timer_id": "run", "seconds": 90, "on_end": "session_ended"}]}
                ),
            )
        )
    )
    score = _score_block(authored)  # type: ignore[arg-type]
    timers = _timers_block(authored)  # type: ignore[arg-type]
    assert score == {"awards": {"wave_cleared": 500}, "display": "hud"}
    assert timers == {
        "entries": [{"timer_id": "run", "seconds": 90, "on_end": "session_ended", "display": "hud"}]
    }
    table = present_blocks(
        PLATFORMER_MANIFEST_BLOCK_VERSIONS, {**every_block_quiet, "score": score, "timers": timers}
    )
    assert table["score"] == "platformer-score-block-v1"
    assert table["timers"] == "platformer-timers-block-v1"
