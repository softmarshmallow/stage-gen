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
from stage_gen.components.sideview_map_design import (
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
#: How far the floor may leave the walk-surface datum, in tiles either way. The hunting-map
#: reference this runtime targets keeps its ground as one nearly level lane and puts the level's
#: interest in the platforms hung above it, so the floor is fenced to a shallow relief rather
#: than left free to climb the grid as terrain. Everything above the band is the designer's to
#: fill with decks, ladders, and stepping platforms.
TERRAIN_FLOOR_RELIEF_TILES = 1
#: Narrowest deck the designer may call standing room. Read off the reference hunting map: the
#: ledge a figure fights on there is three to four figure-heights across, and a figure is 2.4
#: tiles tall, so a deck under six tiles reads as a stepping stone rather than a place to stand.
#: Left to the schema alone the designer picks the minimum every time, so this is validated.
#: It also sets the hop between decks on one storey: at a hop this wide the storey above
#: interlocks with the gaps of the one below, which is the headroom a 2.4-tile figure needs
#: under decks the jump can only carry it two tiles above.
TERRAIN_SHELF_MIN_WIDTH_TILES = 6
#: How many climbables a map may place when it declares an atlas at all.
TERRAIN_CLIMBABLE_COUNT = (1, 8)


def terrain_artifact_path(map_id: str) -> str:
    """Where a map's generated geometry lives inside a run, beside its generated images."""

    return f"maps/{map_id}/terrain.json"


def floor_depth_band(rows: int, walk_surface_row: int) -> tuple[int, int]:
    """Inclusive floor depths the designer may use, centred on the map's walk-surface datum.

    The datum is where painted scenery meets the earth, so the floor is measured from it rather
    than from an absolute bound: a map that pins its walk surface deeper gets a deeper floor, and
    the same relief either side of it. The lower bound never drops below the single tile the
    consumer needs to render ground at all.
    """

    datum = rows - walk_surface_row
    return max(1, datum - TERRAIN_FLOOR_RELIEF_TILES), datum + TERRAIN_FLOOR_RELIEF_TILES


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
            ground_depth_tiles=floor_depth_band(request.rows, request.walk_surface_row),
            max_walkable_height_tiles=ceiling,
            platforms_single_thickness=True,
            shelf_min_width_tiles=TERRAIN_SHELF_MIN_WIDTH_TILES,
        ),
        roles=STANDARD_TILE_ROLES,
        climbable_variants=variants,
        climbable_count=TERRAIN_CLIMBABLE_COUNT if variants else (0, 0),
        # The atlas draws every declared variant once, and the map contract rejects generated
        # terrain that leaves one unplaced. Telling the designer so keeps that rejection inside
        # its own regeneration loop instead of failing the node after the design was accepted.
        climbable_variants_each_placed=bool(variants),
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
