"""The runner's actors: an identity concept, then one motion strip per state, repacked.

The avatar and an encounter's boss ride the same steps with their own vocabulary. A concept
must be a real cut-out at the concept canvas; a strip must fill every required cell and repack
into canonical cells around its authored anchor, or it is drawn again. The repack that
publishes is the same function the judge ran, so what was admitted is what ships.
"""

from __future__ import annotations

from typing import Any

from demo_game_tools.kits.sideview_actor.motion_geometry import DEFAULT_MOTION_ATLAS_GEOMETRY
from gnode import Ctx, node
from iron_petal_unit_pipeline.admission import (
    admit_motion_candidate,
    admit_transparent_sprite,
    motion_source_facts,
)
from stage_gen.media.sprite_sheets import AlphaComponentRepackContract, repack_alpha_components

#: The canvas an identity concept is drawn at.
CONCEPT_SIZE = (1024, 1536)
_ANCHOR = ("center", "bottom", "top")


@node("admit_concept", inputs={"image": "image"}, judge=True, version=1)
def admit_concept(ctx: Ctx) -> dict[str, Any]:
    """A cut-out with real negative space, at the concept canvas, or it is drawn again."""

    try:
        facts = admit_transparent_sprite(ctx.read.bytes("image"))
        if (facts["width"], facts["height"]) != CONCEPT_SIZE:
            raise ValueError(f"a concept is drawn at {CONCEPT_SIZE[0]}x{CONCEPT_SIZE[1]}")
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


@node("admit_motion", inputs={"image": "image"}, params={"anchor": _ANCHOR}, judge=True, version=1)
def admit_motion(ctx: Ctx) -> dict[str, Any]:
    """Every required cell is filled and the strip repacks around its anchor, or it is redrawn."""

    try:
        facts = admit_motion_candidate(ctx.read.bytes("image"), anchor=ctx.params["anchor"])
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts["source"])
    ctx.fact("verdict", "accept")
    return {}


@node(
    "repack_motion",
    inputs={"raw": "image"},
    params={"state": str, "anchor": _ANCHOR},
    outputs={"image": "image/png", "validation": "json"},
    version=1,
)
def repack_motion(ctx: Ctx) -> dict[str, Any]:
    """Repack the strip's alpha components into the canonical cells the runtime plays."""

    geometry = DEFAULT_MOTION_ATLAS_GEOMETRY
    source = ctx.read.bytes("raw")
    source_facts = motion_source_facts(source)
    canonical, repack = repack_alpha_components(
        source,
        AlphaComponentRepackContract(
            rows=geometry.rows,
            columns=geometry.columns,
            required_cells=geometry.required_cells,
            anchor=ctx.params["anchor"],
            source_slot_policy="exact_required_slots",
        ),
    )
    return {
        "image": ctx.out.bytes(canonical, "image/png"),
        "validation": ctx.out.json(
            {
                "schema_version": 2,
                "kind": "sideview-runner-motion-validation-v2",
                "state": ctx.params["state"],
                "columns": geometry.columns,
                "rows": geometry.rows,
                "frames": geometry.required_cells,
                "runtime_horizontal_mirroring": True,
                "source_validation": source_facts,
                "repack": repack,
            }
        ),
    }


__all__ = ["CONCEPT_SIZE", "admit_concept", "admit_motion", "repack_motion"]
