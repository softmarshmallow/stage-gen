"""Supplied layer images to portable scrolling-background assets and preview."""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
from contextlib import AsyncExitStack
from pathlib import Path
from typing import cast

from gnode import (
    ArtifactProvenance,
    AuthoredInput,
    BindingTable,
    GraphBuilder,
    ImageGenerationRequest,
    ImageGenerationService,
    ImageReference,
    ImageRouteRequirementsV1,
    InputProvenance,
    Node,
    NodeCard,
    NodeExecutionResult,
    NodePolicy,
    NodeType,
    ProvenanceInput,
    SoftwareIdentity,
    ViewArchetype,
    seal_graph,
)
from stage_gen.components.image_repeat import (
    ImageRepeatValidationPolicy,
    validate_image_repeat,
)
from stage_gen.components.sideview_layers.contract import (
    LOOP_REPAINT_SPAN_PX,
    LOOP_REPAINT_WINDOW_PX,
)
from stage_gen.components.sideview_layers.parallax import (
    PARALLAX_KIND,
    ParallaxLayer,
    ParallaxLayerConstruction,
    ParallaxSpec,
    PreparedParallaxLayer,
    parallax_manifest,
    prepare_parallax_layer,
    render_parallax,
)
from stage_gen.components.sideview_layers.pipeline import (
    layer_repeat_policies,
    loop_layer,
    recorded_stitches,
)
from stage_gen.config import StageGenConfig, load_config
from stage_gen.identity import STAGE_GEN_TOOL
from stage_gen.media import SeamConditioning, data_url
from stage_gen.media.codec import decode_rgba, encode_png
from stage_gen.model_routes import (
    configured_image_route_catalog,
    configured_image_workload_resolver,
    image_workload_policies,
)
from stage_gen.orchestration.image_routing import RoutedImageGenerationService
from stage_gen.pipeline import (
    InputFiles,
    NodeBinding,
    PipelineContext,
    PipelineDefinition,
    PipelineGraph,
    artifact_port,
    define,
    object_digest,
    record_port,
)

PREPARE_LAYER = NodeType(
    type_id="parallax.prepare_layer",
    title="Make the layer repeat",
    archetype=ViewArchetype.TRANSFORM,
    operation="local",
    contract_version="parallax-layer-v1",
)
REPAINT_LAYER = NodeType(
    type_id="parallax.repaint_layer",
    title="Repaint the seam",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=("transparent_background", "reference_images", "masked_edit"),
    policy=NodePolicy(max_attempts=6),
    contract_version="parallax-layer-repaint-v1",
)
COMPOSE = NodeType(
    type_id="parallax.compose",
    title="Compose the scrolling background",
    archetype=ViewArchetype.PACKAGE,
    operation="local",
    contract_version=PARALLAX_KIND,
)
LOOP_REPORT_KIND = "parallax-layer-loop-report-v1"
LOOP_EDIT_KIND = "parallax-layer-loop-edit-v1"
#: The edit a seam layer publishes when it already looped and no provider was asked.
LOOP_EDIT_BYPASS_MODEL = "parallax-layer-loop-edit-bypass-v1"
#: The provider sees a fixed window, half from each end of the layer, and both halves are written
#: back without overlapping, so a seam layer must be at least as wide as the window.
SEAM_MINIMUM_WIDTH = LOOP_REPAINT_WINDOW_PX


def _loop_ref(layer: ParallaxLayer, name: str) -> str:
    return f"parallax/layers/{layer.layer_id}.{name}"


def _is_opaque(data: bytes) -> bool:
    return cast("tuple[int, int]", decode_rgba(data).getchannel("A").getextrema()) == (255, 255)


def seam_repaint_prompt(layer: ParallaxLayer, *, transparent: bool) -> str:
    """Brief the provider to carry the layer through its own wrap, which it can see both sides of.

    The canvas is ``[ end of the layer | start of the layer ]``, so the hard cut sits in the
    middle of what the provider is shown and is repainted as ordinary interior. The wording is
    the brief that seam-painted Bellweather's layers, less that game's style and universe.
    """

    material = (
        ""
        if layer.description is None
        else "\n\nMaterial reference, describing what this layer is made of and not how to "
        f"compose it: {' '.join(layer.description.split())}\nIgnore anything in that reference "
        "about landmarks, rhythm, centring, or composition."
    )
    alpha = (
        "This is a cut-out layer. Every region that is transparent in the supplied image must "
        "stay fully transparent in yours: above the content, below it, and around it. Paint only "
        "the same band of content the left and right sides occupy, at the same top and bottom "
        "extent. Add no ground, no water, no horizon fill, no backdrop, no matte, and no "
        "vignette. Use true alpha, not a colour approximating emptiness."
        if transparent
        else "Keep the plate completely opaque."
    )
    return (
        "Image repair task. The supplied image is one horizontal strip of scrolling background "
        "art, formed by placing the end of the layer directly against its own beginning. The "
        "centre of the image is therefore a hard cut: the artwork does not line up there."
        f"\n\nRepaint only the marked middle {LOOP_REPAINT_SPAN_PX} pixels so the artwork flows "
        "through the cut as one unbroken band, with no visible seam, step, or discontinuity."
        "\n\nEverything outside that middle region is FINISHED ARTWORK: reproduce it exactly as "
        "given, pixel for pixel, same position, same scale, same vertical alignment. Do not move, "
        "shift, rescale, recompose, or restyle it.\n\nMatch the existing line weight, palette, "
        "lighting, ground line, and horizon exactly. Do not introduce a landmark, a centrepiece, "
        "a frame, or text.\n\nPaint the span at full strength edge to edge. Do not fade, feather, "
        "blur, ghost, or ramp opacity toward either boundary, and do not use a gradient, haze, "
        "glow, or vignette to blend into the neighbours. If the two sides differ, resolve it with "
        "drawn content, not with transparency or a soft wash. Empty space inside the span is "
        "allowed only where the neighbouring artwork is genuinely empty; elsewhere keep the same "
        f"density of drawn detail as the sides.{material}\n\n{alpha}"
    )


def _admit_repeat(data: bytes, *, transparent: bool, record: dict[str, object]) -> bool:
    alpha_policy, coverage = layer_repeat_policies("transparent" if transparent else "opaque")
    report = validate_image_repeat(
        data,
        axis="x",
        alpha_policy=alpha_policy,
        coverage_policy=coverage,
        validation_policy=ImageRepeatValidationPolicy(),
        stitches=recorded_stitches(record),
    )
    return report.verdict == "pass"


def _published_construction(record: dict[str, object]) -> ParallaxLayerConstruction:
    construction = record["construction"]
    if construction == "none":
        return "admitted"
    if construction == "seam_repaint" or construction == "mirror_repeat":
        return construction
    raise ValueError(f"unexpected loop construction {construction!r}")


def _service_origin(saved: ArtifactProvenance) -> ProvenanceInput:
    return ProvenanceInput(
        provider=saved.provider,
        model=saved.model,
        seed=saved.seed,
        prompt=saved.prompt,
        refs=saved.refs,
        inputs=saved.inputs,
        params=saved.params,
        validation=saved.validation,
        component=saved.component,
        tool=saved.tool,
        timestamp=saved.ts,
        attempts=saved.attempts,
        response=saved.response,
        rights=saved.rights,
    )


def create_pipeline(
    spec: ParallaxSpec,
    *,
    pipeline_id: str = "looping-parallax",
    config: StageGenConfig | None = None,
) -> PipelineDefinition:
    """Create a normal Stage Gen pipeline; all inputs and outputs are asset-owned.

    Layer preparation is keyed by source bytes and repeat construction. Composition
    is keyed separately, so offsets and parallax factors reuse prepared images.

    A ``seam_repaint`` layer plans an image-edit node on the configured route, offline, and
    needs a provider only when the supplied layer does not already loop. Its handler uses the
    ``image`` service a caller injects into ``run``; without one it opens the configured
    route for the call itself, which is what ``stage-gen pipeline run --live`` relies on.
    """

    layers = {layer.layer_id: layer for layer in spec.layers}
    seam = any(layer.loop_construction == "seam_repaint" for layer in spec.layers)
    settings = config if config is not None or not seam else load_config()
    dimensions: dict[str, PreparedParallaxLayer] = {}
    sources: dict[str, tuple[int, int]] = {}
    transparency: dict[str, bool] = {}

    def build(inputs: InputFiles) -> PipelineGraph:
        if settings is None:
            builder = GraphBuilder(profile=BindingTable(()))
            resolve_image_workload = None
        else:
            catalog = configured_image_route_catalog(settings)
            builder = GraphBuilder(
                profile=BindingTable(()),
                route_catalog=catalog,
                workload_policies=image_workload_policies(settings.image_provider_override),
            )
            resolve_image_workload = configured_image_workload_resolver(settings, catalog=catalog)
        dependencies: list[str] = []
        for layer in spec.layers:
            source_digest = inputs.digest(layer.source)
            raw = inputs.read(layer.source)
            source = decode_rgba(raw)
            sources[layer.layer_id] = source.size
            node_id = f"layer.{layer.layer_id}"
            dependencies.append(node_id)
            if layer.loop_construction == "seam_repaint":
                if source.width < SEAM_MINIMUM_WIDTH:
                    raise ValueError(
                        f"parallax layer {layer.layer_id} is {source.width}px wide; seam_repaint "
                        f"repaints a {SEAM_MINIMUM_WIDTH}px window made of both ends, so it needs "
                        "at least that width"
                    )
                transparent = not _is_opaque(raw)
                transparency[layer.layer_id] = transparent
                prompt = seam_repaint_prompt(layer, transparent=transparent)
                assert resolve_image_workload is not None
                builder.add(
                    REPAINT_LAYER,
                    node_id,
                    domain="parallax",
                    description=f"Admit the {layer.layer_id} wrap, else repaint it, else reflect",
                    params={"layer_id": layer.layer_id},
                    input_digests=(
                        source_digest,
                        object_digest(layer.generation_identity(source_digest)),
                        object_digest({"brief": prompt}),
                    ),
                    workload=resolve_image_workload(
                        ImageRouteRequirementsV1(
                            operation_variant="edit",
                            background="transparent" if transparent else "opaque",
                            output_format="png",
                            size=f"{LOOP_REPAINT_WINDOW_PX}x{source.height}",
                            reference_count=1,
                            mask_present=True,
                        )
                    ),
                    ports=(
                        artifact_port("image", layer.asset_ref, "parallax-layer-v1"),
                        artifact_port("edit", _loop_ref(layer, "edit.png"), LOOP_EDIT_KIND),
                        record_port("report", _loop_ref(layer, "loop.json"), LOOP_REPORT_KIND),
                    ),
                    card=NodeCard(
                        prompt=prompt,
                        authored_inputs=(
                            AuthoredInput(
                                label=layer.layer_id, ref=layer.source, sha256=source_digest
                            ),
                        ),
                    ),
                )
                continue
            width = source.width * (2 if layer.repeat_x else 1)
            height = source.height * (2 if layer.repeat_y else 1)
            if width > 16384 or height > 16384:
                raise ValueError("prepared parallax layer exceeds 16384 pixels")
            dimensions[layer.layer_id] = PreparedParallaxLayer(b"", width, height, source_digest)
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
            resolved_routes=builder.resolved_routes(),
            terminal_node_id="compose",
        )

    async def prepare(node: Node, context: PipelineContext) -> NodeExecutionResult:
        layer = layers[node.params["layer_id"]]
        prepared = prepare_parallax_layer(context.read_input(layer.source), layer)
        return await context.publish(node, {"image": prepared.data})

    def local_origin(
        node: Node,
        context: PipelineContext,
        *,
        model: str,
        prompt: str,
        inputs: list[InputProvenance],
        validation: dict[str, object],
    ) -> ProvenanceInput:
        return ProvenanceInput(
            provider="local",
            model=model,
            prompt=prompt,
            refs=[item.ref for item in inputs],
            inputs=inputs,
            params={"node_cache_key": node.cache_key},
            validation=validation,
            component=SoftwareIdentity(
                name=REPAINT_LAYER.type_id, version=REPAINT_LAYER.contract_version
            ),
            tool=STAGE_GEN_TOOL,
            attempts=1,
        )

    async def repaint(node: Node, context: PipelineContext) -> NodeExecutionResult:
        layer = layers[node.params["layer_id"]]
        raw = encode_png(decode_rgba(context.read_input(layer.source)))
        transparent = transparency[layer.layer_id]
        prompt = seam_repaint_prompt(layer, transparent=transparent)
        source_input = InputProvenance(
            ref=layer.source,
            sha256=context.plan.input_digests[layer.source],
            source="content",
        )
        edit_origin: ProvenanceInput | None = None
        async with AsyncExitStack() as stack:
            scratch = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="parallax-")))

            async def service() -> ImageGenerationService:
                injected = context.services.get("image")
                if injected is not None:
                    return cast("ImageGenerationService", injected)
                if settings is None:
                    raise RuntimeError("seam_repaint needs an image service or a configuration")
                return await stack.enter_async_context(RoutedImageGenerationService(settings))

            async def paint(conditioning: SeamConditioning) -> tuple[bytes, int]:
                nonlocal edit_origin
                images = await service()
                result = await images.generate(
                    ImageGenerationRequest(
                        prompt=prompt,
                        artifact_path=scratch / "edit.png",
                        input_references=(
                            ImageReference(
                                data_url(conditioning.conditioning_png, "image/png"),
                                "loop-conditioning",
                            ),
                        ),
                        mask_reference=ImageReference(
                            data_url(conditioning.mask_png, "image/png"), "loop-mask"
                        ),
                        quality="max",
                        background="transparent" if transparent else "opaque",
                        output_format="png",
                        size=f"{conditioning.width}x{conditioning.height}",
                        timeout_seconds=600,
                        metadata={"operation": "loop_seam_repaint", "layer_id": layer.layer_id},
                    )
                )
                sidecar = await asyncio.to_thread(Path(result.provenance_path).read_bytes)
                edit_origin = _service_origin(ArtifactProvenance.model_validate_json(sidecar))
                return result.data, result.attempts

            outcome = await loop_layer(
                raw,
                construction="seam_repaint",
                fallback="mirror_repeat",
                alpha_mode="transparent" if transparent else "opaque",
                label=f"parallax layer {layer.layer_id}",
                paint=paint,
            )
        assert outcome.edit_data is not None
        edit_ref = _loop_ref(layer, "edit.png")
        if edit_origin is None:
            edit_origin = local_origin(
                node,
                context,
                model=LOOP_EDIT_BYPASS_MODEL,
                prompt="Record a provider-free bypass for an already seamless layer.",
                inputs=[source_input],
                validation={"construction": "none", "provider_skipped": True},
            )
        loop_inputs = [source_input]
        if outcome.edit_is_the_selected_construction:
            loop_inputs.append(
                InputProvenance(
                    ref=edit_ref,
                    sha256=hashlib.sha256(outcome.edit_data).hexdigest(),
                    source="content",
                )
            )
        record = outcome.record
        return await context.publish(
            node,
            {
                "image": outcome.looped,
                "edit": outcome.edit_data,
                "report": json.dumps(record, sort_keys=True, separators=(",", ":")).encode(),
            },
            provenance={
                "image": local_origin(
                    node,
                    context,
                    model=str(record["kind"]),
                    prompt="Admit or construct the layer's horizontal loop unit.",
                    inputs=loop_inputs,
                    validation=record,
                ),
                "edit": edit_origin,
            },
            attempts=max(1, outcome.provider_operations),
            provider_operations=outcome.provider_operations,
        )

    async def compose(node: Node, context: PipelineContext) -> NodeExecutionResult:
        prepared: dict[str, PreparedParallaxLayer] = {}
        for layer in spec.layers:
            data = context.read_artifact(layer.asset_ref)
            image = decode_rgba(data)
            construction: ParallaxLayerConstruction = "mirror_repeat"
            if layer.loop_construction == "seam_repaint":
                record = json.loads(context.read_artifact(_loop_ref(layer, "loop.json")))
                construction = _published_construction(record)
            prepared[layer.layer_id] = PreparedParallaxLayer(
                data=data,
                width=image.width,
                height=image.height,
                source_sha256=hashlib.sha256(data).hexdigest(),
                construction=construction,
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

    def admit_repaint(node: Node, payloads: tuple[bytes, ...]) -> bool:
        """The published unit must be the size its construction implies and still loop."""

        try:
            layer = layers[node.params["layer_id"]]
            width, height = sources[layer.layer_id]
            record = json.loads(payloads[4])
            construction = _published_construction(record)
            image = decode_rgba(payloads[0])
            period = width * 2 if construction == "mirror_repeat" else width
            return image.size == (period, height) and _admit_repeat(
                payloads[0], transparent=transparency[layer.layer_id], record=record
            )
        except (ValueError, KeyError, IndexError, TypeError):
            return False

    def admit_composition(_node: Node, payloads: tuple[bytes, ...]) -> bool:
        """Every fact is planned except which construction a seam layer ended with."""

        try:
            manifest = json.loads(payloads[0])
            published = {entry["layer_id"]: entry for entry in manifest["layers"]}
            facts = dict(dimensions)
            for layer in spec.layers:
                if layer.loop_construction != "seam_repaint":
                    continue
                width, height = sources[layer.layer_id]
                construction = published[layer.layer_id]["construction"]
                if construction not in ("seam_repaint", "mirror_repeat", "admitted"):
                    return False
                facts[layer.layer_id] = PreparedParallaxLayer(
                    b"",
                    width * 2 if construction == "mirror_repeat" else width,
                    height,
                    "",
                    construction,
                )
            return manifest == parallax_manifest(spec, facts) and decode_rgba(payloads[2]).size == (
                spec.width,
                spec.height,
            )
        except (ValueError, KeyError, IndexError, TypeError):
            return False

    return define(
        pipeline_id,
        title="Looping parallax background",
        build=build,
        bindings=(
            NodeBinding(PREPARE_LAYER, prepare, admit_layer),
            NodeBinding(REPAINT_LAYER, repaint, admit_repaint),
            NodeBinding(COMPOSE, compose, admit_composition),
        ),
    )


__all__ = [
    "COMPOSE",
    "PREPARE_LAYER",
    "REPAINT_LAYER",
    "SEAM_MINIMUM_WIDTH",
    "create_pipeline",
    "seam_repaint_prompt",
]
