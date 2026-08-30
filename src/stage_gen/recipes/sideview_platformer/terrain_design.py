"""Compose a map's terrain the way its artwork is composed.

Terrain shape is generated, not authored. The map document states which generator to use and
what the level should be; this module turns that request into a capability profile the designer
can satisfy, and turns the design it returns into the ``map-terrain-v1`` artifact the rest of
the graph consumes. Nothing here is written back into the authored document.

The movement envelope lives here rather than in a component because it is a property of the
consumer this recipe targets: a side-scrolling runtime with a particular jump arc. A different
consumer would state a different envelope, which is exactly why the designer takes it as data.
"""

from __future__ import annotations

from stage_gen.components.platformer_map.prepared import (
    MAX_UNASSISTED_TERRAIN_RISE_TILES,
    PreparedGameMap,
    PreparedMapClimbablePlacement,
    PreparedMapTerrain,
)
from stage_gen.components.platformer_map_design import (
    STANDARD_TILE_ROLES,
    DesignedMap,
    GeometryProfile,
    MovementProfile,
    PlatformerProfile,
)

#: Measured from the runtime's own jump arc, not assumed: a rise of one tile stays reachable
#: across eight columns of gap and a rise of two across six. Anything higher needs a climbable.
#: See web/lib/sideview-platformer/vertical.ts and player.ts for the source of these numbers.
TERRAIN_JUMP_REACH: dict[int, int] = {1: 8, 2: 6}
#: A level or downward crossing is not free either. Bounding it stops a design from treating two
#: surfaces a whole screen apart as connected.
TERRAIN_LEVEL_GAP_TILES = 8
#: The only rise a climbable spans today; the tiled-band work in TODO.md is what lifts it.
TERRAIN_CLIMBABLE_RISE_TILES: tuple[int, ...] = (4,)
#: The runtime refuses a ladder whose foot has no flat neighbour to its right.
TERRAIN_CLIMBABLE_NEEDS_FLAT_FOOTING = True
#: The consumer's viewport and figure, restated from the runtime's prepared-scene.ts
#: (web/lib/sideview-platformer) so the
#: designer and the runtime cannot disagree about what "in frame" means. VIEW_H is 720, TILE_PX
#: is 64, and a standing player is drawn 154px tall.
TERRAIN_VIEWPORT_HEIGHT_PX = 720
TERRAIN_TILE_PX = 64
TERRAIN_PLAYER_STANDING_HEIGHT_PX = 154
#: Bounds on how deep the floor may be. One tile is the least that renders as ground at all; the
#: upper bound stops the floor eating the playable space.
TERRAIN_GROUND_DEPTH_TILES = (1, 8)
#: How many climbables a map may place when it declares an atlas at all.
TERRAIN_CLIMBABLE_COUNT = (1, 8)


def terrain_artifact_path(map_id: str) -> str:
    """Where a map's generated geometry lives inside a run, beside its generated images."""

    return f"maps/{map_id}/terrain.json"


def framing_ceiling(rows: int, follows_vertical: bool) -> int:
    """Highest walkable surface a standing player still fits above.

    This is the one place the camera reaches into generation, so it reads the same declaration the
    runtime does rather than restating a guess. When the camera follows the player vertically the
    whole grid is reachable; when it does not, the world the player can occupy is only as tall as
    the viewport, and a surface higher than that puts the figure off the top of the screen with no
    way to bring it back.

    Headroom is the figure itself, rounded up to whole tiles, because the constraint is the head
    rather than the feet: a surface the feet can reach and the head cannot is still unplayable.
    """

    headroom = -(-TERRAIN_PLAYER_STANDING_HEIGHT_PX // TERRAIN_TILE_PX)
    visible = rows if follows_vertical else TERRAIN_VIEWPORT_HEIGHT_PX // TERRAIN_TILE_PX
    return max(1, min(rows, visible) - headroom)


def terrain_profile(game_map: PreparedGameMap) -> PlatformerProfile:
    """Build the capability profile that this map's terrain must satisfy.

    The grid and the walk-surface datum come from the map, because those are the author's
    decisions and painted scenery is anchored to them. The movement envelope comes from the
    runtime. The climbable roster comes from the map's declared atlas, so the designer can only
    place a variant the map is able to draw, and a map with no atlas gets no climbable words in
    its grammar at all.
    """

    request = game_map.terrain
    variants = (
        ()
        if game_map.climbable is None
        else tuple(entry.variant_id for entry in game_map.climbable.variants)
    )
    ceiling = framing_ceiling(request.rows, "y" in game_map.camera.follow_axes)
    return PlatformerProfile(
        profile_id=f"{game_map.game_id}-{game_map.map_id}",
        movement=MovementProfile(
            max_step_up_tiles=MAX_UNASSISTED_TERRAIN_RISE_TILES,
            jump_reach=TERRAIN_JUMP_REACH,
            climbable_rise_tiles=TERRAIN_CLIMBABLE_RISE_TILES,
            level_gap_tiles=TERRAIN_LEVEL_GAP_TILES,
            climbable_footing="ground",
            climbable_needs_flat_footing=TERRAIN_CLIMBABLE_NEEDS_FLAT_FOOTING,
        ),
        geometry=GeometryProfile(
            columns=request.columns,
            rows=request.rows,
            ground_depth_tiles=TERRAIN_GROUND_DEPTH_TILES,
            max_walkable_height_tiles=ceiling,
            platforms_single_thickness=True,
        ),
        roles=STANDARD_TILE_ROLES,
        climbable_variants=variants,
        climbable_count=TERRAIN_CLIMBABLE_COUNT if variants else (0, 0),
        notes=f"{game_map.display_name} terrain, generated from the authored brief.",
    )


def compile_terrain(designed: DesignedMap, game_map: PreparedGameMap) -> PreparedMapTerrain:
    """Turn an accepted design into the geometry artifact the rest of the graph consumes.

    The designer works bottom-row-first in role symbols because that is how a person reads a
    side view; the artifact is top-row-first binary because that is what the consumer renders.
    This is the only place that conversion happens.
    """

    profile = terrain_profile(game_map)
    ground = profile.ground_role.symbol
    empty = profile.empty_role.symbol
    occupancy = [
        "".join(
            "0" if designed.grid[height - 1][column] == empty else "1"
            for column in range(designed.columns)
        )
        for height in range(designed.rows, 0, -1)
    ]
    placements = [
        PreparedMapClimbablePlacement(
            climbable_id=climbable.climbable_id,
            variant_id=climbable.variant_id,
            # Mid-column, so the position survives rounding in both directions when the consumer
            # projects it back onto a column.
            normalized_x=round((climbable.foot_column + 0.5) / designed.columns, 6),
            bottom_surface="terrain",
            rise_tiles=4,
        )
        for climbable in designed.climbables
    ]
    # `ground` is unused for the binary projection but naming it documents which symbol the
    # occupancy "1" stands for; a role the profile does not declare could never appear here.
    assert ground
    return PreparedMapTerrain(
        schema_version=1,
        kind="map-terrain-v1",
        map_id=game_map.map_id,
        occupancy=occupancy,
        walk_surface_row=game_map.terrain.walk_surface_row,
        climbable_placements=placements,
    )
