"""Actors and catalog subjects: the cut-out gates, the atlas repacks and the review boards.

A concept or a catalog subject is held to the cut-out gate (exact canvas, true alpha, a clean
border); a projectile is also held to one connected subject. A motion strip or a dialogue
atlas must show every required cell, and is repacked from its native-alpha components into
canonical cells registered at its anchor. A contact sheet lays an actor's or a family's
published pictures out, labeled, for the review.
"""

from __future__ import annotations

from typing import Any

from bellweather_pipeline.assets import (
    contact_sheet as board,
)
from bellweather_pipeline.assets import (
    repack_atlas,
    validate_atlas,
    validate_projectile_image,
    validate_transparent_image,
)
from bellweather_pipeline.briefs import content_review_schema
from demo_game_tools.kits.sideview_actor.motion_geometry import (
    dialogue_atlas_grid,
    runtime_mirrors_source,
)
from gnode import Ctx, node

_CANVAS = {"width": int, "height": int}
_GRID: dict[str, Any] = {"columns": int, "rows": int, "required_cells": int, **_CANVAS}
_EXPRESSIONS = {"type": "array", "items": {"type": "string"}}


def _judged(ctx: Ctx, check: Any) -> dict[str, Any]:
    try:
        facts = check()
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


@node("admit_cutout", inputs={"image": "image"}, params=_CANVAS, judge=True, version=1)
def admit_cutout(ctx: Ctx) -> dict[str, Any]:
    """Exact canvas, true alpha, a visible subject and a clean border, or it is drawn again."""

    return _judged(
        ctx,
        lambda: validate_transparent_image(
            ctx.read.bytes("image"), width=ctx.params["width"], height=ctx.params["height"]
        ),
    )


@node("admit_projectile", inputs={"image": "image"}, judge=True, version=1)
def admit_projectile(ctx: Ctx) -> dict[str, Any]:
    """A clean cut-out of exactly one connected subject that fills enough of its canvas."""

    return _judged(ctx, lambda: validate_projectile_image(ctx.read.bytes("image")))


@node("admit_frames", inputs={"image": "image"}, params=_GRID, judge=True, version=1)
def admit_frames(ctx: Ctx) -> dict[str, Any]:
    """A clean cut-out atlas with something visible in every required cell, or redrawn."""

    params = ctx.params
    return _judged(
        ctx,
        lambda: validate_atlas(
            ctx.read.bytes("image"),
            columns=params["columns"],
            rows=params["rows"],
            required_cells=params["required_cells"],
            width=params["width"],
            height=params["height"],
        ),
    )


@node(
    "publish_strip",
    inputs={"raw": "image"},
    params={
        **_GRID,
        "entity_kind": ("player", "mob", "npc"),
        "entity_id": str,
        "state": str,
        "anchor": str,
        "source_facing": ("right", "back", "front"),
    },
    outputs={"image": "image/png", "validation": "json"},
    version=1,
)
def publish_strip(ctx: Ctx) -> dict[str, Any]:
    """Repack the strip's frames into canonical cells, registered at the state's anchor."""

    params = ctx.params
    raw = ctx.read.bytes("raw")
    grid = {key: params[key] for key in ("columns", "rows", "required_cells")}
    source = validate_atlas(raw, **grid, width=params["width"], height=params["height"])
    canonical, repack = repack_atlas(raw, **grid, anchor=params["anchor"])
    record = {
        "schema_version": 1,
        "kind": "prepared-motion-atlas-validation-v3",
        "entity_kind": params["entity_kind"],
        "entity_id": params["entity_id"],
        "state": params["state"],
        "columns": params["columns"],
        "rows": params["rows"],
        "source_facing": params["source_facing"],
        "frames": params["required_cells"],
        "runtime_horizontal_mirroring": runtime_mirrors_source(params["source_facing"]),
        "source_validation": source,
        "repack": repack,
    }
    return {"image": ctx.out.bytes(canonical, "image/png"), "validation": ctx.out.json(record)}


@node(
    "publish_dialogue",
    inputs={"raw": "image"},
    params={"entity_kind": ("player", "npc"), "entity_id": str, "expressions": _EXPRESSIONS},
    outputs={"image": "image/png", "validation": "json"},
    version=1,
)
def publish_dialogue(ctx: Ctx) -> dict[str, Any]:
    """Repack the portraits into canonical row-major cells, centred."""

    expressions = list(ctx.params["expressions"])
    columns, rows = dialogue_atlas_grid(len(expressions))
    raw = ctx.read.bytes("raw")
    grid = {"columns": columns, "rows": rows, "required_cells": len(expressions)}
    source = validate_atlas(raw, **grid)
    canonical, repack = repack_atlas(raw, **grid, anchor="center")
    record = {
        "schema_version": 1,
        "kind": "prepared-dialogue-atlas-validation-v2",
        "entity_kind": ctx.params["entity_kind"],
        "entity_id": ctx.params["entity_id"],
        "columns": columns,
        "rows": rows,
        "index_order": "row_major",
        "expressions": expressions,
        "source_validation": source,
        "repack": repack,
    }
    return {"image": ctx.out.bytes(canonical, "image/png"), "validation": ctx.out.json(record)}


@node(
    "contact_sheet",
    inputs={"pictures": "image{}"},
    params={"labels": {"type": "array", "items": {"type": "string"}}, "title": str},
    outputs={"sheet": "image/png"},
    version=1,
)
def contact_sheet(ctx: Ctx) -> dict[str, Any]:
    """Every published picture, labeled, over a checkerboard, in the order given."""

    pictures = ctx.inputs["pictures"]
    labels = list(ctx.params["labels"])
    if sorted(labels) != sorted(pictures):
        raise ctx.fail("the sheet's labels and pictures disagree")
    sheet = board(
        [(label, pictures[label].read_bytes()) for label in labels], title=ctx.params["title"]
    )
    return {"sheet": ctx.out.bytes(sheet, "image/png")}


@node("review_schema", outputs={"schema": "json"}, version=1)
def review_schema(ctx: Ctx) -> dict[str, Any]:
    """The content review's answer shape."""

    return {"schema": ctx.out.json(content_review_schema())}


__all__ = [
    "admit_cutout",
    "admit_frames",
    "admit_projectile",
    "contact_sheet",
    "publish_dialogue",
    "publish_strip",
    "review_schema",
]
