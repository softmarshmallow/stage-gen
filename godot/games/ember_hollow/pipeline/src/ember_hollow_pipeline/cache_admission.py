"""Ember Hollow restored-image admission by the requesting node canvas."""

from __future__ import annotations

from typing import Final

from ember_hollow_pipeline.survival_types import (
    ACTOR_CONCEPT,
    DECAL_GENERATE,
    DUST_GENERATE,
    GROUND_CANVAS,
    GROUND_GENERATE,
    ITEM_GENERATE,
    MACRO_GENERATE,
    MOTION_GENERATE,
    PROP_GENERATE,
    ROAD_GENERATE,
    SEASON_LOOK_GENERATE,
    SPRITE_CANVAS,
    STRIP_CANVAS,
    WATER_GENERATE,
    WEATHER_COVER_GENERATE,
    WEATHER_DROPS_GENERATE,
    WEATHER_GROUND_GENERATE,
    WEATHER_ICE_GENERATE,
    WEATHER_STRIKE_GENERATE,
)
from gnode import (
    Node,
    inspect_image,
)

#: The canvas an image node's own port must carry, where the type fixes one. A sheet's
#: canvas is computed from its grid and is not listed; format and a non-zero size still
#: hold for those.
FIXED_CANVAS: Final[dict[str, tuple[int, int]]] = {
    ACTOR_CONCEPT.type_id: SPRITE_CANVAS,
    DECAL_GENERATE.type_id: SPRITE_CANVAS,
    DUST_GENERATE.type_id: SPRITE_CANVAS,
    ITEM_GENERATE.type_id: SPRITE_CANVAS,
    PROP_GENERATE.type_id: SPRITE_CANVAS,
    SEASON_LOOK_GENERATE.type_id: SPRITE_CANVAS,
    WEATHER_DROPS_GENERATE.type_id: SPRITE_CANVAS,
    WEATHER_GROUND_GENERATE.type_id: SPRITE_CANVAS,
    WEATHER_STRIKE_GENERATE.type_id: SPRITE_CANVAS,
    MOTION_GENERATE.type_id: STRIP_CANVAS,
    GROUND_GENERATE.type_id: GROUND_CANVAS,
    MACRO_GENERATE.type_id: GROUND_CANVAS,
    ROAD_GENERATE.type_id: GROUND_CANVAS,
    WATER_GENERATE.type_id: GROUND_CANVAS,
    WEATHER_COVER_GENERATE.type_id: GROUND_CANVAS,
    WEATHER_ICE_GENERATE.type_id: GROUND_CANVAS,
}


def admit_cached(node: Node, payloads: tuple[bytes, ...]) -> bool:
    """Re-read a restored payload the way the live path would before publishing it.

    ``Node.params`` is not a cache-key input, so a key alone cannot prove that what came
    back is the picture this node asks for. Every image node's first payload is decoded
    here and measured against the canvas its type draws on; a node whose canvas is
    computed from the sheet's grid is admitted on format and non-zero size alone, which
    is still enough to refuse a truncated or mistyped file.
    """

    if not payloads:
        return True
    first = node.ports[0].artifact_ref if node.ports else ""
    if not first.endswith(".png"):
        return True
    try:
        facts = inspect_image(payloads[0], expected_media_type="image/png")
    except (ValueError, TypeError, OSError):
        return False
    if facts.width <= 0 or facts.height <= 0:
        return False
    expected = FIXED_CANVAS.get(node.type_id)
    return expected is None or (facts.width, facts.height) == expected
