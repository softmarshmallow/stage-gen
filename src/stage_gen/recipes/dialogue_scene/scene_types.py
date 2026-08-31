"""The dialogue-scene node types: one declaration per kind of work.

Every node in this recipe's graph instantiates one of these declarations. The
type carries what used to live in three unrelated places — the dispatch branch,
the per-family contract version, and the viewer's guess at a display kind — and
its policy states the attempt budgets as data. Publishing an authored plate is
its own type rather than a flag on a generator, because handing a node bytes the
author supplied is a different kind of work from asking a provider for them.

``type_id`` values are persisted taxonomy paths (docs/spec/asset-taxonomy.md):
``2d/frontview/vn/<module>.<step>``.
"""

from __future__ import annotations

from gnode import NodePolicy, NodeType, ViewArchetype

_PROVIDER_POLICY = NodePolicy(max_attempts=6)

#: Payload kinds this recipe's ports carry (persisted vocabulary).
REQUEST_KIND = "dialogue-request-v1"
PROFILE_KIND = "character-profile-v1"
STYLE_ANCHOR_KIND = "style-anchor-v1"
CONCEPT_KIND = "portrait-concept-v1"
PLAN_KIND = "dialogue-plan-v1"
BACKDROP_KIND = "dialogue-backdrop-v1"
PROVIDER_RAW_KIND = "provider-raw-image-v1"
EXPRESSION_SOURCE_KIND = "expression-source-v1"
EXPRESSION_SPRITE_KIND = "expression-sprite-v1"
MATTE_RAW_KIND = "matte-raw-v1"
ATTEMPT_LEDGER_KIND = "attempt-ledger-v1"
MERGED_ATTEMPTS_KIND = "attempt-ledger-merged-v1"
BUNDLE_KIND = "dialogue-bundle-v1"
SCENARIO_KIND = "scenario-program-v1"
SCENARIO_ADMISSION_KIND = "scenario-admission-v1"

SCENARIO_ADMIT = NodeType(
    type_id="2d/frontview/vn/scenario.admit",
    title="Scenario admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="dialogue-scenario-admit-v1",
)

REQUEST_RESOLVE = NodeType(
    type_id="2d/frontview/vn/request.resolve",
    title="Dialogue request",
    archetype=ViewArchetype.SOURCE,
    operation="local",
    # v2: the published document is exactly its canonical bytes, with no
    # trailing newline, so its file digest is the digest the plan binds.
    contract_version="dialogue-request-resolve-v2",
)

PROFILE_RESOLVE = NodeType(
    type_id="2d/frontview/vn/character_profile.resolve",
    title="Character profile",
    archetype=ViewArchetype.SOURCE,
    operation="local",
    contract_version="dialogue-profile-resolve-v1",
)

STYLE_SELECT = NodeType(
    type_id="2d/frontview/vn/style_anchor.select",
    title="Style anchor selection",
    archetype=ViewArchetype.STRUCTURED,
    operation="structured_generation",
    features=("structured_output",),
    policy=_PROVIDER_POLICY,
    contract_version="dialogue-style-select-v1",
)

CONCEPT_INGEST = NodeType(
    type_id="2d/frontview/vn/portrait_concept.publish",
    title="Identity plate",
    archetype=ViewArchetype.SOURCE,
    operation="local",
    contract_version="dialogue-concept-publish-v1",
)

PLAN_COMPILE = NodeType(
    type_id="2d/frontview/vn/scene_plan.compile",
    title="Scene plan",
    archetype=ViewArchetype.STRUCTURED,
    operation="structured_generation",
    features=("structured_output",),
    policy=_PROVIDER_POLICY,
    contract_version="dialogue-plan-compile-v1",
)

BACKDROP_GENERATE = NodeType(
    type_id="2d/frontview/vn/backdrop.generate",
    title="Scene backdrop",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=("transparent_background", "reference_images"),
    policy=_PROVIDER_POLICY,
    contract_version="dialogue-backdrop-v1",
)

EXPRESSION_GENERATE = NodeType(
    type_id="2d/frontview/vn/expression.generate",
    title="Neutral expression source",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=("transparent_background", "reference_images"),
    policy=_PROVIDER_POLICY,
    contract_version="dialogue-expression-source-v1",
)

EXPRESSION_DERIVE = NodeType(
    type_id="2d/frontview/vn/expression.derive",
    title="Derived expression",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=("transparent_background", "reference_images"),
    policy=_PROVIDER_POLICY,
    contract_version="dialogue-expression-derive-v1",
)

SPRITE_MATTE = NodeType(
    type_id="2d/frontview/vn/sprite.matte",
    title="Sprite background removal",
    archetype=ViewArchetype.MATTE,
    operation="background_removal",
    features=("alpha_matte",),
    policy=_PROVIDER_POLICY,
    contract_version="dialogue-sprite-matte-v1",
)

SPRITE_CANONICALIZE = NodeType(
    type_id="2d/frontview/vn/sprite.canonicalize",
    title="Sprite canonicalization",
    archetype=ViewArchetype.TRANSFORM,
    operation="local",
    contract_version="dialogue-sprite-canonicalize-v1",
)

BUNDLE_PACKAGE = NodeType(
    type_id="2d/frontview/vn/bundle.package",
    title="Dialogue bundle",
    archetype=ViewArchetype.PACKAGE,
    operation="local",
    contract_version="dialogue-bundle-v1",
)

DIALOGUE_NODE_TYPES: tuple[NodeType, ...] = (
    REQUEST_RESOLVE,
    SCENARIO_ADMIT,
    PROFILE_RESOLVE,
    STYLE_SELECT,
    CONCEPT_INGEST,
    PLAN_COMPILE,
    BACKDROP_GENERATE,
    EXPRESSION_GENERATE,
    EXPRESSION_DERIVE,
    SPRITE_MATTE,
    SPRITE_CANONICALIZE,
    BUNDLE_PACKAGE,
)


def dialogue_type_index() -> dict[str, NodeType]:
    return {node_type.type_id: node_type for node_type in DIALOGUE_NODE_TYPES}


__all__ = [
    "ATTEMPT_LEDGER_KIND",
    "BACKDROP_GENERATE",
    "BACKDROP_KIND",
    "BUNDLE_KIND",
    "BUNDLE_PACKAGE",
    "CONCEPT_INGEST",
    "CONCEPT_KIND",
    "DIALOGUE_NODE_TYPES",
    "EXPRESSION_DERIVE",
    "EXPRESSION_GENERATE",
    "EXPRESSION_SOURCE_KIND",
    "EXPRESSION_SPRITE_KIND",
    "MATTE_RAW_KIND",
    "MERGED_ATTEMPTS_KIND",
    "PLAN_COMPILE",
    "PLAN_KIND",
    "PROFILE_KIND",
    "PROFILE_RESOLVE",
    "PROVIDER_RAW_KIND",
    "REQUEST_KIND",
    "REQUEST_RESOLVE",
    "SCENARIO_ADMISSION_KIND",
    "SCENARIO_ADMIT",
    "SCENARIO_KIND",
    "SPRITE_CANONICALIZE",
    "SPRITE_MATTE",
    "STYLE_ANCHOR_KIND",
    "STYLE_SELECT",
    "dialogue_type_index",
]
