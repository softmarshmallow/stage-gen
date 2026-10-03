"""A map's ground: the shared 47-mask atlas or painted segments, and the atlas's evidence.

The atlas family (``demo_game_tools.steps.terrain_atlas``) paints and assembles the material
sheet; the painted family (``demo_game_tools.steps.painted_terrain``) paints one segment per
cut of the occupancy. The atlas's evidence is the canonical sheet composed through the map's
generated occupancy, which is what a reviewer reads the ground from.
"""

from __future__ import annotations

from typing import Any

from bellweather_pipeline.assets import ground_evidence as compose_evidence
from demo_game_tools.steps.painted_terrain import (
    admit_painted,
    canonicalize_painted,
    compose_painted,
    painted_guide,
)
from demo_game_tools.steps.terrain_atlas import admit_atlas, assemble_atlas, atlas_paint_target
from gnode import Ctx, node


@node(
    "ground_evidence",
    inputs={"atlas": "image", "terrain": "json"},
    outputs={"image": "image/png"},
    version=1,
)
def ground_evidence(ctx: Ctx) -> dict[str, Any]:
    """The canonical atlas drawn through the map's generated occupancy."""

    occupancy = ctx.read.json("terrain")["occupancy"]
    return {
        "image": ctx.out.bytes(compose_evidence(ctx.read.bytes("atlas"), occupancy), "image/png")
    }


__all__ = [
    "admit_atlas",
    "admit_painted",
    "assemble_atlas",
    "atlas_paint_target",
    "canonicalize_painted",
    "compose_painted",
    "ground_evidence",
    "painted_guide",
]
