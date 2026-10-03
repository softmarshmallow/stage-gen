"""Movie sprite through gnode, offline: a take drawn once, finished, and kept by its request."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from gnode import (
    CallRecord,
    HostServices,
    JobLog,
    LongJob,
    Plan,
    Route,
    RunOutcome,
    WorkflowRun,
    plan_async,
    project_run,
    run_async,
    verify_run,
)
from stage_gen.workflows.movie_sprite.inputs.supplied_clip.make_inputs import make_inputs
from stage_gen.workflows.movie_sprite.nodes.take import QUIET_IDLE


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("_STAGE_GEN_DISABLE_DOTENV", "1")


def _green_take(path: Path) -> bytes:
    """A short clip on the green plate, as a take would come back."""

    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
            "color=c=0x0bf212:s=32x56:d=1:r=8,"
            "drawbox=x=10:y=14:w=12:h=28:color=0xd07a5a:t=fill",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
    )  # fmt: skip
    return path.read_bytes()


class FakeVideo:
    """``video.generate`` as a long job that answers every submission with one clip."""

    def __init__(self, clip: bytes) -> None:
        self.clip = clip
        self.prompts: list[str] = []

    def services(self, plan: Plan) -> HostServices:
        store = plan.planner.store

        async def start(
            route: Route, request: Mapping[str, Any], take: int, log: JobLog
        ) -> CallRecord:
            log.submitting()
            self.prompts.append(str(request["prompt"]))
            log.submitted({"request_id": f"job-{len(self.prompts)}"})
            return CallRecord(
                {"video": store.put_bytes(self.clip, kind="video/mp4", name="video")}, None, 0.09
            )

        async def collect(*_: Any) -> CallRecord:
            raise AssertionError("nothing was left to collect")

        return HostServices(
            store=store, capabilities={"video.generate": LongJob(start, collect)}, live=True
        )


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "gnode.yaml").write_text("gnode: project/v1\n", encoding="utf-8")
    return project


def _take_inputs(tmp_path: Path, name: str, **changes: Any) -> Path:
    folder = tmp_path / "inputs"
    make_inputs(folder)
    finish = {"source_mode": "chroma", "loop_closure": "none", "playback_seconds": 1}
    finish.update(changes.pop("finish", {}))
    (folder / f"{name}-finish.json").write_text(json.dumps(finish), encoding="utf-8")
    document = yaml.safe_load((folder / "take.yaml").read_text(encoding="utf-8"))
    document.update({"finish": f"{name}-finish.json", **changes})
    path = folder / f"{name}.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


async def _run(project: Path, inputs: Path, video: FakeVideo, run: str) -> RunOutcome:
    plan = await plan_async("movie-sprite", input_files=[inputs], cwd=project)
    assert plan.ok, plan.problems
    return await WorkflowRun(
        plan, run_dir=project / "runs" / run, services=video.services(plan)
    ).run()


async def test_a_take_is_drawn_once_and_a_finishing_change_reruns_only_finishing(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    video = FakeVideo(_green_take(tmp_path / "take.mp4"))
    first = await _run(project, _take_inputs(tmp_path, "first"), video, "first")
    longer = _take_inputs(tmp_path, "longer", finish={"playback_seconds": 2})
    second = await _run(project, longer, video, "second")

    assert first.ok and second.ok, (first.failed, second.failed)
    assert len(video.prompts) == 1
    caches = {node.node_id: node.cache for node in project_run(second.run_dir).nodes}
    assert caches == {"plate#1": "hit", "brief#1": "hit", "take#1": "hit", "finish#1": "miss"}
    manifest = json.loads((second.run_dir / "outputs/manifest.json").read_text(encoding="utf-8"))
    assert (manifest["playback_seconds"], manifest["alpha_mode"]) == (2.0, "straight")
    assert verify_run(second.run_dir) == []


async def test_the_brief_keeps_the_authors_sections_in_order(tmp_path: Path) -> None:
    project = _project(tmp_path)
    video = FakeVideo(_green_take(tmp_path / "take.mp4"))
    asked = _take_inputs(
        tmp_path,
        "asked",
        direction="A calm idle.",
        requested_motion=["Let the scarf settle.", "  "],
        constraints=["Keep the head still."],
    )
    quiet = _take_inputs(tmp_path, "quiet", direction="")
    assert (await _run(project, asked, video, "asked")).ok
    assert (await _run(project, quiet, video, "quiet")).ok

    prompt, default = video.prompts
    assert prompt.startswith("Animate this illustrated sprite")
    assert prompt.endswith(
        "Loop duration: 3 seconds.\n\nGeneral direction:\nA calm idle.\n\n"
        "Requested motion:\n- Let the scarf settle.\n\nConstraints:\n- Keep the head still."
    )
    assert default.endswith(f"Loop duration: 3 seconds.\n\nGeneral direction:\n{QUIET_IDLE}")


async def test_a_character_and_footage_together_are_refused_while_planning(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    both = _take_inputs(tmp_path, "both", footage="actor.mkv")
    plan = await plan_async("movie-sprite", input_files=[both], cwd=project)
    assert not plan.ok
    assert any("not both" in problem.message for problem in plan.problems)


async def test_supplied_footage_is_finished_for_free(tmp_path: Path) -> None:
    project = _project(tmp_path)
    make_inputs(tmp_path / "inputs")
    result = await run_async(
        "movie-sprite", input_files=[tmp_path / "inputs/clip.yaml"], cwd=project
    )

    assert result.ok, result.failed
    assert [node.node_id for node in project_run(result.run_dir).nodes] == ["finish#1"]
    manifest = json.loads(result.outputs["manifest"].path.read_bytes())
    assert (manifest["frame_count"], manifest["width"], manifest["height"]) == (12, 96, 160)
    assert result.outputs["loop"].path.read_bytes()[:4] == b"\x1aE\xdf\xa3"
    assert result.outputs["frames"].path.read_bytes()[:2] == b"PK"
    assert verify_run(result.run_dir) == []
