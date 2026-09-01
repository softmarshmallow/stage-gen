"""The tiled-segment ground discipline shared by side-view genres.

The 47-mask terrain atlas (`terrain-atlas-3x3-minimal-v1`) is camera-scoped,
not genre-scoped: a platformer map and a runner track paint the same locked
template and canonicalize through the same admission. Genre-specific terrain
*rules* (escape floors, pits) stay with their genre contracts.
"""

from stage_gen.components.sideview_terrain.atlas import (
    CANONICAL_CELL_PX,
    GRID_COLUMNS,
    GRID_ROWS,
    MASK_ORDER,
    MATERIAL_ASSEMBLER_ID,
    MATERIAL_SOURCE_CONTRACT_ID,
    PLACEHOLDER_CELL,
    TOPOLOGY_ID,
    TerrainAtlasLookup,
    assemble_terrain_atlas,
    cells_from_canonical_atlas,
    compose_canonical_terrain,
    compose_terrain,
    load_terrain_atlas_lookup,
    parse_binary_rows,
    peering_mask,
    require_terrain_atlas_source,
    terrain_atlas_generation_prompt,
)

__all__ = [
    "CANONICAL_CELL_PX",
    "GRID_COLUMNS",
    "GRID_ROWS",
    "MASK_ORDER",
    "MATERIAL_ASSEMBLER_ID",
    "MATERIAL_SOURCE_CONTRACT_ID",
    "PLACEHOLDER_CELL",
    "TOPOLOGY_ID",
    "TerrainAtlasLookup",
    "assemble_terrain_atlas",
    "cells_from_canonical_atlas",
    "compose_canonical_terrain",
    "compose_terrain",
    "load_terrain_atlas_lookup",
    "parse_binary_rows",
    "peering_mask",
    "require_terrain_atlas_source",
    "terrain_atlas_generation_prompt",
]
