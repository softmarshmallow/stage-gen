"""Vertical placement vocabulary shared by the map graph, producer, and runtime manifest."""

from __future__ import annotations

from typing import Literal

LAYER_PLACEMENT_CANONICALIZER = "prepared-map-layer-placement-v1"

LayerVerticalAnchor = Literal["canvas_cover", "screen_top", "screen_bottom", "walk_surface"]

#: Anchors whose offset the producer measures rather than trusting an authored guess. They do not
#: share a registration rule: `screen_bottom` seals the frame edge and needs a row every column
#: spans, while `walk_surface` meets the ground and registers on the row the content rests on,
#: because a midground layer is legitimately sparse between its subjects.
BOTTOM_REGISTERED_ANCHORS: frozenset[str] = frozenset({"screen_bottom", "walk_surface"})

#: Fields that describe where or how a generated layer is consumed rather than what the image
#: model should paint. They are excluded from generation cache identity so adjusting placement or
#: runtime depth treatment never re-bills an image.
NON_GENERATIVE_LAYER_FIELDS: frozenset[str] = frozenset(
    {"vertical_anchor", "vertical_offset", "presentation"}
)

#: Presentation does not alter local canonicalization or repeat admission either. It is projected
#: only into the prepared runtime manifest and applied by the consumer.
RUNTIME_ONLY_LAYER_FIELDS: frozenset[str] = frozenset({"presentation"})

#: The ground equivalent: authored geometry and vertical fit select cells and placement
#: downstream without changing the appearance request sent to the provider.
PLACEMENT_ONLY_GROUND_FIELDS: frozenset[str] = frozenset(
    {"occupancy", "vertical_fit", "walk_surface_row"}
)

#: The climbable equivalent. Placement position is runtime geometry, not art: the atlas draws each
#: declared variant exactly once, and where an instance stands cannot change how it is drawn. The
#: declared ladders and ropes stay in generation identity because their count sets the atlas cell
#: count and their prompts are the appearance request; only the instances come out.
PLACEMENT_ONLY_CLIMBABLE_FIELDS: frozenset[str] = frozenset({"placements"})

#: Deterministic geometry for the generated-bridge loop construction. The context spans are what
#: the provider sees on each side of the editable bridge; the bridge span is what it paints and
#: what the period grows by.
LOOP_BRIDGE_CONTEXT_SPAN_PX = 384
LOOP_BRIDGE_SPAN_PX = 384
#: Columns over which a returned bridge is eased onto its exact neighbours. The endpoint does not
#: honour a mask, so the bridge always arrives misaligned and always needs anchoring.
LOOP_BRIDGE_ANCHOR_BAND_PX = 24
#: Identity of the brief the provider is given for a bridge. It is versioned separately from the
#: layer's own generation brief because the two ask for different things: the layer brief composes
#: a strip, the bridge brief joins one. Sending the composing brief here is what makes the model
#: invent landmarks across the cut.
LOOP_BRIDGE_BRIEF_VERSION = "loop-bridge-brief-v2"
