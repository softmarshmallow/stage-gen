"""Portrait motion through gnode, offline: every stage, every refusal, and the example.

The sample's stand-in answers each paid call from the drawn character's own colours and
returns the sheet as it was sent, so the whole chain runs; a test swaps one answer to make a
stage refuse.
"""

from __future__ import annotations

import json
import runpy
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from gnode import (
    CallRecord,
    HostServices,
    Route,
    RunOutcome,
    WorkflowRun,
    plan_async,
    project_run,
)
from stage_gen.examples import ImportRequest, MadeBy, currency, verify, write_example
from stage_gen.workflows._registry import load_code

MAKE = runpy.run_path(
    str(
        Path(__file__).resolve().parents[4]
        / "src/stage_gen/workflows/portrait_motion/inputs/make_inputs.py"
    )
)


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("_STAGE_GEN_DISABLE_DOTENV", "1")


class StandIn:
    """The sample's stand-in, counting calls, with one structured answer replaceable."""

    def __init__(self, replace: Mapping[str, Any] | None = None) -> None:
        self.replace = dict(replace or {})
        self.calls: list[str] = []

    def services(self, store: Any) -> HostServices:
        answers = MAKE["stand_in"](store)

        async def structured(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
            schema = Path(request["schema"].location).stem
            self.calls.append(schema)
            if schema in self.replace:
                return CallRecord({}, {"json": self.replace[schema]}, 0.0)
            record: CallRecord = await answers["structured.generate"](route, request, take)
            return record

        async def edit(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
            self.calls.append("sheet")
            record: CallRecord = await answers["image.edit"](route, request, take)
            return record

        return HostServices(
            store=store,
            capabilities={"structured.generate": structured, "image.edit": edit},
            live=True,
        )


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    (project / "gnode.yaml").write_text("gnode: project/v1\n", encoding="utf-8")
    return project


async def _run(tmp_path: Path, inputs: str, stand_in: StandIn, run: str) -> RunOutcome:
    folder = tmp_path / "inputs"
    MAKE["write_inputs"](folder)
    MAKE["write_whole"](folder)
    project = _project(tmp_path)
    plan = await plan_async("portrait-motion", input_files=[folder / inputs], cwd=project)
    assert plan.ok, plan.problems
    services = stand_in.services(plan.planner.store)
    return await WorkflowRun(plan, run_dir=project / "runs" / run, services=services).run()


def _result(outcome: RunOutcome) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (outcome.run_dir / "outputs/result.json").read_text(encoding="utf-8")
    )
    return document


async def test_the_face_goes_back_on_the_sprite_unchanged_outside_its_patches(
    tmp_path: Path,
) -> None:
    stand_in = StandIn()
    outcome = await _run(tmp_path, "face.yaml", stand_in, "face")

    assert outcome.ok, outcome.failed
    assert stand_in.calls == ["location", "admission", "sheet", "geometry", "quality"]
    assert _result(outcome)["status"] == "complete"
    outputs = outcome.run_dir / "outputs"
    with Image.open(outputs / "states/rest--rest.png") as rest:
        assert rest.size == (900, 1400) and rest.mode == "RGBA"
    assert len(list((outputs / "states").glob("*.png"))) == 9
    assert len(list((outputs / "patches").glob("*.png"))) == 6
    manifest = json.loads((outputs / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "portrait-face-motion-v2"
    assert manifest["patch_application"] == "replace_selected_rgb_preserve_original_alpha"


async def test_a_whole_portrait_keeps_its_reviewed_combinations(tmp_path: Path) -> None:
    stand_in = StandIn()
    outcome = await _run(tmp_path, "whole.yaml", stand_in, "whole")

    assert outcome.ok, outcome.failed
    assert stand_in.calls == ["admission", "sheet", "geometry", "quality"]
    outputs = outcome.run_dir / "outputs"
    assert _result(outcome)["status"] == "complete"
    assert not (outputs / "patches").exists()
    assert len(list((outputs / "states").glob("*.png"))) == 9


async def test_running_again_pays_for_nothing(tmp_path: Path) -> None:
    first = StandIn()
    assert (await _run(tmp_path, "face.yaml", first, "one")).ok
    again = StandIn()
    outcome = await _run(tmp_path, "face.yaml", again, "two")

    assert outcome.ok and again.calls == []
    caches = {node.cache for node in project_run(outcome.run_dir).nodes if node.cache}
    assert caches == {"hit"}


@pytest.mark.parametrize(
    ("replace", "refused_at", "calls"),
    [
        (
            {"location": {"status": "not_locatable", "bbox_xyxy": None, "reason": "No face."}},
            "face",
            ["location"],
        ),
        (
            {
                "admission": {
                    **MAKE["admission"](),
                    "features": [
                        {**feature, "route": "unsupported", "reason": "uncertain_boundary"}
                        for feature in MAKE["admission"]()["features"]
                    ],
                }
            },
            "admission",
            ["location", "admission"],
        ),
        (
            {
                "quality": {
                    **MAKE["quality"](["mouth"]),
                    "status": "fail",
                    "features": [
                        {"feature_id": f, "status": "fail", "reason": "A ghost lid survives."}
                        for f in ("canvas_left_eye", "canvas_right_eye", "mouth")
                    ],
                }
            },
            "quality",
            ["location", "admission", "sheet", "geometry", "quality"],
        ),
    ],
)
async def test_a_refusal_ends_the_chain_and_names_its_stage(
    tmp_path: Path, replace: dict[str, Any], refused_at: str, calls: list[str]
) -> None:
    stand_in = StandIn(replace)
    outcome = await _run(tmp_path, "face.yaml", stand_in, "refused")

    assert outcome.ok, outcome.failed
    assert stand_in.calls == calls
    result = _result(outcome)
    assert (result["status"], result["refused_at"]) == ("refused", refused_at)
    assert result["accepted_features"] == []
    assert not (outcome.run_dir / "outputs/patches").exists()


async def test_a_malformed_answer_is_drawn_again(tmp_path: Path) -> None:
    stand_in = StandIn({"admission": {"schema_version": 1, "features": []}})
    outcome = await _run(tmp_path, "face.yaml", stand_in, "malformed")

    assert not outcome.ok
    assert stand_in.calls.count("admission") == 6


async def test_an_accepted_face_imports_as_an_example(tmp_path: Path) -> None:
    outcome = await _run(tmp_path, "face.yaml", StandIn(), "example")
    assert outcome.ok, outcome.failed

    code = load_code("portrait-motion")
    assert code.import_example is not None and code.owns_run(outcome.run_dir)
    request = ImportRequest(
        example_id="face",
        made_by=MadeBy(kind="workflow", id="portrait-motion"),
        base=tmp_path,
        runs=(outcome.run_dir,),
        out=tmp_path / "store/portrait-motion/face",
    )
    example = code.import_example(request)

    assert example.importer == "gnode_run"
    assert example.outputs["rig"]["combinations_verified"] == 9
    assert example.outputs["face"]["kind"] == "animation"
    assert example.metrics["features_accepted"] == 3
    assert currency(example, code.type_ids(), code.graph_kinds()) == "current"
    pin = write_example(request.out, example, request.figures(example))
    assert verify(request.out, pin) == []


class ProcessDied(BaseException):
    """The process ending while a call is out: no handler code runs after it."""


async def test_a_sheet_edit_cut_off_mid_flight_stops_the_next_run_for_a_person(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "inputs"
    MAKE["write_inputs"](folder)
    project = _project(tmp_path)

    async def run(services: Any, name: str) -> RunOutcome:
        plan = await plan_async("portrait-motion", input_files=[folder / "face.yaml"], cwd=project)
        return await WorkflowRun(
            plan, run_dir=project / "runs" / name, services=services(plan.planner.store)
        ).run()

    def dying(store: Any) -> HostServices:
        services = StandIn().services(store)

        async def edit(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
            raise ProcessDied

        return HostServices(
            store=store,
            capabilities={**services.capabilities, "image.edit": edit},
            live=True,
        )

    with pytest.raises(ProcessDied):
        await run(dying, "one")
    again = StandIn()
    outcome = await run(again.services, "two")

    assert not outcome.ok and "sheet" not in again.calls
    assert "gnode jobs forget" in (outcome.results["draw.atlas#1"].error or "")
