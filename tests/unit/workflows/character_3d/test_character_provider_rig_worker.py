"""Credential-free provider-rig mapping, preservation, and motion regressions."""

from __future__ import annotations

import copy
import io
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from stage_gen.components.character_3d.worker import provider_rig as worker
from stage_gen.components.character_3d.worker import provider_rig_cli as cli
from stage_gen.components.character_3d.worker import rig_glb as glb
from stage_gen.components.character_3d.worker import rig_metrics

JsonObject = dict[str, Any]


def humanoid(*, transform: bool = False) -> tuple[JsonObject, bytearray]:
    roles = list(worker.MIXAMO)
    positions: dict[str, list[float]] = {
        "pelvis": [0, 1, 0],
        "spine_lower": [0, 1.2, 0],
        "spine_upper": [0, 1.4, 0],
        "chest": [0, 1.6, 0],
        "neck": [0, 1.8, 0],
        "head": [0, 2, 0],
    }
    parents: dict[str, str | None] = {
        "pelvis": None,
        "spine_lower": "pelvis",
        "spine_upper": "spine_lower",
        "chest": "spine_upper",
        "neck": "chest",
        "head": "neck",
    }
    for side, sign in (("left", 1), ("right", -1)):
        for role, pos, parent in (
            ("shoulder", [0.1, 1.7, 0], "chest"),
            ("upper_arm", [0.3, 1.7, 0], "shoulder"),
            ("forearm", [0.6, 1.45, 0], "upper_arm"),
            ("hand", [0.8, 1.2, 0], "forearm"),
            ("upper_leg", [0.18, 1, 0], "pelvis"),
            ("lower_leg", [0.18, 0.55, 0], "upper_leg"),
            ("foot", [0.18, 0.12, 0.1], "lower_leg"),
            ("toes", [0.18, 0.1, 0.3], "foot"),
        ):
            positions[f"{side}_{role}"] = [pos[0] * sign, *pos[1:]]
            parents[f"{side}_{role}"] = (
                parent if parent in {"chest", "pelvis"} else f"{side}_{parent}"
            )
    root: JsonObject = {"name": "Root", "children": []}
    if transform:
        root.update(
            translation=[3, 7, -2],
            rotation=[0, float(np.sin(0.41)), 0, float(np.cos(0.41))],
            scale=[2, 2, 2],
        )
    nodes = [root]
    indexes = {role: i + 1 for i, role in enumerate(roles)}
    for role in roles:
        parent_role = parents[role]
        delta = np.asarray(positions[role]) - np.asarray(
            positions[parent_role] if parent_role else [0, 0, 0]
        )
        nodes.append({"name": "mixamorig:" + worker.MIXAMO[role], "translation": delta.tolist()})
    for role in roles:
        parent_role = parents[role]
        parent_index = indexes[parent_role] if parent_role else 0
        nodes[parent_index].setdefault("children", []).append(indexes[role])
    mesh_node = len(nodes)
    nodes.append({"name": "whole_character", "mesh": 0, "skin": 0})
    nodes[0]["children"].append(mesh_node)
    doc: JsonObject = {
        "asset": {"version": "2.0"},
        "nodes": nodes,
        "scenes": [{"nodes": [0]}],
        "scene": 0,
        "materials": [{"pbrMetallicRoughness": {"metallicFactor": 0, "roughnessFactor": 1}}],
    }
    binary = bytearray()
    world = glb.worlds(doc)
    points, weights, joints, uv = [], [], [], []
    for j, role in enumerate(roles):
        for k, offset in enumerate(([0, 0, 0], [0.05, 0, 0], [0, 0.04, 0.02])):
            points.append(np.asarray(positions[role]) + np.asarray(offset))
            joints.append([j + 1, 0, 0, 0])
            weights.append([1.0, 0, 0, 0])
            uv.append([(j + 0.1 * k) / len(roles), 0.2 * k])
    attrs = {
        "POSITION": glb.append_accessor(doc, binary, points, 5126, "VEC3"),
        "NORMAL": glb.append_accessor(doc, binary, [[0, 0, 1]] * len(points), 5126, "VEC3"),
        "TEXCOORD_0": glb.append_accessor(doc, binary, uv, 5126, "VEC2"),
        "JOINTS_0": glb.append_accessor(doc, binary, joints, 5123, "VEC4"),
        "WEIGHTS_0": glb.append_accessor(doc, binary, weights, 5126, "VEC4"),
    }
    indices = glb.append_accessor(doc, binary, np.arange(len(points))[:, None], 5123, "SCALAR")
    doc["meshes"] = [
        {
            "name": "whole_character_mesh",
            "primitives": [{"attributes": attrs, "indices": indices, "material": 0}],
        }
    ]
    ibm = np.asarray([np.linalg.inv(matrix) @ world[mesh_node] for matrix in world[:mesh_node]])
    accessor = glb.append_accessor(
        doc, binary, ibm.transpose(0, 2, 1).reshape(-1, 16), 5126, "MAT4"
    )
    doc["skins"] = [
        {"joints": list(range(mesh_node)), "inverseBindMatrices": accessor, "skeleton": 0}
    ]
    return doc, binary


def options(**changes: object) -> JsonObject:
    return {"mapping_preset": "mixamo_biped", "required_joints": list(worker.MIXAMO), **changes}


def write_model(path: Path, *, transform: bool = False) -> tuple[JsonObject, bytearray]:
    doc, binary = humanoid(transform=transform)
    glb.save_glb(path, doc, binary)
    return glb.read_glb(path)


def test_mapping_uses_actual_skin_not_colliding_mesh_name() -> None:
    doc, _ = humanoid()
    doc["nodes"][-1]["name"] = "mixamorig:Head"
    mapping = worker.semantic_mapping(doc, preset="mixamo_biped", required=list(worker.MIXAMO))
    assert doc["nodes"][mapping["head"]]["translation"] == [0, 0.19999999999999996, 0]
    assert mapping["head"] != len(doc["nodes"]) - 1


def test_mapping_rejects_duplicate_joint_names_and_missing_required() -> None:
    doc, _ = humanoid()
    doc["nodes"][2]["name"] = doc["nodes"][1]["name"]
    with pytest.raises(ValueError, match="Ambiguous"):
        worker.semantic_mapping(doc, preset="mixamo_biped")
    doc, _ = humanoid()
    with pytest.raises(ValueError, match="absent"):
        worker.semantic_mapping(doc, preset="mixamo_biped", required=["left_fingers_1"])


@pytest.mark.parametrize(
    "mutation",
    [
        lambda o: o.update(mapping_preset="provider_model_name"),
        lambda o: o.update(semantic_mapping={"head": "Head"}),
        lambda o: o.update(required_joints=["head", "head"]),
        lambda o: o.update(diagnostics=1),
        lambda o: o.update(fps=True),
        lambda o: o.update(fps=61),
        lambda o: o.update(target_height=True),
        lambda o: o.update(target_height=0),
        lambda o: o.update(target_height=-2),
        lambda o: o.update(target_height=float("nan")),
        lambda o: o.update(target_height=float("inf")),
        lambda o: o.update(
            motion={
                "source": {"path": "../escape.fbx", "sha256": "a" * 64},
                "clip": "dance",
                "fps": 30,
                "source_mapping_preset": "mixamo_biped",
            }
        ),
        lambda o: o.update(
            preservation={"source": {"path": "a.glb", "sha256": "a" * 64}, "mode": "repaint"}
        ),
        lambda o: o.update(
            preservation={
                "source": {"path": "a.glb", "sha256": "a" * 64},
                "mode": "audit",
                "max_position_error": 0.1,
            }
        ),
    ],
)
def test_invalid_options_fail_before_blender(mutation: Callable[[JsonObject], None]) -> None:
    value = options()
    mutation(value)
    with pytest.raises(ValueError):
        worker.validate_options(value)


def test_diagnostics_preserve_actual_rig_bytes_under_provider_transform(tmp_path: Path) -> None:
    source = tmp_path / "source.glb"
    original, binary = write_model(source, transform=True)
    out = tmp_path / "out"
    out.mkdir()
    report = worker.build_provider_rig(source, options(), out)
    actual, output_binary = glb.read_glb(out / "animated.glb")
    assert (out / "raw-normalized.glb").read_bytes() == source.read_bytes()
    for key in worker.PROTECTED:
        assert actual.get(key) == original.get(key)
    assert output_binary[: len(binary)] == binary
    assert report["external_rig"]["joint_count"] == 23
    assert {clip["name"] for clip in report["clips"]} == {
        "rest",
        "shoulder_raise",
        "elbow_bend",
        "knee_bend",
        "wrist_bend",
        "cheer",
    }
    assert all("finger" not in clip["name"] for clip in report["clips"])
    metrics = json.loads((out / "diagnostics.json").read_text())["clips"]
    assert (
        max(
            sample["max_vertex_displacement"]
            for clip in metrics
            if clip["name"] == "rest"
            for sample in clip["samples"]
        )
        < 1e-6
    )
    assert all(
        max(sample["max_vertex_displacement"] for sample in clip["samples"]) > 0.01
        for clip in metrics
        if clip["name"] != "rest"
    )
    assert report["geometry"]["bounds"]["min"][1] > 7


def test_quaternion_roundtrip_and_direction() -> None:
    for axis in ([1, 0, 0], [0, 1, 0], [1, 2, 3]):
        for radians in (-2.8, -0.5, 0, 0.6, 3.1):
            matrix = worker._axis_rotation(axis, radians)
            actual = glb.local({"rotation": worker._quaternion(matrix).tolist()})[:3, :3]
            np.testing.assert_allclose(actual, matrix, atol=1e-10)


def test_source_preservation_infers_scale_translation_and_restores_only_normals() -> None:
    source, binary = humanoid()
    target = copy.deepcopy(source)
    target_binary = bytearray(binary)
    target["nodes"][0].update(translation=[0.1, 2, -0.3], scale=[0.7, 0.7, 0.7])
    normal = target["meshes"][0]["primitives"][0]["attributes"]["NORMAL"]
    count = target["accessors"][normal]["count"]
    target["meshes"][0]["primitives"][0]["attributes"]["NORMAL"] = glb.append_accessor(
        target, target_binary, [[0, -1, 0]] * count, 5126, "VEC3"
    )
    report, match = worker.audit_preservation(
        source, binary, target, target_binary, {"mode": "restore_normals"}
    )
    assert report["triangle_connectivity_and_winding_equal"]
    np.testing.assert_allclose(
        np.diag(np.asarray(report["source_to_provider"]))[:3], [0.7, 0.7, 0.7], atol=1e-5
    )
    before = copy.deepcopy(target)
    before_binary = bytes(target_binary)
    result = worker.restore_verified_normals(target, target_binary, match, report)
    assert result["geometry_uv_textures_materials_weights_joints_unchanged"]
    for key in worker.PROTECTED:
        if key != "meshes":
            assert before.get(key) == target.get(key)
    new_normal = target["meshes"][0]["primitives"][0]["attributes"]["NORMAL"]
    np.testing.assert_allclose(
        glb.accessor(target, target_binary, new_normal), [[0, 0, 1]] * count, atol=1e-6
    )
    assert target_binary[: len(before_binary)] == before_binary


def seam_source(source: dict[str, Any], binary: bytearray) -> tuple[dict[str, Any], bytearray, Any]:
    """Duplicate vertex 0 with the same position and UV but a normal 90 degrees away,
    and hand one triangle corner to the duplicate: a hard edge inside one UV island."""
    doc, data = copy.deepcopy(source), bytearray(binary)
    primitive = doc["meshes"][0]["primitives"][0]
    attrs = primitive["attributes"]
    position = glb.accessor(doc, data, attrs["POSITION"])
    uv = glb.accessor(doc, data, attrs["TEXCOORD_0"])
    normal = glb.accessor(doc, data, attrs["NORMAL"])
    indices = glb.accessor(doc, data, primitive["indices"])
    duplicate = len(position)
    away = np.array([1.0, 0.0, 0.0]) if abs(normal[0][0]) < 0.5 else np.array([0.0, 1.0, 0.0])
    position = np.vstack([position, position[0:1]])
    uv = np.vstack([uv, uv[0:1]])
    normal = np.vstack([normal, away[None, :]])
    flat = indices.reshape(-1)
    corner = int(np.argmax(flat == 0))
    flat = flat.copy()
    flat[corner] = duplicate
    attrs["POSITION"] = glb.append_accessor(doc, data, position, 5126, "VEC3")
    attrs["TEXCOORD_0"] = glb.append_accessor(doc, data, uv, 5126, "VEC2")
    attrs["NORMAL"] = glb.append_accessor(doc, data, normal, 5126, "VEC3")
    primitive["indices"] = glb.append_accessor(
        doc, data, flat.reshape(indices.shape), 5125, "SCALAR"
    )
    if "JOINTS_0" in attrs:
        for key, kind, width in (("JOINTS_0", 5121, "VEC4"), ("WEIGHTS_0", 5126, "VEC4")):
            values = glb.accessor(doc, data, attrs[key])
            attrs[key] = glb.append_accessor(
                doc, data, np.vstack([values, values[0:1]]), kind, width
            )
    return doc, data, away


def test_seam_ambiguous_normals_follow_the_provider_normal() -> None:
    base, base_binary = humanoid()
    source, binary, away = seam_source(base, base_binary)
    target, target_binary = copy.deepcopy(base), bytearray(base_binary)
    attrs = target["meshes"][0]["primitives"][0]["attributes"]
    normals = glb.accessor(target, target_binary, attrs["NORMAL"])
    normals[0] = away
    attrs["NORMAL"] = glb.append_accessor(target, target_binary, normals, 5126, "VEC3")
    report, match = worker.audit_preservation(
        source, binary, target, target_binary, {"mode": "restore_normals"}
    )
    assert report["ambiguous_normal_correspondence_vertices"] == 1
    assert report["ambiguous_normals_resolved_by_provider_normal"] == 1
    assert report["triangle_connectivity_and_winding_equal"]
    worker.restore_verified_normals(target, target_binary, match, report)
    restored = glb.accessor(target, target_binary, attrs["NORMAL"])
    np.testing.assert_allclose(restored[0], away, atol=1e-6)
    no_normals, no_binary = copy.deepcopy(base), bytearray(base_binary)
    del no_normals["meshes"][0]["primitives"][0]["attributes"]["NORMAL"]
    report, match = worker.audit_preservation(
        source, binary, no_normals, no_binary, {"mode": "restore_normals"}
    )
    assert report["ambiguous_normals_resolved_by_provider_normal"] == 0
    with pytest.raises(ValueError, match="without provider normals"):
        worker.restore_verified_normals(no_normals, no_binary, match, report)


@pytest.mark.parametrize("change", ["geometry", "uv", "winding"])
def test_surface_audit_refuses_changed_geometry_uv_or_winding(change: str) -> None:
    source, binary = humanoid()
    target, target_binary = copy.deepcopy(source), bytearray(binary)
    primitive = target["meshes"][0]["primitives"][0]
    if change == "geometry":
        old = glb.accessor(target, target_binary, primitive["attributes"]["POSITION"])
        old[0] += [0.04, 0.03, 0.05]
        primitive["attributes"]["POSITION"] = glb.append_accessor(
            target, target_binary, old, 5126, "VEC3"
        )
    elif change == "uv":
        old = glb.accessor(target, target_binary, primitive["attributes"]["TEXCOORD_0"])
        old[0] += 0.1
        primitive["attributes"]["TEXCOORD_0"] = glb.append_accessor(
            target, target_binary, old, 5126, "VEC2"
        )
    else:
        old = glb.accessor(target, target_binary, primitive["indices"])
        old[[0, 1]] = old[[1, 0]]
        primitive["indices"] = glb.append_accessor(target, target_binary, old, 5123, "SCALAR")
    with pytest.raises(ValueError, match=r"correspondence|winding"):
        worker.audit_preservation(source, binary, target, target_binary, {"mode": "audit"})


def texture_fixture(*, compression: int = 6, changed: bool = False) -> tuple[JsonObject, bytearray]:
    from PIL import Image

    doc, binary = humanoid()
    for color in ((70, 140, 230, 255), (128, 128, 255, 255)):
        image = Image.new("RGBA", (4, 3), color)
        if changed:
            image.putpixel((1, 2), (255, 0, 0, 255))
        stream = io.BytesIO()
        image.save(stream, format="PNG", compress_level=compression)
        data = stream.getvalue()
        while len(binary) % 4:
            binary.append(0)
        view = len(doc["bufferViews"])
        doc["bufferViews"].append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(data)})
        binary.extend(data)
        doc.setdefault("images", []).append({"bufferView": view, "mimeType": "image/png"})
        doc.setdefault("textures", []).append({"source": len(doc["images"]) - 1})
    material = doc["materials"][0]
    material["pbrMetallicRoughness"]["baseColorTexture"] = {"index": 0}
    material["normalTexture"] = {"index": 1}
    return doc, binary


def test_lossless_image_reencoding_keeps_paint_identity_without_byte_claim() -> None:
    source, sb = texture_fixture(compression=0)
    target, tb = texture_fixture(compression=9)
    report, _ = worker.audit_preservation(source, sb, target, tb, {"mode": "audit"})
    assert not report["provider_image_payloads_all_from_source"]
    assert report["provider_images_pixel_identical_to_source"]
    assert report["texture_binding_preserved"] and report["appearance_preserved"]
    assert report["decoded_image_identity"]


@pytest.mark.parametrize(
    "change", ["paint", "binding", "uv_transform", "sampler", "tint", "vertex_color"]
)
def test_texture_preservation_rejects_changed_paint_or_corresponding_usage(change: str) -> None:
    source, sb = texture_fixture()
    target, tb = texture_fixture(changed=change == "paint")
    material = target["materials"][0]
    if change == "binding":
        material["pbrMetallicRoughness"]["baseColorTexture"]["index"] = 1
        material["normalTexture"]["index"] = 0
    elif change == "uv_transform":
        material["pbrMetallicRoughness"]["baseColorTexture"]["extensions"] = {
            "KHR_texture_transform": {"offset": [0.1, 0]}
        }
    elif change == "sampler":
        target["samplers"] = [{"wrapS": 33071}]
        target["textures"][0]["sampler"] = 0
    elif change == "tint":
        material["pbrMetallicRoughness"]["baseColorFactor"] = [0.8, 1, 1, 1]
    elif change == "vertex_color":
        primitive = target["meshes"][0]["primitives"][0]
        count = target["accessors"][primitive["attributes"]["POSITION"]]["count"]
        primitive["attributes"]["COLOR_0"] = glb.append_accessor(
            target, tb, [[0.8, 1, 1, 1]] * count, 5126, "VEC4"
        )
    report, _ = worker.audit_preservation(source, sb, target, tb, {"mode": "audit"})
    assert not report["appearance_preserved"]
    assert report["texture_binding_preserved"] == (change in {"tint", "vertex_color"})


def test_preservation_ignores_unused_unlit_normal_slot_and_material_renumbering() -> None:
    source, sb = texture_fixture()
    source["materials"][0]["extensions"] = {"KHR_materials_unlit": {}}
    target, tb = copy.deepcopy(source), bytearray(sb)
    del target["materials"][0]["normalTexture"]
    target["materials"].insert(0, {"name": "unused"})
    target["meshes"][0]["primitives"][0]["material"] = 1
    report, _ = worker.audit_preservation(source, sb, target, tb, {"mode": "audit"})
    assert report["appearance_preserved"]


def test_declared_motion_uses_explicit_file_and_keeps_provider_transform(tmp_path: Path) -> None:
    source = tmp_path / "provider.glb"
    original, original_binary = write_model(source, transform=True)
    motion_doc, motion_binary = humanoid()
    mapping = worker.semantic_mapping(motion_doc, preset="mixamo_biped")
    worker.append_diagnostics(motion_doc, motion_binary, mapping)
    motion = tmp_path / "motion.glb"
    glb.save_glb(motion, motion_doc, motion_binary)
    config = options(
        diagnostics=False,
        motion={
            "source": {"path": "motion.glb", "sha256": glb.sha(motion)},
            "clip": "declared_motion",
            "source_clip": "cheer",
            "fps": 24,
            "source_mapping_preset": "mixamo_biped",
        },
    )
    out = tmp_path / "out"
    out.mkdir()
    report = worker.build_provider_rig(source, config, out, motion_source=motion)
    actual, actual_binary = glb.read_glb(out / "animated.glb")
    assert report["clips"][0]["name"] == "declared_motion"
    assert report["clips"][0]["source"]["source_clip"] == "cheer"
    assert report["clips"][0]["duration_seconds"] == 4
    for key in worker.PROTECTED:
        assert actual.get(key) == original.get(key)
    assert actual_binary[: len(original_binary)] == original_binary


def test_cli_confines_inputs_binds_hashes_and_rolls_back_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.glb"
    write_model(source)
    request: JsonObject = {
        "schema_version": 1,
        "operation": "provider_rig",
        "source": {"path": "source.glb", "sha256": glb.sha(source)},
        "output_dir": "candidate",
        "options": options(),
    }
    invalid = copy.deepcopy(request)
    invalid["schema_version"] = True
    with pytest.raises(ValueError):
        cli.validate_request(invalid)
    invalid = copy.deepcopy(request)
    invalid["source"]["sha256"] = "a" * 64
    with pytest.raises(ValueError, match="hash"):
        cli.run(invalid, tmp_path, tmp_path)
    assert not (tmp_path / "candidate").exists()
    (tmp_path / "symlink.glb").symlink_to(source)
    invalid = copy.deepcopy(request)
    invalid["source"]["path"] = "symlink.glb"
    with pytest.raises(ValueError, match="Symlinks"):
        cli.run(invalid, tmp_path, tmp_path)

    def fail(source: Path, options: JsonObject, out: Path, **kwargs: object) -> None:
        (out / "partial.txt").write_text("partial")
        raise ValueError("controlled failure")

    monkeypatch.setattr(worker, "build_provider_rig", fail)
    with pytest.raises(ValueError, match="controlled"):
        cli.run(request, tmp_path, tmp_path)
    assert not (tmp_path / "candidate").exists()
    assert not list(tmp_path.glob(".provider-rig-staging-*"))


def test_format_uses_magic_not_provider_filename(tmp_path: Path) -> None:
    source = tmp_path / "wrong.fbx"
    write_model(source)
    assert worker.detect_format(source) == "glb"
    unknown = tmp_path / "wrong.glb"
    unknown.write_bytes(b"not a model")
    with pytest.raises(ValueError, match="filename"):
        worker.detect_format(unknown)


def test_missing_required_provider_joint_never_creates_replacement(tmp_path: Path) -> None:
    source = tmp_path / "source.glb"
    write_model(source)
    original = source.read_bytes()
    request: JsonObject = {
        "schema_version": 1,
        "operation": "provider_rig",
        "source": {"path": "source.glb", "sha256": glb.sha(source)},
        "output_dir": "candidate",
        "options": options(required_joints=["left_fingers_1"]),
    }
    with pytest.raises(ValueError, match="absent"):
        cli.run(request, tmp_path, tmp_path)
    assert source.read_bytes() == original
    assert not (tmp_path / "candidate").exists()


def test_unweighted_ancestor_still_controls_weighted_descendants() -> None:
    doc, binary = humanoid()
    attrs = doc["meshes"][0]["primitives"][0]["attributes"]
    joints = glb.accessor(doc, binary, attrs["JOINTS_0"])
    mapping = worker.semantic_mapping(doc, preset="mixamo_biped")
    joints[joints == mapping["spine_lower"]] = mapping["spine_upper"]
    attrs["JOINTS_0"] = glb.append_accessor(doc, binary, joints, 5123, "VEC4")
    result = worker.inventory(doc, binary, mapping)
    assert "spine_lower" in result["zero_weight_semantics"]
    assert "spine_lower" not in result["unsupported_control_semantics"]
    assert mapping["spine_upper"] in result["controlled_weighted_nodes"]["spine_lower"]


def test_matte_is_persistent_separate_from_raw_provider_control(tmp_path: Path) -> None:
    source = tmp_path / "source.glb"
    doc, binary = humanoid()
    doc["materials"][0]["pbrMetallicRoughness"].update(metallicFactor=0.8, roughnessFactor=0.1)
    glb.save_glb(source, doc, binary)
    out = tmp_path / "out"
    out.mkdir()
    report = worker.build_provider_rig(source, options(material_policy="matte"), out)
    actual, data = glb.read_glb(out / "animated.glb")
    control, _ = glb.read_glb(out / "raw-normalized.glb")
    assert control["materials"] == doc["materials"]
    assert report["material_changes"][0]["before"] == doc["materials"][0]
    assert actual["materials"][0]["pbrMetallicRoughness"]["roughnessFactor"] == 1
    assert actual["materials"][0]["extensions"]["KHR_materials_specular"]["specularFactor"] == 0.08
    assert data[: len(binary)] == binary


@pytest.mark.parametrize("split_roots", [False, True])
def test_target_height_wraps_transformed_skinned_motion_once(
    tmp_path: Path, split_roots: bool
) -> None:
    source = tmp_path / "source.glb"
    doc, binary = texture_fixture()
    doc["nodes"][0].update(
        translation=[3, 7, -2],
        rotation=[0, float(np.sin(0.41)), 0, float(np.cos(0.41))],
        scale=[2, 2, 2],
    )
    attributes = doc["meshes"][0]["primitives"][0]["attributes"]
    weights = glb.accessor(doc, binary, attributes["WEIGHTS_0"])
    weights[:, :2] = [1 - 1e-6, 1e-6]
    attributes["WEIGHTS_0"] = glb.append_accessor(doc, binary, weights, 5126, "VEC4")
    if split_roots:
        # Mesh and skeleton roots must receive the same parent without changing binds.
        mesh_node = len(doc["nodes"]) - 1
        doc["nodes"][0]["children"].remove(mesh_node)
        doc["scenes"][0]["nodes"].append(mesh_node)
    worker._append_clip(
        doc,
        binary,
        "provider_root_translation",
        np.asarray([0.0, 0.5, 1.0]),
        {},
        {0: [np.asarray(row, dtype=float) for row in ([3, 7, -2], [4, 7.3, -1], [3, 7, -2])]},
    )
    glb.save_glb(source, doc, binary)
    original_bytes = source.read_bytes()
    control_dir, output_dir = tmp_path / "control", tmp_path / "output"
    control_dir.mkdir()
    output_dir.mkdir()
    control_report = worker.build_provider_rig(source, options(), control_dir)
    report = worker.build_provider_rig(source, options(target_height=2), output_dir)
    control, control_binary = glb.read_glb(control_dir / "animated.glb")
    actual, output_binary = glb.read_glb(output_dir / "animated.glb")
    transform = report["output_transform"]
    matrix = np.asarray(transform["matrix"])
    assert report["geometry"]["bounds"]["dimensions"][1] == pytest.approx(2, abs=1e-6)
    assert report["geometry"]["bounds"]["min"][1] == pytest.approx(0, abs=1e-6)
    assert transform["verified_export_sha256"] == glb.sha(output_dir / "animated.glb")
    assert transform["height_before"] == control_report["geometry"]["bounds"]["dimensions"][1]
    assert transform["uniform_scale"] != pytest.approx(1)
    assert transform["postcondition_passed"]
    assert source.read_bytes() == original_bytes
    assert (output_dir / "raw-normalized.glb").read_bytes() == original_bytes
    assert output_binary == control_binary
    assert len(actual["nodes"]) == len(control["nodes"]) + 1
    assert actual["nodes"][:-1] == control["nodes"]
    assert actual["nodes"][-1]["children"] == control["scenes"][0]["nodes"]
    assert actual["scenes"][0]["nodes"] == [len(control["nodes"])]
    assert actual["animations"] == control["animations"]
    assert all(
        actual.get(key) == control.get(key)
        for key in worker.PROTECTED
        if key not in {"nodes", "scenes"}
    )
    assert worker._image_hashes(actual, output_binary) == worker._image_hashes(doc, binary)
    surfaces_before = worker.surfaces(control, control_binary)
    surfaces_after = worker.surfaces(actual, output_binary)
    for clip in control["animations"]:
        original_tracks = rig_metrics.decode_animation(control, control_binary, clip)
        final_tracks = rig_metrics.decode_animation(actual, output_binary, clip)
        for time in (0.0, 0.25, 0.5, 0.75, 1.0):
            worlds_before = rig_metrics.sample_worlds(control, original_tracks, time)
            worlds_after = rig_metrics.sample_worlds(actual, final_tracks, time)
            for old_world, new_world in zip(worlds_before, worlds_after[:-1], strict=True):
                np.testing.assert_allclose(new_world, matrix @ old_world, atol=1e-8)
            for old_surface, new_surface in zip(surfaces_before, surfaces_after, strict=True):
                before_points = rig_metrics.surface_points(old_surface, worlds_before)
                after_points = rig_metrics.surface_points(new_surface, worlds_after)
                np.testing.assert_allclose(
                    after_points, glb.points(before_points, matrix), atol=1e-7
                )
    final_inventory = json.loads((output_dir / "external-rig.json").read_text())
    raw_inventory = json.loads((output_dir / "raw-external-rig.json").read_text())
    assert final_inventory == report["external_rig"]
    assert raw_inventory["bounds"] == control_report["geometry"]["bounds"]
    assert (
        final_inventory["semantic_mapping"]["head"]["head"]
        != raw_inventory["semantic_mapping"]["head"]["head"]
    )
    assert report["motion_preservation"]["output_transform_excluded_fields"] == ["nodes", "scenes"]
    assert "nodes" not in report["motion_preservation"]["provider_fields_exact"]
    metrics = json.loads((output_dir / "diagnostics.json").read_text())["clips"]
    assert any(
        sample["max_vertex_displacement"] > 0.01
        for clip in metrics
        if clip["name"] == "cheer"
        for sample in clip["samples"]
    )


@pytest.mark.parametrize("bad_scene", ["duplicate_root", "missing_root", "multiple_scenes"])
def test_output_normalization_refuses_ambiguous_scene_roots(bad_scene: str) -> None:
    doc, binary = humanoid()
    if bad_scene == "duplicate_root":
        doc["scenes"][0]["nodes"] = [0, 0]
    elif bad_scene == "missing_root":
        doc["nodes"].append({"name": "Unreferenced"})
    else:
        doc["scenes"].append(copy.deepcopy(doc["scenes"][0]))
    with pytest.raises(ValueError, match=r"scene|Scene"):
        worker.normalize_output_space(doc, binary, 2)


def test_output_normalization_rejects_collapsed_and_nonfinite_height() -> None:
    doc, binary = humanoid()
    doc["nodes"][0]["scale"] = [1, 0, 1]
    with pytest.raises(ValueError, match="degenerate"):
        worker.normalize_output_space(doc, binary, 2)
    doc["nodes"][0]["scale"] = [1, float("inf"), 1]
    with np.errstate(invalid="ignore"), pytest.raises(ValueError, match="Invalid node affine"):
        worker.normalize_output_space(doc, binary, 2)


def test_cli_publishes_verified_target_height_and_keeps_raw_inventory(tmp_path: Path) -> None:
    source = tmp_path / "source.glb"
    write_model(source, transform=True)
    request: JsonObject = {
        "schema_version": 1,
        "operation": "provider_rig",
        "source": {"path": "source.glb", "sha256": glb.sha(source)},
        "output_dir": "candidate",
        "options": options(target_height=1.7),
    }
    result = cli.run(request, tmp_path, tmp_path)
    transform = result["output_transform"]
    assert transform["height_after"] == pytest.approx(1.7)
    assert transform["ground_after"] == pytest.approx(0, abs=1e-6)
    assert transform["verified_export_sha256"] == result["output"]["sha256"]
    report = json.loads((tmp_path / result["report"]).read_text())
    assert report["output_transform"] == transform
    assert report["geometry"]["bounds"]["dimensions"][1] == pytest.approx(1.7)
    manifest = json.loads((tmp_path / result["manifest"]).read_text())
    assert {"external-rig.json", "raw-external-rig.json"} <= {
        item["path"] for item in manifest["artifacts"]
    }
