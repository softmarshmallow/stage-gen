"""Painted terrain: one bespoke painting per segment of a map's occupancy, stitched back.

The map's occupancy (a record with an ``occupancy`` list of rows) is cut into its fixed
segments; each segment's guide is drawn as flat registration blocks, painted over (a paid
edit), held by a judge to the guide's silhouette and material and drawn again when it fails,
then cropped and clipped to the published silhouette band. The segments are stitched into
one plate for review and the composite; the runtime always loads segments.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from demo_game_tools.kits.painted_terrain import PAINTED_TERRAIN_MODE
from demo_game_tools.kits.painted_terrain.canonicalize import (
    canonicalize_painted_terrain_segment,
    stitch_painted_terrain,
)
from demo_game_tools.kits.painted_terrain.guide import build_painted_terrain_guide
from demo_game_tools.kits.painted_terrain.models import painted_silhouette_tolerance
from demo_game_tools.kits.painted_terrain.prompt import painted_terrain_generation_prompt
from demo_game_tools.kits.painted_terrain.segments import (
    PAINTED_TERRAIN_GUIDE_HEIGHT,
    PAINTED_TERRAIN_GUIDE_WIDTH,
    PaintedTerrainSegment,
    painted_terrain_segments,
)
from demo_game_tools.kits.painted_terrain.validate import (
    painted_terrain_join_discontinuity,
    validate_painted_terrain_source,
)
from gnode import Ctx, Group, StepRef, node
from stage_gen.media.codec import decode_rgba

#: Paintings a segment gets before the run stops on it.
SEGMENT_TAKES = 6
PAINTED_TERRAIN_GROUND_VALIDATION_KIND = "painted-terrain-ground-validation-v1"

_SEGMENT: dict[str, Any] = {"segment_id": str, "material_identity": str}
_SOURCES = {"terrain": "json", "material": "image[]"}


def _occupancy(ctx: Ctx) -> list[str]:
    occupancy = ctx.read.json("terrain").get("occupancy")
    if not isinstance(occupancy, list) or not all(isinstance(row, str) for row in occupancy):
        raise ctx.fail("the terrain record carries no occupancy rows")
    return occupancy


def _segment(ctx: Ctx, occupancy: Sequence[str]) -> PaintedTerrainSegment:
    for segment in painted_terrain_segments(len(occupancy[0]), len(occupancy)):
        if segment.segment_id == ctx.params["segment_id"]:
            return segment
    raise ctx.fail(f"the map has no painted segment {ctx.params['segment_id']}")


def _materials(ctx: Ctx) -> list[bytes]:
    return [file.read_bytes() for file in ctx.inputs.get("material") or []]


@node(
    "painted_guide",
    inputs=_SOURCES,
    params=_SEGMENT,
    outputs={"image": "image/png", "report": "json"},
    version=1,
)
def painted_guide(ctx: Ctx) -> dict[str, Any]:
    """The segment's authored occupancy as flat registration blocks, bands facing the air."""

    occupancy = _occupancy(ctx)
    guide, report = build_painted_terrain_guide(
        occupancy,
        _segment(ctx, occupancy),
        material_identity=ctx.params["material_identity"],
        material_references=_materials(ctx),
    )
    return {"image": ctx.out.bytes(guide, "image/png"), "report": ctx.out.json(report)}


@node(
    "admit_painted",
    inputs={**_SOURCES, "image": "image", "guide": "image"},
    params=_SEGMENT,
    judge=True,
    version=1,
)
def admit_painted(ctx: Ctx) -> dict[str, Any]:
    """The painting kept the guide's silhouette, gaps and material, or it is drawn again."""

    occupancy = _occupancy(ctx)
    try:
        facts = validate_painted_terrain_source(
            ctx.read.bytes("image"),
            occupancy=occupancy,
            segment=_segment(ctx, occupancy),
            guide=ctx.read.bytes("guide"),
            material_identity=ctx.params["material_identity"],
            material_references=_materials(ctx),
        )
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


@node(
    "canonicalize_painted",
    inputs={**_SOURCES, "raw": "image", "guide": "image"},
    params=_SEGMENT,
    outputs={"image": "image/png", "validation": "json"},
    version=1,
)
def canonicalize_painted(ctx: Ctx) -> dict[str, Any]:
    """Crop the segment's own columns, clip to the silhouette band, fill what was not painted."""

    occupancy = _occupancy(ctx)
    canonical, report = canonicalize_painted_terrain_segment(
        ctx.read.bytes("raw"),
        occupancy=occupancy,
        segment=_segment(ctx, occupancy),
        guide=ctx.read.bytes("guide"),
        material_identity=ctx.params["material_identity"],
        material_references=_materials(ctx),
    )
    return {"image": ctx.out.bytes(canonical, "image/png"), "validation": ctx.out.json(report)}


@node(
    "compose_painted",
    inputs={"terrain": "json", "segments": "image{}"},
    params={"map_id": str, "material_identity": str},
    outputs={"evidence": "image/png", "validation": "json"},
    version=1,
)
def compose_painted(ctx: Ctx) -> dict[str, Any]:
    """Stitch every published segment into one plate of the whole map, and measure its joins."""

    occupancy = _occupancy(ctx)
    segments = painted_terrain_segments(len(occupancy[0]), len(occupancy))
    published = ctx.inputs["segments"]
    missing = [s.segment_id for s in segments if s.segment_id not in published]
    if missing:
        raise ctx.fail(f"no published raster for {', '.join(missing)}")
    plate = stitch_painted_terrain(
        [(segment, published[segment.segment_id].read_bytes()) for segment in segments],
        occupancy=occupancy,
    )
    boundaries = [segment.start_column for segment in segments if segment.start_column]
    validation = {
        "schema_version": 1,
        "kind": PAINTED_TERRAIN_GROUND_VALIDATION_KIND,
        "mode": PAINTED_TERRAIN_MODE,
        "map_id": ctx.params["map_id"],
        "material_identity": ctx.params["material_identity"],
        "geometry_authority": "authored_occupancy",
        "silhouette_tolerance": painted_silhouette_tolerance().model_dump(mode="json"),
        "segments": [
            {
                "segment_id": segment.segment_id,
                "start_column": segment.start_column,
                "columns": segment.columns,
            }
            for segment in segments
        ],
        # Recorded rather than gated: a visible join is a measurement that decides whether to
        # turn on the deterministic jittered cut, not a refusal.
        "joins": painted_terrain_join_discontinuity(decode_rgba(plate), boundaries=boundaries),
    }
    return {"evidence": ctx.out.bytes(plate, "image/png"), "validation": ctx.out.json(validation)}


def add_painted_terrain_steps(
    group: Group,
    *,
    nodes: str,
    map_id: str,
    columns: int,
    rows: int,
    terrain: Any,
    materials: Sequence[Any],
    material_identity: str,
    material_direction: str,
) -> dict[str, Any]:
    """One group per segment (guide, painting, judge, publish) and the stitched plate.

    ``terrain`` is a reference to the map's occupancy record; ``columns`` and ``rows`` are the
    map's authored size, which fixes the partition before the occupancy exists. Returns each
    segment's publish step by segment id, and the compose step.
    """

    sources = {"terrain": terrain, "material": list(materials)}
    published: dict[str, StepRef] = {}
    for segment in painted_terrain_segments(columns, rows):
        facts = {"segment_id": segment.segment_id, "material_identity": material_identity}
        part = group.group(segment.segment_id, title=f"Segment {segment.segment_id}")
        guide = part.step(
            "guide",
            title="Draw the segment's guide",
            uses=f"{nodes}#painted_guide",
            with_={**sources, **facts},
            view=True,
        )
        painting = part.step(
            "generate",
            title="Paint the segment",
            uses="gnode/image.edit@1",
            with_={
                "image": guide.outputs.image,
                "references": list(materials),
                "prompt": painted_terrain_generation_prompt(
                    material_direction, segment=segment, columns=segment.columns, rows=rows
                ),
                "size": f"{PAINTED_TERRAIN_GUIDE_WIDTH}x{PAINTED_TERRAIN_GUIDE_HEIGHT}",
                "background": "transparent",
            },
            requires=["transparent_background"],
            view=True,
        )
        part.step(
            "admit",
            title="Hold the painting to the guide",
            uses=f"{nodes}#admit_painted",
            judges="generate",
            with_={
                **sources,
                **facts,
                "image": painting.outputs.image,
                "guide": guide.outputs.image,
            },
            on_reject={"regenerate": {"max": SEGMENT_TAKES, "then": "fail"}},
        )
        published[segment.segment_id] = part.step(
            "publish",
            title="Clip it to its silhouette",
            uses=f"{nodes}#canonicalize_painted",
            with_={
                **sources,
                **facts,
                "raw": painting.outputs.image,
                "guide": guide.outputs.image,
            },
            view=True,
        )
    compose = group.step(
        "compose",
        title="Stitch the map's ground",
        uses=f"{nodes}#compose_painted",
        with_={
            "terrain": terrain,
            "segments": {key: step.outputs.image for key, step in published.items()},
            "map_id": map_id,
            "material_identity": material_identity,
        },
        view=True,
    )
    return {"segments": published, "compose": compose}


__all__ = [
    "PAINTED_TERRAIN_GROUND_VALIDATION_KIND",
    "SEGMENT_TAKES",
    "add_painted_terrain_steps",
    "admit_painted",
    "canonicalize_painted",
    "compose_painted",
    "painted_guide",
]
