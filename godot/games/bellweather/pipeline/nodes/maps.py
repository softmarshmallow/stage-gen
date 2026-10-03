"""A map's terrain, presentation art, review board and the shapes its answers take.

Terrain shape is composed by a model from the map's brief and judged by the game's own
validator, which hands its complaints back for the next composition; the accepted design
compiles into the ``map-terrain-v1`` geometry the rest of the map reads. Climbables and
portals are held to their sheet gate and repacked one subject per cell. The board lays every
published layer and the ground where the runtime places them, for the review.
"""

from __future__ import annotations

import json
from typing import Any, cast

from bellweather_pipeline.assets import (
    MapAsset,
    canonicalize_map_presentation,
    compose_map_board,
    validate_map_presentation_source,
)
from bellweather_pipeline.briefs import map_review_schema as review_shape
from bellweather_pipeline.climbable_atlas import ClimbableRole
from bellweather_pipeline.maps import PreparedGameMap
from bellweather_pipeline.maps.prepared import (
    canonical_prepared_map_terrain_json,
    validate_generated_terrain,
)
from bellweather_pipeline.terrain_design import compile_terrain, terrain_profile
from demo_game_tools.kits.sideview_map_design import (
    build_chunk_schema,
    expand_design,
    rejection_feedback,
)
from gnode import Ctx, node

_MAP = {"map": dict}
_ASSET: dict[str, Any] = {
    "asset": ("climbable", "portal"),
    #: The climbable roster's roles in atlas order; empty for a portal pair.
    "roles": {"type": "array", "items": {"type": "string"}, "default": []},
}


def _map(ctx: Ctx) -> PreparedGameMap:
    return PreparedGameMap.model_validate(ctx.params["map"])


def _design(ctx: Ctx, game_map: PreparedGameMap) -> tuple[Any, list[str]]:
    profile = terrain_profile(game_map)
    return expand_design(ctx.read.json("design"), profile, profile.geometry.columns)


@node("terrain_schema", params=_MAP, outputs={"schema": "json"}, version=1)
def terrain_schema(ctx: Ctx) -> dict[str, Any]:
    """The composition's shape: the chunk grammar this map's capabilities allow."""

    schema = build_chunk_schema(terrain_profile(_map(ctx)))
    return {"schema": ctx.out.json(schema.json_schema)}


@node("check_terrain", inputs={"design": "json"}, params=_MAP, judge=True, version=1)
def check_terrain(ctx: Ctx) -> dict[str, Any]:
    """The composed level satisfies the map's own rules, or it is composed again, told why."""

    _designed, problems = _design(ctx, _map(ctx))
    if problems:
        ctx.fact("errors", problems)
        ctx.fact("feedback", rejection_feedback(problems))
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("verdict", "accept")
    return {}


@node("terrain", inputs={"design": "json"}, params=_MAP, outputs={"terrain": "json"}, version=1)
def terrain(ctx: Ctx) -> dict[str, Any]:
    """Compile the accepted composition into the map's geometry, checked against its request."""

    game_map = _map(ctx)
    designed, problems = _design(ctx, game_map)
    if problems:
        raise ctx.fail(f"the accepted terrain design breaks the map's rules: {problems[:6]}")
    compiled = compile_terrain(designed, game_map)
    validate_generated_terrain(game_map, compiled)
    return {"terrain": ctx.out.bytes(canonical_prepared_map_terrain_json(compiled), "json")}


def _roles(ctx: Ctx) -> list[ClimbableRole] | None:
    roles = ctx.params["roles"]
    return cast(list[ClimbableRole], list(roles)) if ctx.params["asset"] == "climbable" else None


@node(
    "admit_presentation",
    inputs={"image": "image"},
    params={**_ASSET, "width": int, "height": int},
    judge=True,
    version=1,
)
def admit_presentation(ctx: Ctx) -> dict[str, Any]:
    """The sheet keeps a clean border and holds exactly the declared subjects, or is redrawn."""

    try:
        facts = validate_map_presentation_source(
            ctx.read.bytes("image"),
            asset=cast(MapAsset, ctx.params["asset"]),
            expected_size=(ctx.params["width"], ctx.params["height"]),
            roles=_roles(ctx),
        )
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


@node(
    "publish_presentation",
    inputs={"raw": "image"},
    params=_ASSET,
    outputs={"image": "image/png", "validation": "json"},
    version=1,
)
def publish_presentation(ctx: Ctx) -> dict[str, Any]:
    """Repack the sheet into one canonical cell per subject, left to right."""

    canonical, record = canonicalize_map_presentation(
        ctx.read.bytes("raw"), asset=cast(MapAsset, ctx.params["asset"]), roles=_roles(ctx)
    )
    return {"image": ctx.out.bytes(canonical, "image/png"), "validation": ctx.out.json(record)}


@node(
    "composite",
    inputs={"layers": "image{}", "placements": "json{}", "ground": "image", "terrain": "json"},
    params={**_MAP, "ground_composed": bool},
    outputs={"image": "image/png", "validation": "json"},
    version=1,
)
def composite(ctx: Ctx) -> dict[str, Any]:
    """The whole map at gameplay scale, each layer at its resolved placement, folded."""

    game_map = _map(ctx)
    terrain_record = ctx.read.json("terrain")
    layers = ctx.inputs["layers"]
    placements = ctx.inputs["placements"]
    missing = [layer.layer_id for layer in game_map.layers if layer.layer_id not in layers]
    if missing:
        raise ctx.fail(f"the board has no published layer {', '.join(missing)}")
    board, record = compose_map_board(
        game_map,
        layers={key: file.read_bytes() for key, file in layers.items()},
        placements={
            key: json.loads(file.read_bytes())["placement"] for key, file in placements.items()
        },
        ground=ctx.read.bytes("ground"),
        ground_composed=ctx.params["ground_composed"],
        occupancy=terrain_record["occupancy"],
        walk_surface_row=terrain_record["walk_surface_row"],
    )
    return {"image": ctx.out.bytes(board, "image/png"), "validation": ctx.out.json(record)}


@node("map_review_schema", outputs={"schema": "json"}, version=1)
def map_review_schema(ctx: Ctx) -> dict[str, Any]:
    """The map review's answer shape."""

    return {"schema": ctx.out.json(review_shape())}


__all__ = [
    "admit_presentation",
    "check_terrain",
    "composite",
    "map_review_schema",
    "publish_presentation",
    "terrain",
    "terrain_schema",
]
