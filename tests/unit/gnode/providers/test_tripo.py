"""Tripo: uploads and reads retried, each paid task posted once, models only from Tripo."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from gnode import NonRetryableError
from gnode.providers.tripo import TripoBackend, TripoTaskFailed, model_kind

GLB = b"glTF" + b"\x02\x00\x00\x00" + b"\x00" * 64
FBX = b"Kaydara FBX Binary  \x00" + b"\x00" * 64
STORAGE = "https://tripo-data.rg1.data.tripo3d.com/out/model.fbx"


class Tripo:
    """A scripted Tripo: counts posts, answers tasks from a status sequence."""

    def __init__(self, statuses: list[str], *, output: dict[str, Any] | None = None) -> None:
        self.statuses = statuses
        self.output = output or {"pbr_model": STORAGE}
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.uploads = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/files"):
            self.uploads += 1
            return _ok({"file_token": f"tok{self.uploads}"})
        if request.method == "POST":
            body = json.loads(request.content)
            self.posts.append((path, body))
            return _ok({"task_id": f"task{len(self.posts)}"})
        if "/tasks/" in path:
            task = path.rsplit("/", 1)[1]
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return _ok(
                {"task_id": task, "status": status, "output": self.output, "credits_consumed": 125}
            )
        if request.url.host.endswith("tripo3d.com"):
            return httpx.Response(200, content=FBX)
        raise AssertionError(f"unexpected {request.method} {request.url}")


def _ok(data: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={"code": 0, "data": data})


async def _no_sleep(_: float) -> None:
    return None


def _backend(tripo: Any) -> TripoBackend:
    client = httpx.AsyncClient(transport=httpx.MockTransport(tripo))
    return TripoBackend(api_key="k", client=client, sleep=_no_sleep)


async def test_a_mesh_task_is_posted_once_and_collected_with_its_cost() -> None:
    tripo = Tripo(["queued", "running", "success"])
    backend = _backend(tripo)
    inputs = await backend.mesh_inputs({"back": (b"b", "image/png"), "front": (b"f", "image/png")})
    handle = await backend.submit_mesh(model="P2", inputs=inputs, params={"quad": True})
    result = await backend.collect(handle, deadline_seconds=60)

    assert inputs == [{"front": "tok1"}, {"back": "tok2"}]
    assert tripo.posts == [
        ("/v3/generation/multiview-to-model", {"model": "P2", "quad": True, "inputs": inputs})
    ]
    assert [f.media_type for f in result.files] == ["model/fbx"]
    assert result.cost_usd == pytest.approx(1.25)


async def test_a_post_whose_outcome_is_unknown_is_never_repeated() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("gone")

    with pytest.raises(NonRetryableError) as raised:
        await _backend(broken).submit_mesh(model="P2", inputs=[{"front": "t"}], params={})
    assert raised.value.code == "tripo_submission_uncertain"


async def test_a_failed_task_is_over_and_one_still_running_stays_tripos() -> None:
    with pytest.raises(TripoTaskFailed):
        await _backend(Tripo(["failed"])).collect({"task_id": "task1"}, deadline_seconds=60)
    clock = iter([0.0, 0.0, 100.0])
    backend = TripoBackend(
        api_key="k",
        client=httpx.AsyncClient(transport=httpx.MockTransport(Tripo(["running"]))),
        sleep=_no_sleep,
        clock=lambda: next(clock),
    )
    with pytest.raises(NonRetryableError) as raised:
        await backend.collect({"task_id": "task1"}, deadline_seconds=10)
    assert raised.value.code == "tripo_job_outstanding"


async def test_a_model_from_another_host_is_refused() -> None:
    tripo = Tripo(["success"], output={"model": "https://example.com/model.glb"})
    with pytest.raises(ValueError, match="outside Tripo"):
        await _backend(tripo).collect({"task_id": "task1"}, deadline_seconds=60)


async def test_a_rig_is_checked_free_then_posted_once() -> None:
    tripo = Tripo(["success"], output={"riggable": True, "rig_type": "biped"})
    backend = _backend(tripo)
    check = await backend.check_rig(GLB, deadline_seconds=60)
    handle = await backend.submit_rig(model="v1", file_token=check["file_token"], params={})

    assert check == {
        "file_token": "tok1",
        "task_id": "task1",
        "riggable": True,
        "rig_type": "biped",
    }
    assert [path for path, _ in tripo.posts] == ["/v3/animations/rig-check", "/v3/animations/rig"]
    assert handle == {"task_id": "task2"}


def test_a_model_is_known_by_its_first_bytes() -> None:
    assert model_kind(GLB) == "model/gltf-binary" and model_kind(FBX) == "model/fbx"
    with pytest.raises(ValueError):
        model_kind(b"PK\x03\x04")
