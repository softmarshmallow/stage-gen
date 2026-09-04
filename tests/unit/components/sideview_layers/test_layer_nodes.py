"""The layer node family: declared once, hosted under each recipe's own identity."""

from __future__ import annotations

import io
from enum import StrEnum
from typing import Literal

import pytest
from PIL import Image, ImageDraw

from gnode import Binding, BindingTable, GraphBuilder, ModelRef
from stage_gen.components._node_kit import text_digest
from stage_gen.components.sideview_layers.nodes import (
    LAYER_GENERATE,
    LAYER_LOOP_CONSTRUCT,
    LAYER_LOOP_PAINT,
    LAYER_VALIDATE,
    LAYER_VALIDATION_KIND,
    LayerGate,
    LayerLayout,
    add_layer_nodes,
    admit_layer_candidate,
    layer_node_types,
    publish_layer,
)
from stage_gen.components.sideview_stage import PreparedMapLayer
from stage_gen.recipes.graph_document import RecipeGraph


class _Ops(StrEnum):
    LOCAL = "local"
    IMAGE_GENERATION = "image_generation"


class _Graph(RecipeGraph):
    OPERATIONS = _Ops

    schema_version: Literal[1]
    kind: Literal["layer-family-test-graph-v1"]
    recipe: Literal["layer-family-test"]


PROFILE = BindingTable(
    [
        Binding(
            operation="image_generation",
            model=ModelRef(model="test-image", provider="openai"),
            features=frozenset(("transparent_background", "reference_images", "masked_edit")),
            resource_id="openai-image",
            estimated_duration_seconds=1.0,
            estimated_cost_low_usd=0.0,
            estimated_cost_high_usd=0.0,
            verified_on="2026-09-04",
        )
    ]
)


def _layer(**overrides: object) -> PreparedMapLayer:
    fields: dict[str, object] = {
        "layer_id": "hills",
        "plane": "background",
        "order": 1,
        "parallax": 0.4,
        "alpha_mode": "transparent",
        "vertical_anchor": "walk_surface",
        "prompt": "rolling hills",
        "reference_ids": ["ref"],
        "presentation": {
            "contrast": 1.0,
            "saturation": 1.0,
            "atmosphere_color": "#8899aa",
            "atmosphere_strength": 0.0,
            "detail_blur_screen_pixels": 0.0,
        },
    }
    fields.update(overrides)
    return PreparedMapLayer.model_validate(fields)


def test_a_recipe_keeps_its_shipped_identity_and_contracts() -> None:
    types = layer_node_types(
        identity_prefix="2d/sideview/runner/layer",
        generate_version="runner-layer-v3",
        loop_paint_version="runner-layer-loop-v4",
        loop_construct_version="runner-layer-loop-v1",
    )
    assert types.generate.type_id == LAYER_GENERATE.type_id == "2d/sideview/loop_x.generate"
    assert types.generate.cache_identity == "2d/sideview/runner/layer.generate"
    assert types.generate.contract_version == "runner-layer-v3"
    assert types.loop_paint.cache_identity == "2d/sideview/runner/layer.loop_paint"
    assert types.loop_paint.contract_version == "runner-layer-loop-v4"
    assert types.loop_construct.contract_version == "runner-layer-loop-v1"
    # Admission converges unless the host keeps it.
    assert types.validate.contract_version == LAYER_VALIDATE.contract_version
    kept = layer_node_types(identity_prefix="p/map_layer", validate_version="map-layer-validate-v1")
    assert kept.validate.contract_version == "map-layer-validate-v1"
    assert kept.validate.cache_identity == "p/map_layer.validate"
    plain = layer_node_types()
    assert plain.loop("mirror_repeat") is LAYER_LOOP_CONSTRUCT
    assert plain.loop("seam_repaint") is LAYER_LOOP_PAINT


def _graph(construction: str, *, preview: bool) -> _Graph:
    builder = GraphBuilder(profile=PROFILE)
    layer = _layer()
    validated = add_layer_nodes(
        builder,
        types=layer_node_types(),
        layer=layer,
        construction=construction,  # type: ignore[arg-type]
        node_ids=("hills-generate", "hills-loop", "hills-validate"),
        domain="world",
        depends_on=(),
        generate_digests=(text_digest("hills"),),
        loop_digests=(text_digest(construction),),
        layout=LayerLayout(
            raw="layers/hills.raw.png",
            loop="layers/hills.loop.png",
            loop_report="layers/hills.loop.json",
            loop_edit="layers/hills.edit.png",
            image="layers/hills.png",
            validation="layers/hills.validation.json",
            repeat_preview="layers/hills.repeat.png" if preview else None,
        ),
        params={"layer_id": "hills"},
        generate_prompt="paint hills",
        loop_prompt="carry the hills across the seam",
    )
    assert validated == "hills-validate"
    return _Graph.seal(
        resources=builder.resources(), nodes=builder.nodes, terminal_node_id=validated
    )


def test_the_graph_helper_declares_the_loop_type_the_construction_selects() -> None:
    painted = _graph("seam_repaint", preview=True)
    loop = painted.node("hills-loop")
    assert loop.type_id == LAYER_LOOP_PAINT.type_id
    assert loop.params["construction"] == "seam_repaint"
    assert [port.port_id for port in loop.ports] == ["loop_image", "loop_report", "edit_image"]
    assert loop.card is not None and loop.card.prompt == "carry the hills across the seam"
    assert [port.port_id for port in painted.node("hills-validate").ports] == [
        "image",
        "validation",
        "repeat_preview",
    ]
    constructed = _graph("mirror_repeat", preview=False)
    loop = constructed.node("hills-loop")
    assert loop.type_id == LAYER_LOOP_CONSTRUCT.type_id
    assert [port.port_id for port in loop.ports] == ["loop_image", "loop_report"]
    assert loop.card is not None and loop.card.prompt is None
    assert [port.port_id for port in constructed.node("hills-validate").ports] == [
        "image",
        "validation",
    ]
    generate = painted.node("hills-generate")
    assert generate.card is not None and generate.card.prompt == "paint hills"


def _strip(*, transparent_rows: int) -> bytes:
    image = Image.new("RGBA", (1536, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for y in range(transparent_rows, 1024 - transparent_rows):
        draw.line([0, y, 1535, y], fill=(90, 120, 60, 255))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_publishing_places_a_transparent_layer_and_leaves_an_opaque_cover_to_its_anchor() -> None:
    published, record = publish_layer(_layer(), _strip(transparent_rows=200), place_opaque=False)
    assert len(published) > 0
    assert record["kind"] == LAYER_VALIDATION_KIND
    assert record["height"] == 624 and record["width"] == 1536
    assert isinstance(record["placement"], dict)
    assert record["placement"]["vertical_anchor"] == "walk_surface"
    assert record["repeat"]["verdict"] == "pass"  # type: ignore[index]
    cover = _layer(alpha_mode="opaque", vertical_anchor="canvas_cover")
    untouched, cover_record = publish_layer(cover, _strip(transparent_rows=0), place_opaque=False)
    assert cover_record["placement"] is None and cover_record["trim"] == {"trimmed": False}
    assert untouched == _strip(transparent_rows=0)
    _placed, placed_record = publish_layer(cover, _strip(transparent_rows=0), place_opaque=True)
    assert isinstance(placed_record["placement"], dict)


def test_the_provider_gate_applies_the_hosts_floors_only_to_transparent_layers() -> None:
    bare = LayerGate()
    strict = LayerGate(minimum_transparent_fraction=0.5)
    mostly_opaque = _strip(transparent_rows=40)
    admit_layer_candidate(mostly_opaque, transparent=True, gate=bare)
    with pytest.raises(ValueError):
        admit_layer_candidate(mostly_opaque, transparent=True, gate=strict)
    # An opaque plate is never held to the transparency floors.
    admit_layer_candidate(_strip(transparent_rows=0), transparent=False, gate=strict)
