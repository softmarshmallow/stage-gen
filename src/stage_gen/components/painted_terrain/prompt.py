"""The provider-facing paintover contract. Geometry stays local.

A sibling of the runner's ground prompt rather than an edit of it, because the picture
being described is a different picture. The runner asks for one continuous bank; this asks
for a bank plus a handful of masses hanging unsupported in the air above it, and almost
every clause below exists to stop the model doing the reasonable thing with that.

The last clause is the one that earns the family its keep. Without it a model paints
tight to the guide, the silhouette tolerance is never exercised, and three provider calls
buy a rock-textured tile grid.
"""

from __future__ import annotations

from stage_gen.components.painted_terrain.segments import PaintedTerrainSegment
from stage_gen.components.painted_terrain.silhouette import (
    PAINTED_TERRAIN_DILATE_PX,
    PAINTED_TERRAIN_ERODE_PX,
)


def painted_terrain_generation_prompt(
    material_direction: str,
    *,
    segment: PaintedTerrainSegment,
    columns: int,
    rows: int,
) -> str:
    overhang = round(PAINTED_TERRAIN_DILATE_PX / 64, 3)
    shortfall = round(PAINTED_TERRAIN_ERODE_PX / 64, 3)
    return (
        "Asset type: production 2D side-view platformer terrain segment\n\n"
        "Edit reference image 1 as the exact structural guide. Paint a cohesive, bespoke "
        f"terrain illustration for segment {segment.segment_id!r}, whose authored window is "
        f"{columns} columns by {rows} rows.\n"
        f"Material direction: {material_direction.strip()}\n\n"
        "WHAT THE GUIDE SHOWS:\n"
        "- One continuous bank of ground along the bottom, and several SEPARATE slabs "
        "floating in the air above it. They are separate masses. Nothing connects a "
        "floating slab to the bank, to another slab, or to anything else.\n"
        "- A lighter band along the top of a mass is its walking surface. A darker band "
        "along a side or an underside is where that mass ENDS: it is not a crop, and there "
        "is nothing beyond it.\n"
        "- The columns at the far left and far right continue into the neighbouring "
        "segment. Paint them as ordinary terrain that runs off the edge.\n"
        "- The bank at the bottom runs off the bottom of the frame. It has no underside "
        "and no bottom edge: paint it all the way down to the edge of the canvas.\n\n"
        "HARD CONTRACT:\n"
        "- Keep the full 1536x1024 canvas and the guide's registration unchanged.\n"
        "- Paint every visible guide cell as terrain material.\n"
        "- Keep every transparent guide cell fully transparent with true alpha. Add no "
        "sky, backdrop, horizon, clouds, props, pickups, characters, text, border, "
        "vignette, or cast shadow: a separate painted backdrop already sits behind this.\n"
        "- Never draw a pillar, column, root, trunk, chain, rope, vine, or stalactite "
        "beneath a floating slab, and never bridge two slabs. Each slab hangs unsupported "
        "and its underside terminates in open air.\n"
        "- The narrow air gaps between slabs on the same level are where the player jumps "
        "through. They stay fully transparent from end to end.\n"
        "- Draw in strict orthographic projection: a flat front elevation seen straight "
        "on. No vanishing point, no receding or converging edge, no visible top face.\n"
        "- The guide's flat colour blocks are registration only, never artwork. Paint OVER "
        "every one of them, including the lighter and darker bands. No guide colour may "
        "remain visible anywhere in the result.\n"
        "- Preserve every gap, step, ledge and slab exactly where the guide places it.\n"
        f"- Let each mass read as ROCK RATHER THAN AS TILES: its edge may overhang the "
        f"guide's blocks by up to {overhang} of a block on the sides and underside, and "
        f"fall short by up to {shortfall} of a block, so the outline wanders instead of "
        "running straight. Break up every long horizontal run and round off every corner. "
        "The one exception is the walking surface along the top of each mass, which "
        "follows the guide's top edge closely, because that is the line a player judges a "
        "landing against.\n"
        "- Do not crop, rotate, mirror, relayout, label, or subdivide the guide.\n"
        "The authored occupancy is collision authority; this painting is presentation only."
    )


__all__ = ["painted_terrain_generation_prompt"]
