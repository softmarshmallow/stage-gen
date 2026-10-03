"""The Grain's room builder through gnode, offline: the plan, a whole run, the judges, reuse.

Each run builds a copy of the shipped window room inside a scratch copy of the game's gnode
project. Paid calls are answered by the stand-ins in ``tests.unit.games._grain``.
The build is documented in ``godot/games/the_grain/docs/pointclick-room.md``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from gnode import PlanError
from tests.unit.games._grain import (
    GAME,
    ROOM,
    calls_of,
    deliver,
    failures,
    grain_project,
    plan,
    run,
    stand_ins_for,
)
from the_grain_pipeline.pointclick_room.room_prompts import narration_ids
from the_grain_pipeline.pointclick_room.room_request import (
    read_room_document,
    resolve_pointclick_room,
)
from the_grain_pipeline.pointclick_room.runtime import MANIFEST_KIND

PACKAGE = "inputs/rooms/window"


def room_project(tmp_path: Path) -> Path:
    project = grain_project(tmp_path)
    shutil.copytree(GAME / PACKAGE, project / PACKAGE)
    return project


def _edit(project: Path, old: str, new: str) -> None:
    path = project / PACKAGE / "room.toml"
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    path.write_text(text.replace(old, new), encoding="utf-8")


def _leave_the_win_line_open(project: Path) -> None:
    """The author leaves the win narration to generation, so the build writes it."""

    _edit(
        project,
        'narration = """Henry has attended the supper for less than two hours. For the \\\n'
        'first time that evening, he is working."""\n',
        "",
    )


# ------------------------------------------------------------------------------- the plan


@pytest.mark.parametrize("room", ["window", "motor_court"])
def test_each_shipped_room_plans_inside_the_game_project(room: str) -> None:
    planned = plan(GAME, ROOM, f"inputs/rooms/{room}")

    assert planned.ok, planned.problems
    assert planned.planner.workflow.id == "the-grain-room"
    budget = planned.planner.workflow.budget
    assert budget is not None and planned.estimate()[1] <= budget.max_usd


def test_the_plan_draws_each_room_asset_once() -> None:
    planned = plan(GAME, ROOM, PACKAGE)
    root = GAME / PACKAGE
    resolved = resolve_pointclick_room(read_room_document(root), root=root)
    room = resolved.room
    sprites = sum(hotspot.art == "sprite" for hotspot in room.hotspots)
    calls = calls_of(planned)

    # The backdrop, one cut-out per sprite hotspot, one icon per item, one sheet per role.
    roles = {i.step.split(".")[1] for i in planned.instances if i.step.startswith("interface.")}
    assert calls["image.edit"] == 1 + sprites + len(room.items) + len(roles)
    assert calls["structured.generate"] >= 1 + bool(narration_ids(room))
    assert "music.generate" not in calls


def test_a_room_the_proof_refuses_is_refused_while_planning(tmp_path: Path) -> None:
    project = room_project(tmp_path)
    # A win flag nothing can set leaves the room unfinishable.
    _edit(
        project, '[win]\nrequires = ["left_the_room"]', '[win]\nrequires = ["never_set_anywhere"]'
    )

    with pytest.raises(PlanError, match="never_set_anywhere"):
        plan(project, ROOM, PACKAGE)


# ------------------------------------------------------------------------------- a run


def test_a_whole_room_runs_offline_and_lays_out_what_the_host_plays(tmp_path: Path) -> None:
    project = room_project(tmp_path)
    _leave_the_win_line_open(project)
    stand_ins = stand_ins_for(project, ROOM, PACKAGE)

    outcome = run(project, ROOM, PACKAGE, stand_ins)

    assert outcome.ok, failures(outcome)
    played = deliver(stand_ins.store, outcome, tmp_path / "room")
    manifest = json.loads((played / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == MANIFEST_KIND
    bound = {entry["path"]: entry["sha256"] for entry in manifest["closure"]["artifacts"]}
    delivered = {
        path.relative_to(played).as_posix()
        for path in played.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    assert delivered == set(bound)
    for path, digest in bound.items():
        assert hashlib.sha256((played / path).read_bytes()).hexdigest() == digest
    assert (played / "assets/backdrop.png").is_file()
    # The generated line is inlined where the host reads it; its record stays in the run.
    assert manifest["win"]["narration"] == "A line for win."


def test_every_painting_is_drawn_against_the_authored_cover(tmp_path: Path) -> None:
    project = room_project(tmp_path)
    stand_ins = stand_ins_for(project, ROOM, PACKAGE)

    outcome = run(project, ROOM, PACKAGE, stand_ins)

    assert outcome.ok, failures(outcome)
    cover = hashlib.sha256((project / PACKAGE / "references/cover.png").read_bytes()).hexdigest()
    for kind in ("backdrop", "cutout"):
        for request in stand_ins.requests[kind]:
            assert stand_ins.pictures(request)[0] == cover


def test_a_refused_painting_and_a_short_narration_are_asked_again(tmp_path: Path) -> None:
    project = room_project(tmp_path)
    _leave_the_win_line_open(project)
    planned = calls_of(plan(project, ROOM, PACKAGE))
    stand_ins = stand_ins_for(project, ROOM, PACKAGE, refuse={"backdrop": 1, "narration": 1})

    outcome = run(project, ROOM, PACKAGE, stand_ins)

    assert outcome.ok, failures(outcome)
    assert stand_ins.calls["backdrop"] == 2
    assert stand_ins.calls["narration"] == 2
    images = sum(stand_ins.calls[kind] for kind in ("backdrop", "cutout", "ui"))
    assert images == planned["image.edit"] + 1


# ------------------------------------------------------------------------------- reuse


def test_correcting_a_hit_area_reuses_every_paid_answer(tmp_path: Path) -> None:
    project = room_project(tmp_path)
    first = stand_ins_for(project, ROOM, PACKAGE)
    assert run(project, ROOM, PACKAGE, first, "first").ok
    assert sum(first.calls.values()) > 0

    # Anchored to line start: the hit area moves, and the composition the art was drawn
    # against (``art_region``) stays exactly where it was.
    _edit(
        project,
        "\nregion = { x = 0.4688, y = 0.4097, w = 0.0781, h = 0.3681 }",
        "\nregion = { x = 0.05, y = 0.55, w = 0.33, h = 0.30 }",
    )
    second = stand_ins_for(project, ROOM, PACKAGE)
    outcome = run(project, ROOM, PACKAGE, second, "second")

    assert outcome.ok, failures(outcome)
    assert sum(second.calls.values()) == 0
    played = deliver(second.store, outcome, tmp_path / "room")
    manifest = json.loads((played / "manifest.json").read_text(encoding="utf-8"))
    six_figures = next(entry for entry in manifest["hotspots"] if entry["id"] == "six_figures")
    assert six_figures["region"] == {"x": 0.05, "y": 0.55, "w": 0.33, "h": 0.30}
    assert "art_region" not in six_figures


def test_rewording_one_brief_redraws_that_object_and_nothing_else(tmp_path: Path) -> None:
    project = room_project(tmp_path)
    assert run(project, ROOM, PACKAGE, stand_ins_for(project, ROOM, PACKAGE), "first").ok

    _edit(
        project,
        "a small torn piece of typed script paper, creased where a hand closed on it, "
        "one edge visible beneath curled fingers",
        "a torn pale-blue sheet with a folded corner and a narrow strip of typed marks",
    )
    second = stand_ins_for(project, ROOM, PACKAGE)
    outcome = run(project, ROOM, PACKAGE, second, "second")

    assert outcome.ok, failures(outcome)
    assert dict(second.calls) == {"cutout": 1}
    assert "pale-blue sheet" in str(second.requests["cutout"][0]["prompt"])
