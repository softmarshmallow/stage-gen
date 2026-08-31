"""The one compiler both recipes use to ask a provider for a track.

It lives with the authored intent rather than in a recipe because the two
guarantees it makes are not matters of genre taste: the performance and ending
follow the authored flags, and the output must be original. A recipe that wrote
its own prompt dropped the originality clause once; this is what makes that a
test failure instead of a shipped artifact.
"""

from __future__ import annotations

import pytest

from stage_gen.components.game_soundtrack import TrackGenerationIntent
from stage_gen.components.game_soundtrack.prompt import ORIGINALITY_CLAUSE, music_track_prompt


def _intent(*, instrumental: bool = True, seamless_loop: bool = True) -> TrackGenerationIntent:
    return TrackGenerationIntent(
        intent="generate",
        instrumental=instrumental,
        seamless_loop=seamless_loop,
        target_duration_seconds=75,
    )


@pytest.mark.parametrize("instrumental", [True, False])
@pytest.mark.parametrize("seamless_loop", [True, False])
@pytest.mark.parametrize("medium", ["a 2D game", "a visual novel scene"])
def test_every_compiled_prompt_carries_the_originality_clause(
    instrumental: bool, seamless_loop: bool, medium: str
) -> None:
    prompt = music_track_prompt(
        medium=medium,
        game_id="example",
        track_id="a_track",
        creative_brief="An original brief.",
        generation=_intent(instrumental=instrumental, seamless_loop=seamless_loop),
    )
    assert ORIGINALITY_CLAUSE in prompt


def test_an_instrumental_track_refuses_vocals_and_a_vocal_one_does_not() -> None:
    instrumental = music_track_prompt(
        medium="a 2D game",
        game_id="example",
        track_id="a_track",
        creative_brief="An original brief.",
        generation=_intent(instrumental=True),
    )
    assert "Instrumental only" in instrumental
    vocal = music_track_prompt(
        medium="a 2D game",
        game_id="example",
        track_id="a_track",
        creative_brief="An original brief.",
        generation=_intent(instrumental=False),
    )
    assert "Instrumental only" not in vocal


def test_a_looping_track_asks_for_no_fade_out_and_a_non_looping_one_asks_for_an_ending() -> None:
    looping = music_track_prompt(
        medium="a 2D game",
        game_id="example",
        track_id="a_track",
        creative_brief="An original brief.",
        generation=_intent(seamless_loop=True),
    )
    assert "no fade-out" in looping
    once = music_track_prompt(
        medium="a 2D game",
        game_id="example",
        track_id="a_track",
        creative_brief="An original brief.",
        generation=_intent(seamless_loop=False),
    )
    assert "deliberate musical ending" in once


def test_the_medium_and_optional_direction_are_the_recipe_s_only_say() -> None:
    without = music_track_prompt(
        medium="a visual novel scene",
        game_id="example",
        track_id="a_track",
        creative_brief="An original brief.",
        generation=_intent(),
    )
    with_direction = music_track_prompt(
        medium="a visual novel scene",
        game_id="example",
        track_id="a_track",
        creative_brief="An original brief.",
        generation=_intent(),
        direction="Composed to sit under dialogue.",
    )
    assert "for a visual novel scene" in without
    assert "Composed to sit under dialogue." in with_direction
    # The direction is additive; it never displaces the policy clause.
    assert with_direction.replace("Composed to sit under dialogue.\n", "") == without
