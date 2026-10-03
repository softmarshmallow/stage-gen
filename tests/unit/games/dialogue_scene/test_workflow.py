"""The Grain's scene builder through gnode, offline: the plan, whole runs, the judges, reuse.

Each run builds the small two-actor package from ``package.py`` inside a scratch copy of the
game's gnode project. Paid calls are answered by the stand-ins in ``tests.unit.games._grain``.
The build is documented in ``godot/games/the_grain/docs/dialogue-scene-assets.md``.
"""

from __future__ import annotations

import hashlib
import io
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from gnode import PlanError
from tests.unit.games._grain import (
    GAME,
    SCENE,
    StandIns,
    calls_of,
    cover_digest,
    deliver,
    failures,
    first_takes,
    grain_project,
    keyed,
    plan,
    run,
    stand_ins_for,
)
from the_grain_pipeline.dialogue_scene.models import DialogueBundle

from .package import _to_toml, read_scene_value, repoint_digests, write_scene_package

PACKAGE = "inputs"
FFPROBE = shutil.which("ffprobe")
needs_ffprobe = pytest.mark.skipif(FFPROBE is None, reason="the track judge measures with it")


def scene_project(tmp_path: Path, **options: Any) -> Path:
    project = grain_project(tmp_path)
    write_scene_package(project / PACKAGE, **options)
    return project


def build_scene(
    root: Path, *, write: Callable[[Path], object] = write_scene_package, **options: Any
) -> tuple[Path, StandIns]:
    """One whole offline scene build, its package at ``root/package`` and its delivery at
    ``root/run``."""

    project = grain_project(root)
    write(project / PACKAGE, **options)
    stand_ins = stand_ins_for(project, SCENE, PACKAGE)
    outcome = run(project, SCENE, PACKAGE, stand_ins)
    assert outcome.ok, failures(outcome)
    shutil.copytree(project / PACKAGE, root / "package")
    return deliver(stand_ins.store, outcome, root / "run"), stand_ins


def _bind_an_identity_plate(package: Path) -> bytes:
    """Ren binds a plate of his own, distinct from the style plate."""

    plate = Image.new("RGB", (1024, 1536), (90, 70, 50))
    stream = io.BytesIO()
    plate.save(stream, format="PNG")
    data = stream.getvalue()
    (package / "references/ren.png").write_bytes(data)
    value = read_scene_value(package)
    value["references"].append(
        {
            "reference_id": "ren_plate",
            "source": "references/ren.png",
            "source_sha256": hashlib.sha256(data).hexdigest(),
            "rights_status": "unreviewed",
            "rights_basis": ["Original brand-neutral test fixture."],
        }
    )
    ren = next(actor for actor in value["cast"] if actor["actor_id"] == "ren")
    ren["reference_id"] = "ren_plate"
    (package / "scene.toml").write_text(_to_toml(value), encoding="utf-8")
    return data


# ------------------------------------------------------------------------------- the plan


def test_the_shipped_scene_plans_inside_the_game_project() -> None:
    planned = plan(GAME, SCENE, PACKAGE)

    assert planned.ok, planned.problems
    assert planned.planner.workflow.id == "the-grain-scene"
    budget = planned.planner.workflow.budget
    assert budget is not None and planned.estimate()[1] <= budget.max_usd


def test_several_scenarios_plan_the_union_of_their_art_once(tmp_path: Path) -> None:
    one = plan(scene_project(tmp_path / "one"), SCENE, PACKAGE)
    two = plan(scene_project(tmp_path / "two", second_scenario=True), SCENE, PACKAGE)
    steps_one = {instance.step for instance in first_takes(one)}
    steps_two = {instance.step for instance in first_takes(two)}

    # The second scenario shares both actors and one stage: it adds the one backdrop
    # nobody had drawn, and nothing else.
    assert not steps_one - steps_two
    assert {step.rsplit(".", 1)[0] for step in steps_two - steps_one} == {"stages.corridor"}
    assert calls_of(two)["image.edit"] == calls_of(one)["image.edit"] + 1
    faces = [
        step for step in steps_two if step.startswith("actors.") and step.endswith(".generate")
    ]
    assert len(faces) == 8


def test_ai_transparency_is_refused_while_planning(tmp_path: Path) -> None:
    project = scene_project(tmp_path, transparency_mode="ai")

    with pytest.raises(PlanError, match=r"background\.remove"):
        plan(project, SCENE, PACKAGE)


def test_native_faces_are_refused_on_a_route_without_transparency(tmp_path: Path) -> None:
    project = scene_project(tmp_path, transparency_mode="native")
    settings = project / "gnode.yaml"
    settings.write_text(
        settings.read_text(encoding="utf-8").replace(
            "image.edit: gpt-image-2.5-sunburst@openai",
            "image.edit: openai/gpt-image-2.5-sunburst@openrouter",
        ),
        encoding="utf-8",
    )

    planned = plan(project, SCENE, PACKAGE)

    assert not planned.ok
    assert "transparent_background" in "; ".join(problem.message for problem in planned.problems)


# ------------------------------------------------------------------------------- whole runs


@needs_ffprobe
def test_a_chroma_scene_runs_offline_and_writes_bundle_v9(tmp_path: Path) -> None:
    played, stand_ins = build_scene(tmp_path)

    bundle = DialogueBundle.model_validate_json((played / "bundle.json").read_bytes())
    assert (bundle.kind, bundle.schema_version) == ("dialogue-scene-bundle-v9", 9)
    bound = {
        "request.json",
        bundle.style_reference.path,
        *(asset.path for asset in bundle.assets),
        *(file.path for actor in bundle.actors for file in (actor.character_profile, actor.plan)),
        *(
            file.path
            for scenario in bundle.scenarios
            for file in (scenario.program, scenario.validation)
        ),
    }
    delivered = {
        path.relative_to(played).as_posix() for path in played.rglob("*") if path.is_file()
    }
    assert delivered == bound | {"bundle.json"}
    for asset in bundle.assets:
        assert hashlib.sha256((played / asset.path).read_bytes()).hexdigest() == asset.sha256
    for asset in bundle.assets:
        if asset.role == "expression":
            with Image.open(played / asset.path) as opened:
                assert opened.size == (1024, 1536) and opened.mode == "RGBA"
        if asset.role == "background":
            with Image.open(played / asset.path) as opened:
                assert opened.size == (1672, 941)
    assert stand_ins.calls["face"] == 8 and stand_ins.calls["plan"] == 2
    assert bundle.review.status == "pending"
    assert bundle.rights.publication_authorized is False


@needs_ffprobe
def test_a_native_scene_finishes_its_sprites_on_the_runtime_canvas(tmp_path: Path) -> None:
    played, stand_ins = build_scene(tmp_path, transparency_mode="native")

    for request in stand_ins.requests["face"]:
        assert request["background"] == "transparent"
    for request in stand_ins.requests["backdrop"]:
        assert request["background"] == "opaque"
    bundle = DialogueBundle.model_validate_json((played / "bundle.json").read_bytes())
    for asset in bundle.assets:
        if asset.role == "expression":
            with Image.open(played / asset.path) as opened:
                assert opened.size == (1024, 1536) and opened.mode == "RGBA"


@needs_ffprobe
def test_the_base_face_is_drawn_against_the_plates_and_every_other_face_edits_it(
    tmp_path: Path,
) -> None:
    def write(package: Path) -> None:
        write_scene_package(package)
        _bind_an_identity_plate(package)

    _played, stand_ins = build_scene(tmp_path, write=write)

    package = tmp_path / "package"
    cover = cover_digest(package / "references/cover.png")
    identity = cover_digest(package / "references/ren.png")
    base_output = hashlib.sha256(keyed("1024x1536")).hexdigest()
    bases = [r for r in stand_ins.requests["face"] if stand_ins.pictures(r)[0] == cover]
    edits = [r for r in stand_ins.requests["face"] if stand_ins.pictures(r)[0] != cover]
    # Mio binds the style plate as her own, so it is attached once; Ren's plate rides
    # beside it, and his brief names it.
    assert sorted(len(stand_ins.pictures(r)) for r in bases) == [1, 2]
    with_plate = next(r for r in bases if len(stand_ins.pictures(r)) == 2)
    assert stand_ins.pictures(with_plate) == [cover, identity]
    assert "own authored identity plate" in str(with_plate["prompt"])
    assert len(edits) == 6
    for request in edits:
        assert stand_ins.pictures(request) == [base_output]
    for request in stand_ins.requests["backdrop"]:
        assert stand_ins.pictures(request) == [cover]


@needs_ffprobe
def test_a_draft_outside_the_frame_and_a_refused_face_are_asked_again(tmp_path: Path) -> None:
    project = scene_project(tmp_path)
    stand_ins = stand_ins_for(project, SCENE, PACKAGE, refuse={"plan": 1, "face": 1})

    outcome = run(project, SCENE, PACKAGE, stand_ins)

    assert outcome.ok, failures(outcome)
    assert stand_ins.calls["plan"] == 3
    assert stand_ins.calls["face"] == 9


# ------------------------------------------------------------------------------- reuse


@needs_ffprobe
def test_rewording_a_line_bills_nothing(tmp_path: Path) -> None:
    project = scene_project(tmp_path)
    assert run(project, SCENE, PACKAGE, stand_ins_for(project, SCENE, PACKAGE), "first").ok

    script = project / PACKAGE / "scenarios/after_seminar.scenario"
    script.write_text(
        script.read_text(encoding="utf-8").replace(
            "I hoped you would stay after the seminar.",
            "I did hope you would stay after the seminar.",
        ),
        encoding="utf-8",
    )
    repoint_digests(project / PACKAGE)
    second = stand_ins_for(project, SCENE, PACKAGE)
    outcome = run(project, SCENE, PACKAGE, second, "second")

    assert outcome.ok, failures(outcome)
    assert sum(second.calls.values()) == 0


@needs_ffprobe
def test_binding_a_scenario_with_the_same_cast_bills_only_its_new_stage(tmp_path: Path) -> None:
    project = scene_project(tmp_path)
    assert run(project, SCENE, PACKAGE, stand_ins_for(project, SCENE, PACKAGE), "first").ok

    write_scene_package(project / PACKAGE, second_scenario=True)
    second = stand_ins_for(project, SCENE, PACKAGE)
    outcome = run(project, SCENE, PACKAGE, second, "second")

    assert outcome.ok, failures(outcome)
    assert dict(second.calls) == {"backdrop": 1}
