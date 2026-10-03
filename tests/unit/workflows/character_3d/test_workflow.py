"""Character-3d through gnode, offline: every stage, rebuilds, refusals, resume and support.

Blender is the stand-in in ``stub_blender.py``, found through ``GNODE_TOOL_BLENDER``; its
models are small JSON documents. The paid calls are stand-ins too: the agents follow a
script per episode (draw a canonical and each part's views, build one assembly, accept or
reject as the test says), the image calls return flat pictures of the size asked for, and
Tripo returns models that say which request made them, so a rebuild makes new bytes.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import json
import time
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from gnode import (
    CallRecord,
    CallRefused,
    HostServices,
    Route,
    RunOutcome,
    WorkflowRun,
    plan_async,
)
from stage_gen.workflows.character_3d import support
from tests.unit.workflows.character_3d.stub_blender import glb, unglb

PACKAGE = Path(__file__).resolve().parents[4] / "src/stage_gen/workflows/character_3d"
STUB = Path(__file__).with_name("stub_blender.py")
EPISODES = {
    "draw": "plan_references.md",
    "references": "review_references.md",
    "part": "review_part.md",
    "assemble": "assemble.md",
    "assembly": "review_assembly.md",
    "rig": "review_rig.md",
}
BRIEF = "# Pell\n\nA small courier in a mustard raincoat and rubber boots, with a satchel.\n"


def _png(size: str) -> bytes:
    width, height = (int(side) for side in size.split("x"))
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (180, 150, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


def _model(file: Any) -> dict[str, Any]:
    return unglb(Path(file.location).read_bytes())


def _wait_for(path: Path, seconds: float = 60) -> None:
    """Until the stand-in Blender says it reached its hold point."""

    deadline = time.monotonic() + seconds
    while not path.exists():
        if time.monotonic() > deadline:
            raise TimeoutError(f"{path.name} never appeared")
        time.sleep(0.05)


def _call(name: str, **arguments: Any) -> dict[str, Any]:
    return {"text": "", "tool_calls": [{"id": f"c-{name}", "name": name, "arguments": arguments}]}


def _verdict(subject: Mapping[str, Any], criteria: list[str], accept: bool) -> dict[str, Any]:
    issues = (
        []
        if accept
        else [
            {
                "severity": "blocking",
                "region": "mesh",
                "description": "The left sleeve spikes when the arm rises.",
                "repair": "Rebuild the body.",
                "smallest_visible_character_height_pixels": 120,
            }
        ]
    )
    return {
        "asset_id": subject["asset_id"],
        "source_sha256": subject["source_sha256"],
        "accepted": accept,
        "criteria": [
            {"criterion": name, "passed": accept or index > 0, "evidence": "seen in every view"}
            for index, name in enumerate(criteria)
        ],
        "issues": issues,
        "notes": "stand-in reviewer",
    }


class StandIn:
    """Every paid call, answered; ``reject`` names reviews to reject, the first n of each."""

    def __init__(
        self,
        *,
        reject: Mapping[str, int] | None = None,
        damaged: int = 0,
        extra_views: tuple[str, ...] = (),
    ) -> None:
        self.reject = Counter(reject or {})
        self.damaged = damaged
        self.extra_views = extra_views
        #: The view names each mesh call was given.
        self.meshed: list[list[str]] = []
        self.calls: list[str] = []
        self.asked: Counter[str] = Counter()
        #: How many pictures each kind of episode opened with, the last time it ran.
        self.shown: dict[str, int] = {}
        self.prompts = {
            kind: (PACKAGE / "prompts" / name).read_text() for kind, name in EPISODES.items()
        }

    def services(self, store: Any) -> HostServices:
        async def turn(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
            del route, take
            kind = next(k for k, text in self.prompts.items() if request["system"].startswith(text))
            self.calls.append(f"agent.{kind}")
            self.shown[kind] = len(request["messages"][0].get("images", []))
            return CallRecord({}, self._turn(kind, request["messages"]), 0.01)

        async def image(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
            del route, take
            self.calls.append("image")
            png = _png(request["size"])
            return CallRecord(
                {"image": store.put_bytes(png, kind="image/png", name="image")}, None, 0.2
            )

        async def mesh(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
            del route, take
            self.calls.append("mesh")
            self.meshed.append(sorted(request["views"]))
            # Tripo's multiview vocabulary, as the real adapter refuses it.
            if set(request["views"]) - {"front", "back", "left", "right"}:
                raise CallRefused(
                    f"a multiview task takes the four sides: {sorted(request['views'])}"
                )
            views = sorted((name, file.digest) for name, file in request["views"].items())
            asked = hashlib.sha256(json.dumps(views).encode()).hexdigest()[:12]
            self.asked[asked] += 1
            document = {
                "kind": "part",
                "height": 1.0,
                "made_from": asked,
                "draw": self.asked[asked],
                "damaged": self.asked[asked] <= self.damaged,
            }
            model = store.put_bytes(glb(document), kind="model/gltf-binary", name="model")
            return CallRecord({"model": model}, {"facts": {"task": asked}}, 1.2)

        async def rig(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
            del route, take
            self.calls.append("rig")
            document = _model(request["model"])
            rigged = glb({**document, "rigged": True})
            model = store.put_bytes(rigged, kind="model/gltf-binary", name="model")
            return CallRecord({"model": model}, {"facts": {"riggable": True}}, 0.25)

        return HostServices(
            store=store,
            capabilities={
                "agent.turn": turn,
                "image.generate": image,
                "image.edit": image,
                "mesh.generate": mesh,
                "mesh.rig": rig,
            },
            live=True,
        )

    def _turn(self, kind: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        opening = json.loads(messages[0]["content"])
        tools = [m for m in messages if m["role"] == "tool"]
        for message in tools:
            assert not str(message["content"]).startswith(("refused:", "ValueError")), message
        if kind == "draw":
            made = [json.loads(m["content"])["asset"] for m in tools]
            wanted = [
                (r, v)
                for r in opening["profile"]["required_parts"]
                for v in ("front", "back", *self.extra_views)
            ]
            if not made:
                return _call(
                    "generate_reference",
                    purpose="canonical",
                    roles=[],
                    view=None,
                    prompt="The courier, full body, neutral pose.",
                    reference_asset_ids=[],
                    aspect_ratio="2:3",
                    reason="the canonical picture",
                )
            canonical = made[0]["asset_id"]
            if len(made) - 1 < len(wanted):
                role, view = wanted[len(made) - 1]
                return _call(
                    "generate_reference",
                    purpose="part_view",
                    roles=[role],
                    view=view,
                    prompt=f"The {role}, {view} view.",
                    reference_asset_ids=[canonical],
                    aspect_ratio="2:3",
                    reason=f"the {role} {view} view",
                )
            selections = [
                {"role": item["roles"][0], "view": item["view"], "asset_id": item["asset_id"]}
                for item in made[1:]
            ]
            return _call(
                "submit",
                canonical_asset_id=canonical,
                selections=selections,
                rationale="one canonical and a front and back of every part",
                open_issues=[],
            )
        if kind == "assemble":
            if not tools:
                parts = [
                    {
                        "part_id": part,
                        "uniform_scale": 1.0,
                        "rotation_degrees_xyz": [0, 0, 0],
                        "translation": [0, 0, 0],
                    }
                    for part in sorted(opening["available_parts"])
                ]
                return _call("build_assembly", parts=parts)
            built = json.loads(tools[-1]["content"])["asset_id"]
            return _call("submit", asset_id=built, rationale="stands on the ground", open_issues=[])
        if kind == "references":
            bundle = opening["bundle"]
            subject = {"asset_id": bundle["bundle_id"], "source_sha256": bundle["bundle_sha256"]}
        else:
            subject = opening
        accept = self.reject[kind] <= 0
        self.reject[kind] -= 1
        return _call("submit", **_verdict(subject, opening["required_criteria"], accept))


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir(parents=True, exist_ok=True)
    (project / "gnode.yaml").write_text("gnode: project/v1\n", encoding="utf-8")
    return project


def _inputs(tmp_path: Path, **settings: Any) -> Path:
    folder = tmp_path / "inputs"
    folder.mkdir(parents=True, exist_ok=True)
    document = dict(settings)
    if "parts" not in document:
        (folder / "brief.md").write_text(BRIEF, encoding="utf-8")
        document["brief"] = "brief.md"
    path = folder / "inputs.yaml"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _part(tmp_path: Path, role: str) -> str:
    path = tmp_path / "inputs" / f"{role}.glb"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(glb({"kind": "supplied", "role": role, "height": 1.0}))
    return path.name


async def _run(tmp_path: Path, stand_in: StandIn, run: str = "one", **settings: Any) -> RunOutcome:
    project = _project(tmp_path)
    plan = await plan_async(
        "character-3d", input_files=[_inputs(tmp_path, **settings)], cwd=project
    )
    assert plan.ok, plan.problems
    services = stand_in.services(plan.planner.store)
    return await WorkflowRun(plan, run_dir=project / "runs" / run, services=services).run()


def _result(outcome: RunOutcome) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((outcome.run_dir / "outputs/result.json").read_text())
    return document


async def test_a_brief_becomes_an_accepted_rigged_character(tmp_path: Path, blender: Path) -> None:
    stand_in = StandIn()
    outcome = await _run(tmp_path, stand_in)

    assert outcome.ok, outcome.failed
    assert Counter(stand_in.calls) == {
        "agent.draw": 4,
        "image": 3,
        "agent.references": 1,
        "mesh": 1,
        "agent.part": 1,
        "agent.assemble": 2,
        "agent.assembly": 1,
        "rig": 1,
        "agent.rig": 1,
    }
    result = _result(outcome)
    assert result["status"] == "accepted" and result["qualification_eligible"] is True
    assert result["quality_findings"]["numeric_findings"] == []
    outputs = outcome.run_dir / "outputs"
    character = unglb((outputs / "character.glb").read_bytes())
    assert character["kind"] == "export" and character["height"] == 2.0
    assert (outputs / "references.png").is_file()
    assert len(list((outputs / "atlas").glob("*.png"))) == 7


async def test_a_mesh_is_made_from_the_sides_and_its_review_sees_every_view(
    tmp_path: Path, blender: Path
) -> None:
    stand_in = StandIn(extra_views=("three_quarter",))
    outcome = await _run(tmp_path, stand_in)

    assert outcome.ok, outcome.failed
    assert stand_in.meshed == [["back", "front"]]
    assert stand_in.shown["part"] > StandIn().shown.get("part", 0)
    assert _result(outcome)["status"] == "accepted"


async def test_without_review_the_character_is_delivered_unreviewed(
    tmp_path: Path, blender: Path
) -> None:
    stand_in = StandIn()
    outcome = await _run(tmp_path, stand_in, review="none")

    assert outcome.ok, outcome.failed
    assert not any(
        call in stand_in.calls for call in ("agent.references", "agent.part", "agent.rig")
    )
    result = _result(outcome)
    assert result["status"] == "completed_unreviewed" and result["review_status"] == "skipped"
    assert not (outcome.run_dir / "outputs/atlas").exists()


async def test_supplied_parts_are_fitted_to_the_reference_and_rigged(
    tmp_path: Path, blender: Path
) -> None:
    parts = {role: _part(tmp_path, role) for role in ("body", "head", "hair")}
    (tmp_path / "inputs/sheet.png").write_bytes(_png("256x256"))
    stand_in = StandIn()
    outcome = await _run(
        tmp_path, stand_in, parts=parts, reference="sheet.png", partition="head_body_hair"
    )

    assert outcome.ok, outcome.failed
    assert "image" not in stand_in.calls and "mesh" not in stand_in.calls
    assert stand_in.shown["assemble"] == 1  # the reference sheet the parts are fitted to
    assert _result(outcome)["status"] == "accepted"
    assert unglb((outcome.run_dir / "outputs/character.glb").read_bytes())["meshes"] == [
        "body",
        "hair",
        "head",
    ]


async def test_supplied_parts_must_be_the_profiles_parts(tmp_path: Path, blender: Path) -> None:
    project = _project(tmp_path)
    inputs = _inputs(tmp_path, parts={"body": _part(tmp_path, "body")})

    plan = await plan_async("character-3d", input_files=[inputs], cwd=project)

    assert not plan.ok
    assert "missing required part roles: character" in str(plan.problems)


async def test_a_rejected_rig_rebuilds_the_body_from_a_new_mesh(
    tmp_path: Path, blender: Path
) -> None:
    stand_in = StandIn(reject={"rig": 1})
    outcome = await _run(tmp_path, stand_in)

    assert outcome.ok, outcome.failed
    assert stand_in.calls.count("mesh") == 2 and stand_in.calls.count("rig") == 2
    assert stand_in.calls.count("agent.rig") == 2
    assert stand_in.calls.count("image") == 3  # the references are not drawn again
    character = unglb((outcome.run_dir / "outputs/character.glb").read_bytes())
    assert character["draws"] == [2]
    assert _result(outcome)["status"] == "accepted"


async def test_a_rig_the_audit_refuses_is_rebuilt_without_paying_a_reviewer(
    tmp_path: Path, blender: Path
) -> None:
    stand_in = StandIn(damaged=1)
    outcome = await _run(tmp_path, stand_in)

    assert outcome.ok, outcome.failed
    assert stand_in.calls.count("mesh") == 2
    assert stand_in.calls.count("agent.rig") == 1  # the structural rejection is free
    assert _result(outcome)["status"] == "accepted"


async def test_a_rig_rejected_on_every_build_is_refused_with_the_reason(
    tmp_path: Path, blender: Path
) -> None:
    stand_in = StandIn(reject={"rig": 9})
    outcome = await _run(tmp_path, stand_in, rebuilds=2)

    assert not outcome.ok
    assert stand_in.calls.count("mesh") == 2
    failed = [r for i, r in outcome.results.items() if i.startswith("result#")]
    assert failed and "failed its independent review" in str(failed[0].error)


async def test_running_again_pays_for_nothing(tmp_path: Path, blender: Path) -> None:
    assert (await _run(tmp_path, StandIn())).ok
    again = StandIn()
    outcome = await _run(tmp_path, again, run="two")

    assert outcome.ok and again.calls == []


async def test_a_killed_run_resumes_to_the_same_character(tmp_path: Path, blender: Path) -> None:
    hold = tmp_path / "hold"
    hold.touch()
    first = StandIn()
    project = _project(tmp_path)
    plan = await plan_async("character-3d", input_files=[_inputs(tmp_path)], cwd=project)
    run_dir = project / "runs" / "one"
    task = asyncio.ensure_future(
        WorkflowRun(plan, run_dir=run_dir, services=first.services(plan.planner.store)).run()
    )
    await asyncio.to_thread(_wait_for, tmp_path / "hold.reached")
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    hold.unlink()
    assert "rig" in first.calls and "agent.rig" not in first.calls

    resumed = StandIn()
    replan = await plan_async("character-3d", input_files=[_inputs(tmp_path)], cwd=project)
    outcome = await WorkflowRun(
        replan, run_dir=run_dir, services=resumed.services(replan.planner.store)
    ).run()

    assert outcome.ok, outcome.failed
    assert resumed.calls == ["agent.rig"]
    whole = await _run(tmp_path / "again", StandIn())
    for name in ("character.glb", "result.json"):
        assert (run_dir / "outputs" / name).read_bytes() == (
            whole.run_dir / "outputs" / name
        ).read_bytes()


async def test_support_binds_the_closure_and_the_settings(tmp_path: Path, blender: Path) -> None:
    project = _project(tmp_path)
    plan = await plan_async("character-3d", input_files=[_inputs(tmp_path)], cwd=project)
    build = support.blender_build(blender)
    target = support.support_target(plan, blender=build)

    assert set(target["closure"]) == {
        "workflow_sha256",
        "lock",
        "types",
        "contracts",
        "routes",
        "blender",
    }
    assert set(target["closure"]["routes"]) == {
        "agent.turn",
        "image.generate",
        "image.edit",
        "mesh.generate",
        "mesh.rig",
    }
    assert support.admit(None, target)["mode"] == "development"
    record = {
        "schema_version": 1,
        "decision": "qualified_for_support",
        "qualification_id": "synthetic_host_test",
        "target": target,
        "evidence": {
            name: "d" * 64
            for name in (
                "cohort_manifest",
                "qualification_report",
                "calibration_report",
                "release_review",
            )
        },
    }
    assert support.admit(record, target)["support_qualified"] is True

    other_brief = tmp_path / "other"
    other = await plan_async(
        "character-3d", input_files=[_inputs(other_brief)], cwd=_project(other_brief)
    )
    assert support.admit(record, support.support_target(other, blender=build))["mode"] == (
        "supported"
    )
    stricter = await plan_async(
        "character-3d", input_files=[_inputs(tmp_path / "s", rounds=3)], cwd=project
    )
    with pytest.raises(support.SupportRefused, match="changed: rounds"):
        support.admit(record, support.support_target(stricter, blender=build))
    with pytest.raises(support.SupportRefused, match="changed: blender"):
        support.admit(record, support.support_target(plan, blender={"sha256": "e" * 64}))


def test_a_cohort_dry_run_plans_every_brief_under_one_target(
    tmp_path: Path, blender: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from stage_gen.workflows.character_3d import cohort

    (tmp_path / "briefs").mkdir()
    for name in ("pell", "orrin"):
        (tmp_path / "briefs" / f"{name}.md").write_text(BRIEF.replace("Pell", name.title()))
    (tmp_path / "cohort.yaml").write_text(
        "settings: { quality_bar: low, partition: whole }\n"
        "briefs: [briefs/pell.md, briefs/orrin.md]\n"
    )

    status = cohort.main(
        [str(tmp_path / "cohort.yaml"), "--out", str(tmp_path / "c1"), "--dry-run"]
    )

    assert status == 0, capsys.readouterr().err
    manifest = json.loads((tmp_path / "c1/cohort.json").read_text())
    assert manifest["kind"] == "character-3d-cohort-v1" and manifest["dry_run"] is True
    assert [e["episode_id"] for e in manifest["episodes"]] == ["pell", "orrin"]
    assert manifest["target"]["settings"]["quality_bar"] == "low"
    assert str(tmp_path) not in json.dumps(manifest)
    assert not (tmp_path / "c1/runs").exists()
    (tmp_path / "cohort.yaml").write_text("settings: {}\nbriefs: [briefs/pell.md]\n")
    assert (
        cohort.main([str(tmp_path / "cohort.yaml"), "--out", str(tmp_path / "c2"), "--dry-run"])
        == 2
    )
    assert "at least two briefs" in capsys.readouterr().err


async def test_a_calibration_episode_judges_a_frozen_rig_with_the_workflows_reviewer(
    tmp_path: Path, blender: Path
) -> None:
    profile = json.loads((PACKAGE / "profiles/sd_human_fixed.json").read_text())
    review = profile["review"]
    clips = [*review["required_diagnostics"][1:], review["required_motion"]]
    candidate = glb(
        {
            "kind": "export",
            "height": 2.0,
            "animations": [{"name": name} for name in ["rest", *clips]],
        }
    )
    folder = tmp_path / "subject"
    folder.mkdir()
    (folder / "candidate.glb").write_bytes(candidate)
    frozen = {
        "schema_version": 2,
        "kind": "rig_review_subject_v2",
        "candidate": {"path": "candidate.glb", "sha256": hashlib.sha256(candidate).hexdigest()},
        "required_criteria": review["rig_criteria"],
        "numeric_findings": [],
        "required_but_missing_weights": [],
        "rig_facts": {"clips": [{"name": n, "duration_seconds": 2.0} for n in clips]},
    }
    (folder / "subject.json").write_text(json.dumps(frozen))
    inputs = folder / "inputs.yaml"
    inputs.write_text(json.dumps({"subject": "subject.json", "candidate": "candidate.glb"}))
    stand_in = StandIn(reject={"rig": 1})
    project = _project(tmp_path / "episode")
    plan = await plan_async("character-3d-calibration", input_files=[inputs], cwd=project)
    assert plan.ok, plan.problems
    assert plan.planner.project.root == project.resolve()
    services = stand_in.services(plan.planner.store)

    outcome = await WorkflowRun(plan, run_dir=tmp_path / "run", services=services).run()

    assert outcome.ok, outcome.failed
    assert stand_in.calls == ["agent.rig"]
    verdict = json.loads((outcome.run_dir / "outputs/review.json").read_text())
    assert verdict["accepted"] is False and verdict["asset_id"] == "rig"
    assert verdict["source_sha256"] == frozen["candidate"]["sha256"]
    assert len(list((outcome.run_dir / "outputs/atlas").glob("*.png"))) == 7
    main = await plan_async("character-3d", input_files=[_inputs(tmp_path)], cwd=_project(tmp_path))
    reviewer = "./nodes/rig.py#review"
    assert {i.type_identity for i in plan.instances if i.uses == reviewer} == {
        i.type_identity for i in main.instances if i.uses == reviewer
    }
