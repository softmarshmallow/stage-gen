"""Fixed local Blender capability probe; no input assets, network or credentials."""

from __future__ import annotations

import argparse
import json
import sys
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any


def run(output: Path) -> dict[str, Any]:
    import numpy as np

    if TYPE_CHECKING:
        from stage_gen.components.character_3d.worker import blender_io, rendering
    else:
        from stage_gen.components.character_3d.worker import blender_io as blender_io
        from stage_gen.components.character_3d.worker import rendering as rendering
    from stage_gen.components.character_3d.worker import rig_metrics, rigging

    _ = (rig_metrics, rigging)
    bpy = import_module("bpy")
    if tuple(bpy.app.version[:2]) != (5, 2):
        raise ValueError("Unsupported Blender version family")
    capabilities = {"worker_modules": True}
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 1))
    mesh = bpy.context.object
    mesh.name = "RuntimeProbeMesh"
    image = bpy.data.images.new("RuntimeProbeTexture", width=4, height=4)
    image.pixels[:] = [0.3, 0.65, 0.45, 1] * 16
    image.filepath_raw = str(output / "probe_texture.png")
    image.file_format = "PNG"
    image.save()
    image.pack()
    material = bpy.data.materials.new("RuntimeProbeMaterial")
    material.use_nodes = True
    texture = material.node_tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    material.node_tree.links.new(
        texture.outputs["Color"], material.node_tree.nodes["Principled BSDF"].inputs["Base Color"]
    )
    mesh.data.materials.append(material)
    bpy.ops.object.armature_add(location=(0, 0, 0.5))
    rig = bpy.context.object
    rig.name = "RuntimeProbeRig"
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    if not all(any(item.weight > 0 for item in vertex.groups) for vertex in mesh.data.vertices):
        raise ValueError("Automatic armature weighting failed on the probe cube")
    capabilities["armature_auto_weights"] = True
    before = np.array(
        [
            vertex.co[:]
            for vertex in mesh.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices
        ]
    )
    rig.pose.bones[0].rotation_mode = "XYZ"
    rig.pose.bones[0].rotation_euler[1] = 0.25
    bpy.context.view_layer.update()
    after = np.array(
        [
            vertex.co[:]
            for vertex in mesh.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices
        ]
    )
    if not float(np.max(np.abs(after - before))) > 0.0001:
        raise ValueError("Probe bone did not deform its weighted mesh")
    capabilities["skin_deformation"] = True
    rig.pose.bones[0].rotation_euler[1] = 0
    bpy.context.view_layer.update()
    bpy.ops.export_scene.gltf(
        filepath=str(output / "probe.glb"),
        export_format="GLB",
        use_selection=True,
        export_animations=False,
        export_materials="EXPORT",
    )
    capabilities["glb_export"] = True
    bpy.ops.export_scene.fbx(
        filepath=str(output / "probe.fbx"),
        use_selection=True,
        bake_anim=False,
        add_leaf_bones=False,
        path_mode="COPY",
        embed_textures=True,
    )
    imported, _ = blender_io.import_source(output / "probe.fbx")
    if not any(obj.type == "MESH" for obj in imported):
        raise ValueError("FBX probe import produced no mesh")
    capabilities["fbx_import"] = True
    if not any(
        node.type == "TEX_IMAGE" and node.image and node.image.packed_file
        for obj in imported
        if obj.type == "MESH"
        for material in obj.data.materials
        if material and material.use_nodes
        for node in material.node_tree.nodes
    ):
        raise ValueError("FBX probe lost its embedded material texture")
    capabilities["fbx_embedded_texture_import"] = True
    imported, raw = blender_io.import_source(output / "probe.glb")
    if not raw or not any(obj.type == "ARMATURE" for obj in imported):
        raise ValueError("GLB probe import lost its armature")
    if not any(obj.type == "MESH" and obj.data.uv_layers for obj in imported):
        raise ValueError("GLB probe import lost its UV-bearing mesh")
    capabilities["glb_import"] = True
    if not any(image.packed_file for image in bpy.data.images):
        raise ValueError("GLB probe lost its embedded texture")
    capabilities["embedded_texture_import"] = True
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "probe.blend"))
    capabilities["native_blend_save"] = True
    arrays = blender_io.scene_arrays(imported)
    result = rendering.render(
        imported,
        arrays,
        {
            "resolution": [128, 128],
            "samples": 1,
            "views": ["positive_z"],
            "character_height_pixels": 64,
        },
        output,
    )
    capabilities["cycles_cpu_render"] = True
    projection = result["images"][0]["projected_geometry"]
    if abs(projection["height_pixels"] - 64) > 0.001 or not projection["fully_in_frame"]:
        raise ValueError("Probe pixel-height projection failed")
    capabilities["calibrated_orthographic_render"] = True
    return {
        "schema_version": 1,
        "status": "probe_passed",
        "runtime": {
            "blender_version": list(bpy.app.version),
            "build_hash": bpy.app.build_hash.decode("ascii"),
            "python_version": sys.version.split()[0],
            "numpy_version": np.__version__,
        },
        "capabilities": capabilities,
        "projection": projection,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    output = args.output.resolve(strict=True)
    try:
        result = run(output)
    except BaseException as error:
        (output / "probe.json").write_text(
            json.dumps(
                {"schema_version": 1, "status": "probe_failed", "error_type": type(error).__name__}
            )
        )
        raise
    (output / "probe.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
