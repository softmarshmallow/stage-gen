"""The infinite-runner node types: one declaration per kind of work.

``type_id`` values are persisted taxonomy paths (docs/spec/asset-taxonomy.md):
``2d/sideview/runner/<module>.<step>``. The census is deliberately about a
third of the platformer's: authored segments need no terrain designer, one
avatar needs no roster, and the only admission gates are the two motion-rebase
judges - every other review stays an operator decision.
"""

from __future__ import annotations

from gnode import NodePolicy, NodeType, ViewArchetype
from stage_gen.components.game_fx.nodes import (
    FX_CUT_IN_NODE_TYPES,
    FX_MANIFEST_BLOCK_VERSION,
    FX_SPRITE_NODE_TYPES,
)
from stage_gen.components.game_soundtrack.nodes import (
    SOUNDTRACK_TRACK_KIND,
    SOUNDTRACK_VALIDATION_KIND,
    soundtrack_node_types,
)
from stage_gen.components.sideview_actor.motion_rebase_nodes import (
    REBASE_PLATE_KIND,
    REBASE_READING_KIND,
    REBASE_VERIFICATION_KIND,
    motion_rebase_node_types,
)
from stage_gen.components.sideview_layers.nodes import (
    LAYER_LOOP_EDIT_KIND,
    LAYER_LOOP_KIND,
    LAYER_LOOP_REPORT_KIND,
    LAYER_RAW_KIND,
    LAYER_VALIDATION_KIND,
    layer_node_types,
)

_P = "2d/sideview/runner"
_PROVIDER = NodePolicy(max_attempts=6)

IMAGE_FEATURES = ("transparent_background", "reference_images")
IMAGE_EDIT_FEATURES = (*IMAGE_FEATURES, "masked_edit")
STRUCTURED_FEATURES = ("structured_output", "image_input")
MUSIC_FEATURES = ("instrumental_loop",)
SOUND_EFFECT_FEATURES = ("exact_duration",)
#: A speech route that reads bracketed delivery annotations and takes a stability mode.
SPEECH_FEATURES = ("audio_tags", "stability")

#: Payload kinds (persisted vocabulary).
PACKAGE_KIND = "runner-package-v1"
REFERENCE_KIND = "runner-reference-v1"
GROUND_RAW_KIND = "ground-atlas-raw-v1"
GROUND_ATLAS_KIND = "ground-atlas-canonical-v1"
GROUND_VALIDATION_KIND = "ground-atlas-validation-v1"
STRUCTURAL_GROUND_GUIDE_KIND = "runner-structural-ground-guide-v1"
STRUCTURAL_GROUND_GUIDE_VALIDATION_KIND = "runner-structural-ground-guide-validation-v1"
STRUCTURAL_GROUND_RAW_KIND = "runner-structural-ground-raw-v1"
STRUCTURAL_GROUND_SEAM_BRIDGE_KIND = "runner-structural-ground-seam-bridge-v1"
STRUCTURAL_GROUND_SEAM_BRIDGE_VALIDATION_KIND = "runner-structural-ground-seam-bridge-validation-v2"
STRUCTURAL_GROUND_KIND = "runner-structural-ground-v1"
STRUCTURAL_GROUND_VALIDATION_KIND = "runner-structural-ground-validation-v3"
AVATAR_CONCEPT_KIND = "avatar-concept-v1"
BOSS_CONCEPT_KIND = "boss-concept-v1"
MOTION_RAW_KIND = "avatar-motion-raw-v1"
MOTION_ATLAS_KIND = "avatar-motion-atlas-v1"
MOTION_VALIDATION_KIND = "avatar-motion-validation-v2"
CATALOG_RAW_KIND = "catalog-asset-raw-v1"
CATALOG_ASSET_KIND = "catalog-asset-v1"
CATALOG_VALIDATION_KIND = "catalog-asset-validation-v3"
TRACK_KIND = "runner-track-runtime-track-v1"
SOUNDTRACK_RAW_KIND = "soundtrack-track-raw-v1"
SOUND_EFFECT_CLIP_KIND = "sound-effect-clip-v1"
SOUND_EFFECT_VALIDATION_KIND = "sound-effect-validation-v1"
SPEECH_CLIP_KIND = "speech-line-v1"
SPEECH_VALIDATION_KIND = "speech-validation-v1"
ATTEMPT_LEDGER_KIND = "attempt-ledger-v2"
#: Moves on structural change only (C-R3); the web parser pins kind and version together.
MANIFEST_SCHEMA_VERSION = 13
MANIFEST_KIND = f"sideview-runner-runtime-v{MANIFEST_SCHEMA_VERSION}"
#: The manifest's blocks, each at its own version, in the order the document publishes
#: them. A block whose shape moves bumps its version here and in the parser; the ``fx``
#: block is the family's and is declared beside the function that builds it.
RUNNER_MANIFEST_BLOCK_VERSIONS: dict[str, str] = {
    "presentation": "runner-presentation-block-v1",
    "camera": "runner-camera-block-v1",
    "scale": "runner-scale-block-v1",
    "gameplay": "runner-gameplay-block-v1",
    "ground": "runner-ground-block-v1",
    "layers": "runner-layers-block-v1",
    "segments": "runner-segments-block-v1",
    "avatar": "runner-avatar-block-v1",
    "props": "runner-props-block-v1",
    "items": "runner-items-block-v1",
    "bosses": "runner-bosses-block-v1",
    "projectiles": "runner-projectiles-block-v1",
    "audio": "runner-audio-block-v1",
    "soundtrack": "runner-soundtrack-block-v1",
    "fx": FX_MANIFEST_BLOCK_VERSION,
}

PACKAGE_RESOLVE = NodeType(
    type_id=f"{_P}/package.resolve",
    title="Package capture",
    archetype=ViewArchetype.SOURCE,
    operation="local",
    contract_version="runner-package-resolve-v1",
)

TRACK_GROUND_GENERATE = NodeType(
    type_id=f"{_P}/track_ground.generate",
    title="Ground atlas paintover",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="runner-ground-atlas-v3",
)

TRACK_GROUND_VALIDATE = NodeType(
    type_id=f"{_P}/track_ground.validate",
    title="Ground atlas admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="runner-ground-validate-v2",
)

TRACK_STRUCTURAL_GROUND_GUIDE = NodeType(
    type_id=f"{_P}/structural_ground.guide",
    title="Structural ground guide",
    archetype=ViewArchetype.TRANSFORM,
    operation="local",
    contract_version="runner-structural-ground-guide-v1",
)

TRACK_STRUCTURAL_GROUND_GENERATE = NodeType(
    type_id=f"{_P}/structural_ground.generate",
    title="Structural ground painting",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="runner-structural-ground-generate-v3",
)

TRACK_STRUCTURAL_GROUND_SEAM_BRIDGE = NodeType(
    type_id=f"{_P}/structural_ground.seam_bridge",
    title="Shared structural ground seam bridge",
    archetype=ViewArchetype.TRANSFORM,
    operation="local",
    contract_version="runner-structural-ground-seam-bridge-v2",
)

TRACK_STRUCTURAL_GROUND_VALIDATE = NodeType(
    type_id=f"{_P}/structural_ground.validate",
    title="Structural ground admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="runner-structural-ground-validate-v3",
)

#: The parallax-layer family lives in `sideview_layers`; this recipe shipped it under its
#: own type ids and contracts, which stay as the cache identity so no layer is paid for
#: twice. Admission is local and converged on the family's.
_LAYERS = layer_node_types(
    identity_prefix=f"{_P}/layer",
    generate_version="runner-layer-v3",
    loop_paint_version="runner-layer-loop-v4",
    loop_construct_version="runner-layer-loop-v1",
)
LAYER_GENERATE = _LAYERS.generate
LAYER_LOOP_PAINT = _LAYERS.loop_paint
LAYER_LOOP_CONSTRUCT = _LAYERS.loop_construct
LAYER_VALIDATE = _LAYERS.validate

AVATAR_CONCEPT_GENERATE = NodeType(
    type_id=f"{_P}/avatar_concept.generate",
    title="Avatar identity concept",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="runner-avatar-concept-v4",
)

AVATAR_MOTION_GENERATE = NodeType(
    type_id=f"{_P}/avatar_motion.generate",
    title="Avatar motion atlas",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="runner-avatar-motion-v4",
)

AVATAR_MOTION_VALIDATE = NodeType(
    type_id=f"{_P}/avatar_motion.validate",
    title="Avatar motion admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="runner-avatar-motion-validate-v4",
)

#: The boss's own chain. Separate node types rather than a parameter on the
#: avatar's, because the type is what the plan and the taxonomy read: a reader
#: scanning a graph should see that a boss was drawn, not an "avatar" node with
#: an actor flag. The handlers behind them are the same ones.
BOSS_CONCEPT_GENERATE = NodeType(
    type_id=f"{_P}/boss_concept.generate",
    title="Boss identity concept",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="runner-boss-concept-v1",
)

BOSS_MOTION_GENERATE = NodeType(
    type_id=f"{_P}/boss_motion.generate",
    title="Boss motion atlas",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="runner-boss-motion-v1",
)

BOSS_MOTION_VALIDATE = NodeType(
    type_id=f"{_P}/boss_motion.validate",
    title="Boss motion admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="runner-boss-motion-validate-v1",
)

#: The motion-rebase family lives in `sideview_actor`; this recipe shipped it under its own
#: type ids and contracts, which stay as the cache identity so no reading is paid for twice.
_MOTION_REBASE = motion_rebase_node_types(
    identity_prefix=_P,
    judge_version="runner-motion-rebase-v3",
    verify_version="runner-motion-rebase-verify-v3",
)
MOTION_REBASE_JUDGE = _MOTION_REBASE.judge
MOTION_REBASE_VERIFY = _MOTION_REBASE.verify

CATALOG_ASSET_GENERATE = NodeType(
    type_id=f"{_P}/catalog_asset.generate",
    title="Catalog asset",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="runner-catalog-asset-v3",
)

CATALOG_ASSET_VALIDATE = NodeType(
    type_id=f"{_P}/catalog_asset.validate",
    title="Catalog asset admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="runner-catalog-asset-validate-v3",
)

#: The soundtrack family lives in its component; this recipe shipped its generation under
#: its own type id and contract, which stay as the cache identity so no track is paid for
#: twice. Admission is local and converged on the component's.
_SOUNDTRACK = soundtrack_node_types(identity_prefix=_P, track_version="runner-soundtrack-track-v3")
SOUNDTRACK_GENERATE = _SOUNDTRACK.generate
SOUNDTRACK_VALIDATE = _SOUNDTRACK.validate

SOUND_EFFECT_GENERATE = NodeType(
    type_id=f"{_P}/sound_effect.generate",
    title="Sound effect clip",
    archetype=ViewArchetype.SOUND,
    operation="sound_effect_generation",
    features=SOUND_EFFECT_FEATURES,
    policy=_PROVIDER,
    contract_version="runner-sound-effect-clip-v1",
)

SOUND_EFFECT_VALIDATE = NodeType(
    type_id=f"{_P}/sound_effect.validate",
    title="Clip admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="runner-sound-effect-validate-v1",
)

SPEECH_GENERATE = NodeType(
    type_id=f"{_P}/speech.generate",
    title="Spoken line",
    archetype=ViewArchetype.SOUND,
    operation="speech_generation",
    features=SPEECH_FEATURES,
    policy=_PROVIDER,
    contract_version="runner-speech-line-v1",
)

SPEECH_VALIDATE = NodeType(
    type_id=f"{_P}/speech.validate",
    title="Line admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="runner-speech-validate-v1",
)

AUDIO_REPUBLISH = NodeType(
    type_id=f"{_P}/audio.republish",
    title="Pinned take",
    archetype=ViewArchetype.SOURCE,
    operation="local",
    contract_version="runner-audio-republish-v1",
)

MANIFEST_ASSEMBLE = NodeType(
    type_id=f"{_P}/manifest.assemble",
    title="Runtime manifest assembly",
    archetype=ViewArchetype.PACKAGE,
    operation="local",
    # v10: every cut-in portrait publishes the placement the tool-loop agent
    # judged inside the frame, so the runtime document moved to v9 with it.
    contract_version="runner-manifest-assemble-v12",
)

RUNNER_NODE_TYPES: tuple[NodeType, ...] = (
    PACKAGE_RESOLVE,
    TRACK_GROUND_GENERATE,
    TRACK_GROUND_VALIDATE,
    TRACK_STRUCTURAL_GROUND_GUIDE,
    TRACK_STRUCTURAL_GROUND_GENERATE,
    TRACK_STRUCTURAL_GROUND_SEAM_BRIDGE,
    TRACK_STRUCTURAL_GROUND_VALIDATE,
    LAYER_GENERATE,
    LAYER_LOOP_CONSTRUCT,
    LAYER_LOOP_PAINT,
    LAYER_VALIDATE,
    AVATAR_CONCEPT_GENERATE,
    AVATAR_MOTION_GENERATE,
    AVATAR_MOTION_VALIDATE,
    BOSS_CONCEPT_GENERATE,
    BOSS_MOTION_GENERATE,
    BOSS_MOTION_VALIDATE,
    MOTION_REBASE_JUDGE,
    MOTION_REBASE_VERIFY,
    CATALOG_ASSET_GENERATE,
    CATALOG_ASSET_VALIDATE,
    SOUNDTRACK_GENERATE,
    SOUNDTRACK_VALIDATE,
    SOUND_EFFECT_GENERATE,
    SOUND_EFFECT_VALIDATE,
    SPEECH_GENERATE,
    SPEECH_VALIDATE,
    AUDIO_REPUBLISH,
    *FX_CUT_IN_NODE_TYPES,
    *FX_SPRITE_NODE_TYPES,
    MANIFEST_ASSEMBLE,
)


def runner_type_index() -> dict[str, NodeType]:
    return {node_type.type_id: node_type for node_type in RUNNER_NODE_TYPES}


__all__ = [
    "ATTEMPT_LEDGER_KIND",
    "AUDIO_REPUBLISH",
    "AVATAR_CONCEPT_GENERATE",
    "BOSS_CONCEPT_GENERATE",
    "BOSS_MOTION_GENERATE",
    "BOSS_MOTION_VALIDATE",
    "BOSS_CONCEPT_KIND",
    "AVATAR_CONCEPT_KIND",
    "AVATAR_MOTION_GENERATE",
    "AVATAR_MOTION_VALIDATE",
    "CATALOG_ASSET_GENERATE",
    "CATALOG_ASSET_KIND",
    "CATALOG_ASSET_VALIDATE",
    "CATALOG_RAW_KIND",
    "CATALOG_VALIDATION_KIND",
    "GROUND_ATLAS_KIND",
    "GROUND_RAW_KIND",
    "GROUND_VALIDATION_KIND",
    "IMAGE_EDIT_FEATURES",
    "IMAGE_FEATURES",
    "LAYER_GENERATE",
    "LAYER_LOOP_CONSTRUCT",
    "LAYER_LOOP_EDIT_KIND",
    "LAYER_LOOP_KIND",
    "LAYER_LOOP_PAINT",
    "LAYER_LOOP_REPORT_KIND",
    "LAYER_RAW_KIND",
    "LAYER_VALIDATE",
    "LAYER_VALIDATION_KIND",
    "MANIFEST_ASSEMBLE",
    "MANIFEST_KIND",
    "MANIFEST_SCHEMA_VERSION",
    "RUNNER_MANIFEST_BLOCK_VERSIONS",
    "MOTION_ATLAS_KIND",
    "MOTION_RAW_KIND",
    "MOTION_REBASE_JUDGE",
    "MOTION_REBASE_VERIFY",
    "MOTION_VALIDATION_KIND",
    "MUSIC_FEATURES",
    "PACKAGE_KIND",
    "PACKAGE_RESOLVE",
    "REBASE_PLATE_KIND",
    "REBASE_READING_KIND",
    "REBASE_VERIFICATION_KIND",
    "REFERENCE_KIND",
    "RUNNER_NODE_TYPES",
    "SOUNDTRACK_GENERATE",
    "SOUNDTRACK_RAW_KIND",
    "SOUNDTRACK_TRACK_KIND",
    "SOUNDTRACK_VALIDATE",
    "SOUNDTRACK_VALIDATION_KIND",
    "SPEECH_CLIP_KIND",
    "SPEECH_FEATURES",
    "SPEECH_GENERATE",
    "SPEECH_VALIDATE",
    "SPEECH_VALIDATION_KIND",
    "STRUCTURED_FEATURES",
    "STRUCTURAL_GROUND_GUIDE_KIND",
    "STRUCTURAL_GROUND_GUIDE_VALIDATION_KIND",
    "STRUCTURAL_GROUND_KIND",
    "STRUCTURAL_GROUND_RAW_KIND",
    "STRUCTURAL_GROUND_SEAM_BRIDGE_KIND",
    "STRUCTURAL_GROUND_SEAM_BRIDGE_VALIDATION_KIND",
    "STRUCTURAL_GROUND_VALIDATION_KIND",
    "TRACK_GROUND_GENERATE",
    "TRACK_GROUND_VALIDATE",
    "TRACK_STRUCTURAL_GROUND_GENERATE",
    "TRACK_STRUCTURAL_GROUND_GUIDE",
    "TRACK_STRUCTURAL_GROUND_SEAM_BRIDGE",
    "TRACK_STRUCTURAL_GROUND_VALIDATE",
    "TRACK_KIND",
]
