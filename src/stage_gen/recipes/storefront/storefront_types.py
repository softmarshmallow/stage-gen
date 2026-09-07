"""The storefront node types.

``type_id`` values persist under ``storefront``: this recipe draws no game view,
so it claims no camera or genre path in the asset taxonomy. What it produces is
the outward face of a package — the icon, the preview stills, the banner and the
words beside them — and none of that is an in-game asset.

Every prompt this recipe sends is known at plan time, so every generation node's
card carries its full static prompt and the handlers consume the card: one
composition, stated in the plan, executed verbatim.
"""

from __future__ import annotations

from gnode import NodePolicy, NodeType, ViewArchetype

_P = "storefront"
_PROVIDER = NodePolicy(max_attempts=6)

#: Every storefront surface is opaque and the icon refuses an alpha band outright,
#: so transparency is not among the features the bound route has to offer. What it
#: does have to offer is reference images: the whole point of the recipe is that
#: each picture is drawn against the game's own art.
IMAGE_FEATURES = ("reference_images",)
#: The direction compiler and the surface reviewer are both handed pictures, so the
#: structured route needs image input as well as strict output.
STRUCTURED_FEATURES = ("structured_output", "image_input")

#: Payload kinds (persisted vocabulary).
STOREFRONT_KIND = "storefront-source-v1"
#: The authored references, republished into the run by the close node so the
#: package is a closed set of bytes rather than a pointer at a source directory.
REFERENCE_KIND = "storefront-reference-v1"
DIRECTION_KIND = "storefront-direction-v1"
LISTING_KIND = "storefront-listing-v1"
DRAWN_SURFACE_KIND = "storefront-surface-drawn-v1"
SHIPPED_SURFACE_KIND = "storefront-surface-v1"
SURFACE_VALIDATION_KIND = "storefront-surface-validation-v1"
SURFACE_PROXY_KIND = "storefront-surface-proxy-v1"
SURFACE_REVIEW_KIND = "storefront-surface-review-v1"
SURFACE_RECORD_KIND = "storefront-surface-record-v1"
INVENTORY_KIND = "storefront-inventory-v1"
DRAW_LEDGER_KIND = "storefront-draw-ledger-v1"

STOREFRONT_RESOLVE = NodeType(
    type_id=f"{_P}/storefront.resolve",
    title="Storefront document",
    archetype=ViewArchetype.SOURCE,
    operation="local",
    contract_version="storefront-resolve-v1",
)

DIRECTION_COMPILE = NodeType(
    type_id=f"{_P}/direction.compile",
    title="Storefront direction",
    archetype=ViewArchetype.STRUCTURED,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=_PROVIDER,
    contract_version="storefront-direction-v1",
)

LISTING_COMPILE = NodeType(
    type_id=f"{_P}/listing.compile",
    title="Store listing copy",
    archetype=ViewArchetype.STRUCTURED,
    operation="structured_generation",
    features=("structured_output",),
    policy=_PROVIDER,
    contract_version="storefront-listing-v1",
)

SURFACE_GENERATE = NodeType(
    type_id=f"{_P}/surface.generate",
    title="Storefront surface",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="storefront-surface-generate-v1",
)

SURFACE_NORMALIZE = NodeType(
    type_id=f"{_P}/surface.normalize",
    title="Ship canvas",
    archetype=ViewArchetype.TRANSFORM,
    operation="local",
    contract_version="storefront-surface-normalize-v1",
)

SURFACE_VALIDATE = NodeType(
    type_id=f"{_P}/surface.validate",
    title="Surface admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    policy=NodePolicy(gates=("exact_ship_canvas", "alpha_policy", "byte_ceiling")),
    contract_version="storefront-surface-validate-v1",
)

SURFACE_PROXY = NodeType(
    type_id=f"{_P}/surface.proxy",
    title="Review proxy",
    archetype=ViewArchetype.TRANSFORM,
    operation="local",
    contract_version="storefront-surface-proxy-v1",
)

SURFACE_REVIEW = NodeType(
    type_id=f"{_P}/surface.review",
    title="Surface review",
    archetype=ViewArchetype.STRUCTURED,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=_PROVIDER,
    contract_version="storefront-surface-review-v1",
)

SURFACE_RECORD = NodeType(
    type_id=f"{_P}/surface.record",
    title="Surface record",
    archetype=ViewArchetype.TRANSFORM,
    operation="local",
    contract_version="storefront-surface-record-v1",
)

STOREFRONT_CLOSE = NodeType(
    type_id=f"{_P}/storefront.close",
    title="Storefront package",
    archetype=ViewArchetype.PACKAGE,
    operation="local",
    contract_version="storefront-close-v1",
)

STOREFRONT_NODE_TYPES: tuple[NodeType, ...] = (
    STOREFRONT_RESOLVE,
    DIRECTION_COMPILE,
    LISTING_COMPILE,
    SURFACE_GENERATE,
    SURFACE_NORMALIZE,
    SURFACE_VALIDATE,
    SURFACE_PROXY,
    SURFACE_REVIEW,
    SURFACE_RECORD,
    STOREFRONT_CLOSE,
)


def storefront_type_index() -> dict[str, NodeType]:
    return {node_type.type_id: node_type for node_type in STOREFRONT_NODE_TYPES}


__all__ = [
    "DIRECTION_COMPILE",
    "DIRECTION_KIND",
    "DRAWN_SURFACE_KIND",
    "DRAW_LEDGER_KIND",
    "IMAGE_FEATURES",
    "INVENTORY_KIND",
    "LISTING_COMPILE",
    "LISTING_KIND",
    "REFERENCE_KIND",
    "SHIPPED_SURFACE_KIND",
    "STOREFRONT_CLOSE",
    "STOREFRONT_KIND",
    "STOREFRONT_NODE_TYPES",
    "STOREFRONT_RESOLVE",
    "STRUCTURED_FEATURES",
    "SURFACE_GENERATE",
    "SURFACE_NORMALIZE",
    "SURFACE_PROXY",
    "SURFACE_PROXY_KIND",
    "SURFACE_RECORD",
    "SURFACE_RECORD_KIND",
    "SURFACE_REVIEW",
    "SURFACE_REVIEW_KIND",
    "SURFACE_VALIDATE",
    "SURFACE_VALIDATION_KIND",
    "storefront_type_index",
]
