"""Stage Gen's ``mesh.generate`` and ``mesh.rig`` on Tripo, as long jobs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from gnode import CallRefused, JobLog, NonRetryableError, Store
from gnode.providers.tripo import TripoFile, TripoResult
from stage_gen.config import load_config
from stage_gen.orchestration.gnode_plugin import mesh_job, mesh_routes, rig_job

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360f8cf000000020101a6f3f2660000000049454e44ae426082"
)
GLB = b"glTF" + b"\x00" * 16
FBX = b"Kaydara FBX Binary  \x00" + b"\x00" * 16


class FakeTripo:
    def __init__(self, *, riggable: bool = True, uncertain: bool = False) -> None:
        self.riggable, self.uncertain = riggable, uncertain
        self.posted: list[str] = []

    async def mesh_inputs(self, views: dict[str, Any]) -> list[dict[str, str]]:
        return [{view: "tok"} for view in views]

    async def submit_mesh(self, **_: Any) -> dict[str, Any]:
        self.posted.append("mesh")
        if self.uncertain:
            raise NonRetryableError("unknown", code="tripo_submission_uncertain")
        return {"task_id": "m1"}

    async def check_rig(self, glb: bytes, **_: Any) -> dict[str, Any]:
        return {"file_token": "t", "task_id": "c1", "riggable": self.riggable, "rig_type": "biped"}

    async def submit_rig(self, **_: Any) -> dict[str, Any]:
        self.posted.append("rig")
        return {"task_id": "r1"}

    async def collect(self, handle: dict[str, Any], **_: Any) -> TripoResult:
        files: tuple[TripoFile, ...]
        if handle["task_id"] == "r1":
            files = (TripoFile(GLB, "model/gltf-binary", "model"),)
        else:
            files = (
                TripoFile(GLB, "model/gltf-binary", "model"),
                TripoFile(FBX, "model/fbx", "pbr"),
            )
        return TripoResult(files, 1.25, {})

    async def aclose(self) -> None:
        return None


class Log(JobLog):
    def __init__(self) -> None:
        self.states: list[str] = []

    def submitting(self) -> None:
        self.states.append("submitting")

    def submitted(self, handle: Any) -> None:
        self.states.append("submitted")

    def settled(self) -> None:
        self.states.append("settled")


def _routes() -> dict[str, Any]:
    return {route.capability: route for route in mesh_routes()}


async def test_a_mesh_is_posted_once_and_its_fbx_kept(tmp_path: Path) -> None:
    store = Store(tmp_path / "cache")
    tripo = FakeTripo()
    job = mesh_job(load_config(), store, factory=lambda _: tripo)  # type: ignore[arg-type,return-value]
    views = {"front": store.put_bytes(PNG, kind="image/png", name="front.png")}
    log = Log()
    record = await job.start(_routes()["mesh.generate"], {"views": views, "quad": True}, 1, log)

    assert tripo.posted == ["mesh"] and log.states == ["submitting", "submitted"]
    assert record.files["model"].kind == "model/fbx" and record.cost_usd == 1.25


async def test_an_uncertain_mesh_post_stays_on_record(tmp_path: Path) -> None:
    store = Store(tmp_path / "cache")
    job = mesh_job(load_config(), store, factory=lambda _: FakeTripo(uncertain=True))  # type: ignore[arg-type,return-value]
    views = {"front": store.put_bytes(PNG, kind="image/png", name="front.png")}
    log = Log()
    with pytest.raises(NonRetryableError):
        await job.start(_routes()["mesh.generate"], {"views": views}, 1, log)
    assert log.states == ["submitting"]


async def test_a_doubted_model_is_rigged_only_when_allowed(tmp_path: Path) -> None:
    store = Store(tmp_path / "cache")
    model = store.put_bytes(GLB, kind="model/gltf-binary", name="model.glb")
    tripo = FakeTripo(riggable=False)
    job = rig_job(load_config(), store, factory=lambda _: tripo)  # type: ignore[arg-type,return-value]
    with pytest.raises(CallRefused, match="doubts"):
        await job.start(_routes()["mesh.rig"], {"model": model}, 1, Log())
    assert tripo.posted == []
    record = await job.start(
        _routes()["mesh.rig"], {"model": model, "allow_negative_check": True}, 1, Log()
    )
    assert tripo.posted == ["rig"]
    assert record.data["facts"] == {
        "riggable": False,
        "checked_rig_type": "biped",
        "advisory_override": True,
    }


async def test_only_a_glb_is_rigged(tmp_path: Path) -> None:
    store = Store(tmp_path / "cache")
    model = store.put_bytes(FBX, kind="model/fbx", name="model.fbx")
    job = rig_job(load_config(), store, factory=lambda _: FakeTripo())  # type: ignore[arg-type,return-value]
    with pytest.raises(CallRefused, match="rigs a GLB"):
        await job.start(_routes()["mesh.rig"], {"model": model}, 1, Log())


async def test_a_view_tripo_does_not_take_is_refused_before_anything_is_sent(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "cache")
    tripo = FakeTripo()
    job = mesh_job(load_config(), store, factory=lambda _: tripo)  # type: ignore[arg-type,return-value]
    views = {
        name: store.put_bytes(PNG, kind="image/png", name=f"{name}.png")
        for name in ("front", "three_quarter")
    }
    with pytest.raises(CallRefused, match="three_quarter"):
        await job.start(_routes()["mesh.generate"], {"views": views}, 1, Log())
    assert tripo.posted == []
