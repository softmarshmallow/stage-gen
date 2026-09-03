"""The painted terrain node types, declared beside the contract they serve.

Homed under the taxonomy path the asset taxonomy already reserved for this discipline
(``2d/sideview/painted_terrain``, validation case 1) rather than inside the platformer
recipe, because a painted ground is a second terrain discipline beside the tile atlas and
is genre-neutral: a side-view RPG consumes it on the same terms a platformer does. A host
recipe supplies what only it knows -- the authored map, the art direction that wraps the
prompt, and the digests that make a segment cache-identifiable inside its own graph.

Four types, where the runner has four, but not the same four. Its shared seam bridge
exists so any chunk may follow any chunk on an infinite track; these segments are a fixed
ordered partition of one finite map and meet in exactly one order, so that slot is spent
instead on the compose step that stitches the map back into one plate for the composite,
the evidence and the review.
"""

from __future__ import annotations

from gnode import NodePolicy, NodeType, ViewArchetype

_P = "2d/sideview/painted_terrain"
_PROVIDER = NodePolicy(max_attempts=6)

IMAGE_FEATURES = ("transparent_background", "reference_images")

#: Persisted artifact kinds. The port's kind and the report's own ``kind`` field are the
#: same string here on purpose: the runner's guide node has them differ by one word, which
#: is a trap every reader of that file falls into once.
PAINTED_TERRAIN_GUIDE_KIND = "painted-terrain-guide-v1"
PAINTED_TERRAIN_GUIDE_REPORT_KIND = "painted-terrain-guide-report-v1"
PAINTED_TERRAIN_RAW_KIND = "painted-terrain-raw-v1"
PAINTED_TERRAIN_KIND = "painted-terrain-v1"
PAINTED_TERRAIN_VALIDATION_KIND = "painted-terrain-validation-v1"
PAINTED_TERRAIN_PLATE_KIND = "painted-terrain-plate-v1"
PAINTED_TERRAIN_GROUND_VALIDATION_KIND = "painted-terrain-ground-validation-v1"

PAINTED_TERRAIN_GUIDE = NodeType(
    type_id=f"{_P}/segment.guide",
    title="Painted terrain guide",
    archetype=ViewArchetype.TRANSFORM,
    operation="local",
    contract_version="painted-terrain-guide-v1",
)

PAINTED_TERRAIN_GENERATE = NodeType(
    type_id=f"{_P}/segment.generate",
    title="Painted terrain segment",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="painted-terrain-generate-v1",
)

PAINTED_TERRAIN_CANONICALIZE = NodeType(
    type_id=f"{_P}/segment.canonicalize",
    title="Painted terrain admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="painted-terrain-canonicalize-v1",
)

PAINTED_TERRAIN_COMPOSE = NodeType(
    type_id=f"{_P}/ground.compose",
    title="Painted terrain ground plate",
    archetype=ViewArchetype.TRANSFORM,
    operation="local",
    contract_version="painted-terrain-compose-v1",
)

PAINTED_TERRAIN_NODE_TYPES = (
    PAINTED_TERRAIN_GUIDE,
    PAINTED_TERRAIN_GENERATE,
    PAINTED_TERRAIN_CANONICALIZE,
    PAINTED_TERRAIN_COMPOSE,
)

__all__ = [
    "PAINTED_TERRAIN_CANONICALIZE",
    "PAINTED_TERRAIN_COMPOSE",
    "PAINTED_TERRAIN_GENERATE",
    "PAINTED_TERRAIN_GROUND_VALIDATION_KIND",
    "PAINTED_TERRAIN_GUIDE",
    "PAINTED_TERRAIN_GUIDE_KIND",
    "PAINTED_TERRAIN_GUIDE_REPORT_KIND",
    "PAINTED_TERRAIN_KIND",
    "PAINTED_TERRAIN_NODE_TYPES",
    "PAINTED_TERRAIN_PLATE_KIND",
    "PAINTED_TERRAIN_RAW_KIND",
    "PAINTED_TERRAIN_VALIDATION_KIND",
]
