"""Supplied layer images to portable scrolling-background assets and preview."""

from __future__ import annotations

import hashlib
import json

from gnode import (
    BindingTable,
    GraphBuilder,
    Node,
    NodeExecutionResult,
    NodeType,
    ViewArchetype,
    seal_graph,
)
from stage_gen.components.sideview_layers.parallax import (
    PARALLAX_KIND,
    ParallaxSpec,
    PreparedParallaxLayer,
    parallax_manifest,
    prepare_parallax_layer,
    render_parallax,
)
from stage_gen.media.codec import decode_rgba
from stage_gen.pipeline import (
    InputFiles,
    NodeBinding,
    PipelineContext,
    PipelineDefinition,
    PipelineGraph,
    artifact_port,
    define,
    object_digest,
)

PREPARE_LAYER = NodeType(
    type_id="parallax.prepare_layer",
    title="Prepare repeating layer",
    archetype=ViewArchetype.TRANSFORM,
    operation="local",
    contract_version="parallax-layer-v1",
)
COMPOSE = NodeType(
    type_id="parallax.compose",
    title="Compose scrolling background",
    archetype=ViewArchetype.PACKAGE,
    operation="local",
    contract_version=PARALLAX_KIND,
)


def create_pipeline(
    spec: ParallaxSpec, *, pipeline_id: str = "looping-parallax"
) -> PipelineDefinition:
    """Create a normal Stage Gen pipeline; all inputs and outputs are asset-owned.

    Layer preparation is keyed by source bytes and repeat construction. Composition
    is keyed separately, so offsets and parallax factors reuse prepared images.
    """

    layers = {layer.layer_id: layer for layer in spec.layers}
    dimensions: dict[str, PreparedParallaxLayer] = {}

    def build(inputs: InputFiles) -> PipelineGraph:
        builder = GraphBuilder(profile=BindingTable(()))
        dependencies: list[str] = []
        for layer in spec.layers:
            source_digest = inputs.digest(layer.source)
            source = decode_rgba(inputs.read(layer.source))
            width = source.width * (2 if layer.repeat_x else 1)
            height = source.height * (2 if layer.repeat_y else 1)
            if width > 16384 or height > 16384:
                raise ValueError("prepared parallax layer exceeds 16384 pixels")
            dimensions[layer.layer_id] = PreparedParallaxLayer(b"", width, height, source_digest)
            node_id = f"layer.{layer.layer_id}"
            dependencies.append(node_id)
            builder.add(
                PREPARE_LAYER,
                node_id,
                domain="parallax",
                description=f"Normalize and construct the {layer.layer_id} repeat unit",
                params={"layer_id": layer.layer_id},
                input_digests=(
                    source_digest,
                    object_digest(layer.generation_identity(source_digest)),
                ),
                ports=(artifact_port("image", layer.asset_ref, "parallax-layer-v1"),),
            )
        builder.add(
            COMPOSE,
            "compose",
            domain="parallax",
            description="Publish layer placement, repeat geometry, and an inspection frame",
            depends_on=dependencies,
            input_digests=(object_digest(spec.model_dump(mode="json")),),
            ports=(
                artifact_port("manifest", "parallax/manifest.json", PARALLAX_KIND),
                artifact_port("preview", "parallax/preview.png", "parallax-preview-v1"),
            ),
        )
        return seal_graph(
            PipelineGraph,
            pipeline_id=pipeline_id,
            title="Looping parallax background",
            nodes=builder.nodes,
            resources=builder.resources(),
            terminal_node_id="compose",
        )

    async def prepare(node: Node, context: PipelineContext) -> NodeExecutionResult:
        layer = layers[node.params["layer_id"]]
        prepared = prepare_parallax_layer(context.read_input(layer.source), layer)
        return await context.publish(node, {"image": prepared.data})

    async def compose(node: Node, context: PipelineContext) -> NodeExecutionResult:
        prepared: dict[str, PreparedParallaxLayer] = {}
        for layer in spec.layers:
            data = context.read_artifact(layer.asset_ref)
            image = decode_rgba(data)
            prepared[layer.layer_id] = PreparedParallaxLayer(
                data=data,
                width=image.width,
                height=image.height,
                source_sha256=hashlib.sha256(data).hexdigest(),
            )
        manifest = parallax_manifest(spec, prepared)
        return await context.publish(
            node,
            {
                "manifest": json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(),
                "preview": render_parallax(spec, prepared),
            },
            previews={"manifest": manifest},
        )

    def admit_layer(node: Node, payloads: tuple[bytes, ...]) -> bool:
        try:
            image = decode_rgba(payloads[0])
            layer = layers[node.params["layer_id"]]
            expected = dimensions[layer.layer_id]
            return (
                image.size == (expected.width, expected.height)
                and (
                    not layer.repeat_x
                    or image.crop((0, 0, 1, image.height)).tobytes()
                    == image.crop((image.width - 1, 0, image.width, image.height)).tobytes()
                )
                and (
                    not layer.repeat_y
                    or image.crop((0, 0, image.width, 1)).tobytes()
                    == image.crop((0, image.height - 1, image.width, image.height)).tobytes()
                )
            )
        except (ValueError, KeyError, IndexError):
            return False

    def admit_composition(_node: Node, payloads: tuple[bytes, ...]) -> bool:
        try:
            return json.loads(payloads[0]) == parallax_manifest(spec, dimensions) and decode_rgba(
                payloads[2]
            ).size == (spec.width, spec.height)
        except (ValueError, KeyError, IndexError):
            return False

    return define(
        pipeline_id,
        title="Looping parallax background",
        build=build,
        bindings=(
            NodeBinding(PREPARE_LAYER, prepare, admit_layer),
            NodeBinding(COMPOSE, compose, admit_composition),
        ),
    )


__all__ = ["COMPOSE", "PREPARE_LAYER", "create_pipeline"]
