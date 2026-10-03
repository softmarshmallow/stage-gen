"""The runner's ground: painted structural chunks that share one seam, or one 47-mask atlas.

Structural ground composes each chunk's exact occupancy into a guide, has the guide painted
over (a judge refuses a painting that lost the guide's canvas, alpha, silhouette or
projection and draws it again), takes the first painting's right apron as the one seam bridge
every chunk shares, and masks each painting to its occupancy with the bridge installed at both
edges. The atlas variant paints the locked template's packed cells and assembles the atlas.
"""

from __future__ import annotations

import hashlib
from typing import Any

from demo_game_tools.kits.sideview_terrain import (
    assemble_terrain_atlas,
    require_terrain_atlas_source,
    terrain_atlas_paint_target,
)
from gnode import Ctx, node
from iron_petal_unit_pipeline.track import (
    build_structural_ground_guide,
    canonicalize_structural_ground,
    canonicalize_structural_ground_seam_bridge,
    validate_structural_ground_source,
)
from stage_gen.resources import terrain_atlas_lookup_path, terrain_atlas_template_path

#: What a chunk is: its occupancy rows, the row the avatar walks on, and the shared material.
_CHUNK: dict[str, Any] = {
    "segment_id": str,
    "occupancy": {"type": "array", "items": {"type": "string"}},
    "walk_surface_row": int,
    "material_identity": str,
}
#: Where the seam bridge is published: every chunk's record names it, and the manifest
#: refuses chunks that do not share it.
SEAM_BRIDGE_PATH = "world/ground/shared-seam-bridge.png"


def _materials(ctx: Ctx) -> list[bytes]:
    return [file.read_bytes() for file in ctx.inputs.get("material") or []]


@node(
    "structural_guide",
    inputs={"material": "image[]"},
    params=_CHUNK,
    outputs={"image": "image/png", "validation": "json"},
    version=1,
)
def structural_guide(ctx: Ctx) -> dict[str, Any]:
    """The chunk's exact occupancy, with two common-material apron columns at each seam."""

    guide, report = build_structural_ground_guide(
        ctx.params["occupancy"],
        walk_surface_row=ctx.params["walk_surface_row"],
        material_identity=ctx.params["material_identity"],
        material_references=_materials(ctx),
    )
    return {
        "image": ctx.out.bytes(guide, "image/png"),
        "validation": ctx.out.json({**report, "segment_id": ctx.params["segment_id"]}),
    }


@node(
    "admit_structural",
    inputs={"image": "image", "guide": "image", "material": "image[]"},
    params={**_CHUNK, "projection": str},
    judge=True,
    version=1,
)
def admit_structural(ctx: Ctx) -> dict[str, Any]:
    """The painting kept the guide's canvas, alpha, silhouette and projection, or is redrawn."""

    try:
        facts = validate_structural_ground_source(
            ctx.read.bytes("image"),
            occupancy=ctx.params["occupancy"],
            walk_surface_row=ctx.params["walk_surface_row"],
            guide=ctx.read.bytes("guide"),
            material_identity=ctx.params["material_identity"],
            material_references=_materials(ctx),
            projection=ctx.params["projection"],
        )
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


@node(
    "seam_bridge",
    inputs={"raw": "image", "guide": "image", "material": "image[]"},
    params=_CHUNK,
    outputs={"image": "image/png", "validation": "json"},
    version=1,
)
def seam_bridge(ctx: Ctx) -> dict[str, Any]:
    """The first chunk's painted right apron, as the two-column bridge every seam shares."""

    bridge, report = canonicalize_structural_ground_seam_bridge(
        ctx.read.bytes("raw"),
        occupancy=ctx.params["occupancy"],
        walk_surface_row=ctx.params["walk_surface_row"],
        material_identity=ctx.params["material_identity"],
        material_references=_materials(ctx),
        guide=ctx.read.bytes("guide"),
    )
    return {
        "image": ctx.out.bytes(bridge, "image/png"),
        "validation": ctx.out.json({**report, "source_segment_id": ctx.params["segment_id"]}),
    }


@node(
    "canonicalize_structural",
    inputs={"raw": "image", "guide": "image", "bridge": "image", "material": "image[]"},
    params=_CHUNK,
    outputs={"image": "image/png", "validation": "json"},
    version=1,
)
def canonicalize_structural(ctx: Ctx) -> dict[str, Any]:
    """Mask the painting to its occupancy and install the bridge's two roles at its edges."""

    canonical, report = canonicalize_structural_ground(
        ctx.read.bytes("raw"),
        occupancy=ctx.params["occupancy"],
        walk_surface_row=ctx.params["walk_surface_row"],
        material_identity=ctx.params["material_identity"],
        material_references=_materials(ctx),
        guide=ctx.read.bytes("guide"),
        seam_bridge=ctx.read.bytes("bridge"),
    )
    return {
        "image": ctx.out.bytes(canonical, "image/png"),
        "validation": ctx.out.json(
            {
                **report,
                "segment_id": ctx.params["segment_id"],
                "seam_bridge_ref": SEAM_BRIDGE_PATH,
            }
        ),
    }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _template(ctx: Ctx) -> bytes:
    """The locked template, held to the digest the plan was keyed on."""

    template = terrain_atlas_template_path().read_bytes()
    if _sha256(template) != ctx.params["template_sha256"]:
        raise ctx.fail("the terrain atlas template changed since this plan was made")
    return template


@node(
    "atlas_paint_target",
    params={"template_sha256": str},
    outputs={"image": "image/png"},
    version=1,
)
def atlas_paint_target(ctx: Ctx) -> dict[str, Any]:
    """The locked template's 48 cells, packed edge to edge at the provider canvas."""

    return {"image": ctx.out.bytes(terrain_atlas_paint_target(_template(ctx)), "image/png")}


@node(
    "admit_atlas",
    inputs={"image": "image"},
    params={"template_sha256": str},
    judge=True,
    version=1,
)
def admit_atlas(ctx: Ctx) -> dict[str, Any]:
    """The painted sheet can be sliced on its fixed cell boundaries, or it is redrawn."""

    try:
        facts = require_terrain_atlas_source(ctx.read.bytes("image"), template=_template(ctx))
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


@node(
    "assemble_atlas",
    inputs={"raw": "image"},
    params={"template_sha256": str, "lookup_sha256": str},
    outputs={"image": "image/png", "validation": "json"},
    version=1,
)
def assemble_atlas(ctx: Ctx) -> dict[str, Any]:
    """Slice the painted sheet, apply the 47-mask lookup and harmonize the legal connectors."""

    template = _template(ctx)
    lookup = terrain_atlas_lookup_path().read_bytes()
    if _sha256(lookup) != ctx.params["lookup_sha256"]:
        raise ctx.fail("the terrain atlas lookup changed since this plan was made")
    canonical, validation = assemble_terrain_atlas(
        ctx.read.bytes("raw"), template=template, lookup_data=lookup
    )
    if validation["classification"] != "direct_pass":
        raise ctx.fail("the painted atlas needs repair, and a runner publishes direct passes only")
    return {
        "image": ctx.out.bytes(canonical, "image/png"),
        "validation": ctx.out.json(validation),
    }


__all__ = [
    "SEAM_BRIDGE_PATH",
    "admit_atlas",
    "admit_structural",
    "assemble_atlas",
    "atlas_paint_target",
    "canonicalize_structural",
    "seam_bridge",
    "structural_guide",
]
