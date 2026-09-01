"""The infinite-runner node types: one declaration per kind of work.

``type_id`` values are persisted taxonomy paths (docs/spec/asset-taxonomy.md):
``2d/sideview/runner/<module>.<step>``. The census is deliberately about a
third of the platformer's: authored segments need no terrain designer, one
avatar needs no roster, and the only admission gates are the two motion-rebase
judges - every other review stays an operator decision.
"""

from __future__ import annotations

from gnode import NodePolicy, NodeType, ViewArchetype

_P = "2d/sideview/runner"
_PROVIDER = NodePolicy(max_attempts=6)

IMAGE_FEATURES = ("transparent_background", "reference_images")
STRUCTURED_FEATURES = ("structured_output", "image_input")
MUSIC_FEATURES = ("instrumental_loop",)

#: Payload kinds (persisted vocabulary).
PACKAGE_KIND = "runner-package-v1"
REFERENCE_KIND = "runner-reference-v1"
GROUND_RAW_KIND = "ground-atlas-raw-v1"
GROUND_ATLAS_KIND = "ground-atlas-canonical-v1"
GROUND_VALIDATION_KIND = "ground-atlas-validation-v1"
LAYER_RAW_KIND = "track-layer-raw-v1"
LAYER_LOOP_KIND = "track-layer-loop-v1"
LAYER_LOOP_EDIT_KIND = "track-layer-loop-edit-v1"
LAYER_LOOP_REPORT_KIND = "track-layer-loop-report-v1"
LAYER_VALIDATION_KIND = "track-layer-validation-v1"
AVATAR_CONCEPT_KIND = "avatar-concept-v1"
MOTION_RAW_KIND = "avatar-motion-raw-v1"
MOTION_ATLAS_KIND = "avatar-motion-atlas-v1"
MOTION_VALIDATION_KIND = "avatar-motion-validation-v1"
REBASE_PLATE_KIND = "rebase-plate-v1"
REBASE_READING_KIND = "rebase-reading-v1"
REBASE_VERIFICATION_KIND = "rebase-verification-v1"
CATALOG_RAW_KIND = "catalog-asset-raw-v1"
CATALOG_ASSET_KIND = "catalog-asset-v1"
CATALOG_VALIDATION_KIND = "catalog-asset-validation-v1"
TRACK_KIND = "runner-track-runtime-track-v1"
SOUNDTRACK_RAW_KIND = "soundtrack-track-raw-v1"
SOUNDTRACK_TRACK_KIND = "soundtrack-track-v1"
SOUNDTRACK_VALIDATION_KIND = "soundtrack-validation-v1"
ATTEMPT_LEDGER_KIND = "attempt-ledger-v1"
MANIFEST_KIND = "sideview-runner-runtime-v1"

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
    contract_version="runner-ground-atlas-v1",
)

TRACK_GROUND_VALIDATE = NodeType(
    type_id=f"{_P}/track_ground.validate",
    title="Ground atlas admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="runner-ground-validate-v1",
)

LAYER_GENERATE = NodeType(
    type_id=f"{_P}/layer.generate",
    title="Track layer painting",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="runner-layer-v1",
)

LAYER_LOOP_CONSTRUCT = NodeType(
    type_id=f"{_P}/layer.loop_construct",
    title="Layer loop construction",
    archetype=ViewArchetype.TRANSFORM,
    operation="local",
    contract_version="runner-layer-loop-v1",
)

LAYER_LOOP_PAINT = NodeType(
    type_id=f"{_P}/layer.loop_paint",
    title="Layer loop repaint",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="runner-layer-loop-v1",
)

LAYER_VALIDATE = NodeType(
    type_id=f"{_P}/layer.validate",
    title="Layer admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="runner-layer-validate-v1",
)

AVATAR_CONCEPT_GENERATE = NodeType(
    type_id=f"{_P}/avatar_concept.generate",
    title="Avatar identity concept",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="runner-avatar-concept-v1",
)

AVATAR_MOTION_GENERATE = NodeType(
    type_id=f"{_P}/avatar_motion.generate",
    title="Avatar motion atlas",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="runner-avatar-motion-v1",
)

AVATAR_MOTION_VALIDATE = NodeType(
    type_id=f"{_P}/avatar_motion.validate",
    title="Avatar motion admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="runner-avatar-motion-validate-v1",
)

MOTION_REBASE_JUDGE = NodeType(
    type_id=f"{_P}/motion_rebase.judge",
    title="Scale rebase reading",
    archetype=ViewArchetype.JUDGE,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=NodePolicy(max_attempts=6, gates=("rebase-admission",)),
    contract_version="runner-motion-rebase-v1",
)

MOTION_REBASE_VERIFY = NodeType(
    type_id=f"{_P}/motion_rebase.verify",
    title="Scale rebase residual",
    archetype=ViewArchetype.JUDGE,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=NodePolicy(max_attempts=6, gates=("rebase-admission",)),
    contract_version="runner-motion-rebase-verify-v1",
)

CATALOG_ASSET_GENERATE = NodeType(
    type_id=f"{_P}/catalog_asset.generate",
    title="Catalog asset",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="runner-catalog-asset-v1",
)

CATALOG_ASSET_VALIDATE = NodeType(
    type_id=f"{_P}/catalog_asset.validate",
    title="Catalog asset admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="runner-catalog-asset-validate-v1",
)

SOUNDTRACK_GENERATE = NodeType(
    type_id=f"{_P}/soundtrack.generate",
    title="Soundtrack track",
    archetype=ViewArchetype.MUSIC,
    operation="music_generation",
    features=MUSIC_FEATURES,
    policy=_PROVIDER,
    contract_version="runner-soundtrack-track-v1",
)

SOUNDTRACK_VALIDATE = NodeType(
    type_id=f"{_P}/soundtrack.validate",
    title="Track admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="runner-soundtrack-validate-v1",
)

MANIFEST_ASSEMBLE = NodeType(
    type_id=f"{_P}/manifest.assemble",
    title="Runtime manifest assembly",
    archetype=ViewArchetype.PACKAGE,
    operation="local",
    contract_version="runner-manifest-assemble-v1",
)

RUNNER_NODE_TYPES: tuple[NodeType, ...] = (
    PACKAGE_RESOLVE,
    TRACK_GROUND_GENERATE,
    TRACK_GROUND_VALIDATE,
    LAYER_GENERATE,
    LAYER_LOOP_CONSTRUCT,
    LAYER_LOOP_PAINT,
    LAYER_VALIDATE,
    AVATAR_CONCEPT_GENERATE,
    AVATAR_MOTION_GENERATE,
    AVATAR_MOTION_VALIDATE,
    MOTION_REBASE_JUDGE,
    MOTION_REBASE_VERIFY,
    CATALOG_ASSET_GENERATE,
    CATALOG_ASSET_VALIDATE,
    SOUNDTRACK_GENERATE,
    SOUNDTRACK_VALIDATE,
    MANIFEST_ASSEMBLE,
)


def runner_type_index() -> dict[str, NodeType]:
    return {node_type.type_id: node_type for node_type in RUNNER_NODE_TYPES}


__all__ = [
    "ATTEMPT_LEDGER_KIND",
    "AVATAR_CONCEPT_GENERATE",
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
    "STRUCTURED_FEATURES",
    "TRACK_GROUND_GENERATE",
    "TRACK_GROUND_VALIDATE",
    "TRACK_KIND",
]
