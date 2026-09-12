"""Contained provider rigging: frozen inputs, one submission, resumable collection.

The caller owns budget allocation and scheduling. This module does not author a
skeleton, alter provider geometry, normalize FBX, retarget motion or accept art.
"""

from __future__ import annotations

import hashlib
import tempfile
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import httpx
import numpy as np

from gnode import (
    BinaryArtifact,
    BindingTable,
    InputProvenance,
    ModelRef,
    ProvenanceInput,
    RetryContext,
    retry_with_backoff,
    write_artifact_with_provenance,
)
from stage_gen.components.character_3d.io import (
    canonical_digest,
    confined,
    digest,
    read_json,
    verified_input,
)
from stage_gen.components.character_3d.provider_contracts import (
    OperationStore,
    artifact_record,
    identifier,
    inspect_mesh,
    positive_amount,
)
from stage_gen.providers.character_3d.tripo import (
    API_ROOT,
    TripoParts,
    model_urls,
    response_data,
)
from stage_gen.providers.character_3d.tripo_pricing import credits_value

JsonObject = dict[str, Any]
RIG_PRICING = {
    "provider": "tripo",
    "checked_on": "2026-09-11",
    "usd_per_credit": "0.01",
    "estimated_rig_credits": "25",
    "estimated_check_credits": "0",
    "value_basis": "standard_api_usage_value",
    "sources": [
        "https://developers.tripo3d.ai/en/pricing",
        "https://developers.tripo3d.ai/en/docs/task-query",
    ],
}
CONTRACT_SOURCES = [
    "https://developers.tripo3d.ai/en/docs/animations-rig",
    "https://developers.tripo3d.ai/en/docs/animations-rig-check",
    "https://developers.tripo3d.ai/en/docs/files",
]
SPEC_FIELDS = {
    "schema_version",
    "operation_id",
    "operation",
    "prompt",
    "source",
    "params",
    "rights_basis",
    "reservation_usd",
    "allow_negative_check",
}
GENERATION_STATUSES = {
    "success",
    "raw_parts_collected",
    "artifact_validated_exploratory_unreviewed",
    "raw_format_preserved_requires_local_normalization",
}


def _table(bindings: BindingTable | None) -> BindingTable:
    if bindings is None:
        raise ValueError("Rig planning requires the application's binding table")
    return bindings


def _hash(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("Expected a lowercase SHA256 digest")
    return value


def _glb(path: Path) -> tuple[ModuleType, JsonObject, bytearray]:
    from stage_gen.components.character_3d.worker import rig_glb

    return (rig_glb, *rig_glb.read_glb(path))


def _local_source(source: JsonObject, input_root: Path) -> JsonObject:
    if set(source) != {"kind", "path", "sha256"}:
        raise ValueError("Local rig source requires kind, path and sha256")
    _hash(source["sha256"])
    path = verified_input(input_root, {k: source[k] for k in ("path", "sha256")})
    inspection = inspect_mesh(path.read_bytes())
    if inspection["format"] != "glb":
        raise ValueError("Local rig input must be a self-contained unrigged GLB")
    _, doc, _ = _glb(path)
    if (
        not doc.get("meshes")
        or doc.get("skins")
        or doc.get("animations")
        or any("skin" in n for n in doc.get("nodes", []))
        or any(
            any(k.startswith(("JOINTS_", "WEIGHTS_")) for k in p.get("attributes", {}))
            for m in doc["meshes"]
            for p in m.get("primitives", [])
        )
    ):
        raise ValueError("Local rig input must contain geometry and no existing rig or animation")
    return {
        "kind": "local_mesh",
        "path": source["path"],
        "sha256": source["sha256"],
        "size_bytes": path.stat().st_size,
        "format": "glb",
    }


def _generation_source(source: JsonObject, input_root: Path) -> JsonObject:
    if set(source) != {"kind", "task_id", "lineage"}:
        raise ValueError("Native rig source requires kind, task_id and lineage descriptor")
    task_id = identifier(source["task_id"])
    lineage_path = verified_input(input_root, source["lineage"])
    record = read_json(lineage_path)
    if (
        record.get("task_id") != task_id
        or record.get("status") not in GENERATION_STATUSES
        or (not isinstance(record.get("plan_sha256"), str))
    ):
        raise ValueError("Native rig source needs matching successful generation evidence")
    _hash(record["plan_sha256"])
    artifacts = record.get("artifacts", record.get("outputs"))
    if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= 8:
        raise ValueError("Generation evidence must name its collected model artifacts")
    checked = []
    for item in artifacts:
        ref = item.get("path", item.get("artifact_path"))
        path = verified_input(
            lineage_path.parent, {"path": ref, "sha256": _hash(item.get("sha256"))}
        )
        inspection = inspect_mesh(path.read_bytes())
        checked.append(
            {
                "path": path.relative_to(input_root.resolve()).as_posix(),
                "sha256": item["sha256"],
                "format": inspection["format"],
            }
        )
    return {
        "kind": "generation_task",
        "task_id": task_id,
        "lineage": source["lineage"],
        "generation_plan_sha256": record["plan_sha256"],
        "collected_artifacts": checked,
        "model_uploads": 0,
    }


def plan_rig(
    spec: JsonObject, *, input_root: Path, bindings: BindingTable | None = None
) -> JsonObject:
    """Freeze an operation offline; model identity comes from a binding table."""
    spec = {"allow_negative_check": True, **spec}
    if (
        set(spec) != SPEC_FIELDS
        or type(spec["schema_version"]) is not int
        or spec["schema_version"] != 1
        or (spec["operation"] != "body_rig")
    ):
        raise ValueError("Rig spec has unsupported or missing fields")
    identifier(spec["operation_id"])
    if any(not isinstance(spec[k], str) or not spec[k].strip() for k in ("prompt", "rights_basis")):
        raise ValueError("Rig intent and input rights basis must be nonempty")
    if type(spec["allow_negative_check"]) is not bool:
        raise ValueError("allow_negative_check must be a frozen boolean")
    source, params = (spec["source"], spec["params"])
    if not isinstance(source, dict) or source.get("kind") not in {"local_mesh", "generation_task"}:
        raise ValueError("Unsupported rig input source")
    if (
        not isinstance(params, dict)
        or set(params) != {"rig_type", "spec", "out_format"}
        or params["rig_type"] != "biped"
        or (params["spec"] not in {"mixamo", "tripo"})
        or (params["out_format"] not in {"glb", "fbx"})
    ):
        raise ValueError(
            "Only the verified biped rig, named specification and FBX/GLB outputs are supported"
        )
    binding = _table(bindings).require(
        "body_rig",
        "biped",
        "rig_check",
        "native_fbx_or_glb",
        "local_glb_input" if source["kind"] == "local_mesh" else "generation_task_input",
    )
    if str(binding.model) != "v1.0-20240301@tripo":
        raise ValueError("This adapter contract has only verified the selected Tripo biped route")
    evidence = (_local_source if source["kind"] == "local_mesh" else _generation_source)(
        source, input_root
    )
    if source["kind"] == "local_mesh":
        binding.within("input_bytes", evidence["size_bytes"], subject="unrigged GLB")
    if positive_amount(spec["reservation_usd"]) < binding.estimated_cost_high_usd:
        raise ValueError("Rig reservation is below the binding estimate")
    plan = {
        **spec,
        "route": str(binding.model),
        "features": sorted(binding.features),
        "source_evidence": evidence,
        "source_sha256": canonical_digest(evidence),
        "contract_checked_on": binding.verified_on,
        "contract_sources": CONTRACT_SOURCES,
        "pricing": RIG_PRICING,
        "status": "planned_unspent",
        "maximum_paid_submissions": 1,
        "maximum_check_submissions": 1,
        "maximum_polls_per_task": 120,
    }
    return {**plan, "plan_sha256": canonical_digest(plan)}


def validate_rig_plan(
    plan: JsonObject, *, input_root: Path, bindings: BindingTable | None = None
) -> None:
    if (
        plan_rig({k: plan[k] for k in SPEC_FIELDS}, input_root=input_root, bindings=bindings)
        != plan
    ):
        raise ValueError("Rig plan, binding or source lineage changed; replan offline")


def inspect_provider_rig(path: Path) -> JsonObject:
    """Report actual GLB bones and weighted geometry; FBX requires local import."""
    inspection = inspect_mesh(path.read_bytes())
    if inspection["format"] == "fbx":
        return {
            **inspection,
            "rig_verified": None,
            "bones": None,
            "weighted_vertices": None,
            "local_import_required": True,
            "semantic_status": "unreviewed",
        }
    glb, doc, binary = _glb(path)
    nodes, skins = (doc.get("nodes", []), doc.get("skins", []))
    if not skins:
        raise ValueError("Returned GLB has no skin")
    parents = {
        child: index for index, node in enumerate(nodes) for child in node.get("children", [])
    }
    bones, weighted_vertices, primitives, unskinned = ({}, 0, 0, [])
    for skin in skins:
        joints = skin.get("joints", [])
        if (
            not joints
            or len(set(joints)) != len(joints)
            or any(type(j) is not int or not 0 <= j < len(nodes) for j in joints)
        ):
            raise ValueError("Returned skin has invalid joint references")
        if "inverseBindMatrices" in skin:
            matrices = glb.accessor(doc, binary, skin["inverseBindMatrices"])
            if matrices.shape != (len(joints), 16):
                raise ValueError("Inverse bind matrices do not match the joints")
        for joint in joints:
            name = nodes[joint].get("name", "")
            if not isinstance(name, str) or len(name) > 256:
                raise ValueError("Invalid returned bone name")
            bones[joint] = {
                "node_index": joint,
                "name": name,
                "parent_node_index": parents.get(joint),
                "has_nonzero_weights": False,
            }
    for node_index, node in enumerate(nodes):
        if "mesh" not in node:
            continue
        if "skin" not in node:
            unskinned.append(node_index)
            continue
        if type(node["skin"]) is not int or not 0 <= node["skin"] < len(skins):
            raise ValueError("Mesh references an invalid skin")
        joints = skins[node["skin"]]["joints"]
        for primitive in doc["meshes"][node["mesh"]]["primitives"]:
            attrs = primitive["attributes"]
            positions = glb.accessor(doc, binary, attrs["POSITION"])
            sets = sorted(k[7:] for k in attrs if k.startswith("JOINTS_"))
            if (
                not sets
                or sets != [str(i) for i in range(len(sets))]
                or any("WEIGHTS_" + s not in attrs for s in sets)
            ):
                raise ValueError(
                    "Returned primitive lacks matching contiguous joint/weight attributes"
                )
            if {k[8:] for k in attrs if k.startswith("WEIGHTS_")} != set(sets):
                raise ValueError("Returned primitive contains unmatched weight attributes")
            totals = np.zeros(len(positions))
            for number in sets:
                joint_accessor = doc["accessors"][attrs["JOINTS_" + number]]
                weight_accessor = doc["accessors"][attrs["WEIGHTS_" + number]]
                if joint_accessor["componentType"] not in {5121, 5123} or joint_accessor.get(
                    "normalized"
                ):
                    raise ValueError("Joint indices must be unnormalized unsigned bytes/shorts")
                if weight_accessor["componentType"] not in {5121, 5123, 5126} or (
                    weight_accessor["componentType"] != 5126
                    and (not weight_accessor.get("normalized"))
                ):
                    raise ValueError("Weights require floats or normalized unsigned integers")
                indices = glb.accessor(doc, binary, attrs["JOINTS_" + number])
                weights = glb.accessor(doc, binary, attrs["WEIGHTS_" + number])
                if (
                    indices.shape != (len(positions), 4)
                    or weights.shape != indices.shape
                    or np.any(indices >= len(joints))
                    or np.any(weights < 0)
                    or np.any(weights > 1)
                ):
                    raise ValueError("Invalid per-vertex joint indices or weights")
                totals += weights.sum(axis=1)
                for index in np.unique(indices[weights > 0]):
                    bones[joints[int(index)]]["has_nonzero_weights"] = True
            if not len(totals) or np.any(np.abs(totals - 1) > 0.02):
                raise ValueError("Returned mesh has unweighted vertices or invalid weight sums")
            weighted_vertices += len(totals)
            primitives += 1
    if not primitives or not weighted_vertices:
        raise ValueError("Returned GLB has bones but no weighted mesh")
    return {
        **inspection,
        "validation_scope": "referenced_bones_and_weights",
        "rig_verified": True,
        "bone_count": len(bones),
        "bones": [bones[k] for k in sorted(bones)],
        "skin_count": len(skins),
        "weighted_primitives": primitives,
        "weighted_vertices": weighted_vertices,
        "unskinned_mesh_nodes": unskinned,
        "local_import_required": False,
        "semantic_status": "unreviewed",
    }


def _usage(plan: JsonObject, task_id: str, response: JsonObject) -> JsonObject | None:
    value = credits_value(response.get("credits_consumed"))
    if response.get("task_id") != task_id or response.get("status") not in {
        "success",
        "failed",
        "cancelled",
    }:
        return None
    if value is None:
        return None
    credits, usd = value
    return {
        "provider": "tripo",
        "route": plan["route"],
        "task_id": task_id,
        "plan_sha256": plan["plan_sha256"],
        "task_status": response["status"],
        "credits_consumed": str(credits),
        "standard_api_usage_usd": str(usd),
        "value_basis": "standard_api_usage_value",
        "pricing_sha256": canonical_digest(plan["pricing"]),
    }


def _check_result(store: OperationStore, plan: JsonObject) -> JsonObject:
    result, state = (store.read("check-result.json"), store.read("check-state.json"))
    if result is None:
        raise ValueError("A completed advisory rig check is required")
    if (
        not state
        or result.get("plan_sha256") != plan["plan_sha256"]
        or state.get("task_id") != result.get("task_id")
        or (state.get("result_sha256") != canonical_digest(result))
        or (result.get("status") != "riggability_checked")
        or (type(result.get("riggable")) is not bool)
    ):
        raise ValueError("Rig check evidence changed")
    return result


def _provenance_input(plan: JsonObject) -> JsonObject:
    source = plan["source"]
    ref = (
        {k: source[k] for k in ("path", "sha256")}
        if source["kind"] == "local_mesh"
        else source["lineage"]
    )
    return cast(JsonObject, ref)


def verify_rig_result(store: OperationStore, plan: JsonObject) -> JsonObject | None:
    result = store.read("result.json")
    if result is None:
        return None
    state = store.read("state.json") or {}
    if (
        result.get("plan_sha256") != plan["plan_sha256"]
        or result.get("task_id") != state.get("task_id")
        or result.get("status") != "raw_rig_collected"
        or (state.get("result_sha256") != canonical_digest(result))
        or (not result.get("artifacts"))
        or (len(result["artifacts"]) != len(result.get("inspections", [])))
    ):
        raise ValueError("Collected rig result lineage changed")
    for item, inspection in zip(result["artifacts"], result["inspections"], strict=True):
        path, sidecar = (
            confined(store.path, item["path"]),
            confined(store.path, item["provenance_path"]),
        )
        if digest(path) != item["sha256"] or digest(sidecar) != item["provenance_sha256"]:
            raise ValueError("Cached rig artifact or provenance changed")
        if inspect_provider_rig(path) != inspection:
            raise ValueError("Cached rig structural evidence changed")
        _verify_provenance(read_json(sidecar), plan, result["task_id"], item["sha256"])
    return result


def _verify_provenance(
    metadata: JsonObject, plan: JsonObject, task_id: str, artifact_sha: str
) -> None:
    ref = _provenance_input(plan)
    params = metadata.get("params", {})
    if (
        metadata.get("provider") != "tripo"
        or metadata.get("model") != ModelRef.parse(plan["route"]).model
        or metadata.get("artifact", {}).get("sha256") != artifact_sha
        or (metadata.get("prompt") != plan["prompt"])
        or (
            metadata.get("inputs")
            != [{"ref": ref["path"], "sha256": ref["sha256"], "source": "reference"}]
        )
        or (params.get("plan_sha256") != plan["plan_sha256"])
        or (params.get("task_id") != task_id)
        or (params.get("request") != plan["params"])
        or (params.get("source_sha256") != plan["source_sha256"])
    ):
        raise ValueError("Rig provenance differs from the frozen request")


class TripoRig(TripoParts):
    """Reuse injected Tripo transport; only GET/download calls use retry policy."""

    def _check(self, plan: JsonObject, live: bool = False) -> None:
        validate_rig_plan(plan, input_root=self.input_root, bindings=self.bindings)
        if live is not True:
            raise ValueError("Provider execution requires live=True")

    def _store(self, plan: JsonObject) -> OperationStore:
        validate_rig_plan(plan, input_root=self.input_root, bindings=self.bindings)
        return OperationStore(self.output_root, plan["operation_id"])

    def _start(
        self, store: OperationStore, plan: JsonObject, reservation: JsonObject
    ) -> JsonObject:
        state = store.start(plan, reservation)
        if state.get("reservation") != reservation:
            raise ValueError("Resume reservation differs from the durable operation")
        return state

    async def _input(self, store: OperationStore, plan: JsonObject, state: JsonObject) -> str:
        if plan["source"]["kind"] == "generation_task":
            return identifier(plan["source"]["task_id"])
        saved = store.read("private-upload.json")
        if saved:
            if saved.get("source_sha256") != plan["source_sha256"]:
                raise ValueError("Saved upload belongs to another source")
            return identifier(saved.get("file_token"))
        if state.get("upload_status"):
            raise RuntimeError("Upload already attempted without a durable handle; no repeat")
        state["upload_status"] = "uploading"
        store.write("state.json", state)
        try:
            path = verified_input(
                self.input_root, {k: plan["source"][k] for k in ("path", "sha256")}
            )
            response = await self.client.post(
                API_ROOT + "/files",
                headers={"Authorization": "Bearer " + self._key},
                files={"file": ("unrigged.glb", path.read_bytes(), "model/gltf-binary")},
            )
            token = identifier(response_data(response).get("file_token"))
            store.write(
                "private-upload.json", {"source_sha256": plan["source_sha256"], "file_token": token}
            )
        except BaseException as error:
            state.update(upload_status="upload_uncertain", error_type=type(error).__name__)
            store.write("state.json", state)
            if not isinstance(error, Exception):
                raise
            raise RuntimeError(
                "Upload outcome uncertain; this operation will not re-upload"
            ) from None
        state["upload_status"] = "uploaded"
        store.write("state.json", state)
        return token

    async def _post_once(
        self,
        store: OperationStore,
        filename: str,
        state: JsonObject,
        endpoint: str,
        body: JsonObject,
    ) -> JsonObject:
        store.write(filename, state)
        try:
            response = await self.client.post(
                API_ROOT + endpoint, headers={"Authorization": "Bearer " + self._key}, json=body
            )
            state.update(
                status="submitted", task_id=identifier(response_data(response).get("task_id"))
            )
        except BaseException as error:
            state.update(status="submission_uncertain", error_type=type(error).__name__)
            store.write(filename, state)
            if not isinstance(error, Exception):
                raise
            raise RuntimeError(
                "Submission outcome uncertain; this operation will never repost"
            ) from None
        store.write(filename, state)
        return state

    async def submit_check(
        self, plan: JsonObject, *, reservation: JsonObject, live: bool = False
    ) -> JsonObject:
        self._check(plan, live)
        store = self._store(plan)
        with store.lock():
            state = self._start(store, plan, reservation)
            check = store.read("check-state.json")
            if check is not None:
                if check.get("task_id"):
                    return check
                raise RuntimeError("Check submission already attempted; no repeat")
            token = await self._input(store, plan, state)
            check = {
                "schema_version": 1,
                "plan_sha256": plan["plan_sha256"],
                "status": "submitting",
                "submission_attempts": 1,
                "cost_status": "reserved_actual_unknown",
            }
            return await self._post_once(
                store, "check-state.json", check, "/animations/rig-check", {"input": token}
            )

    async def collect_check(self, plan: JsonObject, *, live: bool = False) -> JsonObject:
        store = self._store(plan)
        with store.lock():
            if store.read("plan.json") != plan:
                raise ValueError("No matching check operation exists")
            if store.read("check-result.json"):
                return _check_result(store, plan)
            self._check(plan, live)
            state, response = await self._query(store, plan, "check-state.json")
            if response is None or response["status"] != "success":
                return state
            output = response.get("output", {})
            if type(output.get("riggable")) is not bool:
                raise ValueError("Unexpected rig check output")
            result = {
                "schema_version": 1,
                "status": "riggability_checked",
                "plan_sha256": plan["plan_sha256"],
                "task_id": state["task_id"],
                "riggable": output["riggable"],
                "rig_type": identifier(output.get("rig_type")),
                "terminal_usage": _usage(plan, state["task_id"], response),
            }
            state.update(
                status="check_collection_committing", result_sha256=canonical_digest(result)
            )
            store.write("check-state.json", state)
            store.write("check-result.json", result)
            state.update(status="riggability_checked", result_sha256=canonical_digest(result))
            store.write("check-state.json", state)
            return result

    async def submit(
        self, plan: JsonObject, *, reservation: JsonObject, live: bool = False
    ) -> JsonObject:
        self._check(plan, live)
        store = self._store(plan)
        with store.lock():
            state = self._start(store, plan, reservation)
            if state.get("task_id"):
                return state
            if state["status"] != "prepared":
                raise RuntimeError(
                    "Rig submission already attempted; retain reservation and reconcile"
                )
            check = _check_result(store, plan)
            advisory = (
                check["riggable"] is not True or check["rig_type"] != plan["params"]["rig_type"]
            )
            if advisory and (not plan["allow_negative_check"]):
                raise ValueError(
                    "Frozen policy stops after a negative or mismatched advisory check"
                )
            token = await self._input(store, plan, state)
            state.update(
                status="submitting",
                paid_submissions=1,
                advisory_check_sha256=canonical_digest(check),
                advisory_override=advisory,
            )
            body = {"input": token, "model": ModelRef.parse(plan["route"]).model, **plan["params"]}
            return await self._post_once(store, "state.json", state, "/animations/rig", body)

    async def _query(
        self, store: OperationStore, plan: JsonObject, filename: str
    ) -> tuple[JsonObject, JsonObject | None]:
        state = store.read(filename) or {}
        if state.get("plan_sha256") != plan["plan_sha256"]:
            raise ValueError("Provider task lineage differs")
        task_id = identifier(state.get("task_id"))
        if state.get("status") in {"failed", "cancelled", "poll_limit_reached"}:
            return (state, None)
        polls = state.get("poll_count", 0)
        if type(polls) is not int or not 0 <= polls < plan["maximum_polls_per_task"]:
            state["status"] = "poll_limit_reached"
            store.write(filename, state)
            return (state, None)
        state["poll_count"] = polls + 1
        store.write(filename, state)
        response = await self._request("GET", "/tasks/" + task_id)
        status = response.get("status")
        if response.get("task_id") != task_id or status not in {
            "queued",
            "running",
            "success",
            "failed",
            "cancelled",
        }:
            raise ValueError("Tripo query returned unexpected task lineage or status")
        state.update(status=status, cost_status="reserved_actual_unknown")
        state.pop("terminal_usage", None)
        usage = _usage(plan, task_id, response)
        if usage is not None:
            state.update(terminal_usage=usage, cost_status="standard_api_usage_value_reported")
        store.write(filename, state)
        return (state, response)

    async def collect(self, plan: JsonObject, *, live: bool = False) -> JsonObject:
        store = self._store(plan)
        with store.lock():
            if store.read("plan.json") != plan:
                raise ValueError("No matching durable rig submission exists")
            cached = verify_rig_result(store, plan)
            if cached is not None:
                return cached
            self._check(plan, live)
            state, response = await self._query(store, plan, "state.json")
            if response is None or response["status"] != "success":
                return state
            outputs = model_urls(response.get("output"))
            if len(outputs) != 1:
                raise ValueError("The verified rig route expects one model artifact")
            field, url = outputs[0]

            async def download(_: RetryContext) -> tuple[bytes, JsonObject]:
                raw = bytearray()
                try:
                    async with self.client.stream("GET", url) as download_response:
                        if download_response.status_code != 200:
                            raise RuntimeError(f"Rig artifact HTTP {download_response.status_code}")
                        async for chunk in download_response.aiter_bytes():
                            raw.extend(chunk)
                            if len(raw) > 150000000:
                                raise ValueError("Rig artifact exceeds 150 MB")
                except httpx.HTTPError:
                    raise RuntimeError("Rig artifact transport failed; URL withheld") from None
                with tempfile.TemporaryDirectory(
                    prefix=".rig-inspect-", dir=store.path
                ) as temporary:
                    path = Path(temporary) / "payload"
                    path.write_bytes(raw)
                    inspection = inspect_provider_rig(path)
                return (bytes(raw), inspection)

            data, inspection = await retry_with_backoff(
                download,
                policy=self.policy,
                secrets=(self._key, url),
                label="Tripo rig download and structural validation",
            )
            path = confined(store.path, "rig." + inspection["format"], must_exist=False)
            ref, task_id = (_provenance_input(plan), state["task_id"])
            sidecar = confined(store.path, path.name + ".meta.json", must_exist=False)
            if path.exists() or sidecar.exists():
                if (
                    not path.is_file()
                    or not sidecar.is_file()
                    or digest(path) != hashlib.sha256(data).hexdigest()
                ):
                    raise ValueError(
                        "Existing interrupted rig artifact pair is incomplete or changed"
                    )
                _verify_provenance(read_json(sidecar), plan, task_id, digest(path))
            else:
                sidecar = Path(
                    write_artifact_with_provenance(
                        path,
                        BinaryArtifact(data=data, media_type="application/octet-stream"),
                        ProvenanceInput(
                            provider="tripo",
                            model=ModelRef.parse(plan["route"]).model,
                            prompt=plan["prompt"],
                            refs=[ref["path"]],
                            inputs=[
                                InputProvenance(
                                    ref=ref["path"], sha256=ref["sha256"], source="reference"
                                )
                            ],
                            params={
                                "plan_sha256": plan["plan_sha256"],
                                "task_id": task_id,
                                "source_sha256": plan["source_sha256"],
                                "source_kind": plan["source"]["kind"],
                                "request": plan["params"],
                                "provider_result_field": field,
                                "intent_prompt_sent_to_provider": False,
                            },
                            validation=inspection,
                            component=self.component,
                            tool=self.tool,
                            attempts=1,
                        ),
                        secrets=(self._key, url),
                    )
                )
            artifacts = [artifact_record(path, sidecar, store.path)]
            result = {
                "schema_version": 1,
                "status": "raw_rig_collected",
                "plan_sha256": plan["plan_sha256"],
                "task_id": task_id,
                "artifacts": artifacts,
                "inspections": [inspection],
                "actual_format": inspection["format"],
                "requested_format": plan["params"]["out_format"],
                "format_contract_deviation": inspection["format"] != plan["params"]["out_format"],
                "rig_verified": inspection["rig_verified"],
                "local_import_required": inspection["local_import_required"],
                "semantic_status": "unreviewed",
                "terminal_usage": _usage(plan, task_id, response),
                "advisory_check_sha256": canonical_digest(_check_result(store, plan)),
            }
            state.update(status="collection_committing", result_sha256=canonical_digest(result))
            store.write("state.json", state)
            store.write("result.json", result)
            state.update(status=result["status"], result_sha256=canonical_digest(result))
            store.write("state.json", state)
            return result


def rig_cost(
    store: OperationStore,
    plan: JsonObject,
    *,
    input_root: Path,
    bindings: BindingTable | None = None,
) -> Decimal | None:
    """Known successful operation usage; unknown usage never becomes zero."""
    validate_rig_plan(plan, input_root=input_root, bindings=bindings)
    result = verify_rig_result(store, plan)
    if result is None:
        return None
    check, state = (_check_result(store, plan), cast(JsonObject, store.read("state.json")))
    if (
        state.get("paid_submissions") != 1
        or state.get("advisory_check_sha256") != canonical_digest(check)
        or result["advisory_check_sha256"] != canonical_digest(check)
    ):
        raise ValueError("Rig usage does not match the submitted advisory decision")
    total = Decimal("0")
    for record in (check, result):
        usage = record.get("terminal_usage")
        if not isinstance(usage, dict):
            return None
        try:
            credits = Decimal(usage["credits_consumed"])
        except (KeyError, ValueError, ArithmeticError):
            return None
        expected = _usage(
            plan,
            record["task_id"],
            {"task_id": record["task_id"], "status": "success", "credits_consumed": credits},
        )
        if expected is None:
            return None
        if usage != expected:
            raise ValueError("Rig terminal usage differs from exact task/pricing lineage")
        total += Decimal(usage["standard_api_usage_usd"])
    return total
