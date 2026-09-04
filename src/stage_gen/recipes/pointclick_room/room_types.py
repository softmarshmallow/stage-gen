"""The point-and-click room node types.

``type_id`` values persist taxonomy paths under ``2d/roomview/pointclick`` —
the ``roomview`` camera alias is bound to the ``screen_space_room_stage_v1``
presentation profile (docs/spec/game/view-and-style-taxonomy.md).

Every prompt this recipe sends is known at plan time, so every generation
node's card carries its full static prompt and the handlers consume the card —
one composition, stated in the plan, executed verbatim.
"""

from __future__ import annotations

from gnode import NodePolicy, NodeType, ViewArchetype
from stage_gen.components.game_ui.nodes import UI_ATLAS_NODE_TYPES

_P = "2d/roomview/pointclick"
_PROVIDER = NodePolicy(max_attempts=6)

IMAGE_FEATURES = ("transparent_background", "reference_images")
STRUCTURED_FEATURES = ("structured_output",)

#: Payload kinds (persisted vocabulary).
ROOM_KIND = "pointclick-room-v3"
#: The authored style reference, republished into the run by the bundle so the
#: playable manifest is a closed set of bytes rather than a pointer at a package.
COVER_KIND = "room-style-reference-v1"
BACKDROP_KIND = "room-backdrop-v1"
PROVIDER_RAW_KIND = "provider-raw-image-v1"
HOTSPOT_SPRITE_KIND = "hotspot-sprite-v1"
ITEM_ICON_KIND = "item-icon-v1"
SPRITE_VALIDATION_KIND = "sprite-validation-v1"
NARRATION_KIND = "room-narration-v1"
PUZZLE_KIND = "room-puzzle-v1"
SOLVABILITY_KIND = "pointclick-solvability-v1"
STYLE_ANCHOR_KIND = "style-anchor-v1"
ATTEMPT_LEDGER_KIND = "attempt-ledger-v1"
MERGED_ATTEMPTS_KIND = "attempt-ledger-merged-v1"
MANIFEST_KIND = "pointclick-room-runtime-v3"
#: Read off the kind rather than pinned beside it: the number had sat at 1 through three
#: kind bumps, a guard that never once fired.
MANIFEST_SCHEMA_VERSION = int(MANIFEST_KIND.rsplit("-v", 1)[1])

ROOM_RESOLVE = NodeType(
    type_id=f"{_P}/room.resolve",
    title="Room document",
    archetype=ViewArchetype.SOURCE,
    operation="local",
    contract_version="room-resolve-v2",
)

STYLE_SELECT = NodeType(
    type_id=f"{_P}/style_anchor.select",
    title="Style anchor selection",
    archetype=ViewArchetype.STRUCTURED,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=_PROVIDER,
    contract_version="room-style-select-v1",
)

BACKDROP_GENERATE = NodeType(
    type_id=f"{_P}/backdrop.generate",
    title="Room backdrop",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="room-backdrop-v1",
)

HOTSPOT_SPRITE_GENERATE = NodeType(
    type_id=f"{_P}/hotspot_sprite.generate",
    title="Hotspot object",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="room-hotspot-sprite-v1",
)

HOTSPOT_SPRITE_VALIDATE = NodeType(
    type_id=f"{_P}/hotspot_sprite.validate",
    title="Hotspot admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="room-hotspot-validate-v1",
)

ITEM_ICON_GENERATE = NodeType(
    type_id=f"{_P}/item_icon.generate",
    title="Inventory item icon",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="room-item-icon-v1",
)

ITEM_ICON_VALIDATE = NodeType(
    type_id=f"{_P}/item_icon.validate",
    title="Item icon admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="room-item-validate-v1",
)

NARRATION_COMPILE = NodeType(
    type_id=f"{_P}/narration.compile",
    title="Room narration",
    archetype=ViewArchetype.STRUCTURED,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=_PROVIDER,
    contract_version="room-narration-v1",
)

PUZZLE_VALIDATE = NodeType(
    type_id=f"{_P}/puzzle.validate",
    title="Puzzle solvability proof",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="room-puzzle-validate-v1",
)

#: v4: the manifest's `schema_version` is read off the kind (3, was pinned at 1). The
#: bundle is a local node admitted on lineage, so without this bump a cached run kept
#: restoring the old document - which is what "re-publish from cache" then did.
ROOM_BUNDLE = NodeType(
    type_id=f"{_P}/room.bundle",
    title="Room runtime bundle",
    archetype=ViewArchetype.PACKAGE,
    operation="local",
    contract_version="room-bundle-v4",
)

POINTCLICK_NODE_TYPES: tuple[NodeType, ...] = (
    ROOM_RESOLVE,
    STYLE_SELECT,
    BACKDROP_GENERATE,
    HOTSPOT_SPRITE_GENERATE,
    HOTSPOT_SPRITE_VALIDATE,
    ITEM_ICON_GENERATE,
    ITEM_ICON_VALIDATE,
    NARRATION_COMPILE,
    PUZZLE_VALIDATE,
    ROOM_BUNDLE,
    # The census names the types this recipe plans, including the ones it does not own:
    # the nine-slice UI atlas triplet is shared with every other genre.
    *UI_ATLAS_NODE_TYPES,
)


def pointclick_type_index() -> dict[str, NodeType]:
    return {node_type.type_id: node_type for node_type in POINTCLICK_NODE_TYPES}


__all__ = [
    "ATTEMPT_LEDGER_KIND",
    "BACKDROP_GENERATE",
    "BACKDROP_KIND",
    "COVER_KIND",
    "HOTSPOT_SPRITE_GENERATE",
    "HOTSPOT_SPRITE_KIND",
    "HOTSPOT_SPRITE_VALIDATE",
    "IMAGE_FEATURES",
    "ITEM_ICON_GENERATE",
    "ITEM_ICON_KIND",
    "ITEM_ICON_VALIDATE",
    "MANIFEST_KIND",
    "MANIFEST_SCHEMA_VERSION",
    "MERGED_ATTEMPTS_KIND",
    "NARRATION_COMPILE",
    "NARRATION_KIND",
    "POINTCLICK_NODE_TYPES",
    "PROVIDER_RAW_KIND",
    "PUZZLE_KIND",
    "PUZZLE_VALIDATE",
    "ROOM_BUNDLE",
    "ROOM_KIND",
    "ROOM_RESOLVE",
    "SOLVABILITY_KIND",
    "SPRITE_VALIDATION_KIND",
    "STRUCTURED_FEATURES",
    "STYLE_ANCHOR_KIND",
    "STYLE_SELECT",
    "pointclick_type_index",
]
