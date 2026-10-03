"""Ember Hollow's builder through gnode, offline: the scope ladder, whole builds, takes, reuse.

Each run builds a copy of the shipped package inside a scratch copy of the game's gnode
project, with its auditioned takes struck so every asset is drawn. Paid calls are answered
by the stand-ins in ``_ember.py``. The build is documented in
``godot/games/ember_hollow/docs/generation-v1.md``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
from itertools import pairwise
from pathlib import Path

import pytest

from ember_hollow_pipeline import survival_prompts
from ember_hollow_pipeline.manifest import MANIFEST_KIND
from ember_hollow_pipeline.scopes import SCOPES
from ember_hollow_pipeline.survival_request import load_package
from gnode import PlanError, plan_async

from ._ember import (
    GAME,
    PACKAGE,
    calls_of,
    deliver,
    ember_project,
    failures,
    first_takes,
    plan,
    plate,
    run,
    stand_ins_for,
)

#: The paid calls each scope makes at first takes, as the generation document's table says.
SCOPE_CALLS = {
    "minimal": {"image": 21, "structured.generate": 0, "agent.turn": 5, "sound.generate": 0},
    "props": {"image": 75, "structured.generate": 11, "agent.turn": 11, "sound.generate": 0},
    "actors": {"image": 96, "structured.generate": 16, "agent.turn": 11, "sound.generate": 0},
    "full": {"image": 103, "structured.generate": 17, "agent.turn": 11, "sound.generate": 3},
}


def _edit(project: Path, document: str, old: str, new: str) -> None:
    path = project / PACKAGE / document
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    path.write_text(text.replace(old, new), encoding="utf-8")


# ------------------------------------------------------------------------------- the plan


@pytest.mark.parametrize("scope", SCOPES)
def test_each_scope_plans_inside_the_game_project(scope: str) -> None:
    planned = plan(GAME, scope)

    assert planned.ok, planned.problems
    assert planned.planner.workflow.id == "ember-hollow"
    budget = planned.planner.workflow.budget
    assert budget is not None and planned.estimate()[1] <= budget.max_usd


@pytest.mark.parametrize("scope", SCOPES)
def test_each_scope_makes_the_paid_calls_its_table_states(scope: str) -> None:
    calls = calls_of(plan(GAME, scope))

    assert {
        "image": calls["image.edit"] + calls["image.generate"],
        "structured.generate": calls["structured.generate"],
        "agent.turn": calls["agent.turn"],
        "sound.generate": calls["sound.generate"],
    } == SCOPE_CALLS[scope]


def test_the_ladder_only_ever_adds_steps_and_keeps_their_identity() -> None:
    plans = {scope: plan(GAME, scope) for scope in SCOPES}
    steps = {
        scope: {i.step: i.identity for i in first_takes(planned)}
        for scope, planned in plans.items()
    }
    for narrow, wide in pairwise(SCOPES):
        assert set(steps[narrow]) <= set(steps[wide]), f"{narrow} is not inside {wide}"
    # A step a narrow build answers is the wide build's step, asked the same thing, so the
    # narrow build's answers are the wide build's too. A review sees more of its family in
    # a wider scope, and the package lays out more, so those two are asked differently.
    for step, identity in steps["minimal"].items():
        if identity is None or step.startswith(("reviews.", "package")):
            continue
        assert steps["full"][step] == identity, step


def test_an_unknown_scope_is_refused_while_planning() -> None:
    with pytest.raises(PlanError, match="unknown scope 'everything'"):
        plan(GAME, "everything")


# ------------------------------------------------------------------------------- a build


def test_a_minimal_build_runs_offline_and_lays_out_what_the_host_reads(tmp_path: Path) -> None:
    project = ember_project(tmp_path)
    stand_ins = stand_ins_for(project)

    outcome = run(project, stand_ins)

    assert outcome.ok, failures(outcome)
    played = deliver(stand_ins.store, outcome, tmp_path / "ember")
    manifest = json.loads((played / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == MANIFEST_KIND
    assert manifest["run"]["scope"] == "minimal"
    assert manifest["status"]["layout"] == "ok"
    for prop_id, block in manifest["props"].items():
        assert (played / f"package/props/{prop_id}/anchor.json").is_file()
        for state in block["states"]:
            assert (played / f"package/props/{prop_id}/{state}.png").is_file(), (prop_id, state)
    assert (played / "package/world/layout.json").is_file()
    # Records the manifest read stay in the run; the host is handed what it plays.
    assert not (played / "production/validation").exists()
    assert stand_ins.calls["anchor"] == SCOPE_CALLS["minimal"]["agent.turn"]


def test_a_refused_draw_is_drawn_again(tmp_path: Path) -> None:
    project = ember_project(tmp_path)
    stand_ins = stand_ins_for(project, refuse={"prop": 1})

    outcome = run(project, stand_ins)

    assert outcome.ok, failures(outcome)
    planned = calls_of(plan(project))
    drawn = sum(stand_ins.calls[kind] for kind in stand_ins.calls if kind not in {"anchor"})
    assert drawn == planned["image.edit"] + planned["image.generate"] + 1


# ------------------------------------------------------------------------------- takes


def test_a_take_on_disk_is_adopted_and_a_missing_one_is_refused_with_a_notice(
    tmp_path: Path,
) -> None:
    project = ember_project(tmp_path, takes=True)
    for take in (project / PACKAGE).rglob("*.take.*"):
        take.unlink()
    # One take is here, under the digest the package declares; the rest are not.
    data = plate(luma=120)
    take = project / PACKAGE / "ground/forest_floor.take.png"
    take.write_bytes(data)
    ground = (project / PACKAGE / "ground.toml").read_text(encoding="utf-8")
    ground = re.sub(
        r'(path = "ground/forest_floor\.take\.png", sha256 = )"[0-9a-f]{64}"',
        lambda match: f'{match.group(1)}"{hashlib.sha256(data).hexdigest()}"',
        ground,
    )
    (project / PACKAGE / "ground.toml").write_text(ground, encoding="utf-8")
    stand_ins = stand_ins_for(project)

    outcome = run(project, stand_ins)

    assert "ground.forest_floor.adopt#1" not in outcome.failed
    refused = outcome.results.get("ground.dry_meadow.adopt#1")
    assert "is not on disk" in str(getattr(refused, "error", ""))
    package = load_package(project / PACKAGE)
    adopted = survival_prompts.ground_prompt(package, package.biomes[0])
    assert package.biomes[0].biome_id == "forest_floor"
    assert adopted not in stand_ins.prompts.get("plate", [])


# ------------------------------------------------------------------------------- reuse


def test_rewording_one_item_brief_redraws_that_item_and_its_icon_only(tmp_path: Path) -> None:
    project = ember_project(tmp_path)
    assert run(project, stand_ins_for(project), name="first").ok

    _edit(
        project,
        "items.toml",
        'prompt = "A short split length of pale-cored firewood with rough bark on one face."',
        'prompt = "A short split length of pale firewood with ridged bark on one face."',
    )
    second = stand_ins_for(project)
    outcome = run(project, second, name="second")

    assert outcome.ok, failures(outcome)
    # The icon sheet draws an item with no icon brief of its own from its pickup brief.
    assert dict(second.calls) == {"item": 1, "pieces": 1}


def test_mixing_edits_bill_nothing(tmp_path: Path) -> None:
    project = ember_project(tmp_path)
    assert run(project, stand_ins_for(project), name="first").ok

    # The ground's edge blend and its display levels are mixing: the manifest carries them
    # and no picture is drawn from them.
    _edit(project, "ground.toml", "edge_softness = 0.03", "edge_softness = 0.05")
    _edit(project, "ground.toml", "forest_floor = 0.34,", "forest_floor = 0.30,")
    second = stand_ins_for(project)
    outcome = run(project, second, name="second")

    assert outcome.ok, failures(outcome)
    assert sum(second.calls.values()) == 0
    played = deliver(second.store, outcome, tmp_path / "ember")
    manifest = json.loads((played / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["ground"]["splat"]["blend"]["edge_softness"] == 0.05


def test_a_package_outside_the_project_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere"
    shutil.copytree(GAME / PACKAGE, outside)

    with pytest.raises(PlanError, match="not inside a gnode project"):
        asyncio.run(
            plan_async(
                "pipeline/workflow.py:build",
                cwd=GAME,
                arguments={"package": str(outside), "scope": "minimal"},
            )
        )
