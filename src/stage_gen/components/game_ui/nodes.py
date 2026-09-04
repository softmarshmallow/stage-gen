"""The UI sheet roles as one recipe-neutral node triplet.

Every 2D game draws panels, buttons and a few system icons, so this is the one piece of
generation that is genuinely the same work in every genre: the geometry template, the
pixel gate, and the review question do not know whether a platformer, a visual novel, a
point-and-click room, or a runner asked for them. The triplet therefore lives beside the
contract it serves rather than inside whichever recipe built it first, under the
component's own taxonomy name (``2d/ui/atlas.*``), so a later promotion into a gnode
ring is a namespace move rather than a rename.

Two sheet families share the triplet. A nine-slice role (``panel_frame``, ``button_rect``)
is gated by slice reconstruction and published with insets; the preview icon grid is
gated by cell registration and published with glyph bounds. The node types, ids, ports,
cache identity and manifest projection are one shape; only the family's own template,
gate, evidence and review question differ, and they are looked up from the role.

A host recipe supplies what only it knows — its authored ``ui`` document, the art
direction that wraps the prompt, the digests that make a role cache-identifiable inside
its own graph, and (where it keeps attempt ledgers) a provider-call wrapper — and keeps
everything else. Nothing here reads a game, a genre, or a camera.

The prompt is composed at plan time and carried on the node card, so a reader sees the
exact instruction the provider will be given without running anything, and a recipe that
gates on full static prompts admits these nodes like any other.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol, cast

from pydantic import Field

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
    PersistedContractModel,
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
from stage_gen.components._game_input import SNAKE_ID_PATTERN
from stage_gen.components.game_ui.atlas import (
    ATLAS_ALPHA_POLICY,
    ATLAS_ROLES,
    BUTTON_RECT,
    PANEL_FRAME,
    AtlasRole,
    atlas_evidence,
    atlas_role_contract,
    canonicalize_atlas_image,
    render_atlas_template,
    validate_atlas_image,
)
from stage_gen.components.game_ui.icons import (
    ICON_ALPHA_POLICY,
    ICON_ROLES,
    PREVIEW_ICON_GLYPHS,
    PREVIEW_ICONS,
    IconGridRole,
    canonicalize_icon_sheet,
    icon_evidence,
    icon_role_contract,
    render_icon_template,
    validate_icon_sheet,
)
from stage_gen.components.game_ui.models import AtlasRoleDirection, GameUi, IconSetDirection
from stage_gen.media import data_url

_P = "2d/ui"
_PROVIDER = NodePolicy(max_attempts=6)

IMAGE_FEATURES = ("transparent_background", "reference_images")
STRUCTURED_FEATURES = ("structured_output", "image_input")

#: The generate node's cache contract: what the model is asked to paint. Bumping it
#: re-bills every sheet, so measured facts that only the local gate reads live under
#: the validation version below instead.
UI_ATLAS_CONTRACT_VERSION = "prepared-ui-atlas-v1"
#: The validate node's own identity, so a richer record (a new measured fact) can re-run
#: the local gate over cached sheets without re-billing the image above.
UI_ATLAS_VALIDATION_VERSION = "prepared-ui-atlas-validation-v2"
UI_ATLAS_REVIEW_VERSION = "prepared-ui-atlas-review-v1"
UI_ATLAS_EVIDENCE_VERSION = "prepared-ui-atlas-evidence-v1"
#: The structured card the review node declares and the review request sends. One name,
#: so a reader of the plan and a reader of the provider call see the same contract.
UI_ATLAS_REVIEW_SCHEMA_NAME = "prepared_ui_atlas_review"

UI_ATLAS_RAW_KIND = "ui-atlas-raw-v1"
UI_ATLAS_IMAGE_KIND = "ui-atlas-v1"
UI_ATLAS_VALIDATION_KIND = "ui-atlas-validation-v1"
UI_ATLAS_EVIDENCE_KIND = "ui-atlas-evidence-v1"
UI_ATLAS_VERDICT_KIND = "review-verdict-v1"

UI_ATLAS_GENERATE = NodeType(
    type_id=f"{_P}/atlas.generate",
    title="UI atlas role",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="ui-atlas-v1",
)

UI_ATLAS_VALIDATE = NodeType(
    type_id=f"{_P}/atlas.validate",
    title="UI atlas admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="ui-atlas-validate-v1",
)

UI_ATLAS_REVIEW = NodeType(
    type_id=f"{_P}/atlas.review",
    title="UI atlas review",
    archetype=ViewArchetype.JUDGE,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=_PROVIDER,
    contract_version="ui-atlas-review-v1",
)

#: Every type this module owns, for a recipe's own type census and registry checks.
UI_ATLAS_NODE_TYPES = (UI_ATLAS_GENERATE, UI_ATLAS_VALIDATE, UI_ATLAS_REVIEW)

#: Either sheet family's role: what the triplet is fanned out over.
UiSheetRole = AtlasRole | IconGridRole

#: Every role the triplet can generate, by name. A node's ``role`` param resolves here.
UI_SHEET_ROLES: dict[str, UiSheetRole] = {**ATLAS_ROLES, **ICON_ROLES}

#: The roles a `game-ui-v4` document requires, in the order a graph fans them out: the
#: two nine-slice roles promoted in `game-ui-v2` and the preview icon set.
DEFAULT_ATLAS_ROLES: tuple[UiSheetRole, ...] = (PANEL_FRAME, BUTTON_RECT, PREVIEW_ICONS)

#: The direction a document authors for a role, by family.
UiSheetDirection = AtlasRoleDirection | IconSetDirection


# ------------------------------------------------------------------ prompt


_GEOMETRY_COMMON = (
    "Use the supplied layout template as the exact geometry authority. It is layout guidance, "
    "not the requested visual style: do not draw its magenta, yellow, or cyan. Magenta marks "
    "where the opaque body goes, the yellow outline is the body's outer edge, and the cyan lines "
    "divide each body into nine regions. Keep the canvas exterior transparent alpha 0 with no "
    "glow, drop shadow, colour wash, backdrop, or scenery; every body must be fully opaque. "
    "No text, numbers, labels, icons, items, characters, logo, signature, or watermark."
)

_NINE_SLICE_RULE = (
    "Nine-slice rule: the four corner regions may carry ornament, and every corner ornament must "
    "stay inside its own corner region without touching or crossing the cyan divider. The four "
    "edge regions must each be one straight, uniform band that repeats identically along its "
    "whole length, with no motif, emblem, medallion, knot, notch, or break anywhere in the band. "
    "The centre region must be one flat, even, unornamented surface that text can sit on, with no "
    "vignette, gradient, hotspot, texture cluster, or pattern. Nothing crosses from a corner into "
    "an edge band except the continuous border itself."
)

_STATE_LOOKS = {
    "hover": "Hover is slightly brighter with a gentle highlight.",
    "pressed": "Pressed is darker with an inset, pushed-in look.",
    "disabled": "Disabled is desaturated and dimmer.",
}


def atlas_content_task(role: AtlasRole, direction: str) -> str:
    """The content task for one atlas role, read off its geometry rather than its name."""

    width, height = role.canvas
    if len(role.cells) == 1:
        body = (
            "Create one nine-slice panel frame for the game's screen-fixed interface.\n"
            f"Authored direction: {direction}\n"
            f"One {width} by {height} canvas holding one rectangular panel body at the "
            "template's magenta rectangle. "
        )
    else:
        looks = " ".join(_STATE_LOOKS[state] for state in role.states if state in _STATE_LOOKS)
        body = (
            f"Create one {role.role.replace('_', ' ')} state sheet for the game's screen-fixed "
            "interface.\n"
            f"Authored direction: {direction}\n"
            f"One {width} by {height} canvas holding {len(role.cells)} identical rectangular "
            "bodies stacked top to bottom at the template's magenta rectangles, in this order: "
            f"{', '.join(role.states)}. All share exactly the same outer silhouette, size, "
            "corner shape, border and ornament; only lighting, value, and hue change between "
            f"states. {looks} Each body is itself a nine-slice. "
        )
    return f"{body}{_NINE_SLICE_RULE} {_GEOMETRY_COMMON}"


def atlas_review_prompt(role: AtlasRole, direction: str, band_fill: object) -> str:
    """What the judge is asked, given what the pixel gate has already proved."""

    bodies = len(role.cells)
    states_clause = (
        ""
        if bodies == 1
        else (
            f"that the {bodies} bodies read as the states {', '.join(role.states)} in "
            "that order from top to bottom, "
        )
    )
    return (
        f"Review the generated {role.role} nine-slice sheet against its authored "
        "direction. Image 1 shows the sheet over a checkerboard on the left and, on the "
        "right, every body re-drawn through the admitted nine-slice at a wider and a "
        "taller size, which is exactly what the game will show; remaining images are "
        "authored visual references. Deterministic pixel validation has already proved "
        f"a transparent exterior, {bodies} fully opaque "
        f"{'body' if bodies == 1 else 'bodies in order'}, repeatable edge bands under "
        f"{band_fill} fill, a flat readable centre, and one silhouette across states. "
        "Do not mistake the checkerboard for artwork. Judge style coherence with the "
        "references, that ornament lives in the corners while the edge bands stay "
        "plain, that the centre is a quiet surface text can sit on, "
        f"{states_clause}"
        "and the absence of text, pseudo-text, labels, icons, items, logos, or "
        f"scenery. Authored direction: {direction} Uncertainty must not be "
        "called accept."
    )


_ICON_GEOMETRY = (
    "Use the supplied layout template as the exact geometry authority. It is layout "
    "guidance, not the requested visual style: do not draw its cyan or yellow. Each cyan "
    "square is one cell of the grid; the yellow square inside it is the extent the glyph "
    "should fill. Draw one glyph centred in each cell and nothing at all between or around "
    "the cells: no cell backgrounds, plates, tiles, frames, badges, shadows, or glow behind "
    "or around the icons, because these are glyphs and not buttons. Keep the canvas exterior "
    "transparent alpha 0. Every glyph must have a fully opaque body with clean edges. No "
    "text, letters, numbers, labels, logo, signature, or watermark anywhere."
)


def icon_content_task(role: IconGridRole, direction: str) -> str:
    """The content task for the icon grid: the fixed vocabulary, then the authored style.

    The glyph list is stated symbol by symbol in reading order, because that list is the
    contract a consumer indexes into; the direction may colour it and nothing more.
    """

    described = dict(PREVIEW_ICON_GLYPHS)
    listing = ", ".join(
        f"{index + 1} {name.replace('_', ' ')} ({described[name]})"
        for index, name in enumerate(role.glyphs)
    )
    width, height = role.canvas
    return (
        f"Create one icon set sheet for the game's screen-fixed interface: {len(role.glyphs)} "
        f"icons in a {role.columns} by {role.rows} grid on one {width} by {height} canvas, "
        "in reading order left to right then top to bottom: "
        f"{listing}. Each icon is one bold, instantly readable symbol that stays legible at "
        "24 pixels: simple, centred in its cell, filling about seventy percent of the cell, "
        "with the same visual weight, stroke thickness, and size across the whole set.\n"
        f"Style direction: {direction}\n{_ICON_GEOMETRY}"
    )


def icon_review_prompt(role: IconGridRole, direction: str) -> str:
    """What the judge is asked about an icon sheet: identity, one set, and nothing else."""

    return (
        f"Review the generated {role.role} icon sheet against its style direction. Image 1 "
        "shows the sheet over a checkerboard on the left and, on the right, one row per cell "
        "in reading order: the glyph the cell was asked to hold, then that cell re-drawn at "
        "the two sizes a game shows it. The names on the right are annotation added by the "
        "validator for you, not part of the sheet. Remaining images are authored visual "
        "references. Deterministic pixel validation has already proved a transparent canvas, "
        f"exactly {len(role.glyphs)} glyphs registered to the grid with nothing drawn between "
        "the cells, and one coherent size across the set. Do not mistake the checkerboard for "
        "artwork. Judge: that every cell reads unmistakably as its named glyph, listing each "
        "mismatch as an issue in the form 'cell <n> <name>: <what it shows instead>'; that all "
        "glyphs share one style, stroke weight and visual density, as one set drawn by one "
        "hand; style coherence with the references and the direction; that no cell carries a "
        "background plate, tile, frame, badge, or shadow behind its glyph; and the absence of "
        f"text, letters, numbers, or labels on the sheet itself. Style direction: {direction} "
        "Uncertainty must not be called accept."
    )


# ------------------------------------------------------------------ family


@dataclass(frozen=True)
class SheetFamily:
    """What differs between a nine-slice sheet and an icon grid, looked up from the role.

    Everything else about the triplet — node types, ids, ports, cache identity, provider
    request shape, manifest binding — is one code path.
    """

    direction_type: type[UiSheetDirection]
    template: Callable[[Any], bytes]
    validate: Callable[[bytes, Any], dict[str, object]]
    canonicalize: Callable[[bytes, Any], tuple[bytes, dict[str, object]]]
    evidence: Callable[[bytes, dict[str, object]], bytes]
    contract: Callable[[dict[str, object]], dict[str, object]]
    content_task: Callable[[Any, str], str]
    #: The review prompt from the role, the authored direction, and the validation record;
    #: at plan time the record is empty and the prompt names what it will be given.
    review_prompt: Callable[[Any, str, Mapping[str, object]], str]
    review_checks: tuple[str, ...]
    alpha_policy: str
    generate_description: str
    validate_description: str
    review_description: str
    canonical_prompt: str
    evidence_prompt: str


NINE_SLICE_FAMILY = SheetFamily(
    direction_type=AtlasRoleDirection,
    template=render_atlas_template,
    validate=validate_atlas_image,
    canonicalize=canonicalize_atlas_image,
    evidence=atlas_evidence,
    contract=atlas_role_contract,
    content_task=atlas_content_task,
    review_prompt=lambda role, direction, record: atlas_review_prompt(
        role, direction, record.get("band_fill", "the admitted")
    ),
    review_checks=(
        "style_coherence",
        "ornament_in_corners",
        "bands_plain",
        "centre_quiet",
        "state_order",
        "text_free",
    ),
    alpha_policy=ATLAS_ALPHA_POLICY,
    generate_description="generate the authored {role} nine-slice atlas",
    validate_description="detect bodies, admit a band fill, and normalize the alpha boundary",
    review_description="review {role} style, ornament placement, and state order",
    canonical_prompt=(
        "Normalize only the admitted alpha boundary: clear the already-transparent "
        "exterior and clamp every admitted content rect to alpha 255."
    ),
    evidence_prompt=(
        "Composite the atlas sheet over a checkerboard and re-draw every cell through "
        "the admitted nine-slice at a wider and a taller size for review evidence."
    ),
)

ICON_GRID_FAMILY = SheetFamily(
    direction_type=IconSetDirection,
    template=render_icon_template,
    validate=validate_icon_sheet,
    canonicalize=canonicalize_icon_sheet,
    evidence=icon_evidence,
    contract=icon_role_contract,
    content_task=icon_content_task,
    review_prompt=lambda role, direction, _record: icon_review_prompt(role, direction),
    review_checks=(
        "style_coherence",
        "glyph_identity",
        "one_set",
        "glyphs_only",
        "text_free",
    ),
    alpha_policy=ICON_ALPHA_POLICY,
    generate_description="generate the fixed {role} glyph grid in the authored style",
    validate_description="register a glyph to every cell and normalize the exterior alpha",
    review_description="review {role} glyph identity, set coherence, and style",
    canonical_prompt=(
        "Normalize only the admitted exterior: clear already-transparent pixels to alpha 0 "
        "and touch nothing inside a glyph."
    ),
    evidence_prompt=(
        "Composite the icon sheet over a checkerboard and draw every cell at two consumer "
        "sizes beside the glyph name it was asked to hold, for review evidence."
    ),
)


def sheet_family(role: UiSheetRole) -> SheetFamily:
    """The family a role belongs to; a role is one or the other by construction."""

    return ICON_GRID_FAMILY if isinstance(role, IconGridRole) else NINE_SLICE_FAMILY


def validate_ui_sheet(data: bytes, role: str) -> dict[str, object]:
    """Gate ``data`` as the named role, whichever family it belongs to.

    For a host that re-checks a cached sheet against the contract before reusing it.
    """

    sheet_role = UI_SHEET_ROLES[role]
    return sheet_family(sheet_role).validate(data, sheet_role)


# ------------------------------------------------------------------- graph


def atlas_node_ids(role: UiSheetRole, *, prefix: str = "ui") -> tuple[str, str, str]:
    """The generate, validate and review ids one role occupies in a host graph."""

    return (
        f"{prefix}-{role.role}-generate",
        f"{prefix}-{role.role}-validate",
        f"{prefix}-{role.role}-review",
    )


def atlas_artifact_refs(role: UiSheetRole) -> tuple[str, str, str, str, str]:
    """Every path one role writes: raw, canonical, validation, evidence, verdict."""

    return (
        f"ui/{role.role}.raw.png",
        f"ui/{role.role}.png",
        f"ui/{role.role}.validation.json",
        f"ui/{role.role}.evidence.png",
        f"ui/{role.role}.review.json",
    )


def _artifact(port_id: str, ref: str, kind: str) -> Port:
    return Port(port_id=port_id, artifact_ref=ref, kind=kind, sidecar_ref=f"{ref}.meta.json")


def _record(port_id: str, ref: str, kind: str) -> Port:
    return Port(port_id=port_id, artifact_ref=ref, kind=kind)


def add_ui_atlas_nodes(
    builder: GraphBuilder,
    *,
    root: str,
    ui: GameUi,
    style_prompt: Callable[[str], str],
    direction_digests: Sequence[str] = (),
    roles: Sequence[UiSheetRole] = DEFAULT_ATLAS_ROLES,
    domain: str = "ui",
    prefix: str = "ui",
    attempts_port: Callable[[str], Port] | None = None,
) -> list[str]:
    """Add one generic sheet triplet per role, fanned out over the role parameter.

    The template is rendered from the role's geometry record at run time, so the record is
    what the cache key hashes: a rasterizer change that draws the same guides differently
    must not re-bill the image, and a geometry change must. ``direction_digests`` is the
    host's own art-direction identity, so a recipe that repaints its whole look re-bills
    its sheets without this module knowing what a look is.

    Returns the review node ids, which are the terminals a host adds to its own list.
    """

    references = {entry.reference_id: entry for entry in ui.references}
    terminals: list[str] = []
    for role in roles:
        family = sheet_family(role)
        direction = _role_direction(ui, role)
        direction_digest = _object_sha256(direction.model_dump(mode="json"))
        geometry_digest = _object_sha256(role.geometry_record())
        generate_id, validate_id, review_id = atlas_node_ids(role, prefix=prefix)
        raw_ref, image_ref, validation_ref, evidence_ref, verdict_ref = atlas_artifact_refs(role)
        # An input that reaches a provider is never invisible in the plan: the card names
        # each authored reference and the bytes it binds, not just an opaque digest.
        authored = tuple(
            AuthoredInput(
                label=reference_id,
                ref=references[reference_id].source,
                sha256=references[reference_id].source_sha256,
            )
            for reference_id in direction.reference_ids
        )
        generate_ports: list[Port] = [_artifact("image", raw_ref, UI_ATLAS_RAW_KIND)]
        review_ports: list[Port] = [_artifact("verdict", verdict_ref, UI_ATLAS_VERDICT_KIND)]
        if attempts_port is not None:
            generate_ports.append(attempts_port(generate_id))
            review_ports.append(attempts_port(review_id))
        generated = builder.add(
            UI_ATLAS_GENERATE,
            generate_id,
            domain=domain,
            description=family.generate_description.format(role=role.role),
            depends_on=(root,),
            cache_depends_on=(),
            params={"role": role.role},
            input_digests=(
                *direction_digests,
                _object_sha256({"contract": UI_ATLAS_CONTRACT_VERSION}),
                direction_digest,
                *(entry.sha256 for entry in authored),
                geometry_digest,
            ),
            ports=tuple(generate_ports),
            card=NodeCard(
                prompt=style_prompt(family.content_task(role, direction.prompt)),
                template_ref=f"{role.layout}_template",
                authored_inputs=authored,
            ),
        )
        validated = builder.add(
            UI_ATLAS_VALIDATE,
            validate_id,
            domain=domain,
            description=family.validate_description,
            depends_on=(generated.node_id,),
            params={"role": role.role},
            input_digests=(
                _object_sha256({"contract": UI_ATLAS_VALIDATION_VERSION}),
                direction_digest,
                geometry_digest,
            ),
            ports=(
                _artifact("image", image_ref, UI_ATLAS_IMAGE_KIND),
                _record("validation", validation_ref, UI_ATLAS_VALIDATION_KIND),
                _artifact("evidence", evidence_ref, UI_ATLAS_EVIDENCE_KIND),
            ),
            card=NodeCard(reference_inputs=(PortRef(node_id=generated.node_id, port_id="image"),)),
            duration_seconds=1.5,
        )
        reviewed = builder.add(
            UI_ATLAS_REVIEW,
            review_id,
            domain=domain,
            description=family.review_description.format(role=role.role),
            depends_on=(validated.node_id,),
            params={"role": role.role},
            input_digests=(
                _object_sha256({"contract": UI_ATLAS_REVIEW_VERSION}),
                direction_digest,
            ),
            ports=tuple(review_ports),
            card=NodeCard(
                prompt=family.review_prompt(role, direction.prompt, {}),
                schema_name=UI_ATLAS_REVIEW_SCHEMA_NAME,
                reference_inputs=(PortRef(node_id=validated.node_id, port_id="image"),),
                authored_inputs=authored,
            ),
        )
        terminals.append(reviewed.node_id)
    return terminals


def _role_direction(ui: GameUi, role: UiSheetRole) -> UiSheetDirection:
    direction = getattr(ui, role.role, None)
    if not isinstance(direction, sheet_family(role).direction_type):
        raise ValueError(f"UI document names no {role.role} direction of the expected family")
    return direction


# ----------------------------------------------------------------- handler


class _PackageFile(Protocol):
    """The two facts the triplet needs about an authored file, however a host stores it."""

    @property
    def data(self) -> bytes: ...

    @property
    def sha256(self) -> str: ...


@dataclass(frozen=True)
class UiAtlasHost:
    """Everything the shared triplet needs from whichever recipe hosts it."""

    #: The authored UI document whose roles this host generates.
    ui: GameUi
    #: The run the host is writing into.
    run_dir: Path
    #: The authored package's own identity, for ``package://`` provenance refs.
    package_id: str
    #: One authored member by its declared source path.
    file: Callable[[str], _PackageFile]
    #: The host's software identity, stamped on the local artifacts the gate writes.
    component: SoftwareIdentity
    #: The host tool identity, stamped alongside the component.
    tool: SoftwareIdentity


ProviderCall = Callable[[Node, str, str, Callable[[], Awaitable[Any]]], Awaitable[Any]]


class UiAtlasHandlers:
    """The three coroutines behind the atlas node types, owned by no recipe.

    A host binds these into its own registry and keeps its caching, tracing, and error
    translation. ``provider_call`` is the seam for a recipe that writes attempt ledgers:
    it receives the node, a role label, the exact prompt, and a thunk, and must return
    whatever the thunk returns.
    """

    def __init__(
        self,
        host: UiAtlasHost,
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

    # -- dispatch ---------------------------------------------------------

    async def generate(self, node: Node) -> NodeExecutionResult:
        role, direction = self._role(node)
        family = sheet_family(role)
        output = self._host.run_dir / node.port("image").artifact_ref
        template_data = family.template(role)
        prompt = _card_prompt(node)
        references = (
            *self._image_references(direction.reference_ids),
            ImageReference(
                url=data_url(template_data, "image/png"),
                provenance_ref=f"geometry://{role.layout}#sha256={_sha(template_data)}",
            ),
        )
        request = ImageGenerationRequest(
            prompt=prompt,
            artifact_path=output,
            input_references=references,
            quality="high",
            background="transparent",
            output_format="png",
            size=f"{role.canvas[0]}x{role.canvas[1]}",
            timeout_seconds=600,
            metadata={
                "checkpoint": "ui",
                "role": role.role,
                "layout": role.layout,
                "alpha_policy": family.alpha_policy,
            },
            validate=lambda artifact: family.validate(artifact.data, role),
        )
        result = await self._call(node, role.role, prompt, lambda: self._images.generate(request))
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def validate(self, node: Node) -> NodeExecutionResult:
        role, _direction = self._role(node)
        family = sheet_family(role)
        run_dir = self._host.run_dir
        source = run_dir / self._dependency(node, kind=UI_ATLAS_RAW_KIND)
        data = source.read_bytes()
        canonical_data, facts = family.canonicalize(data, role)
        canonical_facts = cast(dict[str, object], facts["canonical"])
        contract = family.contract(canonical_facts)
        canonical = run_dir / node.port("image").artifact_ref
        validation = run_dir / node.port("validation").artifact_ref
        evidence = run_dir / node.port("evidence").artifact_ref
        await self._write_local_image(
            canonical,
            canonical_data,
            prompt=family.canonical_prompt,
            inputs=((source.relative_to(run_dir).as_posix(), data),),
            validation=facts,
            model=UI_ATLAS_VALIDATION_VERSION,
        )
        atomic_write_json(
            validation,
            {
                "schema_version": 1,
                "kind": UI_ATLAS_VALIDATION_VERSION,
                **contract,
                "facts": facts,
            },
        )
        evidence_data = family.evidence(canonical_data, canonical_facts)
        await self._write_local_image(
            evidence,
            evidence_data,
            prompt=family.evidence_prompt,
            inputs=((canonical.relative_to(run_dir).as_posix(), canonical_data),),
            validation={"source_validation": contract, "checkerboard_only": False},
            model=UI_ATLAS_EVIDENCE_VERSION,
        )
        return self._result(node, provider_operations=0)

    async def review(self, node: Node) -> NodeExecutionResult:
        role, direction = self._role(node)
        family = sheet_family(role)
        run_dir = self._host.run_dir
        evidence = run_dir / self._dependency(node, kind=UI_ATLAS_EVIDENCE_KIND)
        validation = run_dir / self._dependency(node, kind=UI_ATLAS_VALIDATION_KIND)
        contract = json.loads(validation.read_bytes())
        selected = set(direction.reference_ids)
        references = [_structured_reference_from_run(evidence, run_dir)]
        references.extend(
            self._package_structured_reference(reference.source)
            for reference in self._host.ui.references
            if reference.reference_id in selected
        )
        prompt = family.review_prompt(role, direction.prompt, contract)
        output = run_dir / node.port("verdict").artifact_ref
        request: StructuredGenerationRequest[object] = StructuredGenerationRequest(
            prompt=prompt,
            system=(
                "You are a strict independent 2D game-art technical director. Return only the "
                "requested structured review."
            ),
            artifact_path=output,
            schema=StructuredOutputSchema(
                name=UI_ATLAS_REVIEW_SCHEMA_NAME,
                json_schema=ui_atlas_review_schema(family.review_checks),
            ),
            parse=_parse_review,
            references=tuple(references),
            max_tokens=1800,
            timeout_seconds=600,
            metadata={"checkpoint": "ui", "role": role.role},
        )
        result = await self._call(
            node, role.role, prompt, lambda: self._structured.generate(request)
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    # -- internals --------------------------------------------------------

    def _role(self, node: Node) -> tuple[UiSheetRole, UiSheetDirection]:
        role = UI_SHEET_ROLES[str(node.params["role"])]
        return role, _role_direction(self._host.ui, role)

    async def _call(
        self, node: Node, label: str, prompt: str, thunk: Callable[[], Awaitable[Any]]
    ) -> Any:
        if self._provider_call is None:
            return await thunk()
        return await self._provider_call(node, label, prompt, thunk)

    def _dependency(self, node: Node, *, kind: str) -> str:
        _producer, port = dependency_port(self._graph, node, kind=kind)
        return port.artifact_ref

    def _image_references(self, reference_ids: Sequence[str]) -> tuple[ImageReference, ...]:
        by_id = {entry.reference_id: entry for entry in self._host.ui.references}
        values = []
        for reference_id in reference_ids:
            source = by_id[reference_id].source
            package_file = self._host.file(source)
            values.append(
                ImageReference(
                    url=data_url(package_file.data, _media_type(source)),
                    provenance_ref=(
                        f"package://{self._host.package_id}/{source}#sha256={package_file.sha256}"
                    ),
                )
            )
        return tuple(values)

    def _package_structured_reference(self, source: str) -> StructuredReference:
        package_file = self._host.file(source)
        return StructuredReference(
            url=data_url(package_file.data, _media_type(source)),
            provenance_ref=(
                f"package://{self._host.package_id}/{source}#sha256={package_file.sha256}"
            ),
        )

    async def _write_local_image(
        self,
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
                params={"version": self._host.component.version},
                validation=dict(validation),
                component=self._host.component,
                tool=self._host.tool,
                attempts=1,
            ),
        )

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


def ui_atlas_review_schema(
    checks: Sequence[str] = NINE_SLICE_FAMILY.review_checks,
) -> dict[str, object]:
    """The judge's answer shape: the questions the pixel gate cannot decide, per family."""

    check_properties = {key: {"type": "boolean"} for key in checks}
    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["accept", "reject", "uncertain"]},
            "confidence": {"type": "number"},
            "checks": {"type": "object", "properties": check_properties},
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
        raise ValueError("UI atlas review has an invalid verdict")
    return value


# ---------------------------------------------------------------- manifest


class AtlasRect(PersistedContractModel):
    """One published rectangle, in sheet pixels."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class AtlasCanvas(PersistedContractModel):
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class AtlasInsets(PersistedContractModel):
    """The admitted corner widths, which is where a consumer cuts the nine slices."""

    left: int = Field(ge=1)
    top: int = Field(ge=1)
    right: int = Field(ge=1)
    bottom: int = Field(ge=1)


class AtlasCellLayout(PersistedContractModel):
    state: str = Field(pattern=SNAKE_ID_PATTERN, max_length=32)
    cell: AtlasRect
    #: The geometric interior: the cell minus the sheet insets.
    content_rect: AtlasRect
    #: The measured ornament-free interior, where text is safe. Inside ``content_rect``.
    safe_rect: AtlasRect


class AtlasRoleLayout(PersistedContractModel):
    """The resolved geometry one role publishes, as a typed contract.

    The same projection ``ui_atlas_manifest`` emits as a plain mapping, for consumers whose
    manifest is a validated document rather than a JSON blob. Detected, not declared: the
    model keeps a sheet's cell count and order but re-spaces its bodies, so these numbers
    come from the gate that measured the artwork.
    """

    role: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)
    layout: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    scale_mode: Literal["nine_slice"]
    alpha_policy: Literal["transparent_exterior_opaque_body_v1"]
    band_fill: Literal["stretch", "tile"]
    #: Sheet pixels per screen pixel: lay slices out at this multiple, then scale down.
    draw_scale: int = Field(ge=1)
    canvas: AtlasCanvas
    insets: AtlasInsets
    cells: list[AtlasCellLayout] = Field(min_length=1, max_length=16)


class IconCellLayout(PersistedContractModel):
    glyph: str = Field(pattern=SNAKE_ID_PATTERN, max_length=32)
    #: The published cell: what a consumer cuts as one frame and scales as the glyph's box.
    cell: AtlasRect
    #: The detected bounds of the drawn glyph, inside ``cell``.
    glyph_rect: AtlasRect


class IconSetLayout(PersistedContractModel):
    """The resolved geometry the icon grid publishes, as a typed contract.

    ``scale_mode`` is ``fixed``: a cell is drawn at one size, never sliced. ``cell_size`` is
    every cell's side, so a consumer sizes an icon by scaling its cell and keeps the set's
    own proportions between glyphs.
    """

    role: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)
    layout: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    scale_mode: Literal["fixed"]
    alpha_policy: Literal["transparent_exterior_opaque_glyph_v1"]
    draw_scale: int = Field(ge=1)
    canvas: AtlasCanvas
    cell_size: int = Field(ge=1)
    cells: list[IconCellLayout] = Field(min_length=1, max_length=64)


#: Either family's published block, told apart by ``scale_mode``.
UiSheetLayout = AtlasRoleLayout | IconSetLayout


def ui_atlas_manifest(
    role: str,
    *,
    read_validation: Callable[[str], bytes],
    publish: Callable[[str], object],
    publish_provenance: Callable[[str], None],
) -> dict[str, object]:
    """One published ``ui.<role>`` block, identical in every consumer's manifest.

    The validate node is the only place the detected geometry exists, so this reads the
    resolved contract from its record rather than from the declared template.
    """

    validation_path = f"ui/{role}.validation.json"
    publish_provenance(validation_path)
    record = json.loads(read_validation(validation_path))
    if not isinstance(record, dict) or record.get("role") != role:
        raise ValueError(f"UI atlas {role} validation names a different role")
    try:
        contract = sheet_family(UI_SHEET_ROLES[role]).contract(record)
    except (KeyError, TypeError) as error:
        raise ValueError(f"UI atlas {role} validation lacks resolved geometry: {error}") from error
    return {**contract, "asset": publish(f"ui/{role}.png")}


def ui_atlas_manifest_block(
    *,
    read_validation: Callable[[str], bytes],
    publish: Callable[[str], object],
    publish_provenance: Callable[[str], None],
    roles: Sequence[UiSheetRole] = DEFAULT_ATLAS_ROLES,
) -> dict[str, object]:
    """Every generated role as one ``ui`` block."""

    return {
        role.role: ui_atlas_manifest(
            role.role,
            read_validation=read_validation,
            publish=publish,
            publish_provenance=publish_provenance,
        )
        for role in roles
    }


# ----------------------------------------------------------------- helpers


def _card_prompt(node: Node) -> str:
    if node.card is None or node.card.prompt is None:
        raise ValueError(f"node {node.node_id} carries no prompt on its card")
    return node.card.prompt


def _structured_reference_from_run(path: Path, run_dir: Path) -> StructuredReference:
    return StructuredReference(
        url=data_url(path.read_bytes(), "image/png"),
        provenance_ref=f"run://{path.relative_to(run_dir).as_posix()}",
    )


def _node_artifact(run_dir: Path, path: Path) -> NodeArtifact:
    data = path.read_bytes()
    return NodeArtifact(
        artifact_ref=path.relative_to(run_dir).as_posix(), sha256=_sha(data), bytes=len(data)
    )


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
    "DEFAULT_ATLAS_ROLES",
    "ICON_GRID_FAMILY",
    "NINE_SLICE_FAMILY",
    "AtlasCanvas",
    "AtlasCellLayout",
    "AtlasInsets",
    "AtlasRect",
    "AtlasRoleLayout",
    "IconCellLayout",
    "IconSetLayout",
    "IMAGE_FEATURES",
    "STRUCTURED_FEATURES",
    "UI_SHEET_ROLES",
    "UI_ATLAS_CONTRACT_VERSION",
    "UI_ATLAS_EVIDENCE_KIND",
    "UI_ATLAS_EVIDENCE_VERSION",
    "UI_ATLAS_GENERATE",
    "UI_ATLAS_IMAGE_KIND",
    "UI_ATLAS_NODE_TYPES",
    "UI_ATLAS_RAW_KIND",
    "UI_ATLAS_REVIEW",
    "UI_ATLAS_REVIEW_SCHEMA_NAME",
    "UI_ATLAS_REVIEW_VERSION",
    "UI_ATLAS_VALIDATE",
    "UI_ATLAS_VALIDATION_KIND",
    "UI_ATLAS_VALIDATION_VERSION",
    "UI_ATLAS_VERDICT_KIND",
    "ProviderCall",
    "SheetFamily",
    "UiAtlasHandlers",
    "UiAtlasHost",
    "UiSheetDirection",
    "UiSheetLayout",
    "UiSheetRole",
    "add_ui_atlas_nodes",
    "atlas_artifact_refs",
    "atlas_content_task",
    "atlas_node_ids",
    "atlas_review_prompt",
    "icon_content_task",
    "icon_review_prompt",
    "sheet_family",
    "ui_atlas_manifest",
    "ui_atlas_manifest_block",
    "ui_atlas_review_schema",
    "validate_ui_sheet",
]
