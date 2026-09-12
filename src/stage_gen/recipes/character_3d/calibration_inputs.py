"""Neutral, hash-bound rig-review subjects from retained worker evidence.

The evaluator mapping is returned to the caller; it is never written into the
reviewer's directory. Original model/profile/image bytes remain unchanged.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import math
import os
import re
import shutil
import struct
import sys
import tempfile
from collections.abc import Collection, Sequence
from pathlib import Path
from typing import Any, cast

from stage_gen.recipes.character_3d import qualification as q

JsonObject = dict[str, Any]
_NAME = re.compile("[a-z][a-z0-9_]{0,95}\\Z")
_PRESERVATION = {
    "source_unchanged",
    "original_binary_prefix_exact",
    "geometry_uv_indices_exact",
    "images_textures_exact",
}
_POSE = {"clip", "time_seconds", "effective_fps_after_import", "frame", "frame_range"}
_SETTINGS = {
    "metallic_factor",
    "roughness_factor",
    "normal_scale",
    "specular_factor",
    "unlit",
    "double_sided",
}
_SUBJECT = {
    "schema_version",
    "kind",
    "candidate",
    "profile",
    "required_criteria",
    "evidence",
    "numeric_findings",
    "required_but_missing_weights",
    "rig_facts",
}


def _keys(value: object, required: Collection[str]) -> None:
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValueError("Unexpected calibration subject fields")


def _clean(path: str | Path) -> Path:
    path = Path(path).absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError("Calibration paths must not contain symlinks")
    return path


def _path(root: Path, relative: str) -> Path:
    q._relative(relative)
    path = _clean(root / relative)
    if not path.is_relative_to(root):
        raise ValueError("Calibration path escapes its root")
    return path


def _ref(root: Path, path: Path) -> JsonObject:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": q._sha(path),
        "bytes": path.stat().st_size,
    }


def _verify(root: Path, value: JsonObject) -> Path:
    if not isinstance(value, dict) or set(value) - {
        "path",
        "sha256",
        "bytes",
        "size_bytes",
        "view",
    }:
        raise ValueError("Unexpected artifact reference fields")
    path = _path(root, value["path"])
    for key in ("bytes", "size_bytes"):
        if key in value and (type(value[key]) is not int or value[key] < 0):
            raise ValueError("Artifact byte size must be a nonnegative integer")
    q._verified(root, value)
    if "size_bytes" in value and path.stat().st_size != value["size_bytes"]:
        raise ValueError("Artifact size disagreement")
    return path


def _number(value: object, *, positive: bool = False) -> None:
    if type(value) not in {int, float} or not math.isfinite(cast(float, value)):
        raise ValueError("Expected a finite calibration number")
    if cast(float, value) < 0 or (positive and cast(float, value) <= 0):
        raise ValueError("Expected a nonnegative calibration number")


def _names(values: object) -> None:
    if not isinstance(values, list):
        raise ValueError("Expected unique calibration names")
    if any(not isinstance(value, str) or not _NAME.fullmatch(value) for value in values):
        raise ValueError("Invalid calibration name")
    if len(set(values)) != len(values):
        raise ValueError("Expected unique calibration names")


def _check_glb(path: Path) -> None:
    data = path.read_bytes()
    if len(data) < 20 or struct.unpack("<4sII", data[:12]) != (b"glTF", 2, len(data)):
        raise ValueError("Invalid calibration GLB container")
    size, kind = struct.unpack("<I4s", data[12:20])
    if kind != b"JSON" or 20 + size > len(data):
        raise ValueError("Missing calibration GLB document")
    doc = json.loads(data[20 : 20 + size])
    if any("uri" in item for key in ("buffers", "images") for item in doc.get(key, [])):
        raise ValueError("Calibration GLB must contain its own buffers and images")


def _check_png(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError("Calibration images must be PNG files")
    width, height = struct.unpack(">II", header[16:24])
    return (int(width), int(height))


def _facts(report: JsonObject) -> JsonObject:
    edits = []
    for edit in report["material_edits"]:
        after = edit["after"]
        pbr, extensions = (after.get("pbrMetallicRoughness", {}), after.get("extensions", {}))
        edits.append(
            {
                "source_material": edit["source_material"],
                "output_material": edit["output_material"],
                "policy": edit["policy"],
                "settings": {
                    "metallic_factor": pbr.get("metallicFactor", 1),
                    "roughness_factor": pbr.get("roughnessFactor", 1),
                    "normal_scale": after.get("normalTexture", {}).get("scale", 1),
                    "specular_factor": extensions.get("KHR_materials_specular", {}).get(
                        "specularFactor", 1
                    ),
                    "unlit": "KHR_materials_unlit" in extensions,
                    "double_sided": after.get("doubleSided", False),
                },
            }
        )
    return {
        "joint_count": report["joint_count"],
        "clips": [
            {key: clip[key] for key in ("name", "duration_seconds", "fps", "samples")}
            for clip in report["clips"]
        ],
        "material_edits": edits,
        "preservation": {key: report["preservation"][key] for key in sorted(_PRESERVATION)},
    }


def _validate_subject(subject: JsonObject, profile: JsonObject) -> None:
    _keys(
        subject,
        {
            "schema_version",
            "kind",
            "candidate",
            "profile",
            "required_criteria",
            "evidence",
            "numeric_findings",
            "required_but_missing_weights",
            "rig_facts",
        },
    )
    version = subject["schema_version"]
    if type(version) is not int or (version, subject["kind"]) not in {
        (1, "rig_review_subject_v1"),
        (2, "rig_review_subject_v2"),
    }:
        raise ValueError("Unsupported calibration subject version")
    for key, filename in (("candidate", "candidate.glb"), ("profile", "profile.json")):
        _keys(subject[key], {"path", "sha256", "bytes"})
        if subject[key]["path"] != filename:
            raise ValueError("Calibration input filenames must be neutral")
    _names(subject["required_criteria"])
    if (
        not subject["required_criteria"]
        or subject["required_criteria"] != profile["review"]["rig_criteria"]
    ):
        raise ValueError("Calibration criteria differ from the supplied profile")
    _names(subject["required_but_missing_weights"])
    if subject["numeric_findings"] != []:
        raise ValueError("Nonempty numeric findings require a new projection contract")
    facts = subject["rig_facts"]
    _keys(facts, {"joint_count", "clips", "material_edits", "preservation"})
    if type(facts["joint_count"]) is not int or facts["joint_count"] <= 0:
        raise ValueError("Expected a positive joint count")
    if not isinstance(facts["clips"], list) or not facts["clips"]:
        raise ValueError("Expected exported clips")
    _names([clip["name"] for clip in facts["clips"]])
    for clip in facts["clips"]:
        _keys(clip, {"name", "duration_seconds", "fps", "samples"})
        for key in ("duration_seconds", "fps", "samples"):
            _number(clip[key], positive=True)
    if not isinstance(facts["material_edits"], list):
        raise ValueError("Expected material facts")
    for edit in facts["material_edits"]:
        _keys(edit, {"source_material", "output_material", "policy", "settings"})
        for key in ("source_material", "output_material"):
            if type(edit[key]) is not int or edit[key] < 0:
                raise ValueError("Expected material indices")
        if edit["policy"] not in {"matte", "unlit", "native"}:
            raise ValueError("Unsupported material policy")
        _keys(edit["settings"], _SETTINGS)
        for key, value in edit["settings"].items():
            if key in {"unlit", "double_sided"}:
                if type(value) is not bool:
                    raise ValueError("Expected material flag")
            else:
                _number(value)
    _keys(facts["preservation"], _PRESERVATION)
    if any(
        type(value) is not bool and (not (version == 2 and value is None))
        for value in facts["preservation"].values()
    ):
        raise ValueError("Expected preservation flags")
    views, expected = q._required_grid({"profile": profile, "exported_rig_report": facts}, "rig")
    if not isinstance(subject["evidence"], list) or not subject["evidence"]:
        raise ValueError("Missing mandatory calibration evidence")
    observed, image_number = ([], 0)
    for record in subject["evidence"]:
        _keys(record, {"tier", "pose", "character_height_pixels", "images"})
        _keys(record["pose"], _POSE)
        q._review_pose_timing(record["pose"])
        _number(record["character_height_pixels"], positive=True)
        pose = record["pose"]
        observed.append(
            (record["tier"], pose["clip"], pose["time_seconds"], record["character_height_pixels"])
        )
        if not isinstance(record["images"], list) or len(record["images"]) != len(views):
            raise ValueError("Incomplete calibration views")
        if [image["view"] for image in record["images"]] != views:
            raise ValueError("Calibration views must match the declared order")
        for image in record["images"]:
            _keys(image, {"path", "sha256", "bytes", "view"})
            image_number += 1
            if image["path"] != f"images/image_{image_number:03d}.png":
                raise ValueError("Calibration image names must be sequential and neutral")
    if len(observed) != len(expected) or set(observed) != expected or image_number > 60:
        raise ValueError("Incomplete or duplicate calibration pose/size grid")


def load_subject(
    subject_root: Path, subject_ref: JsonObject
) -> tuple[JsonObject, list[JsonObject]]:
    """Return (subject, all verified relative file references), without labels."""
    root = _clean(subject_root)
    if (
        not isinstance(subject_ref, dict)
        or set(subject_ref) - {"path", "sha256", "bytes"}
        or subject_ref.get("path") != "subject.json"
    ):
        raise ValueError("Expected neutral subject.json")
    path = _verify(root, subject_ref)
    subject = q._json(path)
    _keys(subject, _SUBJECT)
    profile = q._json(_verify(root, subject["profile"]))
    _validate_subject(subject, profile)
    refs = [_ref(root, path), subject["candidate"], subject["profile"]]
    refs.extend(image for record in subject["evidence"] for image in record["images"])
    for value in refs:
        _verify(root, value)
    _check_glb(root / "candidate.glb")
    for value in refs[3:]:
        _check_png(root / value["path"])
    actual = set()
    for entry in root.rglob("*"):
        _clean(entry)
        if entry.is_file():
            actual.add(entry.relative_to(root).as_posix())
        elif not entry.is_dir() or entry.relative_to(root).as_posix() != "images":
            raise ValueError("Unexpected calibration directory entry")
    if actual != {value["path"] for value in refs}:
        raise ValueError("Unlisted files in calibration subject")
    return (subject, [{key: value[key] for key in ("path", "sha256", "bytes")} for value in refs])


def _publish(source: Path, target: Path) -> None:
    """Atomic directory publication that refuses even an existing empty target."""
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        function = libc.renamex_np
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        args = (os.fsencode(source), os.fsencode(target), 4)
    elif sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        function = libc.renameat2
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        args = (-100, os.fsencode(source), -100, os.fsencode(target), 1)
    else:
        raise ValueError("Atomic no-overwrite directory publication unavailable")
    function.restype = ctypes.c_int
    if function(*args):
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            raise FileExistsError("Calibration destination already exists")
        raise OSError(code, "Calibration directory publication failed")


def _provider_facts(report: JsonObject) -> JsonObject:
    """Project measurements, never assembly plans or provider/producer verdicts.

    Provider surface correspondence is not byte identity. In particular an FBX
    import cannot establish the old GLB preservation assertions. Unknown stays
    null rather than being reported as either a verified success or a failure.
    """
    converted: JsonObject = {
        "joint_count": report["external_rig"]["joint_count"],
        "clips": [{**clip, "samples": clip["sample_count"]} for clip in report["clips"]],
        "material_edits": [
            {
                "source_material": edit["material_index"],
                "output_material": edit["material_index"],
                "policy": edit["policy"],
                "after": edit["after"],
            }
            for edit in report["material_changes"]
        ],
        "preservation": {key: None for key in _PRESERVATION},
    }
    converted["preservation"]["source_unchanged"] = report["source_unchanged"]
    return _facts(converted)


def prepare_provider_case(input_root: Path, case: JsonObject, output_root: Path) -> JsonObject:
    """Copy a complete provider-rig review grid into a neutral v2 subject.

    ``case`` contains candidate_glb, profile, rig_report, rig_manifest references
    and render_sets [{tier, report, manifest}]. Optional view_aliases explicitly
    translates retained renderer view IDs to canonical review IDs. It contains
    no expected verdict.
    The caller retains returned source mapping outside the reviewer's tool root.
    Unlike historical prepare_case, no previous LLM review or agent rig plan is
    needed. Worker manifests and actual render contracts bind all input bytes.
    """
    root, output = (_clean(input_root), _clean(output_root))
    _keys(
        case,
        {"candidate_glb", "profile", "rig_report", "rig_manifest", "render_sets"}
        | ({"view_aliases"} if "view_aliases" in case else set()),
    )
    if not root.is_dir() or output.exists():
        raise ValueError("Provider calibration requires an input root and a new destination")
    sources = {}

    def verified(value: JsonObject) -> Path:
        path = _verify(root, value)
        sources[path] = _ref(root, path)
        return path

    def manifest(reference: JsonObject, required: Sequence[Path]) -> tuple[Path, JsonObject]:
        path = verified(reference)
        data = q._json(path)
        entries = data.get("artifacts", [])
        if not entries or len({item["path"] for item in entries}) != len(entries):
            raise ValueError("Missing or duplicate provider calibration manifest entries")
        retained = {}
        for entry in entries:
            artifact = _verify(path.parent, entry)
            sources[artifact] = _ref(root, artifact)
            retained[artifact] = entry["sha256"]
        if any(retained.get(item) != q._sha(item) for item in required):
            raise ValueError("Provider calibration manifest omits a required artifact")
        return (path, data)

    candidate, profile_path, rig_path = (
        verified(case[key]) for key in ("candidate_glb", "profile", "rig_report")
    )
    _check_glb(candidate)
    profile, report = (q._json(profile_path), q._json(rig_path))
    candidate_hash = q._sha(candidate)
    if (
        report.get("operation") != "provider_rig"
        or report.get("status") != "completed_unreviewed"
        or report.get("output", {}).get("sha256") != candidate_hash
        or (report.get("native_format") not in {"glb", "fbx"})
        or (type(report.get("source_unchanged")) is not bool)
    ):
        raise ValueError("Provider calibration facts belong to another candidate or contract")
    manifest(case["rig_manifest"], [candidate, rig_path])
    required = profile["required_joint_semantics"]
    _names(required)
    inventory = report["external_rig"]
    unsupported = inventory["unsupported_control_semantics"]
    _names(unsupported)
    missing = sorted(
        set(required) - set(inventory["semantic_mapping"]) | set(required).intersection(unsupported)
    )
    facts = _provider_facts(report)
    expected_views, _ = q._required_grid({"profile": profile, "exported_rig_report": facts}, "rig")
    aliases = case.get("view_aliases", {view: view for view in expected_views})
    if (
        not isinstance(aliases, dict)
        or len(aliases) != len(expected_views)
        or set(aliases.values()) != set(expected_views)
        or any(not isinstance(key, str) or not _NAME.fullmatch(key) for key in aliases)
    ):
        raise ValueError("Provider render view aliases must be explicit and one-to-one")
    neutral, copies = ([], [])
    copies.extend([(candidate, "candidate.glb"), (profile_path, "profile.json")])
    image_number = 0
    for entry in case["render_sets"]:
        _keys(entry, {"tier", "report", "manifest"})
        path = verified(entry["report"])
        render = q._json(path)
        manifest_path, manifest_data = manifest(entry["manifest"], [path])
        if manifest_path != path.with_name("manifest.json"):
            raise ValueError("Render manifest must belong to its report directory")
        if (
            render.get("request", {}).get("source", {}).get("sha256") != candidate_hash
            or manifest_data.get("source", {}).get("sha256") != candidate_hash
        ):
            raise ValueError("Provider calibration render belongs to another candidate")
        size = render["request"]["options"]["character_height_pixels"]
        _number(size, positive=True)
        q._review_pose_timing(render["pose"])
        cameras = render["result"]["images"]
        if len(cameras) != len(aliases) or {camera["name"] for camera in cameras} != set(aliases):
            raise ValueError("Provider calibration render views differ from explicit aliases")
        cameras = sorted(cameras, key=lambda camera: expected_views.index(aliases[camera["name"]]))
        artifacts = {item["path"]: item["sha256"] for item in manifest_data["artifacts"]}
        images = []
        for camera in cameras:
            source = _path(path.parent, camera["image"])
            verified(_ref(root, source))
            if _check_png(source) != (camera["width"], camera["height"]):
                raise ValueError("PNG dimensions disagree with retained render camera")
            projected = camera["projected_geometry"]
            _number(projected["height_pixels"], positive=True)
            if (
                camera.get("requested_character_height_pixels") != size
                or abs(projected["height_pixels"] - size) > 1
                or projected.get("fully_in_frame") is not True
                or (artifacts.get(camera["image"]) != q._sha(source))
            ):
                raise ValueError("Provider calibration render has stale images or invalid framing")
            image_number += 1
            filename = f"images/image_{image_number:03d}.png"
            images.append({**_ref(root, source), "path": filename, "view": aliases[camera["name"]]})
            copies.append((source, filename))
        neutral.append(
            {
                "tier": entry["tier"],
                "pose": {key: render["pose"][key] for key in sorted(_POSE)},
                "character_height_pixels": size,
                "images": images,
            }
        )
    subject = {
        "schema_version": 2,
        "kind": "rig_review_subject_v2",
        "candidate": {**_ref(root, candidate), "path": "candidate.glb"},
        "profile": {**_ref(root, profile_path), "path": "profile.json"},
        "required_criteria": profile["review"]["rig_criteria"],
        "evidence": neutral,
        "numeric_findings": [],
        "required_but_missing_weights": missing,
        "rig_facts": facts,
    }
    _validate_subject(subject, profile)
    output.parent.mkdir(parents=True, exist_ok=True)
    mapping = []
    with tempfile.TemporaryDirectory(
        prefix=".calibration-pending-", dir=output.parent
    ) as temporary:
        staging = Path(temporary)
        for source, filename in copies:
            destination = staging / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            original, copied = (_ref(root, source), _ref(staging, destination))
            if original["sha256"] != copied["sha256"] or original["bytes"] != copied["bytes"]:
                raise ValueError("Provider calibration input changed during copy")
            mapping.append({"source": original, "neutral": copied})
        (staging / "subject.json").write_text(json.dumps(subject, indent=2, allow_nan=False) + "\n")
        subject_ref = _ref(staging, staging / "subject.json")
        load_subject(staging, subject_ref)
        for value in sources.values():
            _verify(root, value)
        _clean(output)
        _publish(staging, output)
    return {
        "subject": subject,
        "subject_ref": subject_ref,
        "evaluator_mapping": mapping,
        "verification_sources": list(sources.values()),
        "render_view_aliases": aliases,
        "limitations": [
            ("Preservation null values are unknown, never verified passes or failures."),
            ("Original embedded GLB names and profile text remain; audit them for label leakage."),
            ("Labels and source mapping must remain outside the reviewer tool root."),
            "This is evidence intake, not a semantic acceptance verdict.",
        ],
    }


def prepare_case(input_root: Path, index_path: Path, case_id: str, output_root: Path) -> JsonObject:
    """Prepare one neutral subject; provenance is returned outside the subject."""
    root, index_path, output = (_clean(input_root), _clean(index_path), _clean(output_root))
    if not index_path.is_relative_to(root) or not root.is_dir():
        raise ValueError("Calibration index must be inside its input root")
    if output.exists():
        raise FileExistsError("Calibration destination already exists")
    index = q._json(index_path)
    if (
        type(index.get("schema_version")) is not int
        or index.get("schema_version") != 1
        or index.get("not_a_qualification_result") is not True
    ):
        raise ValueError("Unsupported evaluator input index")
    cases = {case["case_id"]: case for case in index["cases"]}
    if len(cases) != len(index["cases"]) or set(cases) != {"case_001", "case_002", "case_003"}:
        raise ValueError("Only the current three-case index is supported")
    if case_id not in cases:
        raise ValueError("Unknown calibration case")
    case = cases[case_id]
    sources = {index_path: _ref(root, index_path)}

    def verified(value: JsonObject) -> Path:
        path = _verify(root, value)
        sources[path] = _ref(root, path)
        return path

    inputs, evaluator = (case["reviewer_inputs"], case["evaluator_only"])
    candidate, profile_path = (verified(inputs["candidate_glb"]), verified(inputs["profile"]))
    profile = q._json(profile_path)
    rig_path, metrics_path = (
        verified(inputs["exported_rig_report"]),
        verified(inputs["numeric_metrics_report"]),
    )
    rig, metrics = (q._json(rig_path), q._json(metrics_path))
    candidate_hash = inputs["candidate_glb"]["sha256"]
    if rig["outputs"]["glb_sha256"] != candidate_hash or metrics["rigged_sha256"] != candidate_hash:
        raise ValueError("Calibration facts belong to another candidate")
    metadata_path = verified(evaluator["original_provider_review_sidecar"])
    run = metadata_path.parent.parent
    if output.is_relative_to(run):
        raise ValueError("Do not publish calibration subjects into their historical run")
    metadata = q._json(metadata_path)
    prompt = metadata["prompt"]
    if (
        metadata.get("provider") != "openrouter"
        or hashlib.sha256(prompt.encode()).hexdigest() != metadata["prompt_sha256"]
        or metadata["params"]["instructions_sha256"] != metadata["prompt_sha256"]
    ):
        raise ValueError("Unverified retained input contract")
    contract = json.loads(prompt)
    if (
        contract["source_sha256"] != candidate_hash
        or contract["profile"] != profile
        or contract["required_criteria"] != inputs["required_criteria"]
        or (contract["exported_rig_report"] != rig)
        or (contract["numeric_findings"] != metrics["blocking_findings"])
    ):
        raise ValueError("Calibration input facts disagree with retained contract")

    def manifest(reference: JsonObject, source_hash: str | None = None) -> JsonObject:
        path = verified(reference)
        data = q._json(path)
        if source_hash is not None and data["source"]["sha256"] != source_hash:
            raise ValueError("Calibration manifest source disagreement")
        if len({item["path"] for item in data["artifacts"]}) != len(data["artifacts"]):
            raise ValueError("Duplicate calibration manifest artifact")
        for artifact in data["artifacts"]:
            item_path = _verify(path.parent, artifact)
            sources[item_path] = _ref(root, item_path)
        return data

    candidate_manifest = manifest(case["verification"]["candidate_manifest"])
    metrics_manifest = manifest(inputs["numeric_metrics_manifest"], candidate_hash)
    for data, required in (
        (candidate_manifest, [candidate, rig_path]),
        (metrics_manifest, [metrics_path]),
    ):
        entries = {item["path"]: item for item in data["artifacts"]}
        if any(
            path.name not in entries or entries[path.name]["sha256"] != q._sha(path)
            for path in required
        ):
            raise ValueError("Calibration manifest omits a required artifact")
    records = contract["initial_evidence"]
    record_lookup = {str(_path(run, record["report"])): record for record in records}
    neutral, copy_inputs = ([], [(candidate, "candidate.glb"), (profile_path, "profile.json")])
    image_number = 0
    for entry in inputs["mandatory_render_sets"]:
        report_path = verified(entry["report"])
        manifest(entry["manifest"], candidate_hash)
        record = record_lookup[str(report_path)]
        if (
            entry["tier"] != record["review_tier"]
            or entry["character_height_pixels"] != record["character_height_pixels"]
            or any(entry["pose"][key] != record["pose"][key] for key in entry["pose"])
            or (len(record["images"]) != entry["verified_image_count"])
        ):
            raise ValueError("Calibration index differs from retained evidence")
        inventory = [
            {key: image[key] for key in ("path", "sha256", "view")} for image in record["images"]
        ]
        if (
            hashlib.sha256(
                json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            != entry["verified_image_inventory_sha256"]
        ):
            raise ValueError("Calibration image inventory disagreement")
        images = []
        for image in record["images"]:
            source = _verify(run, {key: image[key] for key in ("path", "sha256")})
            sources[source] = _ref(root, source)
            width, height = _check_png(source)
            camera = image["camera"]
            if (width, height) != (camera["width"], camera["height"]):
                raise ValueError("PNG dimensions disagree with retained render camera")
            image_number += 1
            filename = f"images/image_{image_number:03d}.png"
            images.append(
                {
                    "path": filename,
                    "sha256": q._sha(source),
                    "bytes": source.stat().st_size,
                    "view": image["view"],
                }
            )
            copy_inputs.append((source, filename))
        neutral.append(
            {
                "tier": entry["tier"],
                "pose": {key: record["pose"][key] for key in sorted(_POSE)},
                "character_height_pixels": entry["character_height_pixels"],
                "images": images,
            }
        )
    verified_images = q._review_evidence(
        run, {"initial_evidence": records}, candidate_hash, contract, metadata, "rig"
    )
    if verified_images != image_number or image_number != inputs["mandatory_image_count"]:
        raise ValueError("Calibration requires every retained mandatory image")
    subject = {
        "schema_version": 1,
        "kind": "rig_review_subject_v1",
        "candidate": {**_ref(root, candidate), "path": "candidate.glb"},
        "profile": {**_ref(root, profile_path), "path": "profile.json"},
        "required_criteria": inputs["required_criteria"],
        "evidence": neutral,
        "numeric_findings": metrics["blocking_findings"],
        "required_but_missing_weights": contract["required_but_missing_weights"],
        "rig_facts": _facts(rig),
    }
    _validate_subject(subject, profile)
    output.parent.mkdir(parents=True, exist_ok=True)
    mapping = []
    with tempfile.TemporaryDirectory(
        prefix=".calibration-pending-", dir=output.parent
    ) as temporary:
        staging = Path(temporary)
        for source, filename in copy_inputs:
            destination = staging / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            original, copied = (_ref(root, source), _ref(staging, destination))
            if original["sha256"] != copied["sha256"] or original["bytes"] != copied["bytes"]:
                raise ValueError("Calibration input changed during copy")
            mapping.append({"source": original, "neutral": copied})
        (staging / "subject.json").write_text(json.dumps(subject, indent=2, allow_nan=False) + "\n")
        subject_ref = _ref(staging, staging / "subject.json")
        load_subject(staging, subject_ref)
        for value in sources.values():
            _verify(root, value)
        _clean(output)
        _publish(staging, output)
    return {
        "subject": subject,
        "subject_ref": subject_ref,
        "evaluator_mapping": mapping,
        "verification_sources": list(sources.values()),
        "limitations": [
            (
                "Original embedded GLB names and profile text remain unchanged;"
                " neutral filenames do not guarantee anonymity."
            ),
            (
                "Only the current three full-rig cases with empty numeric block"
                "er findings are supported."
            ),
            (
                "Material and clip facts are explicit reduced projections; bind"
                "ing/repair plans and historical verdicts are excluded."
            ),
            (
                "Source-to-neutral mapping is evaluator-only and must not be pl"
                "aced in the reviewer tool root."
            ),
        ],
    }
