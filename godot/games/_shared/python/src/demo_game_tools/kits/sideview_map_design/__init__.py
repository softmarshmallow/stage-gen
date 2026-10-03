"""Provider-neutral platformer map design: capabilities, chunk grammar, validator, designer.

WHAT THIS IS. A description of what a 2D side-scrolling game can express (:mod:`capabilities`),
a grammar that composes a map as a left-to-right sentence of named set-pieces (:mod:`grammar`),
a deterministic expander plus the validator that judges the result against those capabilities
(:mod:`design`), and a structured-generation loop that composes a map and re-composes it from
the validator's own complaints (:mod:`designer`).

WHAT THIS IS NOT. It is not a generator: it produces no images, audio, or packaged artifacts,
and it schedules no work. It is not a renderer: it never sees a pixel, a camera, a viewport, or
an engine, and every measurement it makes is in tiles. It is not a recipe or an adapter: it owns
no composition, layout, or runtime assumption. And it knows no specific game -- there is not one
game constant in this package. Every threshold, symbol, climbable variant, and biome tag arrives
in the :class:`PlatformerProfile` a caller hands it, which is the only reason one designer can
serve a fixed-rise ground-founded platformer and a chained-shaft metroidvania without a branch.
"""

from .capabilities import (
    EMPTY_TILE_ROLE,
    GROUND_TILE_ROLE,
    PLATFORM_TILE_ROLE,
    STANDARD_TILE_ROLES,
    ClimbableFooting,
    GeometryProfile,
    MovementProfile,
    PlatformerProfile,
    TileRole,
)
from .design import (
    PLATFORMER_MAP_DESIGN_KIND,
    PLATFORMER_MAP_DESIGN_SCHEMA_VERSION,
    Climbable,
    DesignedMap,
    PlatformerChunkMapDesign,
    PlatformerMapDesignLoadError,
    Surface,
    canonical_platformer_chunk_map_design_json,
    check,
    load_platformer_chunk_map_design_bytes,
    unreachable,
)
from .designer import (
    DESIGN_TIMEOUT_SECONDS,
    MAX_QUOTED_PROBLEMS,
    DesignAttempt,
    DesignBrief,
    design_chunks,
)
from .grammar import (
    ChunkSpan,
    build_chunk_prompt,
    build_chunk_schema,
    expand_chunks,
    translate,
    vocabulary,
)

__all__ = [
    "DESIGN_TIMEOUT_SECONDS",
    "EMPTY_TILE_ROLE",
    "GROUND_TILE_ROLE",
    "MAX_QUOTED_PROBLEMS",
    "PLATFORMER_MAP_DESIGN_KIND",
    "PLATFORMER_MAP_DESIGN_SCHEMA_VERSION",
    "PLATFORM_TILE_ROLE",
    "STANDARD_TILE_ROLES",
    "ChunkSpan",
    "Climbable",
    "ClimbableFooting",
    "DesignAttempt",
    "DesignBrief",
    "DesignedMap",
    "GeometryProfile",
    "MovementProfile",
    "PlatformerChunkMapDesign",
    "PlatformerMapDesignLoadError",
    "PlatformerProfile",
    "Surface",
    "TileRole",
    "build_chunk_prompt",
    "build_chunk_schema",
    "canonical_platformer_chunk_map_design_json",
    "check",
    "design_chunks",
    "expand_chunks",
    "load_platformer_chunk_map_design_bytes",
    "translate",
    "unreachable",
    "vocabulary",
]
