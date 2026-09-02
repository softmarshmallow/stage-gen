"""The universe recipe's node types and persisted payload vocabulary.

``type_id`` values persist a taxonomy path under ``universe/``. The prefix
carries no camera and no genre because half this recipe is modality-free: the
semantic phase proposes, plans, evaluates, reviews and admits a storyworld as
text, and only the gallery phase draws anything.

Every prompt is known at plan time, so every generation node's card carries the
full instruction it will send and the handlers execute the card verbatim.
"""

from __future__ import annotations

from gnode import LOCAL_OPERATION, NodePolicy, NodeType, ViewArchetype

_P = "universe"
_PROVIDER = NodePolicy(max_attempts=6)

#: The semantic phase reads the poster proxy, so its route needs image input.
STRUCTURED_FEATURES = ("structured_output", "image_input")
#: Concept images are opaque compositions at three planned aspect ratios; the
#: route must honour an explicit pixel size rather than a nearest aspect bucket.
IMAGE_FEATURES = ("flexible_size",)

#: Payload kinds (persisted vocabulary).
SOURCE_LOCK_KIND = "universe-source-lock-v1"
POSTER_PROXY_KIND = "universe-poster-proxy-v1"
PROPOSAL_KIND = "universe-proposal-v1"
GALLERY_PLAN_KIND = "universe-gallery-plan-v1"
EVALUATION_KIND = "universe-evaluation-v1"
SEMANTIC_REVIEW_KIND = "universe-semantic-review-v1"
ADMITTED_KIND = "universe-admitted-v1"
ADMISSION_KIND = "universe-admission-v1"
GLOBAL_DIRECTION_KIND = "universe-global-direction-v1"
ENTITY_DIRECTION_KIND = "universe-entity-direction-v1"
#: Lexical checks on compiled direction prose are advisory, never blocking:
#: six blind retries against a hint the model cannot self-correct burn money
#: and change nothing. They are recorded beside the direction instead.
DIRECTION_WARNINGS_KIND = "universe-direction-warnings-v1"
CONCEPT_IMAGE_KIND = "universe-concept-image-v1"
REVIEW_PROXY_KIND = "universe-review-proxy-v1"
IMAGE_REVIEW_KIND = "universe-image-review-v1"
ENTITY_RECORD_KIND = "universe-entity-record-v1"
ENTITY_MARKDOWN_KIND = "universe-entity-markdown-v1"
INVENTORY_KIND = "universe-inventory-v1"
MANIFEST_KIND = "universe-gallery-manifest-v1"
SAMPLE_LEDGER_KIND = "universe-sample-ledger-v1"
ATTEMPT_LEDGER_KIND = "universe-attempt-ledger-v1"

SOURCE_LOCK = NodeType(
    type_id=f"{_P}/source.lock",
    title="Source lock and evidence ledger",
    archetype=ViewArchetype.SOURCE,
    operation=LOCAL_OPERATION,
    contract_version="universe-source-lock-v1",
)

PROPOSE = NodeType(
    type_id=f"{_P}/universe.propose",
    title="Universe proposal",
    archetype=ViewArchetype.STRUCTURED,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=_PROVIDER,
    contract_version="universe-propose-v1",
)

PLAN = NodeType(
    type_id=f"{_P}/gallery.plan",
    title="Set-level gallery plan",
    archetype=ViewArchetype.STRUCTURED,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=_PROVIDER,
    contract_version="universe-gallery-plan-v1",
)

EVALUATE = NodeType(
    type_id=f"{_P}/universe.evaluate",
    title="Deterministic evaluation",
    archetype=ViewArchetype.VALIDATE,
    operation=LOCAL_OPERATION,
    contract_version="universe-evaluate-v1",
)

REVIEW = NodeType(
    type_id=f"{_P}/universe.review",
    title="Independent semantic review",
    archetype=ViewArchetype.JUDGE,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=_PROVIDER,
    contract_version="universe-review-v1",
)

ADMIT = NodeType(
    type_id=f"{_P}/universe.admit",
    title="Semantic admission",
    archetype=ViewArchetype.VALIDATE,
    operation=LOCAL_OPERATION,
    contract_version="universe-admit-v1",
)

GLOBAL_DIRECTION = NodeType(
    type_id=f"{_P}/direction.global",
    title="Global visual grammar",
    archetype=ViewArchetype.STRUCTURED,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=_PROVIDER,
    contract_version="universe-direction-global-v1",
)

ENTITY_DIRECTION = NodeType(
    type_id=f"{_P}/direction.entity",
    title="Entity concept direction",
    archetype=ViewArchetype.STRUCTURED,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=_PROVIDER,
    contract_version="universe-direction-entity-v1",
)

CONCEPT_IMAGE = NodeType(
    type_id=f"{_P}/concept.image",
    title="Entity concept image",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="universe-concept-image-v1",
)

CONCEPT_PROXY = NodeType(
    type_id=f"{_P}/concept.proxy",
    title="Review proxy",
    archetype=ViewArchetype.IMAGE,
    operation=LOCAL_OPERATION,
    contract_version="universe-concept-proxy-v1",
)

CONCEPT_REVIEW = NodeType(
    type_id=f"{_P}/concept.review",
    title="Independent image review",
    archetype=ViewArchetype.JUDGE,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=_PROVIDER,
    contract_version="universe-concept-review-v1",
)

ENTITY_RECORD = NodeType(
    type_id=f"{_P}/entity.record",
    title="Entity text record",
    archetype=ViewArchetype.TRANSFORM,
    operation=LOCAL_OPERATION,
    contract_version="universe-entity-record-v1",
)

GALLERY_CLOSE = NodeType(
    type_id=f"{_P}/gallery.close",
    title="Closed image inventory",
    archetype=ViewArchetype.PACKAGE,
    operation=LOCAL_OPERATION,
    contract_version="universe-gallery-close-v1",
)

UNIVERSE_NODE_TYPES: tuple[NodeType, ...] = (
    SOURCE_LOCK,
    PROPOSE,
    PLAN,
    EVALUATE,
    REVIEW,
    ADMIT,
    GLOBAL_DIRECTION,
    ENTITY_DIRECTION,
    CONCEPT_IMAGE,
    CONCEPT_PROXY,
    CONCEPT_REVIEW,
    ENTITY_RECORD,
    GALLERY_CLOSE,
)


def universe_type_index() -> dict[str, NodeType]:
    return {node_type.type_id: node_type for node_type in UNIVERSE_NODE_TYPES}


__all__ = [
    "ADMISSION_KIND",
    "ADMIT",
    "ADMITTED_KIND",
    "ATTEMPT_LEDGER_KIND",
    "CONCEPT_IMAGE",
    "CONCEPT_IMAGE_KIND",
    "CONCEPT_PROXY",
    "CONCEPT_REVIEW",
    "DIRECTION_WARNINGS_KIND",
    "ENTITY_DIRECTION",
    "ENTITY_DIRECTION_KIND",
    "ENTITY_MARKDOWN_KIND",
    "ENTITY_RECORD",
    "ENTITY_RECORD_KIND",
    "EVALUATE",
    "EVALUATION_KIND",
    "GALLERY_CLOSE",
    "GALLERY_PLAN_KIND",
    "GLOBAL_DIRECTION",
    "GLOBAL_DIRECTION_KIND",
    "IMAGE_FEATURES",
    "IMAGE_REVIEW_KIND",
    "INVENTORY_KIND",
    "MANIFEST_KIND",
    "PLAN",
    "POSTER_PROXY_KIND",
    "PROPOSAL_KIND",
    "PROPOSE",
    "REVIEW",
    "REVIEW_PROXY_KIND",
    "SAMPLE_LEDGER_KIND",
    "SEMANTIC_REVIEW_KIND",
    "SOURCE_LOCK",
    "SOURCE_LOCK_KIND",
    "STRUCTURED_FEATURES",
    "UNIVERSE_NODE_TYPES",
    "universe_type_index",
]
