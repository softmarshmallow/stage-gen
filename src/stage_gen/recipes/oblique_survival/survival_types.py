"""Every node type the oblique-survival graph may contain.

The type ids are taxonomy paths (``2d/obliqueview/survival/<module>.<step>``) and the
contract versions are cache-key inputs, so both are frozen: see
``CONTRACT_VERSION_PREFIX`` below.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from gnode import LOCAL_OPERATION, NodePolicy, NodeType, ViewArchetype

#: The recipe word: document kinds, the graph's ``recipe`` literal, the CLI verb.
RECIPE: Final = "oblique-survival"
#: FROZEN. Every node type's ``contract_version`` is built from this prefix, and
#: ``contract_version`` is one of the eight inputs of a node's cache key. It is
#: deliberately *not* the recipe word: renaming it to ``oblique-survival`` would move
#: every cache key in the graph and re-bill the run that paid for them.
CONTRACT_VERSION_PREFIX: Final = "oblique-survival-v0"
#: The presentation the whole recipe draws for; woven into the graph header.
PRESENTATION_PROFILE: Final = "elevated_oblique_perspective_ground_plane_v1"
#: The scope ladder, narrowest first. A scope selects a subset of nodes and changes
#: nothing about the ones it keeps.
SCOPES: Final = ("minimal", "props", "actors", "full")
SCOPE_RANK: Final = {name: index for index, name in enumerate(SCOPES)}
#: ``seasons`` judges each season look beside its summer twin, and the ice.
REVIEW_FAMILIES: Final = ("props", "ground", "actors", "fx", "seasons")

TYPE_PREFIX: Final = "2d/obliqueview/survival"
IMAGE_FEATURES: Final = ("transparent_background", "reference_images")
STRUCTURED_FEATURES: Final = ("structured_output", "image_input")
TOOL_LOOP_FEATURES: Final = ("tool_use", "image_input")
MUSIC_FEATURES: Final = ("instrumental_loop",)
#: The bolt sheet's four quarters have no authored meaning; a strike picks one.
STRIKE_CELL_KINDS: Final = ("bolt_0", "bolt_1", "bolt_2", "bolt_3")
#: The sound-effect route honours an exact duration and a seamless-loop flag.
SOUND_FEATURES: Final = ("exact_duration",)
#: A clip may come back a little short of what was asked; more than this is a
#: truncated file, not frame quantization.
SOUND_DURATION_TOLERANCE_SECONDS: Final = 0.5


class ObliqueSurvivalOperationKind(StrEnum):
    """The capabilities an oblique-survival node is allowed to use.

    A member's ``str()`` is its value, which is what the cache key hashes, so declaring
    the vocabulary as an enum moves nothing.
    """

    LOCAL = "local"
    IMAGE_GENERATION = "image_generation"
    STRUCTURED_GENERATION = "structured_generation"
    TOOL_LOOP = "tool_loop"
    MUSIC_GENERATION = "music_generation"
    SOUND_EFFECT_GENERATION = "sound_effect_generation"


def _local(
    module: str, step: str, title: str, archetype: ViewArchetype = ViewArchetype.TRANSFORM
) -> NodeType:
    return NodeType(
        type_id=f"{TYPE_PREFIX}/{module}.{step}",
        title=title,
        archetype=archetype,
        operation=LOCAL_OPERATION,
        contract_version=f"{CONTRACT_VERSION_PREFIX}-local-1",
    )


def _image(module: str, step: str, title: str) -> NodeType:
    return NodeType(
        type_id=f"{TYPE_PREFIX}/{module}.{step}",
        title=title,
        archetype=ViewArchetype.IMAGE,
        operation="image_generation",
        features=IMAGE_FEATURES,
        policy=NodePolicy(max_attempts=6),
        contract_version=f"{CONTRACT_VERSION_PREFIX}-image-1",
    )


def _music(module: str, step: str, title: str) -> NodeType:
    return NodeType(
        type_id=f"{TYPE_PREFIX}/{module}.{step}",
        title=title,
        archetype=ViewArchetype.MUSIC,
        operation="music_generation",
        features=MUSIC_FEATURES,
        policy=NodePolicy(max_attempts=6),
        contract_version=f"{CONTRACT_VERSION_PREFIX}-music-1",
    )


def _sound(module: str, step: str, title: str) -> NodeType:
    return NodeType(
        type_id=f"{TYPE_PREFIX}/{module}.{step}",
        title=title,
        archetype=ViewArchetype.SOUND,
        operation="sound_effect_generation",
        features=SOUND_FEATURES,
        policy=NodePolicy(max_attempts=6),
        contract_version=f"{CONTRACT_VERSION_PREFIX}-sound-1",
    )


def _structured(module: str, step: str, title: str) -> NodeType:
    return NodeType(
        type_id=f"{TYPE_PREFIX}/{module}.{step}",
        title=title,
        archetype=ViewArchetype.JUDGE,
        operation="structured_generation",
        features=STRUCTURED_FEATURES,
        policy=NodePolicy(max_attempts=6),
        contract_version=f"{CONTRACT_VERSION_PREFIX}-structured-1",
    )


SOURCE_LOCK = _local("source", "lock", "Source lock and digest ledger", ViewArchetype.SOURCE)
TEMPLATES_DRAW = _local("templates", "draw", "Paintover lattice template")
ACTOR_CONCEPT = _image("actor_concept", "generate", "Actor appearance sheet")
MOTION_GENERATE = _image("motion_atlas", "generate", "Actor motion strip")
MOTION_VALIDATE = _local(
    "motion_atlas", "validate", "Motion strip gate and repack", ViewArchetype.VALIDATE
)
REBASE_PLATE = _local("motion_rebase", "plate", "Cross-state scale plate", ViewArchetype.IMAGE)
REBASE_JUDGE = _structured("motion_rebase", "judge", "Cross-state scale reading")
REBASE_VERIFY_PLATE = _local(
    "motion_rebase", "verify_plate", "Corrected scale plate", ViewArchetype.IMAGE
)
REBASE_VERIFY = _structured("motion_rebase", "verify", "Residual scale reading")
PROP_GENERATE = _image("prop_sprite", "generate", "Prop state sprite")
PROP_VALIDATE = _local("prop_sprite", "validate", "Prop gate and footprint", ViewArchetype.VALIDATE)
PROP_SHEET_GENERATE = _image("prop_sheet", "generate", "Prop look sheet paintover")
PROP_SHEET_VALIDATE = _local(
    "prop_sheet", "validate", "Prop sheet gate and per-look split", ViewArchetype.VALIDATE
)
SEASON_LOOK_GENERATE = _image("season_look", "generate", "Season look paintover of a prop state")
SEASON_LOOK_VALIDATE = _local(
    "season_look",
    "validate",
    "Season look gate and drift against the summer sprite",
    ViewArchetype.VALIDATE,
)
PROP_ANCHOR = NodeType(
    type_id=f"{TYPE_PREFIX}/prop_sprite.anchor",
    title="Prop anchor and motion hint",
    archetype=ViewArchetype.JUDGE,
    operation="tool_loop",
    features=TOOL_LOOP_FEATURES,
    policy=NodePolicy(max_attempts=1),
    contract_version=f"{CONTRACT_VERSION_PREFIX}-tool-loop-1",
)
ITEM_GENERATE = _image("item_sprite", "generate", "Item pickup sprite")
ITEM_VALIDATE = _local("item_sprite", "validate", "Item gate", ViewArchetype.VALIDATE)
GROUND_GENERATE = _image("ground_texture", "generate", "Biome ground plate")
GROUND_ADOPT = _local(
    "ground_texture", "adopt", "Adopt an auditioned ground plate", ViewArchetype.IMAGE
)
GROUND_CANONICALIZE = _local(
    "ground_texture", "canonicalize", "Ground gate and 2-axis mirror", ViewArchetype.VALIDATE
)
DECAL_GENERATE = _image("ground_decal", "generate", "Ground decal")
DECAL_VALIDATE = _local("ground_decal", "validate", "Decal gate", ViewArchetype.VALIDATE)
MACRO_GENERATE = _image("ground_macro", "generate", "Macro colour-field plate")
MACRO_CANONICALIZE = _local(
    "ground_macro", "canonicalize", "Macro gate and 2-axis mirror", ViewArchetype.VALIDATE
)
ROAD_GENERATE = _image("ground_road", "generate", "Road material plate")
ROAD_CANONICALIZE = _local(
    "ground_road", "canonicalize", "Road gate and 2-axis mirror", ViewArchetype.VALIDATE
)
CLUTTER_GENERATE = _image("ground_clutter", "generate", "Ground litter sheet paintover")
CLUTTER_ADOPT = _local(
    "ground_clutter", "adopt", "Adopt an auditioned litter sheet", ViewArchetype.IMAGE
)
CLUTTER_VALIDATE = _local(
    "ground_clutter", "validate", "Litter lattice and isolation gate", ViewArchetype.VALIDATE
)
FORAGE_GENERATE = _image("ground_forage", "generate", "Ground forage sheet paintover")
FORAGE_ADOPT = _local(
    "ground_forage", "adopt", "Adopt an auditioned forage sheet", ViewArchetype.IMAGE
)
PLANTS_GENERATE = _image("ground_plants", "generate", "Standing plant sheet paintover")
PLANTS_ADOPT = _local(
    "ground_plants", "adopt", "Adopt an auditioned plant sheet", ViewArchetype.IMAGE
)
PLANTS_VALIDATE = _local(
    "ground_plants", "validate", "Plant lattice and isolation gate", ViewArchetype.VALIDATE
)
PLANTS_LOOK_GENERATE = _image(
    "ground_plants_look", "generate", "Season look paintover of the plant sheet"
)
PLANTS_LOOK_VALIDATE = _local(
    "ground_plants_look", "validate", "Plant look lattice gate", ViewArchetype.VALIDATE
)
FORAGE_VALIDATE = _local(
    "ground_forage", "validate", "Forage lattice and isolation gate", ViewArchetype.VALIDATE
)
ICONS_GENERATE = _image("item_icons", "generate", "Inventory icon sheet paintover")
ICONS_ADOPT = _local("item_icons", "adopt", "Adopt an auditioned icon sheet", ViewArchetype.IMAGE)
ICONS_VALIDATE = _local(
    "item_icons", "validate", "Icon lattice and isolation gate", ViewArchetype.VALIDATE
)
WATER_GENERATE = _image("ground_water", "generate", "Water material plate")
WATER_CANONICALIZE = _local(
    "ground_water", "canonicalize", "Water gate and 2-axis mirror", ViewArchetype.VALIDATE
)
FIRE_GENERATE = _image("fx_strip", "generate", "Flame cycle paintover")
FIRE_VALIDATE = _local(
    "fx_strip", "validate", "Lattice, coverage and cycle gate", ViewArchetype.VALIDATE
)
DUST_GENERATE = _image("fx_dust", "generate", "Impact puff sheet")
DUST_VALIDATE = _local("fx_dust", "validate", "Puff separability gate", ViewArchetype.VALIDATE)
MUSIC_GENERATE = _music("music_track", "generate", "Music loop")
MUSIC_ADOPT = _local("music_track", "adopt", "Adopt an auditioned take", ViewArchetype.MUSIC)
MUSIC_VALIDATE = _local(
    "music_track", "validate", "Loop length and level gate", ViewArchetype.VALIDATE
)
WEATHER_DROPS_GENERATE = _image("weather_drops", "generate", "Rain streak and drop sheet")
WEATHER_COVER_GENERATE = _image("weather_cover", "generate", "Weather cover plate")
WEATHER_COVER_CANONICALIZE = _local(
    "weather_cover", "canonicalize", "Cover gate and 2-axis mirror", ViewArchetype.VALIDATE
)
WEATHER_DROPS_VALIDATE = _local(
    "weather_drops", "validate", "Two-cell separability gate", ViewArchetype.VALIDATE
)
WEATHER_ICE_GENERATE = _image("weather_ice", "generate", "Frozen water plate")
WEATHER_ICE_ADOPT = _local(
    "weather_ice", "adopt", "Adopt an auditioned ice plate", ViewArchetype.IMAGE
)
WEATHER_ICE_CANONICALIZE = _local(
    "weather_ice", "canonicalize", "Ice gate and 2-axis mirror", ViewArchetype.VALIDATE
)
WEATHER_GROUND_GENERATE = _image("weather_ground", "generate", "Rain splash sheet")
WEATHER_GROUND_VALIDATE = _local(
    "weather_ground", "validate", "Splash separability gate", ViewArchetype.VALIDATE
)
WEATHER_STRIKE_GENERATE = _image("weather_strike", "generate", "Lightning bolt sheet")
WEATHER_STRIKE_VALIDATE = _local(
    "weather_strike", "validate", "Bolt separability and tallness gate", ViewArchetype.VALIDATE
)
WEATHER_SOUND_GENERATE = _sound("weather_sound", "generate", "Weather sound clip")
WEATHER_SOUND_VALIDATE = _local(
    "weather_sound", "validate", "Clip length and level gate", ViewArchetype.VALIDATE
)
SOUND_GENERATE = _sound("sound_effect", "generate", "Interaction sound clip")
SOUND_ADOPT = _local("sound_effect", "adopt", "Adopt an auditioned clip", ViewArchetype.SOUND)
SOUND_VALIDATE = _local(
    "sound_effect", "validate", "Clip length and level gate", ViewArchetype.VALIDATE
)
REVIEW_SHEET = _local("family_review", "sheet", "Family contact sheet", ViewArchetype.REVIEW)
REVIEW_JUDGE = _structured("family_review", "judge", "Family semantic review")
WORLD_LAYOUT = _local("world_layout", "generate", "Algorithmic world layout")
PACKAGE_MANIFEST = _local("package", "manifest", "Runtime manifest", ViewArchetype.PACKAGE)

#: Every declared type, in declaration order.
OBLIQUE_SURVIVAL_NODE_TYPES: Final[tuple[NodeType, ...]] = (
    SOURCE_LOCK,
    TEMPLATES_DRAW,
    ACTOR_CONCEPT,
    MOTION_GENERATE,
    MOTION_VALIDATE,
    REBASE_PLATE,
    REBASE_JUDGE,
    REBASE_VERIFY_PLATE,
    REBASE_VERIFY,
    PROP_GENERATE,
    PROP_VALIDATE,
    PROP_SHEET_GENERATE,
    PROP_SHEET_VALIDATE,
    SEASON_LOOK_GENERATE,
    SEASON_LOOK_VALIDATE,
    PROP_ANCHOR,
    ITEM_GENERATE,
    ITEM_VALIDATE,
    GROUND_GENERATE,
    GROUND_ADOPT,
    GROUND_CANONICALIZE,
    DECAL_GENERATE,
    DECAL_VALIDATE,
    MACRO_GENERATE,
    MACRO_CANONICALIZE,
    ROAD_GENERATE,
    ROAD_CANONICALIZE,
    CLUTTER_GENERATE,
    CLUTTER_ADOPT,
    CLUTTER_VALIDATE,
    FORAGE_GENERATE,
    FORAGE_ADOPT,
    FORAGE_VALIDATE,
    PLANTS_GENERATE,
    PLANTS_ADOPT,
    PLANTS_VALIDATE,
    PLANTS_LOOK_GENERATE,
    PLANTS_LOOK_VALIDATE,
    ICONS_GENERATE,
    ICONS_ADOPT,
    ICONS_VALIDATE,
    WATER_GENERATE,
    WATER_CANONICALIZE,
    FIRE_GENERATE,
    FIRE_VALIDATE,
    DUST_GENERATE,
    DUST_VALIDATE,
    MUSIC_GENERATE,
    MUSIC_ADOPT,
    MUSIC_VALIDATE,
    WEATHER_DROPS_GENERATE,
    WEATHER_DROPS_VALIDATE,
    WEATHER_COVER_GENERATE,
    WEATHER_COVER_CANONICALIZE,
    WEATHER_ICE_GENERATE,
    WEATHER_ICE_ADOPT,
    WEATHER_ICE_CANONICALIZE,
    WEATHER_GROUND_GENERATE,
    WEATHER_GROUND_VALIDATE,
    WEATHER_STRIKE_GENERATE,
    WEATHER_STRIKE_VALIDATE,
    WEATHER_SOUND_GENERATE,
    WEATHER_SOUND_VALIDATE,
    SOUND_GENERATE,
    SOUND_ADOPT,
    SOUND_VALIDATE,
    REVIEW_SHEET,
    REVIEW_JUDGE,
    WORLD_LAYOUT,
    PACKAGE_MANIFEST,
)


def survival_type_index() -> dict[str, NodeType]:
    """Every node type the plan may contain, keyed by its type id."""

    return {node_type.type_id: node_type for node_type in OBLIQUE_SURVIVAL_NODE_TYPES}


__all__ = [
    "ACTOR_CONCEPT",
    "CLUTTER_ADOPT",
    "CLUTTER_GENERATE",
    "CLUTTER_VALIDATE",
    "CONTRACT_VERSION_PREFIX",
    "DECAL_GENERATE",
    "DECAL_VALIDATE",
    "DUST_GENERATE",
    "DUST_VALIDATE",
    "FIRE_GENERATE",
    "FIRE_VALIDATE",
    "FORAGE_ADOPT",
    "FORAGE_GENERATE",
    "FORAGE_VALIDATE",
    "GROUND_ADOPT",
    "GROUND_CANONICALIZE",
    "GROUND_GENERATE",
    "ICONS_ADOPT",
    "ICONS_GENERATE",
    "ICONS_VALIDATE",
    "IMAGE_FEATURES",
    "ITEM_GENERATE",
    "ITEM_VALIDATE",
    "MACRO_CANONICALIZE",
    "MACRO_GENERATE",
    "MOTION_GENERATE",
    "MOTION_VALIDATE",
    "MUSIC_ADOPT",
    "MUSIC_FEATURES",
    "MUSIC_GENERATE",
    "MUSIC_VALIDATE",
    "OBLIQUE_SURVIVAL_NODE_TYPES",
    "PACKAGE_MANIFEST",
    "PLANTS_ADOPT",
    "PLANTS_GENERATE",
    "PLANTS_LOOK_GENERATE",
    "PLANTS_LOOK_VALIDATE",
    "PLANTS_VALIDATE",
    "PRESENTATION_PROFILE",
    "PROP_ANCHOR",
    "PROP_GENERATE",
    "PROP_SHEET_GENERATE",
    "PROP_SHEET_VALIDATE",
    "PROP_VALIDATE",
    "RECIPE",
    "REBASE_JUDGE",
    "REBASE_PLATE",
    "REBASE_VERIFY",
    "REBASE_VERIFY_PLATE",
    "REVIEW_FAMILIES",
    "REVIEW_JUDGE",
    "REVIEW_SHEET",
    "ROAD_CANONICALIZE",
    "ROAD_GENERATE",
    "SCOPES",
    "SCOPE_RANK",
    "SEASON_LOOK_GENERATE",
    "SEASON_LOOK_VALIDATE",
    "SOUND_ADOPT",
    "SOUND_DURATION_TOLERANCE_SECONDS",
    "SOUND_FEATURES",
    "SOUND_GENERATE",
    "SOUND_VALIDATE",
    "SOURCE_LOCK",
    "STRIKE_CELL_KINDS",
    "STRUCTURED_FEATURES",
    "TEMPLATES_DRAW",
    "TOOL_LOOP_FEATURES",
    "TYPE_PREFIX",
    "WATER_CANONICALIZE",
    "WATER_GENERATE",
    "WEATHER_COVER_CANONICALIZE",
    "WEATHER_COVER_GENERATE",
    "WEATHER_DROPS_GENERATE",
    "WEATHER_DROPS_VALIDATE",
    "WEATHER_GROUND_GENERATE",
    "WEATHER_GROUND_VALIDATE",
    "WEATHER_ICE_ADOPT",
    "WEATHER_ICE_CANONICALIZE",
    "WEATHER_ICE_GENERATE",
    "WEATHER_SOUND_GENERATE",
    "WEATHER_SOUND_VALIDATE",
    "WEATHER_STRIKE_GENERATE",
    "WEATHER_STRIKE_VALIDATE",
    "WORLD_LAYOUT",
    "ObliqueSurvivalOperationKind",
    "survival_type_index",
]
