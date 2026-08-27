"""Vertical placement vocabulary shared by the map graph, producer, and runtime manifest."""

from __future__ import annotations

from typing import Literal

LAYER_PLACEMENT_CANONICALIZER = "prepared-map-layer-placement-v1"

LayerVerticalAnchor = Literal["canvas_cover", "screen_top", "screen_bottom", "walk_surface"]

#: Anchors that register the bottom of a layer's solid mass rather than its deepest stray tip.
#: A ragged edge keeps showing gaps until its full-coverage line reaches the datum, so these are
#: the anchors whose offset the producer measures instead of trusting an authored guess.
BOTTOM_REGISTERED_ANCHORS: frozenset[str] = frozenset({"screen_bottom", "walk_surface"})

#: Fields that describe where a layer is placed rather than what the image model should paint.
#: They are excluded from generation cache identity so re-anchoring never re-bills an image.
PLACEMENT_ONLY_LAYER_FIELDS: frozenset[str] = frozenset({"vertical_anchor", "vertical_offset"})

#: The ground equivalent: authored geometry and vertical fit select cells and placement
#: downstream without changing the appearance request sent to the provider.
PLACEMENT_ONLY_GROUND_FIELDS: frozenset[str] = frozenset(
    {"occupancy", "vertical_fit", "walk_surface_row"}
)
