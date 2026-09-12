"""Offline coordinate variants of verified raw-part normalization outputs.

Uses worker.rig_glb, including its NumPy dependency; Blender's bundled Python
can run this module without installing dependencies. No provider, solver, or
budget-pool calls occur. The CLI writes a fresh bundle and an unexecuted experiment.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from stage_gen.components.character_3d.io import (
    canonical_digest,
    confined,
    digest,
    read_json,
    verified_input,
    write_json,
)
from stage_gen.components.character_3d.worker import rig_glb
from stage_gen.recipes.character_3d.experiment import validate_experiment


def transform_matrix(spec: dict[str, Any]) -> NDArray[Any]:
    if not isinstance(spec, dict) or set(spec) != {
        "uniform_scale",
        "rotation_degrees_xyz",
        "translation",
    }:
        raise ValueError("Transform requires uniform scale, XYZ degrees and translation")
    scale = spec["uniform_scale"]
    if (
        type(scale) not in {int, float}
        or not math.isfinite(scale)
        or (not 1e-06 <= scale <= 1000000.0)
    ):
        raise ValueError("Uniform scale must be positive, finite and bounded")
    vectors = []
    for key in ("rotation_degrees_xyz", "translation"):
        values = spec[key]
        if (
            not isinstance(values, list)
            or len(values) != 3
            or any(
                type(x) not in {int, float} or not math.isfinite(x) or abs(x) > 1000000.0
                for x in values
            )
        ):
            raise ValueError("Transform vectors require three bounded finite numbers")
        vectors.append(values)
    x, y, z = np.radians(vectors[0])
    cx, cy, cz, sx, sy, sz = (np.cos(x), np.cos(y), np.cos(z), np.sin(x), np.sin(y), np.sin(z))
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    matrix = np.eye(4)
    matrix[:3, :3] = rz @ ry @ rx * scale
    matrix[:3, 3] = vectors[1]
    return matrix


def _static_scene(doc: dict[str, Any]) -> list[int]:
    if doc.get("skins") or doc.get("animations"):
        raise ValueError("Corpus inputs must be unrigged and unanimated")
    nodes = doc.get("nodes", [])
    scenes = doc.get("scenes", [])
    if not nodes or len(scenes) != 1 or doc.get("scene", 0) != 0:
        raise ValueError("Corpus inputs require one explicit static scene")
    if any("skin" in node or "weights" in node for node in nodes):
        raise ValueError("Skins and morph controls are outside coordinate perturbation")
    roots: list[int] = scenes[0].get("nodes", [])
    if (
        not roots
        or len(roots) != len(set(roots))
        or any(type(index) is not int or not 0 <= index < len(nodes) for index in roots)
    ):
        raise ValueError("Invalid scene roots")
    children = {child for node in nodes for child in node.get("children", [])}
    if children & set(roots):
        raise ValueError("Scene root is also a child")
    reached = set()
    pending = list(roots)
    while pending:
        index = pending.pop()
        reached.add(index)
        pending.extend(nodes[index].get("children", []))
    if reached != set(range(len(nodes))):
        raise ValueError("Every input node must belong to the active scene")
    if not doc.get("meshes"):
        raise ValueError("Corpus input has no mesh")
    for mesh in doc["meshes"]:
        for primitive in mesh.get("primitives", []):
            if (
                primitive.get("mode", 4) != 4
                or primitive.get("targets")
                or "POSITION" not in primitive.get("attributes", {})
            ):
                raise ValueError("Only static triangle primitives are supported")
    return roots


def transform_glb(source: Path, output: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Wrap the whole scene once; retain all original node and BIN data exactly."""
    before_hash = digest(source)
    original, binary = rig_glb.read_glb(source)
    roots = _static_scene(original)
    matrix = transform_matrix(spec)
    edited = copy.deepcopy(original)
    edited["nodes"].append(
        {"name": "CoordinateRoot", "children": roots, "matrix": matrix.T.reshape(-1).tolist()}
    )
    edited["scenes"][0]["nodes"] = [len(original["nodes"])]
    rig_glb.save_glb(output, edited, binary)
    after, after_binary = rig_glb.read_glb(output)
    if binary != after_binary or after["nodes"][:-1] != original["nodes"]:
        raise ValueError("Coordinate variant changed original node or binary data")
    for key in set(original) | set(after):
        if key not in {"nodes", "scenes"} and original.get(key) != after.get(key):
            raise ValueError("Coordinate variant changed non-transform document fields")
    expected_scene = copy.deepcopy(original["scenes"])
    expected_scene[0]["nodes"] = [len(original["nodes"])]
    if after["scenes"] != expected_scene:
        raise ValueError("Coordinate variant changed scene data beyond its root")
    old_worlds, new_worlds = (rig_glb.worlds(original), rig_glb.worlds(after))
    maximum_error, count = (0.0, 0)
    old_points, new_points = ([], [])
    for node_index, node in enumerate(original["nodes"]):
        if "mesh" not in node:
            continue
        for primitive in original["meshes"][node["mesh"]]["primitives"]:
            positions = rig_glb.accessor(original, binary, primitive["attributes"]["POSITION"])
            before = rig_glb.points(positions, old_worlds[node_index])
            observed = rig_glb.points(positions, new_worlds[node_index])
            expected = rig_glb.points(before, matrix)
            maximum_error = max(maximum_error, float(np.max(np.abs(observed - expected))))
            count += len(positions)
            old_points.append(before)
            new_points.append(observed)
    if not count or maximum_error > 1e-08:
        raise ValueError("Reopened GLB does not realize the exact declared transform")
    if digest(source) != before_hash:
        raise ValueError("Source changed during materialization")

    def bounds(values: Sequence[NDArray[Any]]) -> dict[str, list[float]]:
        points = np.concatenate(values)
        return {"min": points.min(axis=0).tolist(), "max": points.max(axis=0).tolist()}

    return {
        "source_sha256": before_hash,
        "output_sha256": digest(output),
        "transform": copy.deepcopy(spec),
        "matrix_row_major": matrix.tolist(),
        "representation": "one_outer_scene_node_existing_mesh_buffers_unchanged",
        "checks": {
            "binary_exact": True,
            "original_nodes_exact": True,
            "non_transform_document_fields_exact": True,
            "materials_textures_uvs_indices_exact": True,
            "all_vertex_records_checked": count,
            "maximum_world_position_error": maximum_error,
            "position_tolerance": 1e-08,
            "source_unchanged": True,
        },
        "before_world_bounds": bounds(old_points),
        "after_world_bounds": bounds(new_points),
    }


def _normalization_manifest(
    path: Path, raw_source: dict[str, Any], model: Path, report: Path
) -> None:
    """Verify the conversion's persisted source/artifact commitment, not just its node."""
    manifest = read_json(path)
    if manifest.get("schema_version") != 1 or manifest.get("source") != raw_source:
        raise ValueError("Normalization manifest must bind the exact original raw source")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or any(not isinstance(item, dict) for item in artifacts):
        raise ValueError("Normalization manifest artifacts must be records")
    for artifact_path in (model, report):
        entries = [item for item in artifacts if item.get("path") == artifact_path.name]
        if (
            len(entries) != 1
            or entries[0].get("sha256") != digest(artifact_path)
            or type(entries[0].get("size_bytes")) is not int
            or (entries[0]["size_bytes"] != artifact_path.stat().st_size)
        ):
            raise ValueError(
                "Normalization manifest must verify unique model/report hashes and sizes"
            )


def materialize(
    *,
    input_root: Path,
    package_root: Path,
    corpus_ref: dict[str, Any],
    preparation_ref: str,
    base_id: str,
    variant_id: str,
    output_dir: str,
    experiment_template: dict[str, Any],
    experiment_id: str,
) -> dict[str, Any]:
    """Create one evaluator-owned variant bundle; never enroll or execute a trial."""
    input_root, package_root = (
        Path(input_root).resolve(strict=True),
        Path(package_root).resolve(strict=True),
    )
    if not package_root.is_relative_to(input_root):
        raise ValueError("Package must be contained by the declared input root")
    corpus_path = verified_input(input_root, corpus_ref)
    corpus = read_json(corpus_path)
    base = next(item for item in corpus["bases"] if item["base_id"] == base_id)
    variant = next(item for item in corpus["variants"] if item["variant_id"] == variant_id)
    preparation = confined(input_root, preparation_ref, must_exist=False)
    if not preparation.is_relative_to(package_root / "runs") or not preparation.is_dir():
        raise ValueError("Select a contained offline preparation run")
    outcome = read_json(confined(preparation, "outcome.json"))
    if (
        outcome.get("status") != "prepared"
        or outcome.get("accounting", {}).get("dispatch_count") != 0
    ):
        raise ValueError("Only zero-dispatch offline preparation outputs are eligible")
    target = confined(package_root, output_dir, must_exist=False)
    if (
        not target.is_relative_to(package_root / "corpus")
        or target == package_root / "corpus"
        or target.exists()
    ):
        raise ValueError("Choose a fresh bundle directory under corpus")
    if not re.fullmatch("[a-z][a-z0-9_]{0,95}", experiment_id):
        raise ValueError("Experiment identity must use lower_snake_case")
    template_path = verified_input(input_root, experiment_template)
    template = validate_experiment(read_json(template_path))
    if (
        template.get("pipeline_mode") != "parts_to_rig"
        or template["parts"] != base["parts"]
        or template.get("reference") != base["reference"]
        or ("budget_account" not in template)
    ):
        raise ValueError("Template must select this exact raw base and an existing shared account")
    profile_path = verified_input(input_root, base["profile"])
    if (
        profile_path != confined(package_root, template["profile"]["path"])
        or template["profile"]["sha256"] != base["profile"]["sha256"]
    ):
        raise ValueError("Template cannot change the pinned profile")
    verified_input(package_root, template["pricing"])
    verified_input(input_root, base["reference"])
    sources = []
    for part in base["parts"]:
        name = part["part_id"]
        if not re.fullmatch("[a-z][a-z0-9_]{0,63}", name):
            raise ValueError("Invalid part identity")
        raw = verified_input(input_root, part["source"])
        node_path = confined(preparation, f"nodes/normalize_{name}.json")
        node = read_json(node_path)
        source = verified_input(input_root, node["source"])
        expected = confined(preparation, f"normalized/{name}/model.glb")
        report_path = confined(preparation, f"normalized/{name}/report.json")
        manifest_path = confined(preparation, f"normalized/{name}/manifest.json")
        _normalization_manifest(manifest_path, part["source"], source, report_path)
        report = read_json(report_path)
        if (
            source != expected
            or node["role"] != part["role"]
            or report.get("operation") != "normalize"
            or (report.get("source_unchanged") is not True)
            or (report.get("request", {}).get("source") != part["source"])
            or (report.get("result", {}).get("applied_transform") != np.eye(4).tolist())
        ):
            raise ValueError(
                "Normalization must bind the original raw part with no fitting transform"
            )
        spec = variant["all_parts"] if "all_parts" in variant else variant["per_role"][part["role"]]
        transform_matrix(spec)
        _static_scene(rig_glb.read_glb(source)[0])
        evidence = {
            key: {"path": path.relative_to(input_root).as_posix(), "sha256": digest(path)}
            for key, path in (
                ("normalization_record", node_path),
                ("normalization_report", report_path),
                ("normalization_manifest", manifest_path),
            )
        }
        sources.append((part, raw, node["source"], source, evidence, spec))
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pending-corpus-", dir=target.parent) as temporary:
        staging = Path(temporary)
        records, parts = ([], [])
        for part, raw, normalized, source, evidence, spec in sources:
            output = staging / (part["part_id"] + ".glb")
            result = transform_glb(source, output, spec)
            if result["source_sha256"] != normalized["sha256"]:
                raise ValueError("Normalized source changed after lineage validation")
            for reference in evidence.values():
                verified_input(input_root, reference)
            artifact = {
                "path": (target / output.name).relative_to(input_root).as_posix(),
                "sha256": result["output_sha256"],
            }
            record = {
                "part_id": part["part_id"],
                "role": part["role"],
                "raw_source": part["source"],
                "normalized_source": normalized,
                **evidence,
                "artifact": artifact,
                **result,
            }
            write_json(staging / (output.name + ".artifact.json"), record)
            records.append(record)
            parts.append({"part_id": part["part_id"], "role": part["role"], "source": artifact})
            if digest(raw) != part["source"]["sha256"]:
                raise ValueError("Original raw source changed")
        experiment = copy.deepcopy(template)
        experiment.update(
            experiment_id=experiment_id,
            parts=parts,
            claim=(
                "Planned fresh fit, rig and independent review from coordinate-"
                "variant parts; no solver decisions are supplied and no live re"
                "sult is established."
            ),
        )
        validate_experiment(experiment)
        write_json(staging / "experiment.json", experiment)
        report = {
            "schema_version": 1,
            "status": "materialized_structurally_verified_not_semantically_reviewed",
            "base_id": base_id,
            "variant_id": variant_id,
            "corpus": corpus_ref,
            "variant_recipe_sha256": canonical_digest(variant),
            "preparation": {
                "path": preparation_ref,
                "outcome_sha256": digest(preparation / "outcome.json"),
            },
            "implementation": [
                {
                    "module": "stage_gen.recipes.character_3d.corpus",
                    "sha256": digest(Path(__file__)),
                },
                {
                    "module": "stage_gen.components.character_3d.worker.rig_glb",
                    "sha256": digest(Path(rig_glb.__file__)),
                },
            ],
            "parts": records,
            "experiment": {
                "path": (target / "experiment.json").relative_to(input_root).as_posix(),
                "sha256": digest(staging / "experiment.json"),
            },
            "provider_calls": 0,
            "budget_reserved_usd": "0",
            "solver_decisions": None,
            "limits": [
                (
                    "GLB scene/accessor verification only; no new Blender reimport "
                    "or visual review is implied."
                ),
                (
                    "The normalization export is the preservation baseline; raw FBX"
                    " bytes and conversion lineage remain referenced."
                ),
                (
                    "Only GLB part bytes, reference and unchanged profile belong in"
                    " solver inputs; do not expose evaluator recipes or historical "
                    "decisions."
                ),
            ],
        }
        write_json(staging / "manifest.json", report)
        if target.exists():
            raise ValueError("Bundle destination appeared during materialization")
        os.rename(staging, target)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in (
        "input-root",
        "corpus",
        "preparation",
        "base",
        "variant",
        "output",
        "template",
        "experiment-id",
    ):
        parser.add_argument("--" + flag, required=True)
    args = parser.parse_args()
    root = Path(args.input_root).resolve(strict=True)

    def reference(value: str) -> dict[str, str]:
        path = confined(root, value)
        return {"path": value, "sha256": digest(path)}

    report = materialize(
        input_root=root,
        package_root=Path(__file__).resolve().parents[1],
        corpus_ref=reference(args.corpus),
        preparation_ref=args.preparation,
        base_id=args.base,
        variant_id=args.variant,
        output_dir=args.output,
        experiment_template=reference(args.template),
        experiment_id=args.experiment_id,
    )
    print(
        json.dumps(
            {"status": report["status"], "experiment": report["experiment"], "provider_calls": 0}
        )
    )


if __name__ == "__main__":
    main()
