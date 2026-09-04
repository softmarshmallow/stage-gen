"""The inventory-panel node family: one painted panel, its alpha admission, its review.

The panel is a screen-fixed interface element every genre with an inventory draws the
same way: one template-guided painting on a transparent canvas, a deterministic alpha
gate that clears the exterior and clamps the panel core and slot interiors, and a
structured review of what the pixel gate cannot decide. The platformer shipped the
family as its own node types; they keep that identity through
``inventory_node_types(identity_prefix=…)``, so no panel is paid for twice.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

from PIL import Image, ImageDraw

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
    Port,
    PortRef,
    StructuredGenerationRequest,
    StructuredGenerationService,
    StructuredOutputSchema,
    StructuredReference,
    ViewArchetype,
    atomic_write_json,
    dependency_port,
)
from stage_gen.canonical import content_sha256
from stage_gen.components._node_kit import (
    ProviderCall,
    artifact_port,
    node_result,
    object_digest,
    record_port,
    write_local_image,
)
from stage_gen.components.game_ui.models import (
    INVENTORY_CANVAS_HEIGHT,
    INVENTORY_CANVAS_WIDTH,
    INVENTORY_PANEL_HEIGHT,
    INVENTORY_PANEL_LEFT,
    INVENTORY_PANEL_TOP,
    INVENTORY_PANEL_WIDTH,
    INVENTORY_SLOT_COLUMNS,
    INVENTORY_SLOT_GUTTER,
    INVENTORY_SLOT_LEFT,
    INVENTORY_SLOT_ROWS,
    INVENTORY_SLOT_SIZE,
    INVENTORY_SLOT_TOP,
    InventoryPanelDirection,
    UiReference,
    inventory_panel_layout_contract,
)
from stage_gen.components.game_ui.nodes import UiAtlasHost, ui_atlas_review_schema
from stage_gen.media import data_url

_P = "2d/ui"
IMAGE_FEATURES = ("transparent_background", "reference_images")
STRUCTURED_FEATURES = ("structured_output", "image_input")

#: Cache identity of the painting and its admission; bumped when the prompt, the template
#: or the gate changes what a panel is asked to be.
INVENTORY_PANEL_CONTRACT_VERSION = "prepared-ui-inventory-panel-v2"
INVENTORY_PANEL_REVIEW_VERSION = "prepared-ui-inventory-panel-review-v1"
INVENTORY_PANEL_VALIDATION_VERSION = "prepared-ui-inventory-validation-v2"
INVENTORY_PANEL_EVIDENCE_VERSION = "prepared-ui-inventory-evidence-v1"
INVENTORY_TEMPLATE_REF = "inventory_grid_4x2_template_v1"
INVENTORY_REVIEW_SCHEMA_NAME = "prepared_ui_inventory_review"
#: What the judge is asked that the pixel gate cannot decide.
INVENTORY_REVIEW_CHECKS = (
    "style_coherence",
    "slot_readability",
    "visual_hierarchy",
    "exterior_silhouette",
    "no_items_or_text",
)

UI_PANEL_RAW_KIND = "ui-panel-raw-v1"
UI_PANEL_KIND = "ui-panel-v1"
UI_PANEL_VALIDATION_KIND = "ui-validation-v1"
UI_PANEL_EVIDENCE_KIND = "ui-evidence-v1"
REVIEW_VERDICT_KIND = "review-verdict-v1"

UI_INVENTORY_GENERATE = NodeType(
    type_id=f"{_P}/inventory.generate",
    title="Inventory panel",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=NodePolicy(max_attempts=6),
    contract_version="ui-inventory-v1",
)
UI_INVENTORY_VALIDATE = NodeType(
    type_id=f"{_P}/inventory.validate",
    title="Inventory panel admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="ui-inventory-validate-v1",
)
UI_INVENTORY_REVIEW = NodeType(
    type_id=f"{_P}/inventory.review",
    title="Inventory panel review",
    archetype=ViewArchetype.JUDGE,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=NodePolicy(max_attempts=6),
    contract_version="ui-inventory-review-v1",
)


@dataclass(frozen=True, slots=True)
class InventoryNodeTypes:
    generate: NodeType
    validate: NodeType
    review: NodeType


def inventory_node_types(*, identity_prefix: str | None = None) -> InventoryNodeTypes:
    """The triplet as one recipe declares it; the prefix keeps a shipped cache identity."""

    generate, validate, review = UI_INVENTORY_GENERATE, UI_INVENTORY_VALIDATE, UI_INVENTORY_REVIEW
    if identity_prefix is not None:
        generate = replace(generate, identity=f"{identity_prefix}/ui_inventory.generate")
        validate = replace(validate, identity=f"{identity_prefix}/ui_inventory.validate")
        review = replace(review, identity=f"{identity_prefix}/ui_inventory.review")
    return InventoryNodeTypes(generate=generate, validate=validate, review=review)


# ------------------------------------------------------------------- graph


def add_inventory_panel_nodes(
    builder: GraphBuilder,
    *,
    types: InventoryNodeTypes,
    panel: InventoryPanelDirection,
    references: Mapping[str, UiReference],
    depends_on: Sequence[str],
    direction_digest: str,
    template_sha256: str,
    domain: str = "ui",
    node_ids: tuple[str, str, str] = (
        "ui-inventory-panel-generate",
        "ui-inventory-panel-validate",
        "ui-inventory-panel-review",
    ),
    attempts_port: Callable[[str], Port] | None = None,
) -> str:
    """Generate, validate, review; returns the review node id, the family's terminal."""

    generate_id, validate_id, review_id = node_ids
    generate_ports: list[Port] = [
        artifact_port("image", "ui/inventory_panel.raw.png", UI_PANEL_RAW_KIND)
    ]
    if attempts_port is not None:
        generate_ports.append(attempts_port(generate_id))
    generated = builder.add(
        types.generate,
        generate_id,
        domain=domain,
        description="generate the authored inventory panel presentation",
        depends_on=tuple(depends_on),
        cache_depends_on=(),
        input_digests=(
            direction_digest,
            object_digest({"contract": INVENTORY_PANEL_CONTRACT_VERSION}),
            object_digest(panel.model_dump(mode="json")),
            *(references[reference_id].source_sha256 for reference_id in panel.reference_ids),
            template_sha256,
        ),
        ports=tuple(generate_ports),
        card=NodeCard(template_ref=INVENTORY_TEMPLATE_REF),
    )
    validated = builder.add(
        types.validate,
        validate_id,
        domain=domain,
        description="validate opaque panel and slot interiors on a transparent exterior",
        depends_on=(generated.node_id,),
        input_digests=(
            object_digest({"contract": INVENTORY_PANEL_CONTRACT_VERSION}),
            object_digest(panel.model_dump(mode="json")),
        ),
        ports=(
            artifact_port("image", "ui/inventory_panel.png", UI_PANEL_KIND),
            record_port(
                "validation", "ui/inventory_panel.validation.json", UI_PANEL_VALIDATION_KIND
            ),
            artifact_port("evidence", "ui/inventory_panel.evidence.png", UI_PANEL_EVIDENCE_KIND),
        ),
        card=NodeCard(reference_inputs=(PortRef(node_id=generated.node_id, port_id="image"),)),
        duration_seconds=0.75,
    )
    review_ports: list[Port] = [
        artifact_port("verdict", "ui/inventory_panel.review.json", REVIEW_VERDICT_KIND)
    ]
    if attempts_port is not None:
        review_ports.append(attempts_port(review_id))
    return builder.add(
        types.review,
        review_id,
        domain=domain,
        description="review inventory readability, style, and filled slot surfaces",
        depends_on=(validated.node_id,),
        input_digests=(
            object_digest({"contract": INVENTORY_PANEL_REVIEW_VERSION}),
            object_digest(panel.model_dump(mode="json")),
        ),
        ports=tuple(review_ports),
        card=NodeCard(
            schema_name=INVENTORY_REVIEW_SCHEMA_NAME,
            reference_inputs=(PortRef(node_id=validated.node_id, port_id="image"),),
        ),
    ).node_id


# ------------------------------------------------------------------- gate


def validate_inventory_panel_image(data: bytes) -> dict[str, object]:
    """Admit a painted panel: transparent exterior, opaque core, opaque slot interiors."""

    with Image.open(io.BytesIO(data)) as opened:
        if "A" not in opened.getbands():
            raise ValueError("inventory panel output must carry an alpha channel")
        image = opened.convert("RGBA")
    if image.size != (INVENTORY_CANVAS_WIDTH, INVENTORY_CANVAS_HEIGHT):
        raise ValueError(
            "inventory panel output must be exactly "
            f"{INVENTORY_CANVAS_WIDTH}x{INVENTORY_CANVAS_HEIGHT}"
        )
    alpha = image.getchannel("A")
    extrema = cast(tuple[int, int], alpha.getextrema())
    opaque_admission_min = 250
    transparent_admission_max = 16
    if extrema[0] > transparent_admission_max or extrema[1] < opaque_admission_min:
        raise ValueError("inventory panel must contain transparent exterior and opaque artwork")
    border = [
        *alpha.crop((0, 0, alpha.width, 1)).get_flattened_data(),
        *alpha.crop((0, alpha.height - 1, alpha.width, alpha.height)).get_flattened_data(),
        *alpha.crop((0, 0, 1, alpha.height)).get_flattened_data(),
        *alpha.crop((alpha.width - 1, 0, alpha.width, alpha.height)).get_flattened_data(),
    ]
    if max(border) > transparent_admission_max:
        raise ValueError("inventory panel exterior must remain transparent at the canvas border")

    transparent_pixels = sum(alpha.histogram()[: transparent_admission_max + 1])
    transparent_pixel_fraction = transparent_pixels / (alpha.width * alpha.height)
    if transparent_pixel_fraction < 0.1:
        raise ValueError("inventory panel must retain meaningful transparent exterior space")

    core_inset = 32
    core = alpha.crop(
        (
            INVENTORY_PANEL_LEFT + core_inset,
            INVENTORY_PANEL_TOP + core_inset,
            INVENTORY_PANEL_LEFT + INVENTORY_PANEL_WIDTH - core_inset,
            INVENTORY_PANEL_TOP + INVENTORY_PANEL_HEIGHT - core_inset,
        )
    )
    core_min = cast(tuple[int, int], core.getextrema())[0]
    if core_min < opaque_admission_min:
        raise ValueError(
            "inventory panel middle must be fully opaque; transparent or translucent pixels found"
        )

    slot_alpha_minima: list[int] = []
    slot_inset = 24
    for row in range(INVENTORY_SLOT_ROWS):
        for column in range(INVENTORY_SLOT_COLUMNS):
            left = (
                INVENTORY_SLOT_LEFT
                + column * (INVENTORY_SLOT_SIZE + INVENTORY_SLOT_GUTTER)
                + slot_inset
            )
            top = (
                INVENTORY_SLOT_TOP
                + row * (INVENTORY_SLOT_SIZE + INVENTORY_SLOT_GUTTER)
                + slot_inset
            )
            interior = alpha.crop(
                (
                    left,
                    top,
                    left + INVENTORY_SLOT_SIZE - 2 * slot_inset,
                    top + INVENTORY_SLOT_SIZE - 2 * slot_inset,
                )
            )
            slot_alpha_minima.append(cast(tuple[int, int], interior.getextrema())[0])
    if any(value < opaque_admission_min for value in slot_alpha_minima):
        raise ValueError(
            "every inventory slot interior must be visually opaque before normalization"
        )

    return {
        "width": image.width,
        "height": image.height,
        "alpha_min": extrema[0],
        "alpha_max": extrema[1],
        "border_alpha_max": max(border),
        "transparent_pixel_fraction": round(transparent_pixel_fraction, 6),
        "panel_core_alpha_min": core_min,
        "slot_interior_alpha_minima": slot_alpha_minima,
        "opaque_admission_min": opaque_admission_min,
        "transparent_admission_max": transparent_admission_max,
        "all_slot_interiors_opaque": True,
        "pixel_rewrite_performed": False,
    }


def canonicalize_inventory_panel_image(data: bytes) -> tuple[bytes, dict[str, object]]:
    """Normalize only the admitted alpha boundary: clear the exterior, clamp the core."""

    source_facts = validate_inventory_panel_image(data)
    with Image.open(io.BytesIO(data)) as opened:
        image = opened.convert("RGBA")
    alpha = image.getchannel("A")

    transparent_admission_max = cast(int, source_facts["transparent_admission_max"])
    alpha = alpha.point(lambda value: 0 if value <= transparent_admission_max else value)
    core_inset = 32
    alpha.paste(
        255,
        (
            INVENTORY_PANEL_LEFT + core_inset,
            INVENTORY_PANEL_TOP + core_inset,
            INVENTORY_PANEL_LEFT + INVENTORY_PANEL_WIDTH - core_inset,
            INVENTORY_PANEL_TOP + INVENTORY_PANEL_HEIGHT - core_inset,
        ),
    )
    image.putalpha(alpha)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False)
    canonical_data = output.getvalue()
    canonical_facts = validate_inventory_panel_image(canonical_data)
    return canonical_data, {
        "source": source_facts,
        "canonical": canonical_facts,
        "pixel_rewrite_performed": True,
        "pixel_rewrite": "alpha_boundary_normalization_v1",
    }


def checkerboard(size: tuple[int, int]) -> Image.Image:
    """The review backdrop: a neutral checker that makes transparency legible to a judge."""

    image = Image.new("RGBA", size, (220, 220, 220, 255))
    draw = ImageDraw.Draw(image)
    block = 20
    for y in range(0, size[1], block):
        for x in range(0, size[0], block):
            if (x // block + y // block) % 2:
                draw.rectangle((x, y, x + block - 1, y + block - 1), fill=(174, 174, 174, 255))
    return image


def inventory_panel_evidence(data: bytes) -> bytes:
    with Image.open(io.BytesIO(data)) as opened:
        panel = opened.convert("RGBA")
    canvas = checkerboard(panel.size)
    canvas.alpha_composite(panel)
    stream = io.BytesIO()
    canvas.convert("RGB").save(stream, format="PNG", optimize=False)
    return stream.getvalue()


# ----------------------------------------------------------------- handler


@dataclass(frozen=True)
class InventoryPanelHost:
    """Everything the triplet needs from whichever recipe hosts it."""

    #: The UI document, the run, the package's files and the host's identities.
    ui: UiAtlasHost
    #: The host's art direction wrapped around the panel task.
    frame_prompt: Callable[[str], str]
    #: The layout template every panel is painted over.
    template_path: Path


class InventoryPanelHandlers:
    """The three coroutines behind the inventory node types, owned by no recipe."""

    def __init__(
        self,
        host: InventoryPanelHost,
        *,
        graph: Graph,
        image_service: ImageGenerationService,
        structured_service: StructuredGenerationService[object],
        provider_call: ProviderCall | None = None,
    ) -> None:
        self._host = host
        self._graph = graph
        self._images = image_service
        self._structured = structured_service
        self._provider_call = provider_call

    async def generate(self, node: Node) -> NodeExecutionResult:
        ui = self._host.ui
        panel = ui.ui.required_inventory_panel()
        output = ui.run_dir / node.port("image").artifact_ref
        template_data = self._host.template_path.read_bytes()
        prompt = self._host.frame_prompt(
            "Create one inventory panel for the game's screen-fixed interface.\n"
            f"Authored direction: {panel.prompt}\n"
            "Use the supplied layout template as the exact geometry authority: one 1536 by 1024 "
            "canvas, one outer panel, and eight empty slots in a strict four-column by two-row "
            "layout. Preserve the template's panel and slot positions. The template is layout "
            "guidance, not the requested visual style. Keep the canvas exterior outside the panel "
            "transparent. The entire panel body and every empty slot well must be solid, filled, "
            "and fully opaque alpha 255. Do not cut transparent or semi-transparent holes into "
            "the panel middle or any slot interior. Slots may look recessed through opaque color "
            "and shading only. Keep the canvas border and empty space beyond the decorated panel "
            "silhouette clear alpha 0. No exterior glow, drop shadow, color wash, backdrop, or "
            "scenery. Straps, leaves, corners, and ornaments may shape the panel silhouette. No "
            "items, text, numbers, labels, icons, cursor, character, logo, signature, or watermark."
        )
        references = (
            *self._image_references(panel.reference_ids),
            ImageReference(
                url=data_url(template_data, "image/png"),
                provenance_ref=(
                    "resource://fixtures/image_gen_templates/inventory_template.png"
                    f"#sha256={content_sha256(template_data)}"
                ),
            ),
        )
        request = ImageGenerationRequest(
            prompt=prompt,
            artifact_path=output,
            input_references=references,
            quality="high",
            background="transparent",
            output_format="png",
            size="1536x1024",
            timeout_seconds=600,
            metadata={
                "checkpoint": "ui",
                "role": "inventory_panel",
                "layout": panel.layout,
                "alpha_policy": panel.alpha_policy,
            },
            validate=lambda artifact: validate_inventory_panel_image(artifact.data),
        )
        result = await self._call(
            node, "inventory_panel", prompt, lambda: self._images.generate(request)
        )
        return node_result(
            ui.run_dir, node, attempts=result.attempts, provider_operations=result.attempts
        )

    async def validate(self, node: Node) -> NodeExecutionResult:
        run_dir = self._host.ui.run_dir
        source = run_dir / self._dependency(node, kind=UI_PANEL_RAW_KIND)
        data = source.read_bytes()
        canonical_data, facts = canonicalize_inventory_panel_image(data)
        canonical = run_dir / node.port("image").artifact_ref
        await write_local_image(
            canonical,
            canonical_data,
            prompt=(
                "Normalize only the admitted alpha boundary: clear the already-transparent "
                "exterior and clamp the already-opaque panel core and slot interiors to alpha 255."
            ),
            inputs=((source.relative_to(run_dir).as_posix(), data),),
            validation=facts,
            model=INVENTORY_PANEL_VALIDATION_VERSION,
            component=self._host.ui.component,
            handler_version=self._host.ui.component.version,
        )
        atomic_write_json(
            run_dir / node.port("validation").artifact_ref,
            {
                "schema_version": 1,
                "kind": INVENTORY_PANEL_VALIDATION_VERSION,
                **inventory_panel_layout_contract(),
                **facts,
            },
        )
        await write_local_image(
            run_dir / node.port("evidence").artifact_ref,
            inventory_panel_evidence(canonical_data),
            prompt="Composite the inventory panel over a checkerboard for review evidence.",
            inputs=((canonical.relative_to(run_dir).as_posix(), data),),
            validation={"source_validation": facts, "checkerboard_only": True},
            model=INVENTORY_PANEL_EVIDENCE_VERSION,
            component=self._host.ui.component,
            handler_version=self._host.ui.component.version,
        )
        return node_result(run_dir, node)

    async def review(self, node: Node) -> NodeExecutionResult:
        ui = self._host.ui
        panel = ui.ui.required_inventory_panel()
        evidence = ui.run_dir / self._dependency(node, kind=UI_PANEL_EVIDENCE_KIND)
        selected = set(panel.reference_ids)
        references: list[StructuredReference] = [
            StructuredReference(
                url=data_url(evidence.read_bytes(), "image/png"),
                provenance_ref=f"run://{evidence.relative_to(ui.run_dir).as_posix()}",
            )
        ]
        references.extend(
            self._package_reference(reference.source)
            for reference in ui.ui.references
            if reference.reference_id in selected
        )
        prompt = (
            "Review the generated inventory panel against its authored direction and the "
            "exact four-column by two-row layout. Image 1 is the generated panel composited "
            "over a checkerboard; remaining images are authored visual references. "
            "Deterministic pixel validation has already proved a transparent canvas border, "
            "a fully opaque panel core, and fully opaque interiors for all eight slots. "
            "Do not mistake the checkerboard outside the panel for artwork. Judge style "
            "coherence, eight-slot readability, consistent visual hierarchy, clean exterior "
            "silhouette, and absence of items, text, pseudo-text, labels, logos, or scenery. "
            f"Authored direction: {panel.prompt} Uncertainty must not be called accept."
        )
        request: StructuredGenerationRequest[object] = StructuredGenerationRequest(
            prompt=prompt,
            system=(
                "You are a strict independent 2D game-art technical director. Return only the "
                "requested structured review."
            ),
            artifact_path=ui.run_dir / node.port("verdict").artifact_ref,
            schema=StructuredOutputSchema(
                name=INVENTORY_REVIEW_SCHEMA_NAME,
                json_schema=ui_atlas_review_schema(INVENTORY_REVIEW_CHECKS),
            ),
            parse=_parse_review,
            references=tuple(references),
            max_tokens=1800,
            timeout_seconds=600,
            metadata={"checkpoint": "ui", "role": "inventory_panel"},
        )
        result = await self._call(
            node, "inventory_panel", prompt, lambda: self._structured.generate(request)
        )
        return node_result(
            ui.run_dir, node, attempts=result.attempts, provider_operations=result.attempts
        )

    # ----------------------------------------------------------------- shared

    async def _call(self, node: Node, label: str, prompt: str, thunk: Callable[[], Any]) -> Any:
        if self._provider_call is None:
            return await thunk()
        return await self._provider_call(node, label, prompt, thunk)

    def _dependency(self, node: Node, *, kind: str) -> str:
        _producer, port = dependency_port(self._graph, node, kind=kind)
        return port.artifact_ref

    def _image_references(self, reference_ids: Sequence[str]) -> tuple[ImageReference, ...]:
        ui = self._host.ui
        by_id = {entry.reference_id: entry for entry in ui.ui.references}
        values = []
        for reference_id in reference_ids:
            source = by_id[reference_id].source
            package_file = ui.file(source)
            values.append(
                ImageReference(
                    url=data_url(package_file.data, _media_type(source)),
                    provenance_ref=(
                        f"package://{ui.package_id}/{source}#sha256={package_file.sha256}"
                    ),
                )
            )
        return tuple(values)

    def _package_reference(self, source: str) -> StructuredReference:
        ui = self._host.ui
        package_file = ui.file(source)
        return StructuredReference(
            url=data_url(package_file.data, _media_type(source)),
            provenance_ref=f"package://{ui.package_id}/{source}#sha256={package_file.sha256}",
        )


def _media_type(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"


def _parse_review(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("verdict") not in {
        "accept",
        "reject",
        "uncertain",
    }:
        raise ValueError("inventory panel review has an invalid verdict")
    return value


__all__ = [
    "INVENTORY_PANEL_CONTRACT_VERSION",
    "INVENTORY_PANEL_EVIDENCE_VERSION",
    "INVENTORY_PANEL_REVIEW_VERSION",
    "INVENTORY_PANEL_VALIDATION_VERSION",
    "INVENTORY_REVIEW_CHECKS",
    "INVENTORY_REVIEW_SCHEMA_NAME",
    "INVENTORY_TEMPLATE_REF",
    "REVIEW_VERDICT_KIND",
    "UI_INVENTORY_GENERATE",
    "UI_INVENTORY_REVIEW",
    "UI_INVENTORY_VALIDATE",
    "UI_PANEL_EVIDENCE_KIND",
    "UI_PANEL_KIND",
    "UI_PANEL_RAW_KIND",
    "UI_PANEL_VALIDATION_KIND",
    "InventoryNodeTypes",
    "InventoryPanelHandlers",
    "InventoryPanelHost",
    "add_inventory_panel_nodes",
    "canonicalize_inventory_panel_image",
    "checkerboard",
    "inventory_node_types",
    "inventory_panel_evidence",
    "validate_inventory_panel_image",
]
