"""The host contract is true of the hosts in the tree.

`spec/game/host-contract.md` states what every host owes, engine-neutrally, and
`docs/godot-host.md` is the operating manual for the projects that owe it. Neither is
allowed to describe a host that is not there, or to omit one that is: a boundary document
that has drifted from the tree is worse than none, because the reader trusts it.

The host layers themselves are checked by `tests/contract/test_godot_boundaries.py`; this
module checks only the prose against the tree.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]
HOST_CONTRACT = REPOSITORY_ROOT / "docs/spec/game/host-contract.md"
HOST_MANUAL = REPOSITORY_ROOT / "docs/godot-host.md"
GODOT_ROOT = REPOSITORY_ROOT / "godot"


def _templates() -> list[Path]:
    """Every template declaration in the tree, in path order.

    A template is one genre's code at one commit; it declares the document kind it plays.
    Before the mono-project lands there are none, and the assertions below are vacuous on
    purpose: they start holding the moment the first one is written.
    """

    return sorted(GODOT_ROOT.glob("**/template.json"))


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
    assert "never a partial result" in source


def test_every_template_in_the_tree_is_named_by_the_host_manual() -> None:
    """One manual, every host. A project the manual does not name is a project nobody
    reviews, and a manual that names a project which is gone sends the reader nowhere."""

    manual = HOST_MANUAL.read_text(encoding="utf-8")
    for template in _templates():
        relative = template.relative_to(REPOSITORY_ROOT).as_posix()
        host_directory = template.parent.relative_to(REPOSITORY_ROOT).as_posix()
        assert host_directory in manual, f"{relative}: the host manual never names {host_directory}"


def test_every_template_declares_a_document_kind_and_a_scene() -> None:
    """A template is selected by the kind it plays; the boot has nothing else to match on."""

    for template in _templates():
        declared = json.loads(template.read_text(encoding="utf-8"))
        relative = template.relative_to(REPOSITORY_ROOT).as_posix()
        for field in ("kind", "document", "recipe", "main_scene", "design_space"):
            assert field in declared, f"{relative}: no {field}"
        scene_ref = declared["main_scene"].removeprefix("res://")
        scene = GODOT_ROOT / scene_ref
        assert scene.is_file(), (
            f"{relative}: main_scene {declared['main_scene']} is not in the tree"
        )


def test_the_host_manual_and_the_contract_point_at_each_other() -> None:
    """The manual is one instance of the contract; a reader who lands on either finds both."""

    assert "spec/game/host-contract.md" in HOST_MANUAL.read_text(encoding="utf-8")
    assert "godot-host.md" in HOST_CONTRACT.read_text(encoding="utf-8")
