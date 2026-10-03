"""Painted terrain: authored occupancy, painted, and masked back to a bounded band of it.

A second terrain discipline beside the 47-mask tile atlas, homed at the taxonomy path the
asset taxonomy reserved for it. Occupancy stays the sole collision authority -- nothing
here or downstream ever samples the image to decide what is solid -- and the drawn edge is
allowed to leave the authored one by a published, asymmetric tolerance, which is what
separates a painted rock mass from a rock-textured grid.
"""

from demo_game_tools.kits.painted_terrain.canonicalize import (
    PAINTED_TERRAIN_CANONICALIZER_ID,
    PAINTED_TERRAIN_VALIDATION_ID,
    canonicalize_painted_terrain_segment,
    occupancy_window,
    painted_terrain_segment_band,
    stitch_painted_terrain,
    validate_painted_terrain_canonical,
)
from demo_game_tools.kits.painted_terrain.guide import (
    PAINTED_TERRAIN_GUIDE_ID,
    PAINTED_TERRAIN_MODE,
    CellExposure,
    build_painted_terrain_guide,
    cell_exposure,
    painted_terrain_guide_layout,
    painted_terrain_material_identity,
    painted_terrain_occupancy_sha256,
    validate_painted_terrain_material_references,
)
from demo_game_tools.kits.painted_terrain.models import (
    PaintedSilhouetteTolerance,
    PaintedTerrainGround,
    painted_silhouette_tolerance,
)
from demo_game_tools.kits.painted_terrain.prompt import painted_terrain_generation_prompt
from demo_game_tools.kits.painted_terrain.segments import (
    PAINTED_TERRAIN_CELL_PX,
    PAINTED_TERRAIN_CONTEXT_COLUMNS,
    PAINTED_TERRAIN_GUIDE_HEIGHT,
    PAINTED_TERRAIN_GUIDE_MARGIN_PX,
    PAINTED_TERRAIN_GUIDE_WIDTH,
    PAINTED_TERRAIN_MAX_ROWS,
    PAINTED_TERRAIN_MAX_SEGMENT_COLUMNS,
    PAINTED_TERRAIN_MIN_SEGMENT_COLUMNS,
    PaintedTerrainSegment,
    painted_terrain_row_window,
    painted_terrain_segments,
)
from demo_game_tools.kits.painted_terrain.silhouette import (
    PAINTED_TERRAIN_DILATE_PX,
    PAINTED_TERRAIN_ERODE_PX,
    PAINTED_TERRAIN_SURFACE_DILATE_PX,
    PaintedSilhouetteBand,
    painted_silhouette_band,
    painted_silhouette_report,
)
from demo_game_tools.kits.painted_terrain.validate import (
    PAINTED_TERRAIN_SOURCE_ID,
    painted_terrain_join_discontinuity,
    validate_painted_terrain_source,
)

__all__ = [
    "PAINTED_TERRAIN_CANONICALIZER_ID",
    "PAINTED_TERRAIN_CELL_PX",
    "PAINTED_TERRAIN_CONTEXT_COLUMNS",
    "PAINTED_TERRAIN_DILATE_PX",
    "PAINTED_TERRAIN_ERODE_PX",
    "PAINTED_TERRAIN_GUIDE_HEIGHT",
    "PAINTED_TERRAIN_GUIDE_ID",
    "PAINTED_TERRAIN_GUIDE_MARGIN_PX",
    "PAINTED_TERRAIN_GUIDE_WIDTH",
    "PAINTED_TERRAIN_MAX_ROWS",
    "PAINTED_TERRAIN_MAX_SEGMENT_COLUMNS",
    "PAINTED_TERRAIN_MIN_SEGMENT_COLUMNS",
    "PAINTED_TERRAIN_MODE",
    "PAINTED_TERRAIN_SOURCE_ID",
    "PAINTED_TERRAIN_SURFACE_DILATE_PX",
    "PAINTED_TERRAIN_VALIDATION_ID",
    "CellExposure",
    "PaintedSilhouetteBand",
    "PaintedSilhouetteTolerance",
    "PaintedTerrainGround",
    "PaintedTerrainSegment",
    "build_painted_terrain_guide",
    "canonicalize_painted_terrain_segment",
    "cell_exposure",
    "occupancy_window",
    "painted_silhouette_band",
    "painted_silhouette_report",
    "painted_silhouette_tolerance",
    "painted_terrain_generation_prompt",
    "painted_terrain_guide_layout",
    "painted_terrain_join_discontinuity",
    "painted_terrain_material_identity",
    "painted_terrain_occupancy_sha256",
    "painted_terrain_row_window",
    "painted_terrain_segment_band",
    "painted_terrain_segments",
    "stitch_painted_terrain",
    "validate_painted_terrain_canonical",
    "validate_painted_terrain_material_references",
    "validate_painted_terrain_source",
]
