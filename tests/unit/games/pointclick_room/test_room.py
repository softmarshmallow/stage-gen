"""The point-and-click room contract and its proof: refused before anything is planned."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

from the_grain_pipeline.pointclick_room.models import (
    PointClickRoom,
    prove_room_solvable,
)
from the_grain_pipeline.pointclick_room.room_request import (
    ResolvedPointClickRoom,
    read_room_document,
    resolve_pointclick_room,
)

REPOSITORY_ROOT = Path(__file__).parents[4]
ROOM = REPOSITORY_ROOT / "godot/games/the_grain/inputs/rooms/window"


def _room_document() -> dict[str, Any]:
    return tomllib.loads((ROOM / "room.toml").read_text(encoding="utf-8"))


def _resolved_room() -> ResolvedPointClickRoom:
    return resolve_pointclick_room(read_room_document(ROOM), root=ROOM)


def test_the_shipped_room_is_valid_and_provably_finishable() -> None:
    resolved = _resolved_room()
    assert resolved.room.room_id == "e1_window"
    report = resolved.solvability
    assert report.solvable
    assert report.solution, "the proof carries one shortest finishing sequence"
    assert report.unreachable_interactions == ()
    # The evidence replays: applying the recorded solution reaches the win flags.
    replay = prove_room_solvable(resolved.room)
    assert replay.solution == report.solution


def test_an_unwinnable_room_is_refused_before_any_art_is_planned() -> None:
    document = _room_document()
    # The exit flag is declared and settable, but now requires itself to be set.
    for interaction in document["interactions"]:
        if {"set_flag": "left_the_room"} in interaction.get("effects", []):
            interaction["requires"] = ["left_the_room"]
    with pytest.raises(ValueError, match="cannot be finished"):
        resolve_pointclick_room(document, root=ROOM)


def test_an_unobtainable_item_is_refused_before_any_art_is_planned() -> None:
    document = _room_document()
    document["items"] = [{"item_id": "key", "label": "Key", "brief": "A plain brass key."}]
    with pytest.raises(ValueError, match="obtainable"):
        resolve_pointclick_room(document, root=ROOM)


def test_a_hidden_hotspot_nothing_reveals_is_refused() -> None:
    document = _room_document()
    document["hotspots"][0]["hidden"] = True
    with pytest.raises(ValueError, match="revealable"):
        PointClickRoom.model_validate(document)


def test_the_proof_searches_the_runtime_machine_not_a_more_permissive_one() -> None:
    """A permanently shadowed interaction must not count as a solution.

    The runtime dispatches a click to the FIRST available interaction with a
    matching trigger. A repeating narration line ahead of an effectful
    interaction on the same trigger shadows it forever, so a proof that
    branched on both would admit a room no player can finish.
    """

    document = _room_document()
    document["hotspots"] = [document["hotspots"][0]]
    document["items"] = []
    document["interactions"] = [
        {
            "on": {"verb": "use", "hotspot": "six_figures"},
            "narration": "You rummage, but your mind wanders.",
        },
        {
            "on": {"verb": "use", "hotspot": "six_figures"},
            "effects": [{"set_flag": "found_it"}],
        },
    ]
    document["win"] = {"requires": ["found_it"]}
    with pytest.raises(ValueError, match=r"cannot be finished|never fire"):
        resolve_pointclick_room(document, root=ROOM)


def test_win_flags_must_be_settable() -> None:
    document = _room_document()
    document["win"] = {"requires": ["flag_nothing_sets"]}
    with pytest.raises(ValueError, match="no interaction sets"):
        PointClickRoom.model_validate(document)


def test_a_reference_that_no_longer_matches_its_digest_is_refused(tmp_path: Path) -> None:
    package = tmp_path / "room"
    (package / "references").mkdir(parents=True)
    (package / "room.toml").write_bytes((ROOM / "room.toml").read_bytes())
    (package / "references/cover.png").write_bytes(b"\x89PNG\r\n\x1a\nnot the reviewed bytes")
    with pytest.raises(ValueError, match="does not match its authored digest"):
        resolve_pointclick_room(read_room_document(package), root=package)


def test_a_style_naming_an_undeclared_reference_is_refused() -> None:
    document = _room_document()
    document["style"]["reference_ids"] = ["some_other_concept"]
    with pytest.raises(ValueError, match="unknown reference ids"):
        PointClickRoom.model_validate(document)
