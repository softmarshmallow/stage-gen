"""The host contract is true of the hosts in the tree.

The shared format documentation describes the existing run-consuming games.
Each game's operating manual must point to source that exists; prose must not
silently validate an empty glob over a retired monolithic project.

The host layers themselves are checked by `tests/contract/test_godot_boundaries.py`; this
module checks only the prose against the tree.
"""

from __future__ import annotations

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]
HOST_CONTRACT = REPOSITORY_ROOT / "godot/games/_shared/docs/formats/host-contract.md"
HOST_MANUAL = REPOSITORY_ROOT / "godot/games/ember_hollow/docs/runtime.md"
GODOT_GAMES = REPOSITORY_ROOT / "godot/games"
GAME_NAMES = ("bellweather", "iron_petal_unit", "ember_hollow", "the_grain")
GAME_INDEX = REPOSITORY_ROOT / "godot/README.md"


def _linked_files(document: Path) -> set[Path]:
    return {
        (document.parent / target.split("#", 1)[0]).resolve()
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8"))
        if "://" not in target and not target.startswith("#")
    }


def test_the_host_contract_states_the_seam_the_engine_evaluation_set() -> None:
    """The one rule a host may never break, in the document a host author reads first."""

    source = HOST_CONTRACT.read_text(encoding="utf-8")
    assert "starts no generation" in source
    assert "never receives a credential" in source
    for owed in ("provider adapter", "reusable component", "artifact or provenance schema"):
        assert owed in source, f"the seam does not name {owed}"
    # The four layers and the direction between them are the taxonomy; naming them is what
    # makes the mechanical test's failures legible to someone who has not read the code.
    for layer in ("kernel", "family", "genre", "host"):
        assert re.search(rf"\*\*{layer}\*\*", source), f"the layer table omits {layer}"
    assert "Dependencies point inward" in source


def test_the_host_contract_states_the_rules_a_replay_rests_on() -> None:
    """A promotion is proved by replaying one seed and one script; these are its premises."""

    source = HOST_CONTRACT.read_text(encoding="utf-8")
    assert "The tick is the only clock and the seed is the only randomness" in source
    assert "A view reads" in source
    assert "never writes a slice" in source
    assert "latch" in source
    assert "A refusal is a value" in source
    prose = " ".join(source.split())
    assert "returns null when the initial document is refused" in prose
    assert "rejects unsafe references, symbolic links, missing files and decoding failures" in prose
    assert "does not perform blanket artifact digest or lineage validation" in prose


def test_every_maintained_game_has_a_documented_project() -> None:
    """The index and game-owned README describe actual source projects."""

    index = GAME_INDEX.read_text(encoding="utf-8")
    for name in GAME_NAMES:
        project = GODOT_GAMES / name
        assert (project / "project.godot").is_file()
        assert f"games/{name}" in index, f"the Godot index omits {name}"
        manual = (project / "README.md").read_text(encoding="utf-8")
        assert f"godot --path godot/games/{name}" in manual
        assert "--run" in manual


def test_each_documented_main_scene_belongs_to_its_game() -> None:
    """Each project's ordinary Godot settings select its own entry scene."""

    for name in GAME_NAMES:
        project = GODOT_GAMES / name
        source = (project / "project.godot").read_text(encoding="utf-8")
        match = re.search(r'run/main_scene="res://([^"\n]+)"', source)
        assert match, f"{name} has no main scene"
        scene = (project / match.group(1)).resolve()
        assert scene.is_relative_to(project.resolve()), f"{name} escapes its project"
        assert scene.is_file(), f"{name} selects a missing scene"


def test_the_host_manual_and_the_contract_point_at_each_other() -> None:
    """The manual is one instance of the contract; a reader who lands on either finds both."""

    assert HOST_CONTRACT.resolve() in _linked_files(HOST_MANUAL)
    assert HOST_MANUAL.resolve() in _linked_files(HOST_CONTRACT)
