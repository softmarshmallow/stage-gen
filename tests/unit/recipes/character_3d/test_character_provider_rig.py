"""Offline provider-rig contract/recovery tests; all HTTP uses MockTransport."""

from __future__ import annotations

import asyncio
import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest

from gnode import RetryExhaustedError, RetryPolicy, SoftwareIdentity
from stage_gen.components.character_3d.io import digest
from stage_gen.components.character_3d.provider_contracts import OperationStore
from stage_gen.components.character_3d.worker import rig_glb
from stage_gen.orchestration.character_3d.bindings import application_bindings
from stage_gen.providers.character_3d.rig import TripoRig, inspect_provider_rig, plan_rig, rig_cost

JsonObject = dict[str, Any]

IDENTITY = SoftwareIdentity(name="provider-rig-offline-test", version="1")
FAST = RetryPolicy(initial_delay_s=0, max_delay_s=0)
FBX = b"Kaydara FBX Binary  \x00\x1a\x00" + b"header-only local fixture"
SIGNED_URL = "https://tripo-data.rg1.data.tripo3d.com/model.fbx?signature=private-test-locator"


def glb_fixture(path: Path, *, rigged: bool = False, zero_weights: bool = False) -> bytes:
    doc: JsonObject = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": 0}],
        "nodes": [{"name": "Mesh", "mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    binary = bytearray()
    position = rig_glb.append_accessor(doc, binary, [[0, 0, 0], [1, 0, 0], [0, 1, 0]], 5126, "VEC3")
    attrs = {"POSITION": position}
    if rigged:
        doc["nodes"][0].update(skin=0, children=[1])
        doc["nodes"].extend([{"name": "Hips", "children": [2]}, {"name": "Head"}])
        ibm = rig_glb.append_accessor(doc, binary, [np.eye(4).flatten().tolist()] * 2, 5126, "MAT4")
        doc["skins"] = [{"joints": [1, 2], "inverseBindMatrices": ibm}]
        attrs["JOINTS_0"] = rig_glb.append_accessor(doc, binary, [[0, 1, 0, 0]] * 3, 5121, "VEC4")
        weights = [0, 0, 0, 0] if zero_weights else [0.75, 0.25, 0, 0]
        attrs["WEIGHTS_0"] = rig_glb.append_accessor(doc, binary, [weights] * 3, 5126, "VEC4")
    doc["meshes"] = [{"primitives": [{"attributes": attrs}]}]
    rig_glb.save_glb(path, doc, binary)
    return path.read_bytes()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "outputs").mkdir()
    glb_fixture(tmp_path / "unrigged.glb")
    (tmp_path / "generation").mkdir()
    (tmp_path / "generation/model.fbx").write_bytes(FBX)
    (tmp_path / "generation/result.json").write_text(
        json.dumps(
            {
                "status": "raw_parts_collected",
                "task_id": "generation-task",
                "plan_sha256": "a" * 64,
                "artifacts": [
                    {"path": "model.fbx", "sha256": digest(tmp_path / "generation/model.fbx")}
                ],
            }
        )
    )
    return tmp_path


def spec(root: Path, *, native: bool = False, allow_negative: bool = True) -> JsonObject:
    source: JsonObject = {
        "kind": "generation_task",
        "task_id": "generation-task",
        "lineage": {
            "path": "generation/result.json",
            "sha256": digest(root / "generation/result.json"),
        },
    }
    if not native:
        source = {
            "kind": "local_mesh",
            "path": "unrigged.glb",
            "sha256": digest(root / "unrigged.glb"),
        }
    return {
        "schema_version": 1,
        "operation_id": "test-rig",
        "operation": "body_rig",
        "prompt": "Rig this original humanoid fixture",
        "source": source,
        "params": {"rig_type": "biped", "spec": "mixamo", "out_format": "glb"},
        "rights_basis": "Original test fixture",
        "reservation_usd": 1,
        "allow_negative_check": allow_negative,
    }


def reservation(plan: JsonObject) -> JsonObject:
    return {
        "reservation_id": "test-reservation",
        "plan_sha256": plan["plan_sha256"],
        "amount_usd": 1,
    }


class Provider:
    def __init__(
        self,
        *,
        payload: bytes = FBX,
        riggable: bool = True,
        credit: object = 25,
        failure: str | None = None,
    ) -> None:
        self.payload, self.riggable, self.credit, self.failure = payload, riggable, credit, failure
        self.calls: list[tuple[str, str, bytes]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path, bytes(request.content)))
        path = request.url.path
        if request.method == "POST":
            if self.failure and path.endswith(self.failure):
                raise httpx.ReadTimeout("uncertain operation")
            if path.endswith("/files"):
                return httpx.Response(
                    200, json={"code": 0, "data": {"file_token": "uploaded-model"}}
                )
            task = "check-task" if path.endswith("rig-check") else "rig-task"
            return httpx.Response(200, json={"code": 0, "data": {"task_id": task}})
        if path.endswith("/tasks/check-task"):
            data: JsonObject = {
                "task_id": "check-task",
                "status": "success",
                "credits_consumed": 0,
                "output": {"riggable": self.riggable, "rig_type": "biped"},
            }
        elif path.endswith("/tasks/rig-task"):
            data = {"task_id": "rig-task", "status": "success", "output": {"model_url": SIGNED_URL}}
            if self.credit is not None:
                data["credits_consumed"] = self.credit
        else:
            assert "authorization" not in request.headers
            return httpx.Response(200, content=self.payload)
        return httpx.Response(200, json={"code": 0, "data": data})

    def count(self, suffix: str) -> int:
        return sum(path.endswith(suffix) for _, path, _ in self.calls)


TABLE = application_bindings()


def adapter(root: Path, provider: Provider) -> TripoRig:
    return TripoRig(
        api_key="not-a-real-provider-key",
        input_root=root,
        output_root=root / "outputs",
        client=httpx.AsyncClient(transport=httpx.MockTransport(provider)),
        retry_policy=FAST,
        bindings=TABLE,
        component=IDENTITY,
        tool=IDENTITY,
    )


async def checked(client: TripoRig, plan: JsonObject) -> JsonObject:
    await client.submit_check(plan, reservation=reservation(plan), live=True)
    return await client.collect_check(plan, live=True)


async def submitted(client: TripoRig, plan: JsonObject) -> JsonObject:
    await checked(client, plan)
    return await client.submit(plan, reservation=reservation(plan), live=True)


def test_plan_rejects_wrong_input_and_route_before_requests(root: Path) -> None:
    request = spec(root)
    for change in ({"rig_type": "quadruped"}, {"out_format": "zip"}, {"model": "other"}):
        changed = copy.deepcopy(request)
        changed["params"].update(change)
        with pytest.raises(ValueError):
            plan_rig(changed, input_root=root, bindings=TABLE)
    glb_fixture(root / "rigged.glb", rigged=True)
    request["source"] = {
        "kind": "local_mesh",
        "path": "rigged.glb",
        "sha256": digest(root / "rigged.glb"),
    }
    with pytest.raises(ValueError, match="no existing rig"):
        plan_rig(request, input_root=root, bindings=TABLE)


@pytest.mark.parametrize("native", [False, True])
def test_frozen_input_and_live_gate_precede_all_http(root: Path, native: bool) -> None:
    plan = plan_rig(spec(root, native=native), input_root=root, bindings=TABLE)
    provider = Provider()
    client = adapter(root, provider)
    with pytest.raises(ValueError):
        asyncio.run(client.submit_check(plan, reservation=reservation(plan)))
    (root / ("generation/model.fbx" if native else "unrigged.glb")).write_bytes(b"changed")
    with pytest.raises(ValueError):
        asyncio.run(client.submit_check(plan, reservation=reservation(plan), live=True))
    assert provider.calls == []


@pytest.mark.parametrize("native", [False, True])
def test_native_fbx_collection_and_exact_cost_without_model_substitution(
    root: Path, native: bool
) -> None:
    plan = plan_rig(spec(root, native=native), input_root=root, bindings=TABLE)
    provider = Provider(riggable=False)
    client = adapter(root, provider)
    asyncio.run(submitted(client, plan))
    asyncio.run(client.submit(plan, reservation=reservation(plan), live=True))
    result = asyncio.run(client.collect(plan, live=True))
    count = len(provider.calls)
    assert asyncio.run(client.collect(plan)) == result
    assert len(provider.calls) == count
    assert provider.count("/files") == (0 if native else 1)
    assert provider.count("/animations/rig") == 1
    body = json.loads(
        next(body for _, path, body in provider.calls if path.endswith("/animations/rig"))
    )
    assert body["input"] == ("generation-task" if native else "uploaded-model")
    assert result["status"] == "raw_rig_collected" and result["format_contract_deviation"]
    assert result["rig_verified"] is None and result["local_import_required"] is True
    assert result["inspections"][0]["bones"] is None
    store = OperationStore(root / "outputs", plan["operation_id"])
    assert (store.path / result["artifacts"][0]["path"]).read_bytes() == FBX
    assert rig_cost(store, plan, input_root=root, bindings=TABLE) == Decimal(".25")
    for path in (root / "outputs").rglob("*.json"):
        assert "private-test-locator" not in path.read_text()
        assert "not-a-real-provider-key" not in path.read_text()


def test_glb_result_reports_referenced_bones_and_nonzero_weights(root: Path) -> None:
    data = glb_fixture(root / "provider.glb", rigged=True)
    provider = Provider(payload=data)
    client = adapter(root, provider)
    plan = plan_rig(spec(root), input_root=root, bindings=TABLE)
    asyncio.run(submitted(client, plan))
    result = asyncio.run(client.collect(plan, live=True))
    evidence = result["inspections"][0]
    assert result["rig_verified"] is True and not result["format_contract_deviation"]
    assert evidence["weighted_vertices"] == 3
    assert [item["name"] for item in evidence["bones"]] == ["Hips", "Head"]
    assert all(item["has_nonzero_weights"] for item in evidence["bones"])


def test_zero_weights_do_not_pass_structural_validation(root: Path) -> None:
    data = glb_fixture(root / "zero.glb", rigged=True, zero_weights=True)
    provider = Provider(payload=data)
    client = adapter(root, provider)
    plan = plan_rig(spec(root), input_root=root, bindings=TABLE)
    asyncio.run(submitted(client, plan))
    with pytest.raises(RetryExhaustedError):
        asyncio.run(client.collect(plan, live=True))
    assert provider.count("/model.fbx") == 6
    assert provider.count("/animations/rig") == 1
    assert not (root / "outputs/test-rig/result.json").exists()


@pytest.mark.parametrize("failure", ["/files", "/animations/rig-check", "/animations/rig"])
def test_uncertain_posts_are_never_repeated(root: Path, failure: str) -> None:
    provider = Provider(failure=failure)
    client = adapter(root, provider)
    plan = plan_rig(spec(root), input_root=root, bindings=TABLE)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            asyncio.run(submitted(client, plan))
    assert provider.count(failure) == 1
    if failure == "/animations/rig":
        assert provider.count("/files") == 1
    state = json.loads((root / "outputs/test-rig/state.json").read_text())
    assert state["cost_status"] == "reserved_actual_unknown"


def test_strict_negative_check_policy_makes_no_paid_post(root: Path) -> None:
    provider = Provider(riggable=False)
    client = adapter(root, provider)
    plan = plan_rig(spec(root, allow_negative=False), input_root=root, bindings=TABLE)
    asyncio.run(checked(client, plan))
    with pytest.raises(ValueError, match="Frozen policy"):
        asyncio.run(client.submit(plan, reservation=reservation(plan), live=True))
    assert provider.count("/animations/rig") == 0


@pytest.mark.parametrize("credit", [None, True, "25"])
def test_unknown_or_invalid_terminal_credits_remain_unknown(root: Path, credit: object) -> None:
    provider = Provider(credit=credit)
    client = adapter(root, provider)
    plan = plan_rig(spec(root), input_root=root, bindings=TABLE)
    asyncio.run(submitted(client, plan))
    result = asyncio.run(client.collect(plan, live=True))
    assert result["terminal_usage"] is None
    assert (
        rig_cost(
            OperationStore(root / "outputs", plan["operation_id"]),
            plan,
            input_root=root,
            bindings=TABLE,
        )
        is None
    )


def test_changed_cached_provenance_refuses_reuse_without_network(root: Path) -> None:
    provider = Provider()
    client = adapter(root, provider)
    plan = plan_rig(spec(root), input_root=root, bindings=TABLE)
    asyncio.run(submitted(client, plan))
    result = asyncio.run(client.collect(plan, live=True))
    path = root / "outputs/test-rig" / result["artifacts"][0]["provenance_path"]
    path.write_bytes(path.read_bytes() + b" ")
    count = len(provider.calls)
    with pytest.raises(ValueError, match="provenance changed"):
        asyncio.run(client.collect(plan))
    assert len(provider.calls) == count


def test_collection_resumes_after_atomic_pair_before_result(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Provider()
    client = adapter(root, provider)
    plan = plan_rig(spec(root), input_root=root, bindings=TABLE)
    asyncio.run(submitted(client, plan))
    write = OperationStore.write
    failed = False

    def crash(self: OperationStore, name: str, value: JsonObject) -> None:
        nonlocal failed
        if name == "result.json" and not failed:
            failed = True
            raise OSError("injected process boundary")
        return write(self, name, value)

    monkeypatch.setattr(OperationStore, "write", crash)
    with pytest.raises(OSError):
        asyncio.run(client.collect(plan, live=True))
    result = asyncio.run(client.collect(plan, live=True))
    assert result["status"] == "raw_rig_collected"
    assert provider.count("/animations/rig") == 1
    assert rig_cost(
        OperationStore(root / "outputs", plan["operation_id"]),
        plan,
        input_root=root,
        bindings=TABLE,
    ) == Decimal(".25")


def test_read_only_actual_artifact_inspection_has_no_provider_dependency(root: Path) -> None:
    (root / "native.fbx").write_bytes(FBX)
    assert inspect_provider_rig(root / "native.fbx")["rig_verified"] is None
    glb_fixture(root / "actual.glb", rigged=True)
    assert inspect_provider_rig(root / "actual.glb")["bone_count"] == 2
