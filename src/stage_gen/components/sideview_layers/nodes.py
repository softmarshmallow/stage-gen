"""The parallax-layer node family: paint, loop, admit and place one side-view layer.

Both side-view genres author layers the same way and ran them through the same four
nodes, each recipe with its own copy of the handlers and its own record shape. The
family lives here once, over a host that supplies the genre's facts: which layer a
node is about, its loop fallback, the prompt framing, the authored references, the
provider gate's floors and whether an opaque cover is placed. A recipe declares the
four types through ``layer_node_types(identity_prefix=…)``, keeping the type ids and
contracts it shipped under as the cache identity: the family may move home, the
layers it already paid for do not move with it.
"""

from __future__ import annotations

import io
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, cast

from PIL import Image

from gnode import (
    AuthoredInput,
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
    Port,
    PortRef,
    SoftwareIdentity,
    ViewArchetype,
    atomic_write_bytes,
    atomic_write_json,
    dependency_port,
)
from stage_gen.components._node_kit import (
    ProviderCall,
    node_result,
    object_digest,
    write_local_image,
)
from stage_gen.components.image_repeat import ImageRepeatValidationPolicy, validate_image_repeat
from stage_gen.components.image_repeat.processing import build_three_repeat_preview
from stage_gen.components.sideview_layers.contract import (
    LAYER_PLACEMENT_CANONICALIZER,
    RUNTIME_ONLY_LAYER_FIELDS,
    resolve_layer_placement,
)
from stage_gen.components.sideview_layers.pipeline import (
    layer_repeat_policies,
    loop_layer,
    validate_provider_image,
)
from stage_gen.components.sideview_stage import PreparedMapLayer
from stage_gen.media import LOOP_METHODS, LoopConstruction, SeamConditioning, data_url
from stage_gen.media.layer_rasters import trim_layer_to_alpha_box

_P = "2d/sideview/loop_x"
IMAGE_FEATURES = ("transparent_background", "reference_images")
IMAGE_EDIT_FEATURES = (*IMAGE_FEATURES, "masked_edit")
#: Every layer is painted on the one provider canvas both genres use.
LAYER_CANVAS = (1536, 1024)
#: The admission's own identity: bumped when what "admitted and placed" means changes.
LAYER_ADMISSION_VERSION = "sideview-layer-admission-v1"
LAYER_LOOP_EDIT_BYPASS_MODEL = "sideview-layer-loop-edit-bypass-v1"

LAYER_RAW_KIND = "sideview-layer-raw-v1"
LAYER_LOOP_KIND = "sideview-layer-loop-v1"
LAYER_LOOP_REPORT_KIND = "sideview-layer-loop-report-v1"
LAYER_LOOP_EDIT_KIND = "sideview-layer-loop-edit-v1"
LAYER_KIND = "sideview-layer-v1"
LAYER_VALIDATION_KIND = "sideview-layer-validation-v1"
LAYER_REPEAT_PREVIEW_KIND = "sideview-layer-repeat-preview-v1"

LAYER_GENERATE = NodeType(
    type_id=f"{_P}.generate",
    title="Layer painting",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=NodePolicy(max_attempts=6),
    contract_version="sideview-layer-v1",
)
LAYER_LOOP_PAINT = NodeType(
    type_id=f"{_P}.loop_paint",
    title="Layer loop repaint",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_EDIT_FEATURES,
    policy=NodePolicy(max_attempts=6),
    contract_version="sideview-layer-loop-paint-v1",
)
LAYER_LOOP_CONSTRUCT = NodeType(
    type_id=f"{_P}.loop_construct",
    title="Layer loop construction",
    archetype=ViewArchetype.TRANSFORM,
    operation="local",
    contract_version="sideview-layer-loop-construct-v1",
)
LAYER_VALIDATE = NodeType(
    type_id=f"{_P}.validate",
    title="Layer admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="sideview-layer-validate-v1",
)


@dataclass(frozen=True, slots=True)
class LayerNodeTypes:
    generate: NodeType
    loop_paint: NodeType
    loop_construct: NodeType
    validate: NodeType

    def loop(self, construction: LoopConstruction) -> NodeType:
        """Which loop type a construction selects follows from the construction's own claim."""

        return self.loop_paint if LOOP_METHODS[construction].is_generative else self.loop_construct


def layer_node_types(
    *,
    identity_prefix: str | None = None,
    generate_version: str = LAYER_GENERATE.contract_version,
    loop_paint_version: str = LAYER_LOOP_PAINT.contract_version,
    loop_construct_version: str = LAYER_LOOP_CONSTRUCT.contract_version,
    validate_version: str = LAYER_VALIDATE.contract_version,
) -> LayerNodeTypes:
    """The four types as one recipe declares them.

    ``identity_prefix`` is the type-id stem a recipe shipped the family under, up to the
    ``.generate``; it becomes each type's cache identity so every layer already painted
    keeps its key. The versions likewise keep a recipe's own contracts until it chooses
    to converge. Admission is local, but a recipe whose paid reviews depend on it keeps its
    admission contract too, or those reviews would re-bill for a local change.
    """

    generate, paint, construct, validate = (
        LAYER_GENERATE,
        LAYER_LOOP_PAINT,
        LAYER_LOOP_CONSTRUCT,
        LAYER_VALIDATE,
    )
    if identity_prefix is not None:
        generate = replace(generate, identity=f"{identity_prefix}.generate")
        paint = replace(paint, identity=f"{identity_prefix}.loop_paint")
        construct = replace(construct, identity=f"{identity_prefix}.loop_construct")
        validate = replace(validate, identity=f"{identity_prefix}.validate")
    if validate_version != validate.contract_version:
        validate = replace(validate, contract_version=validate_version)
    if generate_version != generate.contract_version:
        generate = replace(generate, contract_version=generate_version)
    if loop_paint_version != paint.contract_version:
        paint = replace(paint, contract_version=loop_paint_version)
    if loop_construct_version != construct.contract_version:
        construct = replace(construct, contract_version=loop_construct_version)
    return LayerNodeTypes(
        generate=generate, loop_paint=paint, loop_construct=construct, validate=validate
    )


# ------------------------------------------------------------------- graph


@dataclass(frozen=True, slots=True)
class LayerLayout:
    """Where one layer's artifacts land, run-relative; the host names them."""

    raw: str
    loop: str
    loop_report: str
    loop_edit: str
    image: str
    validation: str
    #: The three-repeat preview a host publishes for a reviewer, or none.
    repeat_preview: str | None = None


def add_layer_nodes(
    builder: GraphBuilder,
    *,
    types: LayerNodeTypes,
    layer: PreparedMapLayer,
    construction: LoopConstruction,
    node_ids: tuple[str, str, str],
    domain: str,
    depends_on: Sequence[str],
    generate_digests: Sequence[str],
    loop_digests: Sequence[str],
    layout: LayerLayout,
    params: Mapping[str, str],
    generate_prompt: str | None = None,
    authored_inputs: tuple[AuthoredInput, ...] = (),
    loop_prompt: str | None = None,
    attempts_port: Callable[[str], Port] | None = None,
    validate_digests: Sequence[str] | None = None,
) -> str:
    """Paint, loop, admit; returns the admission node id, the family's terminal.

    The host keys the painting and the loop - both are cache identity, and both differ
    between the recipes that shipped this family - while the family owns the ports, the
    loop type the construction selects, and the admission's key, which is the authored
    layer minus its runtime-only fields plus the admission's own version.
    """

    generate_id, loop_id, validate_id = node_ids
    generate_ports: list[Port] = [
        Port(
            port_id="image",
            artifact_ref=layout.raw,
            kind=LAYER_RAW_KIND,
            sidecar_ref=f"{layout.raw}.meta.json",
        )
    ]
    if attempts_port is not None:
        generate_ports.append(attempts_port(generate_id))
    generated = builder.add(
        types.generate,
        generate_id,
        domain=domain,
        description=f"paint the {layer.layer_id} parallax layer",
        params=dict(params),
        depends_on=tuple(depends_on),
        cache_depends_on=(),
        input_digests=tuple(generate_digests),
        ports=tuple(generate_ports),
        card=NodeCard(prompt=generate_prompt, authored_inputs=authored_inputs),
    )
    generative = LOOP_METHODS[construction].is_generative
    loop_ports: list[Port] = [
        Port(
            port_id="loop_image",
            artifact_ref=layout.loop,
            kind=LAYER_LOOP_KIND,
            sidecar_ref=f"{layout.loop}.meta.json",
        ),
        Port(port_id="loop_report", artifact_ref=layout.loop_report, kind=LAYER_LOOP_REPORT_KIND),
    ]
    if generative:
        # The repaint intermediate exists only when admission escalates to a provider edit;
        # declaring it keeps that channel visible.
        loop_ports.append(
            Port(
                port_id="edit_image",
                artifact_ref=layout.loop_edit,
                kind=LAYER_LOOP_EDIT_KIND,
                sidecar_ref=f"{layout.loop_edit}.meta.json",
            )
        )
        if attempts_port is not None:
            loop_ports.append(attempts_port(loop_id))
    looped = builder.add(
        types.loop(construction),
        loop_id,
        domain=domain,
        description=f"admit the x-axis loop for {layer.layer_id}, else {construction}",
        params={**params, "construction": construction},
        # The generated raster is this node's content input, so the edge is cache lineage:
        # a repainted layer must never be served a loop derived from the discarded image.
        depends_on=(generated.node_id,),
        input_digests=tuple(loop_digests),
        ports=tuple(loop_ports),
        card=NodeCard(
            prompt=loop_prompt if generative else None,
            reference_inputs=(PortRef(node_id=generated.node_id, port_id="image"),),
        ),
        duration_seconds=None if generative else 1.0,
    )
    validate_ports: list[Port] = [
        Port(
            port_id="image",
            artifact_ref=layout.image,
            kind=LAYER_KIND,
            sidecar_ref=f"{layout.image}.meta.json",
        ),
        Port(port_id="validation", artifact_ref=layout.validation, kind=LAYER_VALIDATION_KIND),
    ]
    if layout.repeat_preview is not None:
        validate_ports.append(
            Port(
                port_id="repeat_preview",
                artifact_ref=layout.repeat_preview,
                kind=LAYER_REPEAT_PREVIEW_KIND,
            )
        )
    validated = builder.add(
        types.validate,
        validate_id,
        domain=domain,
        description=f"admit and place the {layer.layer_id} layer",
        params=dict(params),
        depends_on=(looped.node_id,),
        # The family's admission key, unless the host keeps the one its paid reviews depend on.
        input_digests=tuple(validate_digests)
        if validate_digests is not None
        else (
            object_digest(layer.model_dump(mode="json", exclude=set(RUNTIME_ONLY_LAYER_FIELDS))),
            object_digest(
                {"admission": LAYER_ADMISSION_VERSION, "placement": LAYER_PLACEMENT_CANONICALIZER}
            ),
        ),
        ports=tuple(validate_ports),
        card=NodeCard(reference_inputs=(PortRef(node_id=looped.node_id, port_id="loop_image"),)),
        duration_seconds=1.0,
    )
    return validated.node_id


# ------------------------------------------------------------------- gates


@dataclass(frozen=True, slots=True)
class LayerGate:
    """The floors a painted layer must clear before it is accepted from the provider.

    All zero is the bare canvas gate; a genre whose transparent layers must carry
    meaningful content sets the floors it measured.
    """

    minimum_transparent_fraction: float = 0.0
    minimum_visible_fraction: float = 0.0
    minimum_transparent_edge_fraction: float = 0.0


def admit_layer_candidate(data: bytes, *, transparent: bool, gate: LayerGate) -> dict[str, object]:
    """Run the refusal-bearing check the provider retry owner runs, at the host's floors."""

    return validate_provider_image(
        data,
        width=LAYER_CANVAS[0],
        height=LAYER_CANVAS[1],
        transparent=transparent,
        minimum_transparent_fraction=gate.minimum_transparent_fraction if transparent else 0.0,
        minimum_visible_fraction=gate.minimum_visible_fraction if transparent else 0.0,
        minimum_transparent_edge_fraction=(
            gate.minimum_transparent_edge_fraction if transparent else 0.0
        ),
    )


def publish_layer(
    layer: PreparedMapLayer, looped: bytes, *, place_opaque: bool
) -> tuple[bytes, dict[str, object]]:
    """Trim an admitted loop unit to its alpha box and resolve its placement, once.

    A transparent layer's offset is resolved from the raster it actually received. An
    opaque cover is trimmed and placed only where the host places covers; otherwise it
    ships as painted and is placed by its anchor alone. Pure, so a host that re-derives
    the record cannot drift from the node that wrote it.
    """

    alpha_policy, coverage = layer_repeat_policies(layer.alpha_mode)
    if layer.alpha_mode == "transparent" or place_opaque:
        published, trim = trim_layer_to_alpha_box(looped)
        placement: dict[str, object] | None = resolve_layer_placement(layer, trim)
    else:
        published, trim, placement = looped, {"trimmed": False}, None
    report = validate_image_repeat(
        published,
        axis="x",
        alpha_policy=alpha_policy,
        coverage_policy=coverage,
        validation_policy=ImageRepeatValidationPolicy(),
    )
    if report.verdict != "pass":
        # The bytes that ship must be the bytes that passed. Trimming empty rows can change
        # the edge statistics, so the artifact is re-admitted after the trim rather than
        # inheriting a verdict earned by a raster we no longer publish.
        raise ValueError(f"layer {layer.layer_id} failed x-repeat admission after the trim")
    with Image.open(io.BytesIO(published)) as opened:
        width, height = opened.size
    record: dict[str, object] = {
        "schema_version": 1,
        "kind": LAYER_VALIDATION_KIND,
        "layer_id": layer.layer_id,
        "alpha_mode": layer.alpha_mode,
        "vertical_anchor": layer.vertical_anchor,
        "width": width,
        "height": height,
        "trim": trim,
        "placement": placement,
        "repeat": report.model_dump(mode="json"),
    }
    return published, record


def bounded_repeat_preview(data: bytes) -> bytes:
    """Three repeats side by side, bounded so a reviewer's viewer can open it."""

    preview_data = build_three_repeat_preview(data, axis="x")
    with Image.open(io.BytesIO(preview_data)) as opened:
        preview = opened.convert("RGB")
    if preview.width > 4_608:
        target_height = round(preview.height * 4_608 / preview.width)
        preview = preview.resize((4_608, target_height), Image.Resampling.LANCZOS)
    stream = io.BytesIO()
    preview.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


# ----------------------------------------------------------------- handler


LoopPrompt = Callable[[Node, PreparedMapLayer, SeamConditioning, LoopConstruction], str]


@dataclass(frozen=True)
class LayerHost:
    """Everything the family needs from whichever recipe hosts it."""

    run_dir: Path
    #: The authored layer a node is about.
    layer: Callable[[Node], PreparedMapLayer]
    #: The deterministic construction a failed generative loop falls back to.
    fallback: Callable[[Node], LoopConstruction]
    #: How the host names a layer in a refusal, e.g. ``crowncrag/hills``.
    label: Callable[[Node], str]
    #: Request metadata the host wants on every provider call for this node.
    metadata: Callable[[Node], Mapping[str, str]]
    #: The authored references a painting is shown.
    references: Callable[[Node], tuple[ImageReference, ...]]
    #: The loop brief for the construction actually selected, over the canvas it will see.
    loop_prompt: LoopPrompt
    #: The host's software identity, stamped on the local artifacts the family writes.
    component: SoftwareIdentity
    handler_version: str
    #: The floors a painted layer must clear.
    gate: LayerGate = LayerGate()
    #: Whether an opaque cover is trimmed and placed like a cut-out layer.
    place_opaque: bool = True
    #: The painting brief when the plan carries none on the card.
    generate_prompt: Callable[[Node], str] | None = None


class LayerHandlers:
    """The three coroutines behind the four layer node types, owned by no recipe.

    ``loop`` serves both loop types: which one the plan carries follows from the
    construction, and both routes read one implementation. ``provider_call`` is the seam
    for a recipe that writes attempt ledgers.
    """

    def __init__(
        self,
        host: LayerHost,
        *,
        graph: Graph,
        image_service: ImageGenerationService,
        provider_call: ProviderCall | None = None,
    ) -> None:
        self._host = host
        self._graph = graph
        self._images = image_service
        self._provider_call = provider_call

    def generate_request(self, node: Node) -> ImageGenerationRequest:
        host = self._host
        layer = host.layer(node)
        transparent = layer.alpha_mode == "transparent"
        if node.card is not None and node.card.prompt is not None:
            prompt = node.card.prompt
        elif host.generate_prompt is not None:
            prompt = host.generate_prompt(node)
        else:
            raise ValueError(f"node {node.node_id} declares no painting prompt")
        return ImageGenerationRequest(
            prompt=prompt,
            artifact_path=host.run_dir / node.port("image").artifact_ref,
            input_references=host.references(node),
            quality="high",
            background="transparent" if transparent else "opaque",
            output_format="png",
            size=f"{LAYER_CANVAS[0]}x{LAYER_CANVAS[1]}",
            timeout_seconds=600,
            metadata=dict(host.metadata(node)),
            validate=lambda artifact: admit_layer_candidate(
                artifact.data, transparent=transparent, gate=host.gate
            ),
        )

    async def generate(self, node: Node) -> NodeExecutionResult:
        request = self.generate_request(node)
        result = await self._call(node, request.prompt, lambda: self._images.generate(request))
        return node_result(
            self._host.run_dir, node, attempts=result.attempts, provider_operations=result.attempts
        )

    async def loop(self, node: Node) -> NodeExecutionResult:
        """Admit the generated layer as a loop, or construct one by the declared construction."""

        host = self._host
        layer = host.layer(node)
        construction: LoopConstruction = node.params["construction"]  # type: ignore[assignment]
        _producer, source_port = dependency_port(self._graph, node, kind=LAYER_RAW_KIND)
        raw_data = (host.run_dir / source_port.artifact_ref).read_bytes()
        generative = LOOP_METHODS[construction].is_generative
        edit_ref = node.port("edit_image").artifact_ref if generative else None

        async def paint(conditioning: SeamConditioning) -> tuple[bytes, int]:
            assert edit_ref is not None
            edit_path = host.run_dir / edit_ref
            prompt = host.loop_prompt(node, layer, conditioning, construction)
            request = ImageGenerationRequest(
                prompt=prompt,
                artifact_path=edit_path,
                input_references=(
                    ImageReference(
                        data_url(conditioning.conditioning_png, "image/png"), "loop-conditioning"
                    ),
                ),
                mask_reference=ImageReference(
                    data_url(conditioning.mask_png, "image/png"), "loop-mask"
                ),
                quality="high",
                background="transparent" if layer.alpha_mode == "transparent" else "opaque",
                output_format="png",
                size=f"{conditioning.width}x{conditioning.height}",
                timeout_seconds=600,
                metadata={**host.metadata(node), "operation": f"loop_{construction}"},
            )
            generation = await self._call(node, prompt, lambda: self._images.generate(request))
            return edit_path.read_bytes(), generation.attempts

        outcome = await loop_layer(
            raw_data,
            construction=construction,
            fallback=host.fallback(node),
            alpha_mode=layer.alpha_mode,
            label=host.label(node),
            paint=paint if generative else None,
        )
        if outcome.edit_bypassed and edit_ref is not None and outcome.edit_data is not None:
            await self._write(
                host.run_dir / edit_ref,
                outcome.edit_data,
                prompt="Record a provider-free bypass for an already seamless layer.",
                inputs=[(source_port.artifact_ref, raw_data)],
                validation={"construction": "none", "provider_skipped": True},
                model=LAYER_LOOP_EDIT_BYPASS_MODEL,
            )
        inputs = [(source_port.artifact_ref, raw_data)]
        if outcome.edit_is_the_selected_construction and edit_ref is not None:
            assert outcome.edit_data is not None
            inputs.append((edit_ref, outcome.edit_data))
        await self._write(
            host.run_dir / node.port("loop_image").artifact_ref,
            outcome.looped,
            prompt="Admit or construct the layer's horizontal loop unit.",
            inputs=inputs,
            validation=outcome.record,
            model=str(outcome.record["kind"]),
        )
        atomic_write_json(host.run_dir / node.port("loop_report").artifact_ref, outcome.record)
        return node_result(
            host.run_dir,
            node,
            attempts=max(1, outcome.provider_operations),
            provider_operations=outcome.provider_operations,
        )

    async def validate(self, node: Node) -> NodeExecutionResult:
        host = self._host
        layer = host.layer(node)
        _producer, loop_port = dependency_port(self._graph, node, kind=LAYER_LOOP_KIND)
        looped = (host.run_dir / loop_port.artifact_ref).read_bytes()
        published, record = publish_layer(layer, looped, place_opaque=host.place_opaque)
        await self._write(
            host.run_dir / node.port("image").artifact_ref,
            published,
            prompt=(
                "Trim the admitted loop unit to its alpha box vertically while preserving the "
                "repeat period, and resolve its placement."
            ),
            inputs=[(loop_port.artifact_ref, looped)],
            validation=record,
            model=LAYER_PLACEMENT_CANONICALIZER,
        )
        atomic_write_json(host.run_dir / node.port("validation").artifact_ref, record)
        preview = next((port for port in node.ports if port.port_id == "repeat_preview"), None)
        if preview is not None:
            atomic_write_bytes(
                host.run_dir / preview.artifact_ref, bounded_repeat_preview(published)
            )
        return node_result(host.run_dir, node)

    # ----------------------------------------------------------------- shared

    async def _call[T](self, node: Node, prompt: str, thunk: Callable[[], Awaitable[T]]) -> T:
        if self._provider_call is None:
            return await thunk()
        return cast(T, await self._provider_call(node, "layer", prompt, thunk))

    async def _write(
        self,
        path: Path,
        data: bytes,
        *,
        prompt: str,
        inputs: Sequence[tuple[str, bytes]],
        validation: Mapping[str, object],
        model: str,
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


AlphaMode = Literal["opaque", "transparent"]

__all__ = [
    "IMAGE_EDIT_FEATURES",
    "IMAGE_FEATURES",
    "LAYER_ADMISSION_VERSION",
    "LAYER_CANVAS",
    "LAYER_GENERATE",
    "LAYER_KIND",
    "LAYER_LOOP_CONSTRUCT",
    "LAYER_LOOP_EDIT_KIND",
    "LAYER_LOOP_KIND",
    "LAYER_LOOP_PAINT",
    "LAYER_LOOP_REPORT_KIND",
    "LAYER_RAW_KIND",
    "LAYER_REPEAT_PREVIEW_KIND",
    "LAYER_VALIDATE",
    "LAYER_VALIDATION_KIND",
    "LayerGate",
    "LayerHandlers",
    "LayerHost",
    "LayerLayout",
    "LayerNodeTypes",
    "add_layer_nodes",
    "admit_layer_candidate",
    "bounded_repeat_preview",
    "layer_node_types",
    "publish_layer",
]
