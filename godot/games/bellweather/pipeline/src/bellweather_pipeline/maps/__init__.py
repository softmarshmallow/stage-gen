"""The authored game map, at its current contract only.

The previous document (`game-map-v2`), its ordered book, and the two CLI verbs
that validated them were retired in the engineering pass: no map in the library
had parsed under them since `game-map-v10`, and the book required an index file
the library forbids.
"""

from .prepared import (
    PREPARED_GAME_MAP_SCHEMA_VERSION,
    PreparedGameMap,
    PreparedMapCamera,
    PreparedMapClimbable,
    PreparedMapClimbablePlacement,
    PreparedMapClimbableVariant,
    PreparedMapContinuity,
    PreparedMapGround,
    PreparedMapLayer,
    PreparedMapLayerPresentation,
    PreparedMapPortal,
    PreparedMapPortalEndpoint,
    PreparedMapReference,
    PreparedMapView,
    bottom_contiguous_surface_row,
    canonical_prepared_game_map_json,
    load_prepared_game_map_bytes,
    normalized_terrain_column,
)

__all__ = [
    "PREPARED_GAME_MAP_SCHEMA_VERSION",
    "PreparedGameMap",
    "PreparedMapCamera",
    "PreparedMapClimbable",
    "PreparedMapClimbablePlacement",
    "PreparedMapClimbableVariant",
    "PreparedMapContinuity",
    "PreparedMapGround",
    "PreparedMapLayer",
    "PreparedMapLayerPresentation",
    "PreparedMapPortal",
    "PreparedMapPortalEndpoint",
    "PreparedMapReference",
    "PreparedMapView",
    "bottom_contiguous_surface_row",
    "canonical_prepared_game_map_json",
    "load_prepared_game_map_bytes",
    "normalized_terrain_column",
]
