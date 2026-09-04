"""The side-view platformer node types: one declaration per kind of work.

This is the recipe's whole type census. Each declaration carries the dispatch
identity, the view archetype, the capability + features the binding table must
serve, the attempt policy, and the per-type cache contract version — replacing
the graph-level contract constant, the twelve dispatch regexes, and the
path-convention display guesses with one table.

``type_id`` values are persisted taxonomy paths (docs/spec/asset-taxonomy.md):
``2d/sideview/platformer/<module>.<step>``. The census also names the types this
recipe does not own: the nine-slice UI atlas triplet is shared with every other
genre and carries the component's own path (``2d/ui/atlas.*``), so the type census
stays complete while the declaration lives beside the contract it serves.

Policy honesty: only the two motion-rebase judges gate admission today —
every other review is advisory by design (an operator decision, not a node
failure). Declaring that here makes the asymmetry visible instead of
accidental.
"""

from __future__ import annotations

from gnode import NodePolicy, NodeType, ViewArchetype
from stage_gen.components.game_soundtrack.nodes import soundtrack_node_types
from stage_gen.components.game_ui.inventory_nodes import inventory_node_types
from stage_gen.components.game_ui.nodes import (
    UI_ATLAS_GENERATE,
    UI_ATLAS_REVIEW,
    UI_ATLAS_VALIDATE,
)
from stage_gen.components.sideview_actor.motion_rebase_nodes import motion_rebase_node_types

_P = "2d/sideview/platformer"
_PROVIDER = NodePolicy(max_attempts=6)

IMAGE_FEATURES = ("transparent_background", "reference_images")
STRUCTURED_FEATURES = ("structured_output", "image_input")
MUSIC_FEATURES = ("instrumental_loop",)

PACKAGE_RESOLVE = NodeType(
    type_id=f"{_P}/package.resolve",
    title="Package capture",
    archetype=ViewArchetype.SOURCE,
    operation="local",
    contract_version="package-resolve-v1",
)

MAP_LAYER_GENERATE = NodeType(
    type_id=f"{_P}/map_layer.generate",
    title="Map layer painting",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="map-layer-v2",
)

MAP_LAYER_LOOP_PAINT = NodeType(
    type_id=f"{_P}/map_layer.loop_paint",
    title="Layer loop repaint",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="map-layer-loop-v2",
)

MAP_LAYER_LOOP_CONSTRUCT = NodeType(
    type_id=f"{_P}/map_layer.loop_construct",
    title="Layer loop construction",
    archetype=ViewArchetype.TRANSFORM,
    operation="local",
    contract_version="map-layer-loop-v1",
)

MAP_LAYER_VALIDATE = NodeType(
    type_id=f"{_P}/map_layer.validate",
    title="Layer admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="map-layer-validate-v1",
)

MAP_TERRAIN_DESIGN = NodeType(
    type_id=f"{_P}/map_terrain.design",
    title="Terrain geometry design",
    archetype=ViewArchetype.STRUCTURED,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    # The designer owns a bounded semantic-regeneration loop on top of the
    # transport budget: a rejected design is a new identity, not a retry.
    # Three matches the designer's own max_attempts default.
    policy=NodePolicy(max_attempts=6, semantic_attempts=3),
    # v2: the floor is fenced to a shallow relief around the walk-surface datum instead of a
    # free 1..8 depth, and the grammar gained ``shelves``, the word that stacks decks over one
    # column range. Neither lives in the authored terrain table, so a cached design composed
    # under the old rule and vocabulary would otherwise be reused unexamined.
    # v3: shelves are held to a validated standing-room width. The first v2 design took the
    # advisory schema minimum of four tiles for every deck, which is a stepping stone.
    # v4: a shelves tier is a lane of decks rather than a single deck, so a storey is walkable
    # across the map the way the floor is. The v3 shape read as one narrow tower per chunk.
    contract_version="map-terrain-design-v4",
)

MAP_GROUND_GENERATE = NodeType(
    type_id=f"{_P}/map_ground.generate",
    title="Ground atlas paintover",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="map-ground-atlas-v1",
)

MAP_GROUND_VALIDATE = NodeType(
    type_id=f"{_P}/map_ground.validate",
    title="Ground atlas admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="map-ground-validate-v1",
)

MAP_CLIMBABLE_GENERATE = NodeType(
    type_id=f"{_P}/map_climbable.generate",
    title="Climbable atlas",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="map-climbable-v1",
)

MAP_CLIMBABLE_VALIDATE = NodeType(
    type_id=f"{_P}/map_climbable.validate",
    title="Climbable admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="map-climbable-validate-v1",
)

MAP_PORTAL_GENERATE = NodeType(
    type_id=f"{_P}/map_portal.generate",
    title="Portal pair",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="map-portal-v1",
)

MAP_PORTAL_VALIDATE = NodeType(
    type_id=f"{_P}/map_portal.validate",
    title="Portal admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="map-portal-validate-v1",
)

MAP_COMPOSITE = NodeType(
    type_id=f"{_P}/map.composite",
    title="Map composition",
    archetype=ViewArchetype.TRANSFORM,
    operation="local",
    contract_version="map-composite-v1",
)

MAP_REVIEW = NodeType(
    type_id=f"{_P}/map.review",
    title="Map review",
    archetype=ViewArchetype.JUDGE,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=_PROVIDER,
    contract_version="map-review-v1",
)

ACTOR_CONCEPT_GENERATE = NodeType(
    type_id=f"{_P}/actor_concept.generate",
    title="Actor identity concept",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="actor-concept-v1",
)

MOTION_ATLAS_GENERATE = NodeType(
    type_id=f"{_P}/motion_atlas.generate",
    title="Motion atlas",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="motion-atlas-v1",
)

MOTION_ATLAS_VALIDATE = NodeType(
    type_id=f"{_P}/motion_atlas.validate",
    title="Motion atlas admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="motion-atlas-validate-v1",
)

DIALOGUE_ATLAS_GENERATE = NodeType(
    type_id=f"{_P}/dialogue_atlas.generate",
    title="Dialogue expression atlas",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="dialogue-atlas-v1",
)

DIALOGUE_ATLAS_VALIDATE = NodeType(
    type_id=f"{_P}/dialogue_atlas.validate",
    title="Dialogue atlas admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="dialogue-atlas-validate-v1",
)

WORLD_SPRITE_GENERATE = NodeType(
    type_id=f"{_P}/world_sprite.generate",
    title="NPC world sprite",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="world-sprite-v1",
)

WORLD_SPRITE_VALIDATE = NodeType(
    type_id=f"{_P}/world_sprite.validate",
    title="World sprite admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="world-sprite-validate-v1",
)

#: The motion-rebase family lives in `sideview_actor`; this recipe shipped it under its own
#: type ids, which stay as the cache identity so no reading is paid for twice.
_MOTION_REBASE = motion_rebase_node_types(identity_prefix=_P)
MOTION_REBASE_JUDGE = _MOTION_REBASE.judge
MOTION_REBASE_VERIFY = _MOTION_REBASE.verify

ACTOR_CONTACT_SHEET = NodeType(
    type_id=f"{_P}/actor.contact_sheet",
    title="Actor review board",
    archetype=ViewArchetype.REVIEW,
    operation="local",
    contract_version="actor-contact-sheet-v1",
)

ACTOR_REVIEW = NodeType(
    type_id=f"{_P}/actor.review",
    title="Actor review",
    archetype=ViewArchetype.JUDGE,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=_PROVIDER,
    contract_version="actor-review-v1",
)

CATALOG_ASSET_GENERATE = NodeType(
    type_id=f"{_P}/catalog_asset.generate",
    title="Catalog asset",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="catalog-asset-v1",
)

CATALOG_ASSET_VALIDATE = NodeType(
    type_id=f"{_P}/catalog_asset.validate",
    title="Catalog asset admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="catalog-asset-validate-v1",
)

CATALOG_CONTACT_SHEET = NodeType(
    type_id=f"{_P}/catalog.contact_sheet",
    title="Catalog review board",
    archetype=ViewArchetype.REVIEW,
    operation="local",
    contract_version="catalog-contact-sheet-v1",
)

CATALOG_REVIEW = NodeType(
    type_id=f"{_P}/catalog.review",
    title="Catalog review",
    archetype=ViewArchetype.JUDGE,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=_PROVIDER,
    contract_version="catalog-review-v1",
)

#: The soundtrack family lives in its component; this recipe shipped it under its own
#: type ids, which stay as the cache identity so no track is paid for twice.
_SOUNDTRACK = soundtrack_node_types(identity_prefix=_P)
SOUNDTRACK_GENERATE = _SOUNDTRACK.generate
SOUNDTRACK_VALIDATE = _SOUNDTRACK.validate

#: The inventory-panel family lives in `game_ui`; this recipe shipped it under its own
#: type ids, which stay as the cache identity so no panel is paid for twice.
_INVENTORY = inventory_node_types(identity_prefix=_P)
UI_INVENTORY_GENERATE = _INVENTORY.generate
UI_INVENTORY_VALIDATE = _INVENTORY.validate
UI_INVENTORY_REVIEW = _INVENTORY.review

GAMEPLAY_BINDINGS_VALIDATE = NodeType(
    type_id=f"{_P}/gameplay_bindings.validate",
    title="Gameplay binding validation",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="gameplay-bindings-v1",
)

#: The runtime manifest's identity. Moves on structural change only (C-R3): a block that
#: changes shape moves its own version in ``PLATFORMER_MANIFEST_BLOCKS``. Declared here,
#: beside the node that publishes it, so the graph's port kind and the document agree.
PREPARED_RUNTIME_MANIFEST_SCHEMA_VERSION = 12
PREPARED_RUNTIME_MANIFEST_KIND = (
    f"prepared-game-runtime-v{PREPARED_RUNTIME_MANIFEST_SCHEMA_VERSION}"
)

MANIFEST_ASSEMBLE = NodeType(
    type_id=f"{_P}/manifest.assemble",
    title="Runtime manifest assembly",
    archetype=ViewArchetype.PACKAGE,
    operation="local",
    contract_version="manifest-assemble-v1",
)

PLATFORMER_NODE_TYPES: tuple[NodeType, ...] = (
    PACKAGE_RESOLVE,
    MAP_LAYER_GENERATE,
    MAP_LAYER_LOOP_PAINT,
    MAP_LAYER_LOOP_CONSTRUCT,
    MAP_LAYER_VALIDATE,
    MAP_TERRAIN_DESIGN,
    MAP_GROUND_GENERATE,
    MAP_GROUND_VALIDATE,
    MAP_CLIMBABLE_GENERATE,
    MAP_CLIMBABLE_VALIDATE,
    MAP_PORTAL_GENERATE,
    MAP_PORTAL_VALIDATE,
    MAP_COMPOSITE,
    MAP_REVIEW,
    ACTOR_CONCEPT_GENERATE,
    MOTION_ATLAS_GENERATE,
    MOTION_ATLAS_VALIDATE,
    DIALOGUE_ATLAS_GENERATE,
    DIALOGUE_ATLAS_VALIDATE,
    WORLD_SPRITE_GENERATE,
    WORLD_SPRITE_VALIDATE,
    MOTION_REBASE_JUDGE,
    MOTION_REBASE_VERIFY,
    ACTOR_CONTACT_SHEET,
    ACTOR_REVIEW,
    CATALOG_ASSET_GENERATE,
    CATALOG_ASSET_VALIDATE,
    CATALOG_CONTACT_SHEET,
    CATALOG_REVIEW,
    SOUNDTRACK_GENERATE,
    SOUNDTRACK_VALIDATE,
    UI_INVENTORY_GENERATE,
    UI_INVENTORY_VALIDATE,
    UI_INVENTORY_REVIEW,
    UI_ATLAS_GENERATE,
    UI_ATLAS_VALIDATE,
    UI_ATLAS_REVIEW,
    GAMEPLAY_BINDINGS_VALIDATE,
    MANIFEST_ASSEMBLE,
)


def platformer_type_index() -> dict[str, NodeType]:
    return {node_type.type_id: node_type for node_type in PLATFORMER_NODE_TYPES}


__all__ = [
    "ACTOR_CONCEPT_GENERATE",
    "ACTOR_CONTACT_SHEET",
    "ACTOR_REVIEW",
    "CATALOG_ASSET_GENERATE",
    "CATALOG_ASSET_VALIDATE",
    "CATALOG_CONTACT_SHEET",
    "CATALOG_REVIEW",
    "DIALOGUE_ATLAS_GENERATE",
    "DIALOGUE_ATLAS_VALIDATE",
    "GAMEPLAY_BINDINGS_VALIDATE",
    "IMAGE_FEATURES",
    "MANIFEST_ASSEMBLE",
    "PREPARED_RUNTIME_MANIFEST_KIND",
    "PREPARED_RUNTIME_MANIFEST_SCHEMA_VERSION",
    "MAP_CLIMBABLE_GENERATE",
    "MAP_CLIMBABLE_VALIDATE",
    "MAP_COMPOSITE",
    "MAP_GROUND_GENERATE",
    "MAP_GROUND_VALIDATE",
    "MAP_LAYER_GENERATE",
    "MAP_LAYER_LOOP_CONSTRUCT",
    "MAP_LAYER_LOOP_PAINT",
    "MAP_LAYER_VALIDATE",
    "MAP_PORTAL_GENERATE",
    "MAP_PORTAL_VALIDATE",
    "MAP_REVIEW",
    "MAP_TERRAIN_DESIGN",
    "MOTION_ATLAS_GENERATE",
    "MOTION_ATLAS_VALIDATE",
    "MOTION_REBASE_JUDGE",
    "MOTION_REBASE_VERIFY",
    "MUSIC_FEATURES",
    "PACKAGE_RESOLVE",
    "PLATFORMER_NODE_TYPES",
    "SOUNDTRACK_GENERATE",
    "SOUNDTRACK_VALIDATE",
    "STRUCTURED_FEATURES",
    "UI_ATLAS_GENERATE",
    "UI_ATLAS_REVIEW",
    "UI_ATLAS_VALIDATE",
    "UI_INVENTORY_GENERATE",
    "UI_INVENTORY_REVIEW",
    "UI_INVENTORY_VALIDATE",
    "WORLD_SPRITE_GENERATE",
    "WORLD_SPRITE_VALIDATE",
    "platformer_type_index",
]
