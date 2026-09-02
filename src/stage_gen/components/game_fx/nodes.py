"""The cut-in plates as one recipe-neutral node set.

A stage-start cut-in, a fever entry, a map change: every 2D game slams something over its
screen at a moment, and the plates it slams are the same work in every genre. The node set
therefore lives beside the contract it serves, under the family's own taxonomy name
(``2d/fx/cut_in.*``), so a later promotion into a gnode ring is a namespace move.

A host recipe supplies what only it knows — its authored ``fx`` document, the art direction
that wraps the prompt, the digests that make a plate cache-identifiable inside its own graph,
an attempts-port factory where it keeps ledgers, and a ``file(source)`` accessor — and keeps
everything else. Nothing here reads a game, a genre, or a camera.

Two seams are exported on purpose. The *request builders* (``cut_in_generate_request``,
``cut_in_review_request``) and the *derivation* (``derive_cut_in_validation``) are what the
handlers run, and they are also what a host with a strict cache mirror re-runs to prove a
restored artifact is exactly what today's contract would produce. One function, two callers,
no drift.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, cast

from gnode import (
    AuthoredInput,
    BinaryArtifact,
    CacheDisposition,
    Graph,
    GraphBuilder,
    ImageGenerationRequest,
    ImageGenerationService,
    ImageReference,
    InputProvenance,
    Node,
    NodeArtifact,
    NodeCard,
    NodeExecutionResult,
    NodePolicy,
    NodeType,
    Port,
    PortRef,
    ProvenanceInput,
    SoftwareIdentity,
    StructuredGenerationRequest,
    StructuredGenerationService,
    StructuredOutputSchema,
    StructuredReference,
    ViewArchetype,
    atomic_write_json,
    dependency_port,
    write_artifact_with_provenance_async,
)
from stage_gen.components.game_fx.cut_in import (
    CUT_IN_FRAME,
    CUT_IN_PORTRAIT,
    CutInPlate,
    canonicalize_plate,
    cut_in_evidence,
    cut_in_plate_contract,
    draw_procedural_frame,
    validate_frame_plate,
    validate_portrait_plate,
)
from stage_gen.components.game_fx.models import (
    CutInFrameDirection,
    CutInPortraitDirection,
    GameFx,
)

_P = "2d/fx"
_PROVIDER = NodePolicy(max_attempts=6)

IMAGE_FEATURES = ("transparent_background", "reference_images")
STRUCTURED_FEATURES = ("structured_output", "image_input")

#: The generate node's cache contract: what the model is asked to paint. Bumping it
#: re-bills every plate, so measured facts the local gate reads live under the
#: validation version instead.
FX_CUT_IN_CONTRACT_VERSION = "prepared-fx-cut-in-v1"
FX_CUT_IN_DRAW_VERSION = "prepared-fx-cut-in-draw-v1"
FX_CUT_IN_VALIDATION_VERSION = "prepared-fx-cut-in-validation-v1"
FX_CUT_IN_REVIEW_VERSION = "prepared-fx-cut-in-review-v1"
FX_CUT_IN_EVIDENCE_VERSION = "prepared-fx-cut-in-evidence-v1"
FX_CUT_IN_REVIEW_SCHEMA_NAME = "prepared_fx_cut_in_review"

FX_CUT_IN_RAW_KIND = "fx-cut-in-raw-v1"
FX_CUT_IN_PLATE_KIND = "fx-cut-in-plate-v1"
FX_CUT_IN_VALIDATION_KIND = "fx-cut-in-validation-v1"
FX_CUT_IN_EVIDENCE_KIND = "fx-cut-in-evidence-v1"
FX_CUT_IN_VERDICT_KIND = "review-verdict-v1"

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
FX_CUT_IN_NODE_TYPES = (FX_CUT_IN_GENERATE, FX_CUT_IN_DRAW, FX_CUT_IN_VALIDATE, FX_CUT_IN_REVIEW)


# ------------------------------------------------------------------ prompt


_PLATE_COMMON = (
    "Everything outside the described subject is fully transparent, alpha 0, with no glow, "
    "drop shadow, colour wash, backdrop, vignette, or scenery behind it. No text, numbers, "
    "labels, logos, signatures, or watermarks anywhere."
)

_FRAME_TASK = (
    "Create one torn-paper rip silhouette to be used as a game cut-in frame. One connected, "
    "wide, slightly tilted ragged strip that runs across the entire canvas from the left edge "
    "to the right edge, cut off by both edges, occupying roughly half the canvas height, with "
    "rough hand-torn jagged edges along its top and its bottom. Fill the strip with flat pure "
    "white only, and draw a thick uneven black hand-inked outline hugging its torn edges. "
    "Nothing at all inside the strip: no drawing, no character, no texture, no shadow, no "
    "gradient, no colour. Flat graphic 2D, bold print-poster cut-out look."
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


def frame_content_task(direction: str) -> str:
    return f"{_FRAME_TASK}\nAuthored direction: {direction}\n{_PLATE_COMMON}"


def portrait_content_task(direction: str) -> str:
    return f"{_PORTRAIT_TASK}\nExpression and mood: {direction}\n{_PLATE_COMMON}"


def cut_in_review_prompt(plate: CutInPlate, direction: str) -> str:
    """What the judge is asked, given what the pixel gate has already proved."""

    if plate.role == "frame":
        return (
            "Review the generated cut-in frame plate against its authored direction. Image 1 "
            "shows the plate over a checkerboard on the left and, on the right, the plate "
            "composed the way the game shows it: a flat backdrop with stripes revealed through "
            "the plate's silhouette. Remaining images are authored visual references. "
            "Deterministic pixel validation has already proved a transparent exterior, one "
            "connected edge-to-edge strip with no holes, a flat white fill, and an inked rim. "
            "Do not mistake the checkerboard for artwork. Judge style coherence with the "
            "references, that the strip reads as one torn edge rather than a drawn frame, that "
            "the rim is ink and not a glow, and the absence of text, pseudo-text, characters, "
            f"or scenery. Authored direction: {direction} Uncertainty must not be called accept."
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


# ------------------------------------------------------------------- graph


def plate_id_for(role: str, portrait_id: str | None = None) -> str:
    return "frame" if role == "frame" else f"portrait-{portrait_id}"


def cut_in_node_ids(plate_id: str, *, prefix: str = "fx") -> tuple[str, str, str, str]:
    """The generate/draw, validate and review ids one plate occupies in a host graph."""

    base = f"{prefix}-cut_in-{plate_id}"
    return (f"{base}-generate", f"{base}-draw", f"{base}-validate", f"{base}-review")


def cut_in_artifact_refs(plate_id: str) -> tuple[str, str, str, str, str]:
    """Every path one plate writes: raw, canonical, validation, evidence, verdict."""

    name = plate_id.replace("portrait-", "portrait.", 1)
    return (
        f"fx/cut_in/{name}.raw.png",
        f"fx/cut_in/{name}.png",
        f"fx/cut_in/{name}.validation.json",
        f"fx/cut_in/{name}.evidence.png",
        f"fx/cut_in/{name}.review.json",
    )


def _artifact(port_id: str, ref: str, kind: str) -> Port:
    return Port(port_id=port_id, artifact_ref=ref, kind=kind, sidecar_ref=f"{ref}.meta.json")


def _record(port_id: str, ref: str, kind: str) -> Port:
    return Port(port_id=port_id, artifact_ref=ref, kind=kind)


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
) -> list[str]:
    """Add the frame and every portrait the document declares.

    The frame is generated or drawn per its declared mode; either way it is validated
    into the same plate kind and the same polygon record. A portrait's validation depends
    on the frame's, so its reviewer sees the exact composition a runtime shows. Returns
    the terminal ids a host adds to its own list.
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
    frame_geometry = _object_sha256(CUT_IN_FRAME.geometry_record())
    frame_direction = _object_sha256(frame.model_dump(mode="json"))
    generate_id, draw_id, validate_id, review_id = cut_in_node_ids("frame", prefix=prefix)
    raw_ref, plate_ref, validation_ref, evidence_ref, verdict_ref = cut_in_artifact_refs("frame")
    params: dict[str, str] = {"plate": "frame"}
    if frame.mode == "generated_v1":
        authored = authored_for(frame.reference_ids)
        ports: list[Port] = [_artifact("image", raw_ref, FX_CUT_IN_RAW_KIND)]
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
                _object_sha256({"contract": FX_CUT_IN_CONTRACT_VERSION}),
                frame_direction,
                *(entry.sha256 for entry in authored),
                frame_geometry,
            ),
            ports=tuple(ports),
            card=NodeCard(
                prompt=style_prompt(frame_content_task(frame.prompt or "")),
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
                _object_sha256({"contract": FX_CUT_IN_DRAW_VERSION}),
                frame_direction,
                frame_geometry,
            ),
            ports=(_artifact("image", raw_ref, FX_CUT_IN_RAW_KIND),),
            duration_seconds=1.0,
        )
    frame_validated = builder.add(
        FX_CUT_IN_VALIDATE,
        validate_id,
        domain=domain,
        description="admit the frame plate, clear its exterior, and trace its mask polygon",
        depends_on=(producer.node_id,),
        params=params,
        input_digests=(
            _object_sha256({"contract": FX_CUT_IN_VALIDATION_VERSION}),
            frame_geometry,
        ),
        ports=(
            _artifact("image", plate_ref, FX_CUT_IN_PLATE_KIND),
            _record("validation", validation_ref, FX_CUT_IN_VALIDATION_KIND),
            _artifact("evidence", evidence_ref, FX_CUT_IN_EVIDENCE_KIND),
        ),
        card=NodeCard(reference_inputs=(PortRef(node_id=producer.node_id, port_id="image"),)),
        duration_seconds=2.0,
    )
    if frame.mode == "generated_v1":
        review_ports: list[Port] = [_artifact("verdict", verdict_ref, FX_CUT_IN_VERDICT_KIND)]
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
                _object_sha256({"contract": FX_CUT_IN_REVIEW_VERSION}),
                frame_direction,
            ),
            ports=tuple(review_ports),
            card=NodeCard(
                prompt=cut_in_review_prompt(CUT_IN_FRAME, frame.prompt or ""),
                schema_name=FX_CUT_IN_REVIEW_SCHEMA_NAME,
                reference_inputs=(PortRef(node_id=frame_validated.node_id, port_id="image"),),
                authored_inputs=authored_for(frame.reference_ids),
            ),
        )
        terminals.append(reviewed.node_id)
    else:
        terminals.append(frame_validated.node_id)

    portrait_geometry = _object_sha256(CUT_IN_PORTRAIT.geometry_record())
    for portrait in fx.cut_in.portraits:
        plate_id = plate_id_for("portrait", portrait.portrait_id)
        direction_digest = _object_sha256(portrait.model_dump(mode="json"))
        generate_id, _draw_id, validate_id, review_id = cut_in_node_ids(plate_id, prefix=prefix)
        raw_ref, plate_ref, validation_ref, evidence_ref, verdict_ref = cut_in_artifact_refs(
            plate_id
        )
        params = {"plate": "portrait", "portrait_id": portrait.portrait_id}
        authored = authored_for(portrait.reference_ids)
        ports = [_artifact("image", raw_ref, FX_CUT_IN_RAW_KIND)]
        if attempts_port is not None:
            ports.append(attempts_port(generate_id))
        generated = builder.add(
            FX_CUT_IN_GENERATE,
            generate_id,
            domain=domain,
            description=f"generate the {portrait.portrait_id} cut-in portrait plate",
            depends_on=(root,),
            cache_depends_on=(),
            params=params,
            input_digests=(
                *direction_digests,
                _object_sha256({"contract": FX_CUT_IN_CONTRACT_VERSION}),
                direction_digest,
                *(entry.sha256 for entry in authored),
                portrait_geometry,
            ),
            ports=tuple(ports),
            card=NodeCard(
                prompt=style_prompt(portrait_content_task(portrait.prompt)),
                authored_inputs=authored,
            ),
        )
        validated = builder.add(
            FX_CUT_IN_VALIDATE,
            validate_id,
            domain=domain,
            description=f"admit the {portrait.portrait_id} portrait and compose it in the frame",
            depends_on=(generated.node_id, frame_validated.node_id),
            params=params,
            input_digests=(
                _object_sha256({"contract": FX_CUT_IN_VALIDATION_VERSION}),
                portrait_geometry,
            ),
            ports=(
                _artifact("image", plate_ref, FX_CUT_IN_PLATE_KIND),
                _record("validation", validation_ref, FX_CUT_IN_VALIDATION_KIND),
                _artifact("evidence", evidence_ref, FX_CUT_IN_EVIDENCE_KIND),
            ),
            card=NodeCard(reference_inputs=(PortRef(node_id=generated.node_id, port_id="image"),)),
            duration_seconds=2.0,
        )
        review_ports = [_artifact("verdict", verdict_ref, FX_CUT_IN_VERDICT_KIND)]
        if attempts_port is not None:
            review_ports.append(attempts_port(review_id))
        reviewed = builder.add(
            FX_CUT_IN_REVIEW,
            review_id,
            domain=domain,
            description=f"review the {portrait.portrait_id} portrait's identity and expression",
            depends_on=(validated.node_id,),
            params=params,
            input_digests=(
                _object_sha256({"contract": FX_CUT_IN_REVIEW_VERSION}),
                direction_digest,
            ),
            ports=tuple(review_ports),
            card=NodeCard(
                prompt=cut_in_review_prompt(CUT_IN_PORTRAIT, portrait.prompt),
                schema_name=FX_CUT_IN_REVIEW_SCHEMA_NAME,
                reference_inputs=(PortRef(node_id=validated.node_id, port_id="image"),),
                authored_inputs=authored,
            ),
        )
        terminals.append(reviewed.node_id)
    return terminals


# ----------------------------------------------------------------- host


class _PackageFile(Protocol):
    """The two facts the node set needs about an authored file, however a host stores it."""

    @property
    def data(self) -> bytes: ...

    @property
    def sha256(self) -> str: ...


@dataclass(frozen=True)
class FxCutInHost:
    """Everything the shared node set needs from whichever recipe hosts it."""

    fx: GameFx
    run_dir: Path
    package_id: str
    file: Callable[[str], _PackageFile]
    component: SoftwareIdentity
    tool: SoftwareIdentity


ProviderCall = Callable[[Node, str, str, Callable[[], Awaitable[Any]]], Awaitable[Any]]


def cut_in_direction(
    fx: GameFx, node: Node
) -> tuple[CutInPlate, CutInFrameDirection | CutInPortraitDirection]:
    """Which plate a node works on, read off its params."""

    if fx.cut_in is None:
        raise ValueError(f"node {node.node_id} needs a cut_in the document does not declare")
    if str(node.params["plate"]) == "frame":
        return CUT_IN_FRAME, fx.cut_in.frame
    return CUT_IN_PORTRAIT, fx.cut_in.portrait(str(node.params["portrait_id"]))


def _card_prompt(node: Node) -> str:
    if node.card is None or node.card.prompt is None:
        raise ValueError(f"node {node.node_id} carries no prompt on its card")
    return node.card.prompt


def _authored_references(
    host: FxCutInHost, reference_ids: Sequence[str]
) -> tuple[ImageReference, ...]:
    by_id = {entry.reference_id: entry for entry in host.fx.references}
    values = []
    for reference_id in reference_ids:
        source = by_id[reference_id].source
        package_file = host.file(source)
        values.append(
            ImageReference(
                url=_data_url(package_file.data, _media_type(source)),
                provenance_ref=f"package://{host.package_id}/{source}#sha256={package_file.sha256}",
            )
        )
    return tuple(values)


def cut_in_generate_request(host: FxCutInHost, node: Node) -> ImageGenerationRequest:
    """The exact image request one generate node sends: shared by the handler and by a
    host's provenance mirror, so the two can never disagree on identity."""

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
    return ImageGenerationRequest(
        prompt=_card_prompt(node),
        artifact_path=host.run_dir / node.port("image").artifact_ref,
        input_references=_authored_references(host, direction.reference_ids),
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
            url=_data_url(read(evidence_ref), "image/png"),
            provenance_ref=f"run://{evidence_ref}",
        )
    ]
    by_id = {entry.reference_id: entry for entry in host.fx.references}
    for reference_id in direction.reference_ids:
        source = by_id[reference_id].source
        package_file = host.file(source)
        references.append(
            StructuredReference(
                url=_data_url(package_file.data, _media_type(source)),
                provenance_ref=f"package://{host.package_id}/{source}#sha256={package_file.sha256}",
            )
        )
    return StructuredGenerationRequest(
        prompt=_card_prompt(node),
        system=(
            "You are a strict independent 2D game-art technical director. Return only the "
            "requested structured review."
        ),
        artifact_path=host.run_dir / node.port("verdict").artifact_ref,
        schema=StructuredOutputSchema(
            name=FX_CUT_IN_REVIEW_SCHEMA_NAME, json_schema=fx_cut_in_review_schema()
        ),
        parse=_parse_review,
        references=tuple(references),
        max_tokens=1800,
        timeout_seconds=600,
        metadata={"checkpoint": "fx", "effect": "cut_in", "plate": str(node.params["plate"])},
    )


def derive_cut_in_validation(
    raw: bytes,
    node: Node,
    *,
    frame_record: Mapping[str, object] | None = None,
) -> tuple[bytes, dict[str, object], dict[str, Any]]:
    """The deterministic half of a validate node: canonical plate, validation record, facts.

    Pure over its inputs, so a host's cache mirror can re-derive and byte-compare.
    """

    plate = CUT_IN_PLATES_BY_ROLE[str(node.params["plate"])]
    canonical, facts = canonicalize_plate(raw, plate)
    if plate.role == "portrait":
        if frame_record is None:
            raise ValueError(f"node {node.node_id} needs the frame's validation record")
        facts["frame_geometry"] = dict(cast(Mapping[str, object], frame_record["geometry"]))
    record: dict[str, object] = {
        "schema_version": 1,
        "kind": FX_CUT_IN_VALIDATION_VERSION,
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
    if str(node.params["plate"]) == "portrait":
        _frame_node, frame_plate_port = dependency_port(graph, node, kind=FX_CUT_IN_PLATE_KIND)
        _frame_node, frame_record_port = dependency_port(
            graph, node, kind=FX_CUT_IN_VALIDATION_KIND
        )
        frame_data = read(frame_plate_port.artifact_ref)
        frame_record = cast(dict[str, object], json.loads(read(frame_record_port.artifact_ref)))
    canonical, record, facts = derive_cut_in_validation(raw, node, frame_record=frame_record)
    plate_path = run_dir / node.port("image").artifact_ref
    await _write_local_image(
        host,
        plate_path,
        canonical,
        prompt="Clear the already-transparent exterior to alpha 0; nothing else is rewritten.",
        inputs=((raw_port.artifact_ref, raw),),
        validation=record,
        model=FX_CUT_IN_VALIDATION_VERSION,
    )
    atomic_write_json(run_dir / node.port("validation").artifact_ref, record)
    evidence = cut_in_evidence(canonical, facts, frame_data=frame_data)
    await _write_local_image(
        host,
        run_dir / node.port("evidence").artifact_ref,
        evidence,
        prompt=(
            "Composite the plate over a checkerboard and draw the cut-in's hold frame through "
            "the published mask polygon for review evidence."
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
        provider_call: ProviderCall | None = None,
    ) -> None:
        self._host = host
        self._graph = graph
        self._images = image_service
        self._structured = structured_service
        self._provider_call = provider_call

    async def generate(self, node: Node) -> NodeExecutionResult:
        request = cut_in_generate_request(self._host, node)
        result = await self._call(
            node, str(node.params["plate"]), request.prompt, lambda: self._images.generate(request)
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def draw(self, node: Node) -> NodeExecutionResult:
        await write_cut_in_draw(self._host, node)
        return self._result(node, provider_operations=0)

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
        run_dir = self._host.run_dir
        refs: list[str] = []
        for port in node.ports:
            refs.append(port.artifact_ref)
            if port.sidecar_ref is not None:
                refs.append(port.sidecar_ref)
        return NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=attempts,
            provider_operations=provider_operations,
            artifacts=tuple(
                _node_artifact(run_dir, run_dir / ref) for ref in refs if (run_dir / ref).is_file()
            ),
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


def _parse_review(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("verdict") not in {
        "accept",
        "reject",
        "uncertain",
    }:
        raise ValueError("cut-in review has an invalid verdict")
    return value


# ---------------------------------------------------------------- manifest


def fx_manifest_block(fx: GameFx, *, read_validation: Callable[[str], bytes]) -> dict[str, object]:
    """The published ``fx`` block, identical in every consumer's manifest.

    The validate node is the only place the traced geometry exists, so this reads each
    plate's record rather than the declared layout.
    """

    block: dict[str, object] = {
        "moments": [entry.model_dump(mode="json") for entry in fx.moments],
    }
    if fx.cut_in is None:
        block["cut_in"] = None
        return block

    def plate_block(plate_id: str, expected_role: str) -> dict[str, object]:
        _raw, plate_ref, validation_ref, _evidence, _verdict = cut_in_artifact_refs(plate_id)
        record = json.loads(read_validation(validation_ref))
        if not isinstance(record, dict) or record.get("plate") != expected_role:
            raise ValueError(f"cut-in {plate_id} validation names a different plate")
        geometry = record.get("geometry")
        if not isinstance(geometry, dict):
            raise ValueError(f"cut-in {plate_id} validation lacks traced geometry")
        return {**geometry, "asset": plate_ref}

    frame_block = plate_block("frame", "frame")
    frame_block["mode"] = fx.cut_in.frame.mode
    portraits = []
    for portrait in fx.cut_in.portraits:
        entry = plate_block(plate_id_for("portrait", portrait.portrait_id), "portrait")
        portraits.append({"portrait_id": portrait.portrait_id, **entry})
    block["cut_in"] = {"frame": frame_block, "portraits": portraits}
    return block


# ----------------------------------------------------------------- helpers


async def _write_local_image(
    host: FxCutInHost,
    path: Path,
    data: bytes,
    *,
    prompt: str,
    inputs: Sequence[tuple[str, bytes]],
    validation: Mapping[str, object],
    model: str,
) -> Path:
    return await write_artifact_with_provenance_async(
        path,
        BinaryArtifact(data=data, media_type="image/png"),
        ProvenanceInput(
            provider="local",
            model=model,
            prompt=prompt,
            refs=[ref for ref, _ in inputs],
            inputs=[
                InputProvenance(
                    ref=ref,
                    sha256=_sha(payload),
                    source="content",
                    bytes=len(payload),
                    media_type="image/png",
                )
                for ref, payload in inputs
            ],
            params={"version": host.component.version},
            validation=dict(validation),
            component=host.component,
            tool=host.tool,
            attempts=1,
        ),
    )


def _node_artifact(run_dir: Path, path: Path) -> NodeArtifact:
    data = path.read_bytes()
    return NodeArtifact(
        artifact_ref=path.relative_to(run_dir).as_posix(), sha256=_sha(data), bytes=len(data)
    )


def _data_url(data: bytes, media_type: str) -> str:
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"


def _media_type(path: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }[PurePosixPath(path).suffix.lower()]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _object_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "FX_CUT_IN_CONTRACT_VERSION",
    "FX_CUT_IN_DRAW",
    "FX_CUT_IN_DRAW_VERSION",
    "FX_CUT_IN_EVIDENCE_KIND",
    "FX_CUT_IN_EVIDENCE_VERSION",
    "FX_CUT_IN_GENERATE",
    "FX_CUT_IN_NODE_TYPES",
    "FX_CUT_IN_PLATE_KIND",
    "FX_CUT_IN_RAW_KIND",
    "FX_CUT_IN_REVIEW",
    "FX_CUT_IN_REVIEW_SCHEMA_NAME",
    "FX_CUT_IN_REVIEW_VERSION",
    "FX_CUT_IN_VALIDATE",
    "FX_CUT_IN_VALIDATION_KIND",
    "FX_CUT_IN_VALIDATION_VERSION",
    "FX_CUT_IN_VERDICT_KIND",
    "IMAGE_FEATURES",
    "STRUCTURED_FEATURES",
    "FxCutInHandlers",
    "FxCutInHost",
    "ProviderCall",
    "add_cut_in_nodes",
    "cut_in_artifact_refs",
    "cut_in_direction",
    "cut_in_generate_request",
    "cut_in_node_ids",
    "cut_in_review_prompt",
    "cut_in_review_request",
    "derive_cut_in_validation",
    "frame_content_task",
    "fx_cut_in_review_schema",
    "fx_manifest_block",
    "plate_id_for",
    "portrait_content_task",
    "write_cut_in_draw",
    "write_cut_in_validation",
]
