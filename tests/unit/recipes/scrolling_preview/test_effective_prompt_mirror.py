"""`_effective_image_prompt` must reproduce what `_generate_image_asset` actually sends.

The generator assembles an image prompt inline: theme directive, then style anchor, then the
game art-direction clause, then the transparency clause. `_effective_image_prompt` is a second
copy of that assembly, used to recompute a prompt digest when deciding whether an artifact
already on disk can be resumed.

Nothing fails loudly when the two drift. The recorded digest stops matching the recomputed one,
every resume check misses, and the stage regenerates from scratch on every run against an
artifact that was valid the whole time. That is exactly what adding the art-direction clause to
the generator and not to the mirror did to the tileset: an accepted atlas was rediscarded and
rebuilt each run - six sheet attempts, three swatches, a fresh composition, roughly twenty-seven
minutes - re-rolling two stochastic variant contracts every time.

These tests pin the clauses and their order, so the next clause added to one side and not the
other fails here instead of quietly costing half an hour a run.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from stage_gen.components.game_contract import resolve_game_contract_binding
from stage_gen.recipes.scrolling_preview import executor as executor_module
from stage_gen.recipes.scrolling_preview.game import GAME_DIRECTION_PREFIX

COMPONENT_FIXTURE_REF = "library/games/test-game/game.toml"


def _spec(
    prompt: str = "Ground tileset, strict 12-column x 4-row atlas.",
) -> executor_module._ImageSpec:
    return executor_module._ImageSpec(
        stage="tileset",
        prompt=prompt,
        output=Path("tileset.png"),
        width=2400,
        height=800,
    )


def _game(root: Path) -> executor_module._GameContractContext:
    """A real context built from a component fixture, with no run directory involved.

    The mirror only reads `.contract`, but constructing the real dataclass rather than a stub
    keeps this test honest: if the field the mirror reads is ever renamed, this fails to build
    instead of silently testing a shape the executor no longer uses.
    """

    source = root / COMPONENT_FIXTURE_REF
    source.parent.mkdir(parents=True)
    source.write_bytes(
        b"""schema_version = 3
kind = "game-contract-v3"
game_id = "test-game"
revision = 1
display_name = "Test Game"

[camera]
projection = "side_view_2d"

[style]
keywords = ["hand-painted gouache", "warm dusk palette", "soft diffuse light"]
avoid = ["3D rendering"]

[proportion]
heads_tall = 2.0

[cast.player]
body_kind = "human"

[cast.resident]
body_kind_default = "human"

[rights]
status = "unreviewed"
"""
    )
    resolved = resolve_game_contract_binding(
        {
            "schema_version": 1,
            "kind": "game-contract-binding-v1",
            "ref": COMPONENT_FIXTURE_REF,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        },
        game_library_root=root,
    )
    return executor_module._GameContractContext(
        resolved=resolved,
        identity={},
        artifact_bytes=len(resolved.canonical_bytes),
    )


def test_the_mirror_carries_the_art_direction_when_a_game_is_bound(tmp_path: Path) -> None:
    rendered = executor_module._effective_image_prompt(_spec(), None, "chroma", _game(tmp_path))
    assert GAME_DIRECTION_PREFIX in rendered


def test_the_mirror_omits_it_when_no_game_is_bound() -> None:
    # An undirected run must keep the exact prompt it always had, or every existing run's
    # artifacts stop resuming.
    rendered = executor_module._effective_image_prompt(_spec(), None, "chroma", None)
    assert GAME_DIRECTION_PREFIX not in rendered
    assert executor_module._effective_image_prompt(_spec(), None, "chroma") == rendered


def test_the_art_direction_sits_after_the_prompt_and_before_transparency(
    tmp_path: Path,
) -> None:
    # Order is part of the contract: the digest is over the whole string, so a clause in the
    # right place with the wrong neighbours still misses.
    rendered = executor_module._effective_image_prompt(_spec(), None, "chroma", _game(tmp_path))
    body = rendered.index("Ground tileset")
    direction = rendered.index(GAME_DIRECTION_PREFIX)
    assert body < direction
    transparency = executor_module._prompt_for_transparency("", "chroma").strip()
    if transparency:
        assert rendered.index(transparency.split("\n")[0]) > direction


def test_the_clause_is_not_doubled_when_the_prompt_already_carries_it(tmp_path: Path) -> None:
    # The mirror uses the same idempotent appender the generator does, so a prompt that already
    # contains the clause is unchanged rather than carrying it twice.
    game = _game(tmp_path)
    once = executor_module._effective_image_prompt(_spec(), None, "chroma", game)
    assert once.count(GAME_DIRECTION_PREFIX) == 1
    twice = executor_module._effective_image_prompt(_spec(once), None, "chroma", game)
    assert twice.count(GAME_DIRECTION_PREFIX) == 1
