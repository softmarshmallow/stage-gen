"""Optional demo application decisions remain outside the public product."""

import pytest

from demo_game_tools.application import resolve_genre
from stage_gen.application import UsageError


def test_a_genre_defaults_only_when_the_package_declares_one() -> None:
    assert resolve_genre(["platformer"], None) == "platformer"
    assert resolve_genre(["platformer", "runner"], "runner") == "runner"
    with pytest.raises(UsageError, match="--genre is required"):
        resolve_genre(["platformer", "runner"], None)
    with pytest.raises(UsageError, match="not declared"):
        resolve_genre(["platformer"], "runner")
    assert issubclass(UsageError, ValueError)
