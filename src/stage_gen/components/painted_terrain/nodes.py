"""The painted terrain node family: types, graph helper, and the handler kit behind them.

Homed under the taxonomy path the asset taxonomy already reserved for this discipline
(``2d/sideview/painted_terrain``, validation case 1) rather than inside the platformer
recipe, because a painted ground is a second terrain discipline beside the tile atlas and
is genre-neutral: a side-view RPG consumes it on the same terms a platformer does. A host
recipe supplies what only it knows -- the authored occupancy, the material the map names
and the art direction that wraps its prompt, the digests that make a segment
cache-identifiable inside its own graph -- through :class:`PaintedTerrainHost`.

Four types, where the runner has four, but not the same four. Its shared seam bridge
exists so any chunk may follow any chunk on an infinite track; these segments are a fixed
ordered partition of one finite map and meet in exactly one order, so that slot is spent
instead on the compose step that stitches the map back into one plate for the composite,
the evidence and the review.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from gnode import (
    Graph,
    GraphBuilder,
    ImageGenerationRequest,
    ImageGenerationService,
    ImageReference,
    Node,
    NodeCard,
    NodeExecutionResult,
    NodePolicy,
    NodeType,
    PortRef,
    SoftwareIdentity,
    ViewArchetype,
    atomic_write_json,
    dependency_port,
)
from stage_gen.components._node_kit import (
    ProviderCall,
    artifact_port,
    card_prompt,
    node_result,
    object_digest,
    record_port,
    text_digest,
    write_local_image,
)
from stage_gen.components.painted_terrain.canonicalize import (
    PAINTED_TERRAIN_CANONICALIZER_ID,
    canonicalize_painted_terrain_segment,
    stitch_painted_terrain,
)
from stage_gen.components.painted_terrain.guide import (
    PAINTED_TERRAIN_GUIDE_ID,
    PAINTED_TERRAIN_MODE,
    build_painted_terrain_guide,
)
from stage_gen.components.painted_terrain.models import painted_silhouette_tolerance
from stage_gen.components.painted_terrain.prompt import painted_terrain_generation_prompt
from stage_gen.components.painted_terrain.segments import (
    PAINTED_TERRAIN_GUIDE_HEIGHT,
    PAINTED_TERRAIN_GUIDE_WIDTH,
    PaintedTerrainSegment,
    painted_terrain_segments,
)
from stage_gen.components.painted_terrain.validate import (
    painted_terrain_join_discontinuity,
    validate_painted_terrain_source,
)
from stage_gen.media import data_url
from stage_gen.media.codec import decode_rgba

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
#: The stitched plate's local model identity, stamped on its provenance.
PAINTED_TERRAIN_PLATE_ID = "painted-terrain-plate-v1"
#: The graph template every segment's three nodes are declared within.
PAINTED_TERRAIN_SEGMENT_TEMPLATE = "painted-terrain-segment-pipeline@v1"

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


@dataclass(frozen=True, slots=True)
class PaintedTerrainNodeTypes:
    guide: NodeType
    generate: NodeType
    canonicalize: NodeType
    compose: NodeType


def painted_terrain_node_types(*, identity_prefix: str | None = None) -> PaintedTerrainNodeTypes:
    """The four types as one recipe declares them.

    ``identity_prefix`` is the type-id stem a recipe shipped the family under; it becomes
    each type's cache identity so every segment already painted keeps its key. The
    platformer shipped the family at its own home, so it passes none.
    """

    guide, generate, canonicalize, compose = PAINTED_TERRAIN_NODE_TYPES
    if identity_prefix is not None:
        guide = replace(guide, identity=f"{identity_prefix}/segment.guide")
        generate = replace(generate, identity=f"{identity_prefix}/segment.generate")
        canonicalize = replace(canonicalize, identity=f"{identity_prefix}/segment.canonicalize")
        compose = replace(compose, identity=f"{identity_prefix}/ground.compose")
    return PaintedTerrainNodeTypes(
        guide=guide, generate=generate, canonicalize=canonicalize, compose=compose
    )


# ------------------------------------------------------------------- graph


@dataclass(frozen=True, slots=True)
class PaintedTerrainLayout:
    """Where one map's painted artifacts land, run-relative; the host names the roots."""

    #: The directory every segment's files are named under.
    directory: str
    #: The stitched plate of the whole map: evidence, composite input, review subject.
    evidence: str
    #: The map-wide validation record the compose node writes.
    validation: str

    def guide(self, segment_id: str) -> str:
        return f"{self.directory}/{segment_id}.guide.png"

    def guide_report(self, segment_id: str) -> str:
        return f"{self.directory}/{segment_id}.guide.json"

    def raw(self, segment_id: str) -> str:
        return f"{self.directory}/{segment_id}.raw.png"

    def image(self, segment_id: str) -> str:
        return f"{self.directory}/{segment_id}.png"

    def segment_validation(self, segment_id: str) -> str:
        return f"{self.directory}/{segment_id}.validation.json"


def add_painted_terrain_nodes(
    builder: GraphBuilder,
    *,
    types: PaintedTerrainNodeTypes,
    map_id: str,
    columns: int,
    rows: int,
    domain: str,
    node_prefix: str,
    terrain_node_id: str,
    depends_on: Sequence[str],
    guide_digests: Sequence[str],
    material_direction: str,
    layout: PaintedTerrainLayout,
    params: Mapping[str, str] | None = None,
) -> str:
    """Fan one map out into its derived segments; returns the node that composes them.

    Every node here declares an edge to the terrain node, and none of them opts out of
    cache inheritance the way a tile atlas does. That is the honest cost of the mode and
    it is the inverse of the atlas's designed property: the atlas paints a material that
    knows nothing about the level, so reshaping a level never re-bills it, while a painting
    OF the occupancy must be repainted when the occupancy moves. The partition is what
    bounds it -- a deck edited in the middle of one segment re-bills that segment alone.

    The host keys the guide (``guide_digests``: its art direction, the ground table, the
    material references) while the family owns the partition identity, the prompt and the
    admission key.
    """

    segments = painted_terrain_segments(columns, rows)
    base_params = {"map_id": map_id, **(params or {})}
    canonical_ids: list[str] = []
    with builder.within_template(PAINTED_TERRAIN_SEGMENT_TEMPLATE):
        for segment in segments:
            segment_identity = object_digest(
                {
                    "index": segment.index,
                    "start_column": segment.start_column,
                    "columns": segment.columns,
                    "count": len(segments),
                    "guide": PAINTED_TERRAIN_GUIDE_ID,
                }
            )
            segment_params = {**base_params, "segment_id": segment.segment_id}
            base = f"{node_prefix}-{segment.segment_id}"
            guide = builder.add(
                types.guide,
                f"{base}-guide",
                domain=domain,
                description=f"draw the {segment.segment_id} terrain guide for {map_id}",
                params=segment_params,
                # Terrain is a real input, not a scheduling nicety: without the edge the
                # scheduler may draw a guide before the occupancy exists.
                depends_on=(*depends_on, terrain_node_id),
                input_digests=(*guide_digests, segment_identity),
                ports=(
                    artifact_port(
                        "guide", layout.guide(segment.segment_id), PAINTED_TERRAIN_GUIDE_KIND
                    ),
                    record_port(
                        "guide_report",
                        layout.guide_report(segment.segment_id),
                        PAINTED_TERRAIN_GUIDE_REPORT_KIND,
                    ),
                ),
            )
            prompt = painted_terrain_generation_prompt(
                material_direction, segment=segment, columns=segment.columns, rows=rows
            )
            generated = builder.add(
                types.generate,
                f"{base}-generate",
                domain=domain,
                description=f"paint {segment.segment_id} of {map_id}",
                params=segment_params,
                depends_on=(guide.node_id,),
                input_digests=(text_digest(prompt),),
                ports=(
                    artifact_port(
                        "image", layout.raw(segment.segment_id), PAINTED_TERRAIN_RAW_KIND
                    ),
                ),
                card=NodeCard(
                    prompt=prompt,
                    reference_inputs=(PortRef(node_id=guide.node_id, port_id="guide"),),
                ),
            )
            canonical = builder.add(
                types.canonicalize,
                f"{base}-canonicalize",
                domain=domain,
                description=f"admit {segment.segment_id} of {map_id} to its authored geometry",
                params=segment_params,
                depends_on=(guide.node_id, generated.node_id),
                input_digests=(
                    object_digest({"canonicalizer": PAINTED_TERRAIN_CANONICALIZER_ID}),
                    object_digest(painted_silhouette_tolerance().model_dump(mode="json")),
                ),
                ports=(
                    artifact_port("image", layout.image(segment.segment_id), PAINTED_TERRAIN_KIND),
                    record_port(
                        "validation",
                        layout.segment_validation(segment.segment_id),
                        PAINTED_TERRAIN_VALIDATION_KIND,
                    ),
                ),
                duration_seconds=2.0,
            )
            canonical_ids.append(canonical.node_id)
    compose = builder.add(
        types.compose,
        f"{node_prefix}-compose",
        domain=domain,
        description=f"stitch the painted terrain of {map_id} into one plate",
        params=base_params,
        depends_on=(*canonical_ids, terrain_node_id),
        input_digests=(object_digest({"segments": len(segments)}),),
        ports=(
            # The plate is evidence, a composite input and a review subject. It is never a
            # runtime asset: fifty-six columns fit inside a 4096-pixel texture and
            # sixty-five do not, so the consumer always loads segments.
            artifact_port("evidence", layout.evidence, PAINTED_TERRAIN_PLATE_KIND),
            record_port("validation", layout.validation, PAINTED_TERRAIN_GROUND_VALIDATION_KIND),
        ),
        duration_seconds=1.5,
    )
    return compose.node_id


# ------------------------------------------------------------------- handlers


@dataclass(frozen=True, slots=True)
class PaintedMaterial:
    """What the map's ground names, resolved by the host to what the family needs.

    The identity is what every painted node agrees on: the guide, the source validator
    and the canonicalizer all derive it from the same host call, so the canonicalizer's
    re-derived guide can refuse a mismatch only because none of them can drift apart.
    """

    identity: str
    #: The authored reference bytes the identity is derived from, in declaration order.
    references: tuple[bytes, ...]
    #: The same references, as the provider is shown them.
    image_references: tuple[ImageReference, ...]


@dataclass(frozen=True, slots=True)
class PaintedTerrainHost:
    """Everything the family needs from whichever recipe hosts it."""

    run_dir: Path
    #: The generated occupancy rows of the node's map, walk surface and all.
    occupancy: Callable[[Node], Sequence[str]]
    #: The material the node's map names.
    material: Callable[[Node], PaintedMaterial]
    #: The run-relative ref and bytes the guide records as its occupancy input.
    terrain_input: Callable[[Node], tuple[str, bytes]]
    #: Request metadata the host wants on every provider call for this node.
    metadata: Callable[[Node], Mapping[str, object]]
    #: The host's software identity, stamped on the local artifacts the family writes.
    component: SoftwareIdentity
    handler_version: str


class PaintedTerrainHandlers:
    """The four coroutines behind the four node types, owned by no recipe.

    ``provider_call`` is the seam for a recipe that writes attempt ledgers.
    """

    def __init__(
        self,
        host: PaintedTerrainHost,
        *,
        graph: Graph,
        image_service: ImageGenerationService,
        provider_call: ProviderCall | None = None,
    ) -> None:
        self._host = host
        self._graph = graph
        self._images = image_service
        self._provider_call = provider_call

    def segment(self, node: Node) -> PaintedTerrainSegment:
        """The derived segment a node instance is bound to, read off the map's partition."""

        segment_id = node.params.get("segment_id")
        if segment_id is None:
            raise ValueError(f"node {node.node_id} declares no segment_id")
        occupancy = self._host.occupancy(node)
        for segment in painted_terrain_segments(len(occupancy[0]), len(occupancy)):
            if segment.segment_id == segment_id:
                return segment
        raise ValueError(f"node {node.node_id} names no painted segment {segment_id}")

    def revalidate_source(self, node: Node, data: bytes) -> None:
        """Re-prove a restored painting against the gate its generation ran inside."""

        occupancy = self._host.occupancy(node)
        segment = self.segment(node)
        material = self._host.material(node)
        guide, _report = build_painted_terrain_guide(
            occupancy,
            segment,
            material_identity=material.identity,
            material_references=material.references,
        )
        validate_painted_terrain_source(
            data,
            occupancy=occupancy,
            segment=segment,
            guide=guide,
            material_identity=material.identity,
            material_references=material.references,
        )

    async def guide(self, node: Node) -> NodeExecutionResult:
        host = self._host
        occupancy = host.occupancy(node)
        material = host.material(node)
        guide, report = build_painted_terrain_guide(
            occupancy,
            self.segment(node),
            material_identity=material.identity,
            material_references=material.references,
        )
        await self._write(
            host.run_dir / node.port("guide").artifact_ref,
            guide,
            model=PAINTED_TERRAIN_GUIDE_ID,
            prompt=(
                "Draw the authored occupancy of one map segment as flat registration blocks, "
                "with a band on every side that faces air and the bottom row running off the "
                "canvas."
            ),
            inputs=[host.terrain_input(node)],
            validation=report,
        )
        atomic_write_json(host.run_dir / node.port("guide_report").artifact_ref, report)
        return node_result(host.run_dir, node)

    def generate_request(self, node: Node) -> ImageGenerationRequest:
        host = self._host
        occupancy = host.occupancy(node)
        segment = self.segment(node)
        material = host.material(node)
        _producer, guide_port = dependency_port(self._graph, node, kind=PAINTED_TERRAIN_GUIDE_KIND)
        guide = (host.run_dir / guide_port.artifact_ref).read_bytes()
        return ImageGenerationRequest(
            prompt=card_prompt(node),
            artifact_path=host.run_dir / node.port("image").artifact_ref,
            input_references=(
                ImageReference(
                    url=data_url(guide, "image/png"),
                    provenance_ref=(
                        f"run://{guide_port.artifact_ref}#sha256={hashlib.sha256(guide).hexdigest()}"
                    ),
                ),
                *material.image_references,
            ),
            quality="high",
            background="transparent",
            output_format="png",
            size=f"{PAINTED_TERRAIN_GUIDE_WIDTH}x{PAINTED_TERRAIN_GUIDE_HEIGHT}",
            timeout_seconds=600,
            metadata={
                **host.metadata(node),
                "segment_id": segment.segment_id,
                "ground_mode": PAINTED_TERRAIN_MODE,
                "native_alpha": True,
            },
            # Admission runs inside the provider's own retry budget, so a painting that
            # closed a hop gap or hung a support re-rolls rather than failing the run
            # after the spend.
            validate=lambda artifact: validate_painted_terrain_source(
                artifact.data,
                occupancy=occupancy,
                segment=segment,
                guide=guide,
                material_identity=material.identity,
                material_references=material.references,
            ),
        )

    async def generate(self, node: Node) -> NodeExecutionResult:
        request = self.generate_request(node)
        result = await self._call(node, request.prompt, lambda: self._images.generate(request))
        return node_result(
            self._host.run_dir, node, attempts=result.attempts, provider_operations=result.attempts
        )

    async def canonicalize(self, node: Node) -> NodeExecutionResult:
        host = self._host
        material = host.material(node)
        _guide_producer, guide_port = dependency_port(
            self._graph, node, kind=PAINTED_TERRAIN_GUIDE_KIND
        )
        _source_producer, source_port = dependency_port(
            self._graph, node, kind=PAINTED_TERRAIN_RAW_KIND
        )
        guide = (host.run_dir / guide_port.artifact_ref).read_bytes()
        source = (host.run_dir / source_port.artifact_ref).read_bytes()
        canonical, report = canonicalize_painted_terrain_segment(
            source,
            occupancy=host.occupancy(node),
            segment=self.segment(node),
            guide=guide,
            material_identity=material.identity,
            material_references=material.references,
        )
        await self._write(
            host.run_dir / node.port("image").artifact_ref,
            canonical,
            model=PAINTED_TERRAIN_CANONICALIZER_ID,
            prompt=(
                "Crop the segment's own columns from the conditioning canvas, clip the "
                "painting to the published silhouette band, and lay deterministic material "
                "under whatever the model did not paint."
            ),
            inputs=[(guide_port.artifact_ref, guide), (source_port.artifact_ref, source)],
            validation=report,
        )
        atomic_write_json(host.run_dir / node.port("validation").artifact_ref, report)
        return node_result(host.run_dir, node)

    async def compose(self, node: Node) -> NodeExecutionResult:
        host = self._host
        occupancy = host.occupancy(node)
        material = host.material(node)
        segments = painted_terrain_segments(len(occupancy[0]), len(occupancy))
        # Each segment's published raster is read off the edge that carries it, by the
        # producer's segment binding, never by a path convention the graph never promised.
        image_refs: dict[str, str] = {}
        for dependency_id in node.depends_on:
            producer = self._graph.node(dependency_id)
            segment_id = producer.params.get("segment_id")
            for port in producer.ports:
                if port.kind == PAINTED_TERRAIN_KIND and segment_id is not None:
                    image_refs[segment_id] = port.artifact_ref
        published: list[tuple[PaintedTerrainSegment, bytes]] = []
        inputs: list[tuple[str, bytes]] = []
        boundaries: list[int] = []
        for segment in segments:
            ref = image_refs.get(segment.segment_id)
            if ref is None:
                raise ValueError(f"node {node.node_id} has no edge carrying {segment.segment_id}")
            data = (host.run_dir / ref).read_bytes()
            published.append((segment, data))
            inputs.append((ref, data))
            if segment.start_column:
                boundaries.append(segment.start_column)
        plate = stitch_painted_terrain(published, occupancy=occupancy)
        joins = painted_terrain_join_discontinuity(decode_rgba(plate), boundaries=boundaries)
        validation: dict[str, object] = {
            "schema_version": 1,
            "kind": PAINTED_TERRAIN_GROUND_VALIDATION_KIND,
            "mode": PAINTED_TERRAIN_MODE,
            "map_id": node.params.get("map_id"),
            "material_identity": material.identity,
            "geometry_authority": "authored_occupancy",
            "silhouette_tolerance": painted_silhouette_tolerance().model_dump(mode="json"),
            "segments": [
                {
                    "segment_id": segment.segment_id,
                    "start_column": segment.start_column,
                    "columns": segment.columns,
                }
                for segment in segments
            ],
            # A cut is invisible when the step across it is unremarkable among the steps
            # inside the paintings. Recorded rather than gated: the deterministic jittered
            # cut that would fix a visible one costs no provider call, so this is the
            # measurement that decides whether to turn it on.
            "joins": joins,
        }
        await self._write(
            host.run_dir / node.port("evidence").artifact_ref,
            plate,
            model=PAINTED_TERRAIN_PLATE_ID,
            prompt="Stitch every published painted segment into one plate of the whole map.",
            inputs=inputs,
            validation=validation,
        )
        atomic_write_json(host.run_dir / node.port("validation").artifact_ref, validation)
        return node_result(host.run_dir, node)

    # ----------------------------------------------------------------- shared

    async def _write(
        self,
        path: Path,
        data: bytes,
        *,
        model: str,
        prompt: str,
        inputs: Sequence[tuple[str, bytes]],
        validation: Mapping[str, object],
    ) -> Path:
        return await write_local_image(
            path,
            data,
            prompt=prompt,
            inputs=inputs,
            validation=validation,
            model=model,
            component=self._host.component,
            handler_version=self._host.handler_version,
        )

    async def _call[T](self, node: Node, prompt: str, thunk: Callable[[], Awaitable[T]]) -> T:
        if self._provider_call is None:
            return await thunk()
        return cast(T, await self._provider_call(node, "painted_terrain", prompt, thunk))


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
    "PAINTED_TERRAIN_PLATE_ID",
    "PAINTED_TERRAIN_PLATE_KIND",
    "PAINTED_TERRAIN_RAW_KIND",
    "PAINTED_TERRAIN_SEGMENT_TEMPLATE",
    "PAINTED_TERRAIN_VALIDATION_KIND",
    "PaintedMaterial",
    "PaintedTerrainHandlers",
    "PaintedTerrainHost",
    "PaintedTerrainLayout",
    "PaintedTerrainNodeTypes",
    "add_painted_terrain_nodes",
    "painted_terrain_node_types",
]
