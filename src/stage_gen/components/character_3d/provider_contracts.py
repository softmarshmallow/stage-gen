"""Offline upstream planning and durable, confined operation records."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import Any, cast

from PIL import Image

from gnode import Binding, BindingTable, atomic_write_json
from stage_gen.components.character_3d.io import (
    canonical_digest,
    confined,
    digest,
    verified_input,
)

JsonObject = dict[str, Any]


def default_bindings() -> BindingTable:
    raise ValueError("Application bindings must be injected explicitly")


def identifier(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch("[A-Za-z0-9][A-Za-z0-9_-]{0,99}", value):
        raise ValueError("Expected an opaque identifier")
    return value


def positive_amount(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or (not math.isfinite(value))
        or (value <= 0)
    ):
        raise ValueError("Reservation must be positive and finite")
    return float(value)


def inspect_image(data: bytes) -> JsonObject:
    if not data or len(data) > 20000000:
        raise ValueError("Reference image must be nonempty and at most 20 MB")
    with Image.open(BytesIO(data)) as image:
        if image.format not in {"PNG", "JPEG"}:
            raise ValueError("This narrow adapter accepts PNG or JPEG only")
        if min(image.size) < 64 or max(image.size) > 8192:
            raise ValueError("Reference dimensions must be within 64 through 8192 pixels")
        result: JsonObject = {
            "format": image.format.lower(),
            "width": image.width,
            "height": image.height,
        }
        image.verify()
    result["media_type"] = "image/png" if result["format"] == "png" else "image/jpeg"
    return result


def inspect_mesh(data: bytes) -> JsonObject:
    if not data or len(data) > 150000000:
        raise ValueError("Mesh output must be nonempty and at most 150 MB")
    if data[:4] == b"glTF":
        import struct

        if len(data) < 20 or struct.unpack_from("<II", data, 4) != (2, len(data)):
            raise ValueError("Invalid GLB container header")
        length, kind = struct.unpack_from("<II", data, 12)
        if kind != 1313821514 or 20 + length > len(data):
            raise ValueError("Invalid GLB JSON chunk")
        document = json.loads(data[20 : 20 + length])
        for collection in ("buffers", "images"):
            if any("uri" in item for item in document.get(collection, [])):
                raise ValueError("Only self-contained GLB is accepted")
        return {
            "format": "glb",
            "media_type": "model/gltf-binary",
            "validation_scope": "container_only",
        }
    if data.startswith(b"Kaydara FBX Binary  \x00\x1a\x00"):
        return {
            "format": "fbx",
            "media_type": "application/octet-stream",
            "validation_scope": "header_only",
        }
    raise ValueError(
        "Only embedded GLB or recognizable binary FBX is accepted; local import remains required"
    )


def validate_parameters(
    operation: str, params: JsonObject, binding: Binding, *, views: Sequence[str] = ()
) -> None:
    """Validate route parameters even before planned source images exist."""
    if operation == "reference_image":
        allowed_params = {"aspect_ratio", "quality", "background", "output_compression"}
    elif operation == "part_mesh":
        allowed_params = {
            "quad",
            "face_limit",
            "texture",
            "pbr",
            "texture_quality",
            "texture_alignment",
            "model_seed",
            "texture_seed",
            "orientation",
            "auto_size",
            "export_uv",
        }
    else:
        raise ValueError("Unsupported generation operation")
    if not isinstance(params, dict) or params.keys() - allowed_params:
        raise ValueError("Unsupported provider parameters refused offline")
    if operation == "reference_image":
        if params.get("aspect_ratio", "1:1") not in {
            "1:1",
            "3:2",
            "2:3",
            "4:3",
            "3:4",
            "16:9",
            "9:16",
            "21:9",
        }:
            raise ValueError(
                "Unsupported aspect ratio; omit automatic ratio instead of passing 'auto'"
            )
        if params.get("quality", "auto") not in {"auto", "low", "medium", "high"} or params.get(
            "background", "opaque"
        ) not in {"auto", "opaque"}:
            raise ValueError("Unsupported image quality or background")
        if "output_compression" in params and (
            type(params["output_compression"]) is not int
            or not 0 <= params["output_compression"] <= 100
        ):
            raise ValueError("Invalid output_compression")
    else:
        if (
            len(views) < 2
            or "front" not in views
            or len(set(views)) != len(views)
            or set(views) - {"front", "left", "back", "right"}
        ):
            raise ValueError("Tripo requires front plus at least one other unique named view")
        if any(params.get(key) is not True for key in ("quad", "texture", "pbr")):
            raise ValueError("This measured route requires quad, texture and pbr true")
        if type(params.get("face_limit")) is not int or params["face_limit"] < 48:
            raise ValueError(
                "Quad face_limit must be an integer from 48 through the binding ceiling"
            )
        binding.within("quad_face_limit", params["face_limit"], subject="quad face request")
        if params.get("texture_quality", "standard") not in {
            "standard",
            "detailed",
            "extreme",
        } or params.get("texture_alignment", "original_image") not in {
            "original_image",
            "geometry",
        }:
            raise ValueError("Unsupported texture settings")
        if params.get("orientation", "default") not in {"default", "align_image"}:
            raise ValueError("Unsupported orientation")
        for key in ("auto_size", "export_uv"):
            if key in params and type(params[key]) is not bool:
                raise ValueError(f"{key} must be boolean")
        for key in ("model_seed", "texture_seed"):
            if key in params and (
                type(params[key]) is not int or not 0 <= params[key] <= 2147483647
            ):
                raise ValueError(f"{key} must be an unsigned 31-bit seed")


def plan_generation(
    spec: JsonObject, *, input_root: Path, bindings: BindingTable | None = None
) -> JsonObject:
    fields = {
        "schema_version",
        "operation_id",
        "operation",
        "prompt",
        "inputs",
        "params",
        "rights_basis",
        "reservation_usd",
    }
    if (
        not isinstance(spec, dict)
        or set(spec) != fields
        or type(spec["schema_version"]) is not int
        or (spec["schema_version"] != 1)
    ):
        raise ValueError("Generation spec has unknown or missing fields")
    identifier(spec["operation_id"])
    if not isinstance(spec["rights_basis"], str) or not spec["rights_basis"].strip():
        raise ValueError("An explicit input rights basis is required")
    if not isinstance(spec["prompt"], str) or not spec["prompt"].strip():
        raise ValueError("Prompt or mesh intent must be nonempty")
    inputs = spec["inputs"]
    if not isinstance(inputs, list):
        raise ValueError("Inputs must be a list")
    table = bindings or default_bindings()
    operation = spec["operation"]
    if operation == "reference_image":
        binding = table.require(
            operation, "text_input", "opaque_image", *(["reference_images"] if inputs else [])
        )
    elif operation == "part_mesh":
        binding = table.require(
            operation, "multiview", "textured_mesh", "quad_request", "native_fbx_or_glb"
        )
    else:
        raise ValueError("Unsupported generation operation")
    binding.within("reference_count", len(inputs), subject="input views")
    for item in inputs:
        expected = {"path", "sha256", "view"} if operation == "part_mesh" else {"path", "sha256"}
        if not isinstance(item, dict) or set(item) != expected:
            raise ValueError("Input descriptor fields differ from the operation contract")
        path = verified_input(input_root, {key: item[key] for key in ("path", "sha256")})
        inspect_image(path.read_bytes())
    validate_parameters(
        operation, spec["params"], binding, views=[item.get("view") for item in inputs]
    )
    if positive_amount(spec["reservation_usd"]) < binding.estimated_cost_high_usd:
        raise ValueError("Reservation is below the selected binding estimate")
    plan = {
        **spec,
        "route": str(binding.model),
        "contract_checked_on": binding.verified_on,
        "features": sorted(binding.features),
        "status": "planned_unspent",
    }
    return {**plan, "plan_sha256": canonical_digest(plan)}


def validate_plan(plan: JsonObject, input_root: Path, bindings: BindingTable | None = None) -> None:
    fields = (
        "schema_version",
        "operation_id",
        "operation",
        "prompt",
        "inputs",
        "params",
        "rights_basis",
        "reservation_usd",
    )
    if (
        plan_generation(
            {key: plan[key] for key in fields}, input_root=input_root, bindings=bindings
        )
        != plan
    ):
        raise ValueError("Plan, current binding, or input lineage differs; plan again offline")


class OperationStore:
    """One host process at a time; ambiguous writes never imply permission to repost."""

    def __init__(self, output_root: Path, operation_id: str) -> None:
        self.path = confined(output_root, identifier(operation_id), must_exist=False)
        self.path.mkdir(exist_ok=True)

    @contextmanager
    def lock(self) -> Iterator[OperationStore]:
        lock_path = confined(self.path, ".operation.lock", must_exist=False)
        with lock_path.open("a+b") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Operation is already running") from None
            try:
                yield self
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def read(self, name: str) -> JsonObject | None:
        path = confined(self.path, name, must_exist=False)
        return cast(JsonObject, json.loads(path.read_text())) if path.exists() else None

    def write(self, name: str, value: JsonObject) -> None:
        atomic_write_json(confined(self.path, name, must_exist=False), value)

    def start(self, plan: JsonObject, reservation: JsonObject) -> JsonObject:
        old = self.read("plan.json")
        if old is not None and old != plan:
            raise ValueError("Operation ID is already bound to a different plan")
        state = self.read("state.json")
        if state is not None:
            if state["plan_sha256"] != plan["plan_sha256"]:
                raise ValueError("Persisted operation lineage mismatch")
            return state
        if set(reservation) != {"reservation_id", "plan_sha256", "amount_usd"}:
            raise ValueError("Caller must inject a durable budget reservation")
        identifier(reservation["reservation_id"])
        if (
            reservation["plan_sha256"] != plan["plan_sha256"]
            or positive_amount(reservation["amount_usd"]) < plan["reservation_usd"]
        ):
            raise ValueError("Budget reservation does not cover this plan")
        self.write("plan.json", plan)
        state = {
            "schema_version": 1,
            "plan_sha256": plan["plan_sha256"],
            "status": "prepared",
            "reservation": reservation,
            "cost_status": "reserved_actual_unknown",
            "paid_submissions": 0,
        }
        self.write("state.json", state)
        return state


def adopt(
    source: JsonObject,
    *,
    input_root: Path,
    output_root: Path,
    operation_id: str,
    kind: str,
    rights_basis: str,
) -> JsonObject:
    """Reference a canonical asset in place, without copying or accepting its semantics."""
    path = verified_input(input_root, source)
    if not rights_basis.strip():
        raise ValueError("An explicit rights basis is required")
    if kind not in {"reference_image", "part_mesh"}:
        raise ValueError("Unknown adopted artifact kind")
    inspection = (
        inspect_image(path.read_bytes())
        if kind == "reference_image"
        else inspect_mesh(path.read_bytes())
    )
    result = {
        "schema_version": 1,
        "operation": "adopt",
        "kind": kind,
        "source": source,
        "rights_basis": rights_basis,
        "inspection": inspection,
        "semantic_status": "unreviewed",
        "provider_calls": 0,
        "copied": False,
    }
    store = OperationStore(output_root, operation_id)
    with store.lock():
        previous = store.read("adoption.json")
        if previous is not None and previous != result:
            raise ValueError("Adoption ID already identifies different content")
        store.write("adoption.json", result)
    return result


def verify_result(store: OperationStore, plan: JsonObject) -> JsonObject | None:
    result = store.read("result.json")
    if result is None:
        return None
    if result["plan_sha256"] != plan["plan_sha256"]:
        raise ValueError("Result lineage differs from the plan")
    for item in result["artifacts"]:
        path = confined(store.path, item["path"])
        sidecar = confined(store.path, item["provenance_path"])
        if digest(path) != item["sha256"] or digest(sidecar) != item["provenance_sha256"]:
            raise ValueError("Cached artifact or provenance changed")
        validator = inspect_image if plan["operation"] == "reference_image" else inspect_mesh
        validator(path.read_bytes())
    return result


def artifact_record(path: Path, sidecar: Path, base: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(base).as_posix(),
        "sha256": digest(path),
        "provenance_path": sidecar.relative_to(base).as_posix(),
        "provenance_sha256": digest(sidecar),
    }


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
