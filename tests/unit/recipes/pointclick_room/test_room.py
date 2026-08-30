"""The point-and-click room recipe: contract, proof, plan, and dry run."""

from __future__ import annotations

import asyncio
import json
import tomllib
from pathlib import Path
from typing import Any

import pytest

from stage_gen.config import StageGenConfig
from stage_gen.recipes.pointclick_room.models import (
    PointClickRoom,
    prove_room_solvable,
)
from stage_gen.recipes.pointclick_room.room_executor import PointClickRoomExecutor
from stage_gen.recipes.pointclick_room.room_graph import (
    build_pointclick_room_graph,
    room_graph_profile,
)
from stage_gen.recipes.pointclick_room.room_request import (
    read_room_document,
    resolve_pointclick_room,
)
from stage_gen.recipes.pointclick_room.room_types import pointclick_type_index
from stage_gen.recipes.pointclick_room.room_view import build_pointclick_room_view

REPOSITORY_ROOT = Path(__file__).parents[4]
ATTIC = REPOSITORY_ROOT / "library/rooms/clockmakers_attic/room.toml"


def _attic_document() -> dict[str, Any]:
    return tomllib.loads(ATTIC.read_text(encoding="utf-8"))


def test_the_shipped_room_is_valid_and_provably_finishable() -> None:
    resolved = resolve_pointclick_room(read_room_document(ATTIC))
    assert resolved.room.room_id == "clockmakers_attic"
    report = resolved.solvability
    assert report.solvable
    assert report.solution, "the proof carries one shortest finishing sequence"
    assert report.unreachable_interactions == ()
    # The evidence replays: applying the recorded solution reaches the win flags.
    replay = prove_room_solvable(resolved.room)
    assert replay.solution == report.solution


def test_an_unwinnable_room_is_refused_before_any_art_is_planned() -> None:
    document = _attic_document()
    # Sever the chain: the clock no longer yields the gear the music box needs.
    for interaction in document["interactions"]:
        effects = interaction.get("effects", [])
        interaction["effects"] = [
            effect for effect in effects if effect.get("grant_item") != "small_gear"
        ]
    with pytest.raises(ValueError, match=r"obtainable|cannot be finished"):
        resolve_pointclick_room(document)


def test_a_hidden_hotspot_nothing_reveals_is_refused() -> None:
    document = _attic_document()
    for interaction in document["interactions"]:
        effects = interaction.get("effects", [])
        interaction["effects"] = [effect for effect in effects if "reveal_hotspot" not in effect]
    with pytest.raises(ValueError, match="revealable"):
        PointClickRoom.model_validate(document)


def test_the_proof_searches_the_runtime_machine_not_a_more_permissive_one() -> None:
    """A permanently shadowed interaction must not count as a solution.

    The runtime dispatches a click to the FIRST available interaction with a
    matching trigger. A repeating narration line ahead of an effectful
    interaction on the same trigger shadows it forever, so a proof that
    branched on both would admit a room no player can finish.
    """

    document = _attic_document()
    document["hotspots"] = [document["hotspots"][0]]
    document["items"] = []
    document["interactions"] = [
        {
            "on": {"verb": "use", "hotspot": "workbench"},
            "narration": "You rummage, but your mind wanders.",
        },
        {
            "on": {"verb": "use", "hotspot": "workbench"},
            "effects": [{"set_flag": "found_it"}],
        },
    ]
    document["win"] = {"requires": ["found_it"]}
    with pytest.raises(ValueError, match=r"cannot be finished|never fire"):
        resolve_pointclick_room(document)


def test_win_flags_must_be_settable() -> None:
    document = _attic_document()
    document["win"] = {"requires": ["flag_nothing_sets"]}
    with pytest.raises(ValueError, match="no interaction sets"):
        PointClickRoom.model_validate(document)


def test_the_plan_carries_full_static_prompts_on_every_generation_card() -> None:
    resolved = resolve_pointclick_room(read_room_document(ATTIC))
    graph = build_pointclick_room_graph(resolved, profile=room_graph_profile(StageGenConfig()))
    types = pointclick_type_index()
    for node in graph.nodes:
        assert node.type_id in types
        declared = types[node.type_id]
        assert node.operation == declared.operation
        if node.operation != "local":
            assert node.card is not None and node.card.prompt, node.node_id
    backdrop = graph.node("room-backdrop")
    assert backdrop.card is not None and backdrop.card.prompt is not None
    # Scenery hotspots are painted into the backdrop at stated regions; sprite
    # hotspots never appear in it by name — their clearance zones are anonymous.
    assert "Great brass clock" in backdrop.card.prompt
    assert "Tin lantern" in backdrop.card.prompt
    assert "Dust sheet" not in backdrop.card.prompt
    assert "music box" not in backdrop.card.prompt.lower()
    sprite = graph.node("hotspot-dust_sheet-generate")
    assert sprite.params == {"hotspot_id": "dust_sheet"}
    assert sprite.template_id == "hotspot-pipeline@v1"
    assert sprite.port("image").artifact_ref == "assets/hotspots/dust_sheet.png"
    # Scenery hotspots get no sprite nodes at all.
    assert all(node.node_id != "hotspot-workbench-generate" for node in graph.nodes)


def test_dry_run_and_view_round_trip(tmp_path: Path) -> None:
    executor = PointClickRoomExecutor(StageGenConfig())
    run_dir = tmp_path / "run"
    run = asyncio.run(
        executor.dry_run(
            ATTIC,
            run_dir=run_dir,
            cache_dir=tmp_path / "cache",
            invocation_id="room-test",
        )
    )
    assert run.summary.ok
    view = build_pointclick_room_view(run_dir)
    assert view.kind == "pointclick-room-execution-view-v1"
    assert view.schema_version == 3
    assert view.recipe == "pointclick-room"
    assert view.room_id == "clockmakers_attic"
    assert view.run_state == "succeeded"
    assert view.gaps == ()
    by_id = {node.node_id: node for node in view.nodes}
    assert by_id["room-backdrop"].archetype == "image"
    assert by_id["room-backdrop"].card is not None
    assert by_id["room-puzzle-validate"].archetype == "validate"
    plan = json.loads((run_dir / "execution-plan.json").read_text(encoding="utf-8"))
    assert plan["kind"] == "pointclick-room-execution-graph-v1"
    assert plan["recipe"] == "pointclick-room"
