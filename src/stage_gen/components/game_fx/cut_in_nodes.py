"""The cut-in node family: plate, draw, validate, place, review.

One portrait plate becomes a framed cut-in through a deterministic draw, a pixel gate,
a tool-loop placement and a structured review; the host binds the five coroutines.
"""

from __future__ import annotations

import io
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, cast

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
    NodeType,
    Port,
    PortRef,
    StructuredGenerationRequest,
    StructuredGenerationService,
    StructuredOutputSchema,
    StructuredReference,
    Tool,
    ToolInvocationError,
    ToolLoopReference,
    ToolLoopRequest,
    ToolLoopService,
    ToolResult,
    ViewArchetype,
    atomic_write_json,
    dependency_port,
)
from stage_gen.canonical import content_sha256
from stage_gen.components._node_kit import (
    ProviderCall,
    artifact_port,
    card_prompt,
    node_result,
    object_digest,
    record_port,
)
from stage_gen.components.game_fx._host import (
    _P,
    _PLATE_COMMON,
    _PROVIDER,
    _RENDER_STAGE,
    _RENDER_WIDTH,
    _START_SCALE,
    IMAGE_FEATURES,
    STRUCTURED_FEATURES,
    TOOL_LOOP_FEATURES,
    FxCutInHost,
    _authored_references,
    _media_type,
    _produced_reference,
    _write_local_image,
    cut_in_direction,
    subject_port,
)
from stage_gen.components.game_fx.cut_in import (
    CUT_IN_FRAME,
    CUT_IN_PLACEMENT_KIND,
    CUT_IN_PORTRAIT,
    PLACEMENT_CENTRE_RANGE,
    PLACEMENT_SCALE_RANGE,
    CutInPlate,
    admit_cut_in_placement,
    canonicalize_plate,
    compose_hold_frame,
    cut_in_evidence,
    cut_in_plate_contract,
    draw_procedural_frame,
    mask_reveal_facts,
    placement_transform,
    validate_frame_plate,
    validate_portrait_plate,
)
from stage_gen.components.game_fx.models import (
    CutInPortraitDirection,
    CutInPortraitSubject,
    GameFx,
)
from stage_gen.media import data_url

#: The generate node's cache contract: what the model is asked to paint. Bumping it
#: re-bills every plate, so measured facts the local gate reads live under the
#: validation version instead. The validation version is per role: the portrait's
#: record gained its placement, the frame's did not, and one shared constant would
#: rekey the frame's review through lineage for nothing.
FX_CUT_IN_CONTRACT_VERSION = "prepared-fx-cut-in-v2"
FX_CUT_IN_DRAW_VERSION = "prepared-fx-cut-in-draw-v1"
FX_CUT_IN_FRAME_VALIDATION_VERSION = "prepared-fx-cut-in-validation-v3"
FX_CUT_IN_PORTRAIT_VALIDATION_VERSION = "prepared-fx-cut-in-validation-v3"
FX_CUT_IN_PLACE_VERSION = "prepared-fx-cut-in-place-v1"
FX_CUT_IN_REVIEW_VERSION = "prepared-fx-cut-in-review-v2"
FX_CUT_IN_EVIDENCE_VERSION = "prepared-fx-cut-in-evidence-v3"
FX_CUT_IN_REVIEW_SCHEMA_NAME = "prepared_fx_cut_in_review"
FX_CUT_IN_PLACE_SCHEMA_NAME = "prepared_fx_cut_in_place"

FX_CUT_IN_RAW_KIND = "fx-cut-in-raw-v1"
FX_CUT_IN_PLATE_KIND = "fx-cut-in-plate-v1"
FX_CUT_IN_PLACEMENT_KIND = CUT_IN_PLACEMENT_KIND
FX_CUT_IN_VALIDATION_KIND = "fx-cut-in-validation-v1"
FX_CUT_IN_EVIDENCE_KIND = "fx-cut-in-evidence-v1"
FX_CUT_IN_VERDICT_KIND = "review-verdict-v1"

#: The placement episode's budget. Six looks is what an art director needs to settle
#: a scale and a centre; the token ceiling bounds a runaway transcript of images.
FX_CUT_IN_PLACE_MAX_STEPS = 6
FX_CUT_IN_PLACE_MAX_TOTAL_TOKENS = 300_000

FX_CUT_IN_GENERATE = NodeType(
    type_id=f"{_P}/cut_in.generate",
    title="Cut-in plate",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="fx-cut-in-v1",
)

FX_CUT_IN_DRAW = NodeType(
    type_id=f"{_P}/cut_in.draw",
    title="Procedural cut-in frame",
    archetype=ViewArchetype.IMAGE,
    operation="local",
    contract_version="fx-cut-in-draw-v1",
)

FX_CUT_IN_VALIDATE = NodeType(
    type_id=f"{_P}/cut_in.validate",
    title="Cut-in plate admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="fx-cut-in-validate-v1",
)

FX_CUT_IN_PLACE = NodeType(
    type_id=f"{_P}/cut_in.place",
    title="Cut-in portrait placement",
    archetype=ViewArchetype.JUDGE,
    operation="tool_loop",
    features=TOOL_LOOP_FEATURES,
    policy=_PROVIDER,
    contract_version="fx-cut-in-place-v1",
)

FX_CUT_IN_REVIEW = NodeType(
    type_id=f"{_P}/cut_in.review",
    title="Cut-in plate review",
    archetype=ViewArchetype.JUDGE,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=_PROVIDER,
    contract_version="fx-cut-in-review-v1",
)

#: Every type this module owns, for a recipe's own type census and registry checks.
FX_CUT_IN_NODE_TYPES = (
    FX_CUT_IN_GENERATE,
    FX_CUT_IN_DRAW,
    FX_CUT_IN_PLACE,
    FX_CUT_IN_VALIDATE,
    FX_CUT_IN_REVIEW,
)

#: The shape an unopinionated game gets. An authored ``cut_in.frame.shape`` replaces it
#: outright rather than arguing with it, so the two can never contradict each other in
#: one prompt; everything around the slot is the invariant a plate must hold whatever
#: its silhouette is.
_FRAME_SHAPE_DEFAULT = (
    "One connected, wide, slightly tilted ragged strip that runs across the entire canvas "
    "from the left edge to the right edge, cut off by both edges, occupying roughly half the "
    "canvas height, with rough hand-torn jagged edges along its top and its bottom."
)

#: The frame around the slot says paper, ink and emptiness — never how the edge is cut.
#: It used to open "one torn-paper rip" and end on "hugging its torn edges", which outvoted
#: an authored shape three to one: two live rejects in a row said the silhouette came back
#: conventionally ragged however clearly the shape asked for clean facets. Edge character
#: belongs to exactly one sentence, and the default one still says hand-torn.
_FRAME_TASK = (
    "Create one paper cut-out silhouette to be used as a game cut-in frame. {shape} It must "
    "read as a single bold graphic element that carries the width of the screen. Fill it with "
    "flat pure white only, and draw a thick uneven black hand-inked outline hugging its "
    "edges, following their shape exactly. Nothing at all inside it: no drawing, no "
    "character, no texture, no shadow, no gradient, no colour. Flat graphic 2D, bold "
    "print-poster cut-out look."
)

_PORTRAIT_TASK = (
    "Create one die-cut character plate for a game cut-in: a tight close-up of the character "
    "in the references, head, hair, neck and collar only, filling the canvas so the hair is "
    "cropped by the top and both side edges and the collar by the bottom edge. Identity comes "
    "from the references alone: exactly that face, eyes, hair, and accessories, at the same "
    "age and proportions as shown. Bold clean ink contours and cel shading, slightly tilted "
    "dynamic angle, eyes toward the viewer. The plate has a clean alpha edge along the "
    "silhouette."
)


def frame_content_task(direction: str, shape: str | None = None) -> str:
    task = _FRAME_TASK.format(shape=shape or _FRAME_SHAPE_DEFAULT)
    return f"{task}\nAuthored direction: {direction}\n{_PLATE_COMMON}"


#: The same plate for an actor the run draws itself. Everything the human portrait
#: takes from an authored face - the identity, the proportions, what a "close-up" even
#: means for this body - this one takes from the concept plate the graph hands it as
#: image 1, so it never has to be described twice and cannot be described differently.
#: The connectedness clause leads rather than trails because the plate gate admits one
#: dominant shape: a machine's hanging parts are exactly what drifts off into debris,
#: and a demand made late in a prompt is the one that gets dropped.
_SUBJECT_TASK = (
    "Create one die-cut plate for a game cut-in: a tight close-up of the front of the "
    "subject in image 1, drawn as one connected mass with every hanging or trailing part "
    "touching the body rather than floating apart, filling the canvas so its silhouette "
    "is cropped by the top and by both side edges. Identity comes from image 1 alone: "
    "exactly that build, those markings, colours, and fittings, in the same proportions, "
    "turned so that whatever on it reads as a face - a lens, a head, a mouth of tools - "
    "faces the viewer. Bold clean ink contours and cel shading, slightly tilted dynamic "
    "angle. The plate has a clean alpha edge along the silhouette."
)


def portrait_content_task(direction: str) -> str:
    return f"{_PORTRAIT_TASK}\nExpression and mood: {direction}\n{_PLATE_COMMON}"


def subject_content_task(direction: str) -> str:
    return f"{_SUBJECT_TASK}\nMoment and mood: {direction}\n{_PLATE_COMMON}"


_PLACE_TASK = (
    "Place this character portrait inside the torn-strip cut-in frame so the composition "
    "reads like a production cut-in. The face should fill the band: eyes in the band's "
    "upper-middle, the mouth fully inside the band, the head neither floating in empty "
    "backdrop nor so large that the eyes or mouth are cut by the torn edges. Hair, ears, "
    "and shoulders may bleed past the edges; that is the look. Prefer the face over the "
    "band's thickest stretch. Iterate: render a placement, look at it, adjust the scale "
    "and the centre, and submit only a placement you have rendered and seen."
)

_PLACE_SYSTEM = (
    "You are a 2D game presentation art director. You place a die-cut portrait plate "
    "inside a torn-strip frame by trying placements with the render tool and judging the "
    "result with your eyes. Every turn calls a tool; finish with submit."
)


#: A subject plate has no eyes or mouth to keep inside the band, so the same
#: instruction is written against the parts it does have.
_PLACE_SUBJECT_TASK = (
    "Place this cut-out subject plate inside the torn-strip cut-in frame so the "
    "composition reads like a production cut-in. The subject should fill the band: the "
    "part of it that reads as a face over the band's upper-middle, the body fully inside "
    "the band, neither floating in empty backdrop nor so large that the front of it is "
    "cut away by the torn edges. Outlying parts may bleed past the edges; that is the "
    "look. Prefer the subject over the band's thickest stretch. Iterate: render a "
    "placement, look at it, adjust the scale and the centre, and submit only a placement "
    "you have rendered and seen."
)


def place_content_task(
    portrait_id: str, direction: str, *, subject: CutInPortraitSubject | None = None
) -> str:
    task = _PLACE_TASK if subject is None else _PLACE_SUBJECT_TASK
    return f"{task}\nPortrait: {portrait_id}. Its authored mood: {direction}"


def cut_in_review_prompt(
    plate: CutInPlate,
    direction: str,
    shape: str | None = None,
    *,
    subject: CutInPortraitSubject | None = None,
) -> str:
    """What the judge is asked, given what the pixel gate has already proved.

    The gate no longer fixes the rip's topology, so the frame's silhouette is judged
    here, against the shape its author asked for."""

    if plate.role == "frame":
        return (
            "Review the generated cut-in frame plate against its authored direction. Image 1 "
            "shows the plate over a checkerboard on the left and, on the right, the plate "
            "composed the way the game shows it: a flat backdrop with stripes revealed through "
            "the plate's silhouette. Remaining images are authored visual references. "
            "Deterministic pixel validation has already proved a transparent exterior with a "
            "binary edge, few enough pieces and no debris, a flat white fill, and an inked "
            "rim. It did not judge the silhouette; you do. Do not mistake the checkerboard "
            "for artwork. Judge style coherence with the references, that the plate reads as "
            "a torn cut-out rather than a drawn frame, that its silhouette is the authored "
            "shape and carries the screen's width, that the rim is ink and not a glow, and "
            "the absence of text, pseudo-text, characters, or scenery. Authored shape: "
            f"{shape or _FRAME_SHAPE_DEFAULT} Authored direction: {direction} Uncertainty "
            "must not be called accept."
        )
    if subject is not None:
        return (
            "Review the generated cut-in subject plate against its authored direction. Image 1 "
            "shows the plate over a checkerboard on the left and, on the right, the plate "
            "composed inside the game's cut-in frame exactly as the game shows it. Image 2 is "
            "the identity concept plate of the very subject this cut-in announces, drawn in "
            "the same run; any remaining images are authored style references. Deterministic "
            "pixel validation has already proved a transparent exterior with no painted "
            "backdrop and one dominant shape. Do not mistake the checkerboard for artwork. "
            "Judge that the build, markings, colours and fittings are unmistakably the same "
            "subject as image 2 rather than another of its kind, that it is drawn close and "
            "cropped by the canvas rather than floating small in it, that the mood matches the "
            "direction, and the absence of text, pseudo-text, logos, or scenery. Authored "
            f"direction: {direction} Uncertainty must not be called accept."
        )
    return (
        "Review the generated cut-in portrait plate against its authored direction. Image 1 "
        "shows the plate over a checkerboard on the left and, on the right, the plate composed "
        "inside the game's cut-in frame exactly as the game shows it. Remaining images are the "
        "authored character references. Deterministic pixel validation has already proved a "
        "transparent exterior with no painted backdrop and one subject. Do not mistake the "
        "checkerboard for artwork. Judge that the face, hair, eyes and accessories are the "
        "same character as the references, that the expression matches the direction, that "
        "the head is cropped by the canvas rather than floating, and the absence of text, "
        f"pseudo-text, logos, or scenery. Authored direction: {direction} Uncertainty must "
        "not be called accept."
    )


def plate_id_for(role: str, portrait_id: str | None = None) -> str:
    return "frame" if role == "frame" else f"portrait-{portrait_id}"


def cut_in_node_ids(plate_id: str, *, prefix: str = "fx") -> tuple[str, str, str, str, str]:
    """The generate/draw, place, validate and review ids one plate occupies in a host graph."""

    base = f"{prefix}-cut_in-{plate_id}"
    return (
        f"{base}-generate",
        f"{base}-draw",
        f"{base}-place",
        f"{base}-validate",
        f"{base}-review",
    )


def cut_in_artifact_refs(plate_id: str) -> tuple[str, str, str, str, str, str]:
    """Every path one plate writes: raw, canonical, placement, validation, evidence, verdict."""

    name = plate_id.replace("portrait-", "portrait.", 1)
    return (
        f"fx/cut_in/{name}.raw.png",
        f"fx/cut_in/{name}.png",
        f"fx/cut_in/{name}.placement.json",
        f"fx/cut_in/{name}.validation.json",
        f"fx/cut_in/{name}.evidence.png",
        f"fx/cut_in/{name}.review.json",
    )


def add_cut_in_nodes(
    builder: GraphBuilder,
    *,
    root: str,
    fx: GameFx,
    style_prompt: Callable[[str], str],
    direction_digests: Sequence[str] = (),
    domain: str = "fx",
    prefix: str = "fx",
    attempts_port: Callable[[str], Port] | None = None,
    subject_reference: Callable[[CutInPortraitSubject], PortRef] | None = None,
) -> list[str]:
    """Add the frame and every portrait the document declares.

    The frame is generated or drawn per its declared mode; either way it is validated
    into the same plate kind and the same polygon record. A portrait is placed inside the
    frame's band by the tool-loop agent before it is validated, and its validation depends
    on both, so its reviewer sees the exact composition a runtime shows. Returns the
    terminal ids a host adds to its own list.

    ``subject_reference`` resolves a portrait's declared subject to the port of the node
    that draws it. A host that supplies none draws no actors, so a document naming one is
    refused here, while the graph is still being built and before any spend.
    """

    if fx.cut_in is None:
        return []
    references = {entry.reference_id: entry for entry in fx.references}

    def authored_for(reference_ids: Sequence[str]) -> tuple[AuthoredInput, ...]:
        # An input that reaches a provider is never invisible in the plan: the card
        # names each authored reference and the bytes it binds.
        return tuple(
            AuthoredInput(
                label=reference_id,
                ref=references[reference_id].source,
                sha256=references[reference_id].source_sha256,
            )
            for reference_id in reference_ids
        )

    terminals: list[str] = []
    frame = fx.cut_in.frame
    frame_geometry = object_digest(CUT_IN_FRAME.geometry_record())
    frame_direction = object_digest(frame.model_dump(mode="json"))
    generate_id, draw_id, _place_id, validate_id, review_id = cut_in_node_ids(
        "frame", prefix=prefix
    )
    raw_ref, plate_ref, _placement_ref, validation_ref, evidence_ref, verdict_ref = (
        cut_in_artifact_refs("frame")
    )
    params: dict[str, str] = {"plate": "frame"}
    if frame.mode == "generated_v1":
        authored = authored_for(frame.reference_ids)
        ports: list[Port] = [artifact_port("image", raw_ref, FX_CUT_IN_RAW_KIND)]
        if attempts_port is not None:
            ports.append(attempts_port(generate_id))
        producer = builder.add(
            FX_CUT_IN_GENERATE,
            generate_id,
            domain=domain,
            description="generate the authored cut-in frame plate",
            depends_on=(root,),
            cache_depends_on=(),
            params=params,
            input_digests=(
                *direction_digests,
                object_digest({"contract": FX_CUT_IN_CONTRACT_VERSION}),
                frame_direction,
                *(entry.sha256 for entry in authored),
                frame_geometry,
            ),
            ports=tuple(ports),
            card=NodeCard(
                prompt=style_prompt(frame_content_task(frame.prompt or "", frame.shape)),
                authored_inputs=authored,
            ),
        )
    else:
        producer = builder.add(
            FX_CUT_IN_DRAW,
            draw_id,
            domain=domain,
            description="draw the procedural cut-in frame plate",
            depends_on=(root,),
            cache_depends_on=(),
            params=params,
            input_digests=(
                object_digest({"contract": FX_CUT_IN_DRAW_VERSION}),
                frame_direction,
                frame_geometry,
            ),
            ports=(artifact_port("image", raw_ref, FX_CUT_IN_RAW_KIND),),
            duration_seconds=1.0,
        )
    frame_validated = builder.add(
        FX_CUT_IN_VALIDATE,
        validate_id,
        domain=domain,
        description="admit the frame plate, clear its exterior, and measure its mask",
        depends_on=(producer.node_id,),
        params=params,
        input_digests=(
            object_digest({"contract": FX_CUT_IN_FRAME_VALIDATION_VERSION}),
            frame_geometry,
        ),
        ports=(
            artifact_port("image", plate_ref, FX_CUT_IN_PLATE_KIND),
            record_port("validation", validation_ref, FX_CUT_IN_VALIDATION_KIND),
            artifact_port("evidence", evidence_ref, FX_CUT_IN_EVIDENCE_KIND),
        ),
        card=NodeCard(reference_inputs=(PortRef(node_id=producer.node_id, port_id="image"),)),
        duration_seconds=2.0,
    )
    if frame.mode == "generated_v1":
        review_ports: list[Port] = [artifact_port("verdict", verdict_ref, FX_CUT_IN_VERDICT_KIND)]
        if attempts_port is not None:
            review_ports.append(attempts_port(review_id))
        reviewed = builder.add(
            FX_CUT_IN_REVIEW,
            review_id,
            domain=domain,
            description="review the frame plate's style and torn-edge reading",
            depends_on=(frame_validated.node_id,),
            params=params,
            input_digests=(
                object_digest({"contract": FX_CUT_IN_REVIEW_VERSION}),
                frame_direction,
            ),
            ports=tuple(review_ports),
            card=NodeCard(
                prompt=cut_in_review_prompt(CUT_IN_FRAME, frame.prompt or "", frame.shape),
                schema_name=FX_CUT_IN_REVIEW_SCHEMA_NAME,
                reference_inputs=(PortRef(node_id=frame_validated.node_id, port_id="image"),),
                authored_inputs=authored_for(frame.reference_ids),
            ),
        )
        terminals.append(reviewed.node_id)
    else:
        terminals.append(frame_validated.node_id)

    portrait_geometry = object_digest(CUT_IN_PORTRAIT.geometry_record())
    for portrait in fx.cut_in.portraits:
        plate_id = plate_id_for("portrait", portrait.portrait_id)
        # Absent fields are absent from the digest, so a portrait that declares no
        # subject keeps the cache key it had before subjects existed. What a plate
        # does not say cannot re-bill it.
        direction_digest = object_digest(portrait.model_dump(mode="json", exclude_none=True))
        generate_id, _draw_id, place_id, validate_id, review_id = cut_in_node_ids(
            plate_id, prefix=prefix
        )
        raw_ref, plate_ref, placement_ref, validation_ref, evidence_ref, verdict_ref = (
            cut_in_artifact_refs(plate_id)
        )
        params = {"plate": "portrait", "portrait_id": portrait.portrait_id}
        authored = authored_for(portrait.reference_ids)
        subject = portrait.subject
        if subject is not None and subject_reference is None:
            raise ValueError(
                f"cut_in portrait {portrait.portrait_id} takes its identity from the "
                f"{subject.actor_id!r} {subject.kind} plate, which this genre does not draw"
            )
        # The drawn subject is lineage, not a digest: its bytes are what the plate is
        # copied from, so the concept being redrawn has to re-key the portrait. Every
        # other input is authored, and stays a digest.
        subject_port = None if subject is None else subject_reference(subject)  # type: ignore[misc]
        ports = [artifact_port("image", raw_ref, FX_CUT_IN_RAW_KIND)]
        if attempts_port is not None:
            ports.append(attempts_port(generate_id))
        generated = builder.add(
            FX_CUT_IN_GENERATE,
            generate_id,
            domain=domain,
            description=f"generate the {portrait.portrait_id} cut-in portrait plate",
            depends_on=(root,) if subject_port is None else (root, subject_port.node_id),
            cache_depends_on=() if subject_port is None else (subject_port.node_id,),
            params=params,
            input_digests=(
                *direction_digests,
                object_digest({"contract": FX_CUT_IN_CONTRACT_VERSION}),
                direction_digest,
                *(entry.sha256 for entry in authored),
                portrait_geometry,
            ),
            ports=tuple(ports),
            card=NodeCard(
                prompt=style_prompt(
                    portrait_content_task(portrait.prompt)
                    if subject is None
                    else subject_content_task(portrait.prompt)
                ),
                authored_inputs=authored,
                reference_inputs=() if subject_port is None else (subject_port,),
            ),
        )
        place_ports = [artifact_port("placement", placement_ref, FX_CUT_IN_PLACEMENT_KIND)]
        if attempts_port is not None:
            place_ports.append(attempts_port(place_id))
        placed = builder.add(
            FX_CUT_IN_PLACE,
            place_id,
            domain=domain,
            description=f"place the {portrait.portrait_id} portrait inside the frame's band",
            depends_on=(generated.node_id, frame_validated.node_id),
            params=params,
            input_digests=(
                object_digest({"contract": FX_CUT_IN_PLACE_VERSION}),
                portrait_geometry,
                frame_geometry,
            ),
            ports=tuple(place_ports),
            card=NodeCard(
                prompt=place_content_task(portrait.portrait_id, portrait.prompt, subject=subject),
                schema_name=FX_CUT_IN_PLACE_SCHEMA_NAME,
                reference_inputs=(
                    PortRef(node_id=generated.node_id, port_id="image"),
                    PortRef(node_id=frame_validated.node_id, port_id="image"),
                ),
            ),
        )
        validated = builder.add(
            FX_CUT_IN_VALIDATE,
            validate_id,
            domain=domain,
            description=f"admit the {portrait.portrait_id} portrait and compose it in the frame",
            depends_on=(generated.node_id, frame_validated.node_id, placed.node_id),
            params=params,
            input_digests=(
                object_digest({"contract": FX_CUT_IN_PORTRAIT_VALIDATION_VERSION}),
                portrait_geometry,
            ),
            ports=(
                artifact_port("image", plate_ref, FX_CUT_IN_PLATE_KIND),
                record_port("validation", validation_ref, FX_CUT_IN_VALIDATION_KIND),
                artifact_port("evidence", evidence_ref, FX_CUT_IN_EVIDENCE_KIND),
            ),
            card=NodeCard(reference_inputs=(PortRef(node_id=generated.node_id, port_id="image"),)),
            duration_seconds=2.0,
        )
        review_ports = [artifact_port("verdict", verdict_ref, FX_CUT_IN_VERDICT_KIND)]
        if attempts_port is not None:
            review_ports.append(attempts_port(review_id))
        reviewed = builder.add(
            FX_CUT_IN_REVIEW,
            review_id,
            domain=domain,
            description=f"review the {portrait.portrait_id} portrait's identity and expression",
            depends_on=(
                (validated.node_id,)
                if subject_port is None
                else (validated.node_id, subject_port.node_id)
            ),
            params=params,
            input_digests=(
                object_digest({"contract": FX_CUT_IN_REVIEW_VERSION}),
                direction_digest,
            ),
            ports=tuple(review_ports),
            card=NodeCard(
                prompt=cut_in_review_prompt(CUT_IN_PORTRAIT, portrait.prompt, subject=subject),
                schema_name=FX_CUT_IN_REVIEW_SCHEMA_NAME,
                # The judge is shown what the plate had to match: the composed plate
                # first, then the identity it was copied from.
                reference_inputs=(
                    (PortRef(node_id=validated.node_id, port_id="image"),)
                    if subject_port is None
                    else (
                        PortRef(node_id=validated.node_id, port_id="image"),
                        subject_port,
                    )
                ),
                authored_inputs=authored,
            ),
        )
        terminals.append(reviewed.node_id)
    return terminals


def cut_in_generate_request(
    host: FxCutInHost, graph: Graph, node: Node, *, read: Callable[[str], bytes]
) -> ImageGenerationRequest:
    """The exact image request one generate node sends: shared by the handler and by a
    host's provenance mirror, so the two can never disagree on identity.

    ``read`` resolves a run-relative artifact ref to bytes, for the drawn subject a
    portrait may take its identity from; a portrait without one never calls it."""

    plate, direction = cut_in_direction(host.fx, node)
    validate = validate_frame_plate if plate.role == "frame" else validate_portrait_plate
    metadata: dict[str, object] = {
        "checkpoint": "fx",
        "effect": "cut_in",
        "plate": plate.role,
        "layout": plate.layout,
        "alpha_policy": plate.alpha_policy,
    }
    if isinstance(direction, CutInPortraitDirection):
        metadata["portrait_id"] = direction.portrait_id
    port_ref = subject_port(node, direction)
    subject_references: tuple[ImageReference, ...] = ()
    if port_ref is not None and isinstance(direction, CutInPortraitDirection):
        subject = direction.subject
        artifact_ref, data = _produced_reference(graph, port_ref, read)
        # First, because the prompt calls it image 1: the identity the plate is drawn
        # from leads the authored style references it is drawn in.
        subject_references = (ImageReference(data_url(data, "image/png"), f"run://{artifact_ref}"),)
        if subject is not None:
            metadata["subject_id"] = subject.actor_id
    return ImageGenerationRequest(
        prompt=card_prompt(node),
        artifact_path=host.run_dir / node.port("image").artifact_ref,
        input_references=(
            *subject_references,
            *_authored_references(host, direction.reference_ids),
        ),
        quality="high",
        background="transparent",
        output_format="png",
        size=f"{plate.canvas[0]}x{plate.canvas[1]}",
        timeout_seconds=600,
        metadata=metadata,
        validate=lambda artifact: validate(artifact.data),
    )


def cut_in_review_request(
    host: FxCutInHost,
    graph: Graph,
    node: Node,
    *,
    read: Callable[[str], bytes],
) -> StructuredGenerationRequest[object]:
    """The exact structured request one review node sends. ``read`` resolves a run-relative
    artifact ref to bytes, so a cache mirror can supply restored payloads."""

    _plate, direction = cut_in_direction(host.fx, node)
    _producer, evidence_port = dependency_port(graph, node, kind=FX_CUT_IN_EVIDENCE_KIND)
    evidence_ref = evidence_port.artifact_ref
    references: list[StructuredReference] = [
        StructuredReference(
            url=data_url(read(evidence_ref), "image/png"),
            provenance_ref=f"run://{evidence_ref}",
        )
    ]
    port_ref = subject_port(node, direction)
    if port_ref is not None:
        # Image 2 for the judge, exactly as the review prompt says: the identity the
        # plate was copied from, not a description of it.
        artifact_ref, data = _produced_reference(graph, port_ref, read)
        references.append(
            StructuredReference(
                url=data_url(data, "image/png"), provenance_ref=f"run://{artifact_ref}"
            )
        )
    by_id = {entry.reference_id: entry for entry in host.fx.references}
    for reference_id in direction.reference_ids:
        source = by_id[reference_id].source
        package_file = host.file(source)
        references.append(
            StructuredReference(
                url=data_url(package_file.data, _media_type(source)),
                provenance_ref=f"package://{host.package_id}/{source}#sha256={package_file.sha256}",
            )
        )
    return StructuredGenerationRequest(
        prompt=card_prompt(node),
        system=(
            "You are a strict independent 2D game-art technical director. Return only the "
            "requested structured review."
        ),
        artifact_path=host.run_dir / node.port("verdict").artifact_ref,
        schema=StructuredOutputSchema(
            name=FX_CUT_IN_REVIEW_SCHEMA_NAME, json_schema=fx_cut_in_review_schema()
        ),
        parse=parse_cut_in_review,
        references=tuple(references),
        max_tokens=1800,
        timeout_seconds=600,
        metadata={"checkpoint": "fx", "effect": "cut_in", "plate": str(node.params["plate"])},
    )


_PLACEMENT_PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "scale": {
            "type": "number",
            "description": (
                "Portrait display height as a fraction of the frame canvas height "
                f"({PLACEMENT_SCALE_RANGE[0]:g} to {PLACEMENT_SCALE_RANGE[1]:g})."
            ),
        },
        "x": {
            "type": "number",
            "description": (
                "Portrait canvas centre x in frame-canvas units, 0 = left edge, 1 = right "
                f"edge ({PLACEMENT_CENTRE_RANGE[0]:g} to {PLACEMENT_CENTRE_RANGE[1]:g})."
            ),
        },
        "y": {
            "type": "number",
            "description": (
                "Portrait canvas centre y in frame-canvas units, 0 = top edge, 1 = bottom "
                f"edge ({PLACEMENT_CENTRE_RANGE[0]:g} to {PLACEMENT_CENTRE_RANGE[1]:g})."
            ),
        },
    },
}


def fx_cut_in_place_schema() -> dict[str, object]:
    """The submit payload: the placement plus the reason it is right."""

    properties = dict(cast(Mapping[str, object], _PLACEMENT_PARAMETERS["properties"]))
    properties["rationale"] = {
        "type": "string",
        "description": "One or two sentences on why this placement reads correctly.",
    }
    return {"type": "object", "properties": properties}


def _parse_placement(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not {"scale", "x", "y", "rationale"} <= set(value):
        raise ValueError("placement must carry scale, x, y, and rationale")
    return value


def _mask_facts(reveal: Mapping[str, Any]) -> str:
    """The opening described to the agent in words, measured from the mask raster.

    Raster, not the published outline: the numbers must stay true for a shape no single
    polygon describes, and ``filled`` is what tells the agent one thick band from two
    thin pieces stacked at the same x."""

    centre_x, centre_y = cast(list[float], reveal["centroid"])
    spans = []
    for column in cast(list[dict[str, float]], reveal["columns"]):
        x = column["x"]
        if "top" not in column:
            spans.append(f"x={x:.1f}: closed")
            continue
        spans.append(
            f"x={x:.1f}: y {column['top']:.2f}-{column['bottom']:.2f} "
            f"({column['filled']:.2f} of the column open)"
        )
    return (
        "The frame's opening (the region the portrait shows through) has its centroid at "
        f"x={centre_x:.3f}, y={centre_y:.3f} and covers {reveal['coverage']:.2f} of the "
        "canvas. Where it lies, in frame-canvas units: " + "; ".join(spans) + "."
    )


def _renderdata_url(composed: Image.Image) -> str:
    stage = Image.new("RGBA", composed.size, (*_RENDER_STAGE, 255))
    stage.alpha_composite(composed)
    scaled = stage.convert("RGB").resize(
        (_RENDER_WIDTH, round(composed.height * _RENDER_WIDTH / composed.width)),
        Image.Resampling.LANCZOS,
    )
    stream = io.BytesIO()
    scaled.save(stream, format="JPEG", quality=85, optimize=True)
    return data_url(stream.getvalue(), "image/jpeg")


def cut_in_place_request(
    host: FxCutInHost,
    graph: Graph,
    node: Node,
    *,
    read: Callable[[str], bytes],
) -> ToolLoopRequest[dict[str, object]]:
    """The exact tool-loop request one place node runs: what the agent sees, the tools
    it holds, the budget it has, and the admission its submit must pass. ``read``
    resolves a run-relative artifact ref to bytes, so a cache mirror can supply restored
    payloads and rebuild the identical request."""

    _plate, direction = cut_in_direction(host.fx, node)
    if not isinstance(direction, CutInPortraitDirection):
        raise ValueError(f"node {node.node_id} places a plate that is not a portrait")
    _producer, raw_port = dependency_port(graph, node, kind=FX_CUT_IN_RAW_KIND)
    _frame_node, frame_plate_port = dependency_port(graph, node, kind=FX_CUT_IN_PLATE_KIND)
    raw = read(raw_port.artifact_ref)
    frame_data = read(frame_plate_port.artifact_ref)
    portrait_sha256 = content_sha256(raw)
    frame_sha256 = content_sha256(frame_data)
    with Image.open(io.BytesIO(frame_data)) as opened:
        reveal = mask_reveal_facts(opened.convert("RGBA").getchannel("A"))
    centre_x, centre_y = cast(list[float], reveal["centroid"])
    start = {"scale": _START_SCALE, "x": round(centre_x, 4), "y": round(centre_y, 4)}

    def render(arguments: Mapping[str, object]) -> ToolResult:
        try:
            scale, x, y = placement_transform(arguments)
        except ValueError as exc:
            raise ToolInvocationError(str(exc)) from None
        composed = compose_hold_frame(frame_data, raw, placement={"scale": scale, "x": x, "y": y})
        return ToolResult(
            text=f"Rendered the composition at scale={scale:g}, x={x:g}, y={y:g}.",
            images=(_renderdata_url(composed),),
        )

    def admit(value: object) -> dict[str, object]:
        return admit_cut_in_placement(
            value, portrait_sha256=portrait_sha256, frame_sha256=frame_sha256
        )

    starting = compose_hold_frame(frame_data, raw, placement=start)
    return ToolLoopRequest(
        instructions=card_prompt(node),
        system=(
            f"{_PLACE_SYSTEM} Image 1 is the portrait plate (its transparent exterior may "
            "render as flat black or white). Image 2 is the frame plate. Image 3 is the "
            f"composition at the starting placement scale={start['scale']:g}, "
            f"x={start['x']:g}, y={start['y']:g}. Units: scale is the portrait's display "
            "height as a fraction of the frame height; x and y are the portrait canvas "
            "centre in frame-canvas units (0-1 inside the canvas; the centre may sit "
            f"outside it). {_mask_facts(reveal)}"
        ),
        artifact_path=host.run_dir / node.port("placement").artifact_ref,
        tools=(
            Tool(
                name="render_with_placement",
                description=(
                    "Render the cut-in hold frame with the portrait at the given placement "
                    "and return the picture to look at."
                ),
                parameters=_PLACEMENT_PARAMETERS,
                handler=render,
            ),
        ),
        submit_schema=fx_cut_in_place_schema(),
        submit_description="Submit the placement you rendered and judged correct.",
        parse=_parse_placement,
        artifact_value=admit,
        validate=admit,
        references=(
            ToolLoopReference(
                url=data_url(raw, "image/png"), provenance_ref=f"run://{raw_port.artifact_ref}"
            ),
            ToolLoopReference(
                url=data_url(frame_data, "image/png"),
                provenance_ref=f"run://{frame_plate_port.artifact_ref}",
            ),
            ToolLoopReference(url=_renderdata_url(starting)),
        ),
        max_steps=FX_CUT_IN_PLACE_MAX_STEPS,
        max_total_tokens=FX_CUT_IN_PLACE_MAX_TOTAL_TOKENS,
        timeout_seconds=600,
        metadata={
            "checkpoint": "fx",
            "effect": "cut_in",
            "plate": "portrait",
            "portrait_id": direction.portrait_id,
        },
    )


def validation_version_for(role: str) -> str:
    return (
        FX_CUT_IN_FRAME_VALIDATION_VERSION
        if role == "frame"
        else FX_CUT_IN_PORTRAIT_VALIDATION_VERSION
    )


def derive_cut_in_validation(
    raw: bytes,
    node: Node,
    *,
    frame_record: Mapping[str, object] | None = None,
    frame_data: bytes | None = None,
    placement_record: Mapping[str, object] | None = None,
) -> tuple[bytes, dict[str, object], dict[str, Any]]:
    """The deterministic half of a validate node: canonical plate, validation record, facts.

    Pure over its inputs, so a host's cache mirror can re-derive and byte-compare. A
    portrait needs the frame's record and plate and its own admitted placement, and the
    placement must name exactly these plates: a placement judged over other pixels is
    refused, not reused.
    """

    plate = CUT_IN_PLATES_BY_ROLE[str(node.params["plate"])]
    placement: dict[str, object] | None = None
    if plate.role == "portrait":
        if frame_record is None or frame_data is None:
            raise ValueError(f"node {node.node_id} needs the frame's validation record and plate")
        if placement_record is None:
            raise ValueError(f"node {node.node_id} needs the portrait's admitted placement")
        placement = admit_cut_in_placement(
            placement_record,
            portrait_sha256=content_sha256(raw),
            frame_sha256=content_sha256(frame_data),
        )
        for key in ("portrait_sha256", "frame_sha256"):
            if placement_record.get(key) != placement[key]:
                raise ValueError(f"node {node.node_id} placement was judged over other plates")
    canonical, facts = canonicalize_plate(raw, plate, placement=placement)
    if plate.role == "portrait":
        assert frame_record is not None
        facts["frame_geometry"] = dict(cast(Mapping[str, object], frame_record["geometry"]))
    record: dict[str, object] = {
        "schema_version": 1,
        "kind": validation_version_for(plate.role),
        "plate": plate.role,
        "portrait_id": node.params.get("portrait_id"),
        "geometry": cut_in_plate_contract(facts),
        "facts": {"source": facts["source"], "canonical": facts["canonical"]},
        "pixel_rewrite": facts["pixel_rewrite"],
    }
    return canonical, record, facts


CUT_IN_PLATES_BY_ROLE: dict[str, CutInPlate] = {"frame": CUT_IN_FRAME, "portrait": CUT_IN_PORTRAIT}


async def write_cut_in_validation(
    host: FxCutInHost,
    graph: Graph,
    node: Node,
    *,
    read: Callable[[str], bytes],
) -> dict[str, object]:
    """Run one validate node end to end: canonical plate, record, evidence, all written."""

    run_dir = host.run_dir
    _producer, raw_port = dependency_port(graph, node, kind=FX_CUT_IN_RAW_KIND)
    raw = read(raw_port.artifact_ref)
    frame_record: dict[str, object] | None = None
    frame_data: bytes | None = None
    placement_record: dict[str, object] | None = None
    if str(node.params["plate"]) == "portrait":
        _frame_node, frame_plate_port = dependency_port(graph, node, kind=FX_CUT_IN_PLATE_KIND)
        _frame_node, frame_record_port = dependency_port(
            graph, node, kind=FX_CUT_IN_VALIDATION_KIND
        )
        _place_node, placement_port = dependency_port(graph, node, kind=FX_CUT_IN_PLACEMENT_KIND)
        frame_data = read(frame_plate_port.artifact_ref)
        frame_record = cast(dict[str, object], json.loads(read(frame_record_port.artifact_ref)))
        placement_record = cast(dict[str, object], json.loads(read(placement_port.artifact_ref)))
    canonical, record, facts = derive_cut_in_validation(
        raw,
        node,
        frame_record=frame_record,
        frame_data=frame_data,
        placement_record=placement_record,
    )
    plate_path = run_dir / node.port("image").artifact_ref
    await _write_local_image(
        host,
        plate_path,
        canonical,
        prompt="Clear the already-transparent exterior to alpha 0; nothing else is rewritten.",
        inputs=((raw_port.artifact_ref, raw),),
        validation=record,
        model=str(record["kind"]),
    )
    atomic_write_json(run_dir / node.port("validation").artifact_ref, record)
    evidence = cut_in_evidence(canonical, facts, frame_data=frame_data)
    await _write_local_image(
        host,
        run_dir / node.port("evidence").artifact_ref,
        evidence,
        prompt=(
            "Composite the plate over a checkerboard and draw the cut-in's hold frame through "
            "the published mask polygon, the portrait at its admitted placement, for review "
            "evidence."
        ),
        inputs=((node.port("image").artifact_ref, canonical),),
        validation={"source_validation": record["geometry"], "checkerboard_only": False},
        model=FX_CUT_IN_EVIDENCE_VERSION,
    )
    return record


async def write_cut_in_draw(host: FxCutInHost, node: Node) -> bytes:
    """Run one draw node: the procedural frame, written with local provenance."""

    data = draw_procedural_frame()
    await _write_local_image(
        host,
        host.run_dir / node.port("image").artifact_ref,
        data,
        prompt="Draw the procedural torn-strip cut-in frame: white fill, black rim.",
        inputs=(),
        validation={"procedural": True, "seed": 7},
        model=FX_CUT_IN_DRAW_VERSION,
    )
    return data


class FxCutInHandlers:
    """The coroutines behind the node types, owned by no recipe.

    A host binds these into its own registry. ``provider_call`` is the seam for a recipe
    that writes attempt ledgers; a host with its own result and ledger discipline may
    instead call the request builders and derivations above directly.
    """

    def __init__(
        self,
        host: FxCutInHost,
        *,
        graph: Graph,
        image_service: ImageGenerationService,
        structured_service: StructuredGenerationService[object],
        tool_loop_service: ToolLoopService[dict[str, object]],
        provider_call: ProviderCall | None = None,
    ) -> None:
        self._host = host
        self._graph = graph
        self._images = image_service
        self._structured = structured_service
        self._tool_loop = tool_loop_service
        self._provider_call = provider_call

    async def generate(self, node: Node) -> NodeExecutionResult:
        request = cut_in_generate_request(self._host, self._graph, node, read=self._read)
        result = await self._call(
            node, str(node.params["plate"]), request.prompt, lambda: self._images.generate(request)
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def draw(self, node: Node) -> NodeExecutionResult:
        await write_cut_in_draw(self._host, node)
        return self._result(node, provider_operations=0)

    async def place(self, node: Node) -> NodeExecutionResult:
        request = cut_in_place_request(self._host, self._graph, node, read=self._read)
        result = await self._call(
            node,
            str(node.params["plate"]),
            request.instructions,
            lambda: self._tool_loop.run(request),
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def validate(self, node: Node) -> NodeExecutionResult:
        await write_cut_in_validation(self._host, self._graph, node, read=self._read)
        return self._result(node, provider_operations=0)

    async def review(self, node: Node) -> NodeExecutionResult:
        request = cut_in_review_request(self._host, self._graph, node, read=self._read)
        result = await self._call(
            node,
            str(node.params["plate"]),
            request.prompt,
            lambda: self._structured.generate(request),
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    def _read(self, ref: str) -> bytes:
        return (self._host.run_dir / ref).read_bytes()

    async def _call(
        self, node: Node, label: str, prompt: str, thunk: Callable[[], Awaitable[Any]]
    ) -> Any:
        if self._provider_call is None:
            return await thunk()
        return await self._provider_call(node, label, prompt, thunk)

    def _result(
        self, node: Node, *, attempts: int = 1, provider_operations: int
    ) -> NodeExecutionResult:
        return node_result(
            self._host.run_dir, node, attempts=attempts, provider_operations=provider_operations
        )


def fx_cut_in_review_schema() -> dict[str, object]:
    """The judge's answer shape: the questions the pixel gate cannot decide."""

    checks = {
        key: {"type": "boolean"}
        for key in (
            "style_coherence",
            "identity_match",
            "expression_matches_direction",
            "reads_as_torn_edge",
            "text_free",
        )
    }
    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["accept", "reject", "uncertain"]},
            "confidence": {"type": "number"},
            "checks": {"type": "object", "properties": checks},
            "issues": {"type": "array", "items": {"type": "string"}},
            "evidence": {"type": "string"},
        },
    }


def parse_cut_in_review(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("verdict") not in {
        "accept",
        "reject",
        "uncertain",
    }:
        raise ValueError("cut-in review has an invalid verdict")
    return value


__all__ = [
    "CUT_IN_PLATES_BY_ROLE",
    "FX_CUT_IN_CONTRACT_VERSION",
    "FX_CUT_IN_DRAW",
    "FX_CUT_IN_DRAW_VERSION",
    "FX_CUT_IN_EVIDENCE_KIND",
    "FX_CUT_IN_EVIDENCE_VERSION",
    "FX_CUT_IN_FRAME_VALIDATION_VERSION",
    "FX_CUT_IN_GENERATE",
    "FX_CUT_IN_NODE_TYPES",
    "FX_CUT_IN_PLACE",
    "FX_CUT_IN_PLACEMENT_KIND",
    "FX_CUT_IN_PLACE_MAX_STEPS",
    "FX_CUT_IN_PLACE_MAX_TOTAL_TOKENS",
    "FX_CUT_IN_PLACE_SCHEMA_NAME",
    "FX_CUT_IN_PLACE_VERSION",
    "FX_CUT_IN_PLATE_KIND",
    "FX_CUT_IN_PORTRAIT_VALIDATION_VERSION",
    "FX_CUT_IN_RAW_KIND",
    "FX_CUT_IN_REVIEW",
    "FX_CUT_IN_REVIEW_SCHEMA_NAME",
    "FX_CUT_IN_REVIEW_VERSION",
    "FX_CUT_IN_VALIDATE",
    "FX_CUT_IN_VALIDATION_KIND",
    "FX_CUT_IN_VERDICT_KIND",
    "FxCutInHandlers",
    "add_cut_in_nodes",
    "cut_in_artifact_refs",
    "cut_in_generate_request",
    "cut_in_node_ids",
    "cut_in_place_request",
    "cut_in_review_prompt",
    "cut_in_review_request",
    "derive_cut_in_validation",
    "frame_content_task",
    "fx_cut_in_place_schema",
    "fx_cut_in_review_schema",
    "parse_cut_in_review",
    "place_content_task",
    "plate_id_for",
    "portrait_content_task",
    "subject_content_task",
    "validation_version_for",
    "write_cut_in_draw",
    "write_cut_in_validation",
]
