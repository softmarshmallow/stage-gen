"""The painted-terrain node family: its graph helper and the kit behind the four types."""

from __future__ import annotations

import json
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from typing import Literal

from gnode import (
    Binding,
    BindingTable,
    GraphBuilder,
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageReference,
    ModelRef,
    ProviderResponseMetadata,
    SoftwareIdentity,
    atomic_write_bytes,
)
from stage_gen.components._node_kit import text_digest
from stage_gen.components.painted_terrain import (
    PAINTED_TERRAIN_COMPOSE,
    PAINTED_TERRAIN_GENERATE,
    PAINTED_TERRAIN_GROUND_VALIDATION_KIND,
    PAINTED_TERRAIN_GUIDE,
    PAINTED_TERRAIN_GUIDE_KIND,
    PAINTED_TERRAIN_KIND,
    PAINTED_TERRAIN_PLATE_KIND,
    PAINTED_TERRAIN_SEGMENT_TEMPLATE,
    PAINTED_TERRAIN_VALIDATION_KIND,
    PaintedMaterial,
    PaintedTerrainHandlers,
    PaintedTerrainHost,
    PaintedTerrainLayout,
    add_painted_terrain_nodes,
    painted_terrain_node_types,
    painted_terrain_segments,
)
from stage_gen.media import data_url
from stage_gen.recipes.graph_document import RecipeGraph

from ._fixture import MATERIAL_IDENTITY, OCCUPANCY, material_reference, organic_alpha, painting


class _Ops(StrEnum):
    LOCAL = "local"
    IMAGE_GENERATION = "image_generation"


class _Graph(RecipeGraph):
    OPERATIONS = _Ops

    schema_version: Literal[1]
    kind: Literal["painted-terrain-family-test-graph-v1"]
    recipe: Literal["painted-terrain-family-test"]


PROFILE = BindingTable(
    [
        Binding(
            operation="image_generation",
            model=ModelRef(model="test-image", provider="openai"),
            features=frozenset(("transparent_background", "reference_images")),
            resource_id="openai-image",
            estimated_duration_seconds=1.0,
            estimated_cost_low_usd=0.0,
            estimated_cost_high_usd=0.0,
            verified_on="2026-09-05",
        )
    ]
)
LAYOUT = PaintedTerrainLayout(
    directory="maps/m/ground",
    evidence="maps/m/ground.evidence.png",
    validation="maps/m/ground.validation.json",
)


def _graph(columns: int, rows: int) -> _Graph:
    builder = GraphBuilder(profile=PROFILE)
    terrain = builder.add(
        replace(PAINTED_TERRAIN_GUIDE, type_id="test/terrain", contract_version="t-v1"),
        "map-m-terrain",
        domain="map-m",
        description="the occupancy",
        params={"map_id": "m"},
        depends_on=(),
        input_digests=(text_digest("occupancy"),),
        ports=(),
    )
    compose = add_painted_terrain_nodes(
        builder,
        types=painted_terrain_node_types(),
        map_id="m",
        columns=columns,
        rows=rows,
        domain="map-m",
        node_prefix="map-m-ground",
        terrain_node_id=terrain.node_id,
        depends_on=(),
        guide_digests=(text_digest("direction"),),
        material_direction="warm sandstone",
        layout=LAYOUT,
    )
    assert compose == "map-m-ground-compose"
    return _Graph.seal(resources=builder.resources(), nodes=builder.nodes, terminal_node_id=compose)


def test_a_recipe_keeps_its_shipped_identity() -> None:
    plain = painted_terrain_node_types()
    assert plain.generate is PAINTED_TERRAIN_GENERATE
    assert plain.generate.cache_identity == "2d/sideview/painted_terrain/segment.generate"
    hosted = painted_terrain_node_types(identity_prefix="p/ground")
    assert hosted.generate.type_id == PAINTED_TERRAIN_GENERATE.type_id
    assert hosted.generate.cache_identity == "p/ground/segment.generate"
    assert hosted.compose.cache_identity == "p/ground/ground.compose"


def test_the_graph_helper_fans_one_map_out_into_its_derived_partition() -> None:
    graph = _graph(56, 14)
    segments = painted_terrain_segments(56, 14)
    assert [segment.columns for segment in segments] == [19, 19, 18]
    by_id = {node.node_id: node for node in graph.nodes}
    for segment in segments:
        base = f"map-m-ground-{segment.segment_id}"
        guide, generate, canonical = (
            by_id[f"{base}-{step}"] for step in ("guide", "generate", "canonicalize")
        )
        assert guide.type_id == PAINTED_TERRAIN_GUIDE.type_id
        assert guide.depends_on == ("map-m-terrain",)
        assert guide.params == {"map_id": "m", "segment_id": segment.segment_id}
        assert generate.depends_on == (guide.node_id,)
        assert generate.card is not None and generate.card.prompt is not None
        assert "warm sandstone" in generate.card.prompt
        assert canonical.depends_on == (guide.node_id, generate.node_id)
        assert [port.kind for port in canonical.ports] == [
            PAINTED_TERRAIN_KIND,
            PAINTED_TERRAIN_VALIDATION_KIND,
        ]
        assert canonical.port("image").artifact_ref == f"maps/m/ground/{segment.segment_id}.png"
        assert guide.template_id == PAINTED_TERRAIN_SEGMENT_TEMPLATE
    compose = by_id["map-m-ground-compose"]
    assert compose.type_id == PAINTED_TERRAIN_COMPOSE.type_id
    assert compose.depends_on == (
        *(f"map-m-ground-{segment.segment_id}-canonicalize" for segment in segments),
        "map-m-terrain",
    )
    assert [port.kind for port in compose.ports] == [
        PAINTED_TERRAIN_PLATE_KIND,
        PAINTED_TERRAIN_GROUND_VALIDATION_KIND,
    ]
    # Ten nodes: the terrain, three segments of three, and the compose.
    assert len(graph.nodes) == 11


class _Images:
    """Paints the fixture's organic silhouette wherever the family asks, through its gate."""

    def __init__(self) -> None:
        self.requests: list[ImageGenerationRequest] = []

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        self.requests.append(request)
        data = painting(organic_alpha())
        if request.validate is not None:
            request.validate(
                ImageGenerationResult(  # type: ignore[arg-type]
                    data=data,
                    media_type="image/png",
                    provider="openai",
                    model="test-image",
                    attempts=1,
                    provenance_path="",
                    response_metadata=ProviderResponseMetadata(request_id="r", usage={}),
                )
            )
        atomic_write_bytes(request.artifact_path, data)
        return ImageGenerationResult(
            data=data,
            media_type="image/png",
            provider="openai",
            model="test-image",
            attempts=1,
            provenance_path=str(request.artifact_path) + ".meta.json",
            response_metadata=ProviderResponseMetadata(request_id="r", usage={}),
        )


async def test_the_kit_guides_paints_admits_and_composes_the_fixture_map(tmp_path: Path) -> None:
    graph = _graph(len(OCCUPANCY[0]), len(OCCUPANCY))
    reference = material_reference()
    material = PaintedMaterial(
        identity=MATERIAL_IDENTITY,
        references=(reference,),
        image_references=(
            ImageReference(url=data_url(reference, "image/png"), provenance_ref="ref"),
        ),
    )
    images = _Images()
    handlers = PaintedTerrainHandlers(
        PaintedTerrainHost(
            run_dir=tmp_path,
            occupancy=lambda node: OCCUPANCY,
            material=lambda node: material,
            terrain_input=lambda node: ("maps/m/terrain.json", "\n".join(OCCUPANCY).encode()),
            metadata=lambda node: {"checkpoint": "test", "map_id": "m"},
            component=SoftwareIdentity(name="@stage-gen/test", version="t-v1"),
            handler_version="t-v1",
        ),
        graph=graph,
        image_service=images,  # type: ignore[arg-type]
    )
    (segment,) = painted_terrain_segments(len(OCCUPANCY[0]), len(OCCUPANCY))
    base = f"map-m-ground-{segment.segment_id}"

    guided = await handlers.guide(graph.node(f"{base}-guide"))
    assert (tmp_path / LAYOUT.guide(segment.segment_id)).is_file()
    assert guided.provider_operations == 0

    generated = await handlers.generate(graph.node(f"{base}-generate"))
    assert generated.provider_operations == 1
    (request,) = images.requests
    assert request.metadata["segment_id"] == segment.segment_id
    guide_ref = request.input_references[0].provenance_ref
    assert guide_ref is not None and guide_ref.startswith("run://maps/m/ground/")
    assert request.input_references[1] is material.image_references[0]

    admitted = await handlers.canonicalize(graph.node(f"{base}-canonicalize"))
    assert admitted.provider_operations == 0
    record = json.loads((tmp_path / LAYOUT.segment_validation(segment.segment_id)).read_text())
    assert record["kind"] == PAINTED_TERRAIN_VALIDATION_KIND

    composed = await handlers.compose(graph.node("map-m-ground-compose"))
    assert composed.provider_operations == 0
    plate = json.loads((tmp_path / LAYOUT.validation).read_text())
    assert plate["kind"] == PAINTED_TERRAIN_GROUND_VALIDATION_KIND
    assert plate["map_id"] == "m"
    assert plate["material_identity"] == MATERIAL_IDENTITY
    assert [entry["segment_id"] for entry in plate["segments"]] == [segment.segment_id]
    assert (tmp_path / LAYOUT.evidence).is_file()

    # The cache re-gate runs the same admission the painting was generated inside.
    handlers.revalidate_source(
        graph.node(f"{base}-generate"),
        (tmp_path / LAYOUT.raw(segment.segment_id)).read_bytes(),
    )
    assert graph.node(f"{base}-guide").port("guide").kind == PAINTED_TERRAIN_GUIDE_KIND
