"""The shell's plates as one recipe-neutral node triplet, fanned out over the plate role.

Every genre that shows a title screen draws the same three things — a picture, a mark,
and a picture with a strip kept quiet at the bottom — and the geometry, the gate and the
review question do not know which genre asked. So the triplet lives beside the contract
it serves, under the component's own taxonomy name (``2d/shell/plate.*``), exactly as the
UI sheet triplet does.

A **role** here is one plate the document declared: a backdrop layer at a depth, an
emblem, a loading backdrop, or one shot of the opening. Adding a screen is a fan-out
change over ``document_plate_roles``, not a new node type.

A host recipe supplies what only it knows — its authored document, the art direction that
wraps each prompt, the digests that make a plate cache-identifiable inside its own graph,
and (where it keeps attempt ledgers) a provider-call wrapper. Nothing here reads a game,
a genre, or a camera.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, cast

from gnode import (
    AuthoredInput,
    BinaryArtifact,
    Graph,
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
    Port,
    PortRef,
    ProvenanceInput,
    SoftwareIdentity,
    StructuredGenerationRequest,
    StructuredGenerationService,
    StructuredOutputSchema,
    StructuredReference,
    VideoGenerationRequest,
    VideoGenerationService,
    VideoReference,
    VideoResolution,
    ViewArchetype,
    WorkloadRequestV1,
    atomic_write_json,
    dependency_port,
    write_artifact_with_provenance_async,
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
from stage_gen.components.game_shell.clips import (
    SHELL_CLIP_VALIDATION_VERSION,
    match_title_verdict,
    shell_clip_record,
)
from stage_gen.components.game_shell.layouts import (
    CUTOUT_ALPHA_POLICY,
    LOADING_SCREEN,
    OPAQUE_ALPHA_POLICY,
    OPENING_CLIP,
    OPENING_SHOT,
    TITLE_SCREEN,
    ShellLayout,
)
from stage_gen.components.game_shell.models import (
    FIRST_SHELL_DRAW,
    GameShell,
    ShellClip,
    ShellPlate,
)
from stage_gen.components.game_shell.plates import (
    SHELL_PLATE_VALIDATION_VERSION,
    canonicalize_shell_plate,
    shell_plate_evidence,
    validate_shell_plate,
)
from stage_gen.components.video_clip import (
    CLIP_REVIEW_CELL_WIDTH,
    CLIP_REVIEW_COLUMNS,
    admit_clip_bytes,
    admit_clip_file,
    clip_sample_times,
)
from stage_gen.media import (
    contact_sheet,
    data_url,
    extract_frame_png,
    run_process,
    scratch_clip,
    theora_transcode_args,
)

_P = "2d/shell"
_PROVIDER = NodePolicy(max_attempts=6)

IMAGE_FEATURES = ("transparent_background", "reference_images")
STRUCTURED_FEATURES = ("structured_output", "image_input")

#: The generate node's cache contract: what the model is asked to paint. Bumping it
#: re-bills every plate, so measured facts only the local gate reads live under the
#: validation version instead.
SHELL_CONTRACT_VERSION = "shell-plate-v1"
SHELL_REVIEW_VERSION = "shell-plate-review-v1"
SHELL_EVIDENCE_VERSION = "shell-plate-evidence-v1"
SHELL_REVIEW_SCHEMA_NAME = "shell_plate_review"

SHELL_RAW_KIND = "shell-plate-raw-v1"
SHELL_IMAGE_KIND = "shell-plate-v1"
SHELL_VALIDATION_KIND = "shell-plate-validation-v1"
SHELL_EVIDENCE_KIND = "shell-plate-evidence-v1"
SHELL_VERDICT_KIND = "review-verdict-v1"

SHELL_PLATE_GENERATE = NodeType(
    type_id=f"{_P}/plate.generate",
    title="Shell plate",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="shell-plate-v2",
)

SHELL_PLATE_VALIDATE = NodeType(
    type_id=f"{_P}/plate.validate",
    title="Shell plate admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="shell-plate-validate-v1",
)

SHELL_PLATE_REVIEW = NodeType(
    type_id=f"{_P}/plate.review",
    title="Shell plate review",
    archetype=ViewArchetype.JUDGE,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=_PROVIDER,
    contract_version="shell-plate-review-v1",
)

#: The typeface the host sets every composited string in. It is authored, not drawn, so
#: this node draws nothing — it republishes the package's face into the run, because a
#: host resolves nothing above the run root and a manifest may only bind what the run
#: carries. Local, free, and present exactly when the document declares a face.
SHELL_TYPEFACE_PUBLISH = NodeType(
    type_id=f"{_P}/typeface.publish",
    title="Shell typeface",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="shell-typeface-v1",
)

VIDEO_FEATURES = ("reference_images",)

#: The two codecs a clip wears: the response arrives as h264 in mp4 and is published as
#: Theora in Ogg, the only video codec the pinned host plays.
CLIP_SOURCE_CODEC = "h264"
CLIP_PUBLISHED_CODEC = "theora"

#: Which rung of the route's ladder a canvas is. Derived rather than declared beside the
#: layout, because the two disagreeing is a gate that refuses every honest draw: ask for
#: 720p, measure against a 1080p canvas, and six attempts die on a discrepancy nobody
#: authored.
_RESOLUTION_BY_HEIGHT: dict[int, VideoResolution] = {
    360: "360p",
    720: "720p",
    1080: "1080p",
    2160: "4k",
}


def clip_resolution(layout: ShellLayout) -> VideoResolution:
    """The rung this layout's canvas is, refusing a canvas no route draws."""

    height = layout.canvas[1]
    if height not in _RESOLUTION_BY_HEIGHT:
        raise ValueError(
            f"{layout.layout} declares a {layout.canvas[0]}x{height} canvas, which is not "
            f"a rung a video route draws ({', '.join(_RESOLUTION_BY_HEIGHT.values())})"
        )
    return _RESOLUTION_BY_HEIGHT[height]


#: The clip generate node's cache contract. Separate from the plate's: the two are
#: bought from different routes and asked for different things, and bumping one must
#: not re-bill the other.
SHELL_CLIP_CONTRACT_VERSION = "shell-clip-v1"
#: The adopt node's own cache contract, separate from the draw's for the reason the draw's
#: is separate from the plate's: the two nodes read different things, and bumping the one
#: that copies a file must never re-buy the one that films a shot.
SHELL_CLIP_ADOPT_CONTRACT_VERSION = "shell-clip-adopt-v1"
SHELL_CLIP_REVIEW_VERSION = "shell-clip-review-v2"
SHELL_CLIP_REVIEW_SCHEMA_NAME = "shell_clip_review"

#: The encoder a clip is published through, named rather than discovered. A plan cannot
#: be keyed on the output of ``ffmpeg -version``, so the constant is the identity and the
#: measured version string is recorded beside the artifact. Bumping the encoder is a
#: deliberate edit here that re-runs every transcode and re-buys no clip.
SHELL_CLIP_ENCODER = "theora-ffmpeg7-v1"

SHELL_CLIP_RAW_KIND = "shell-clip-raw-v1"
SHELL_CLIP_KIND = "shell-clip-v1"
SHELL_CLIP_VALIDATION_KIND = "shell-clip-validation-v1"
SHELL_CLIP_CONTACT_KIND = "shell-clip-contact-v1"
SHELL_CLIP_PUBLISHED_KIND = "shell-clip-published-v1"
SHELL_OPENING_ENDING_KIND = "shell-opening-ending-v1"

SHELL_CLIP_GENERATE = NodeType(
    type_id=f"{_P}/clip.generate",
    title="Shell clip",
    archetype=ViewArchetype.VIDEO,
    operation="video_generation",
    features=VIDEO_FEATURES,
    policy=_PROVIDER,
    contract_version="shell-clip-v1",
)

#: The clip a package already owns, copied into the run instead of bought. Local, and
#: deliberately the same archetype as the draw it replaces: what a reader is looking at is
#: a video either way, and only the price differs. It writes the same raw port, so the gate,
#: the transcode and the review downstream cannot tell which one filled it.
SHELL_CLIP_ADOPT = NodeType(
    type_id=f"{_P}/clip.adopt",
    title="Shell clip adoption",
    archetype=ViewArchetype.VIDEO,
    operation="local",
    contract_version="shell-clip-adopt-v1",
)

SHELL_CLIP_VALIDATE = NodeType(
    type_id=f"{_P}/clip.validate",
    title="Shell clip admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="shell-clip-validate-v1",
)

#: The publication transcode. The pinned host plays one video codec, so a clip is
#: republished as Ogg Theora with fixed parameters - no crop, no trim, no scale, no
#: filter. It is a transform rather than a repair because the admission gate runs again
#: on the result, so nothing it did can hide from the check that follows it.
SHELL_CLIP_TRANSCODE = NodeType(
    type_id=f"{_P}/clip.transcode",
    title="Shell clip publication",
    archetype=ViewArchetype.TRANSFORM,
    operation="local",
    contract_version="shell-clip-transcode-v1",
)

SHELL_CLIP_REVIEW = NodeType(
    type_id=f"{_P}/clip.review",
    title="Shell clip review",
    archetype=ViewArchetype.JUDGE,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=_PROVIDER,
    contract_version="shell-clip-review-v1",
)

#: The one ending that is a claim about the picture rather than about presentation, so
#: the one that is measured. Present exactly when the document declares ``match_title``,
#: and the family's only node that reads two screens at once.
SHELL_OPENING_ENDING = NodeType(
    type_id=f"{_P}/opening.ending",
    title="Opening ending",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="shell-opening-ending-v1",
)

#: Every type this module owns, for a recipe's own type census and registry checks.
SHELL_NODE_TYPES = (
    SHELL_PLATE_GENERATE,
    SHELL_PLATE_VALIDATE,
    SHELL_PLATE_REVIEW,
    SHELL_CLIP_GENERATE,
    SHELL_CLIP_ADOPT,
    SHELL_CLIP_VALIDATE,
    SHELL_CLIP_TRANSCODE,
    SHELL_CLIP_REVIEW,
    SHELL_OPENING_ENDING,
    SHELL_TYPEFACE_PUBLISH,
)

SHELL_TYPEFACE_KIND = "shell-typeface-v1"


def shell_typeface_ref(shell: GameShell) -> str:
    """Where the run carries the face, keyed by the name the package gave it."""

    if shell.typeface is None:
        raise ValueError("this shell document declares no typeface")
    return f"shell/typeface/{PurePosixPath(shell.typeface.source).name}"


#: What a reviewer answers about a clip that no measurement can. Deliberately not a
#: superset of the plate's: a clip has no reserved region to keep quiet, and it has one
#: question a still never has - whether the look survived the frames nobody drew.
SHELL_CLIP_REVIEW_CHECKS = (
    "style_coherence",
    "text_free",
    "subject_matches_brief",
    "motion_reads_as_hand_drawn",
)

#: What a reviewer answers that the pixel gate cannot.
SHELL_REVIEW_CHECKS = (
    "style_coherence",
    "text_free",
    "subject_matches_brief",
    "reserved_regions_read_as_quiet",
)


@dataclass(frozen=True, slots=True)
class ShellPlateRole:
    """One plate the document declared, resolved to everything the triplet needs."""

    role: str
    screen: str
    layout: ShellLayout
    alpha_policy: str
    #: The reserved regions *this* plate must keep quiet. A shot with no card is not
    #: gated on the card band.
    measured_regions: tuple[str, ...]
    plate: ShellPlate

    def geometry_record(self) -> dict[str, object]:
        """The declared geometry this plate is billed against."""

        return {
            "role": self.role,
            "screen": self.screen,
            "alpha_policy": self.alpha_policy,
            "measured_regions": list(self.measured_regions),
            **self.layout.geometry_record(),
        }


def document_plate_roles(shell: GameShell) -> tuple[ShellPlateRole, ...]:
    """Every plate one document plans, in the order a player meets it.

    A loading backdrop bound to an artifact the run already publishes is absent from this
    list: it is not generated, so it is never billed and never gated.
    """

    roles: list[ShellPlateRole] = []
    if shell.opening is not None:
        for shot in shell.opening.shots:
            # A clip shot is planned by the clip family: it is bought from another
            # route, gated on whether it moves, and published as a container this
            # one knows nothing about.
            if not isinstance(shot.plate, ShellPlate):
                continue
            roles.append(
                ShellPlateRole(
                    role=f"opening_{shot.shot_id}",
                    screen="opening",
                    layout=OPENING_SHOT,
                    alpha_policy=shot.plate.alpha_policy,
                    measured_regions=("card_band",) if shot.card is not None else (),
                    plate=shot.plate,
                )
            )
    if shell.title is not None:
        for layer in shell.title.backdrop:
            roles.append(
                ShellPlateRole(
                    role=f"title_backdrop_{layer.depth}",
                    screen="title",
                    layout=TITLE_SCREEN,
                    alpha_policy=layer.plate.alpha_policy,
                    # Only the picture behind the text is gated for legibility; a
                    # cut-out drawn over it is mostly air and its mean says nothing.
                    #
                    # And only the *mark band* is gated, not the control stack. The
                    # wordmark is set straight onto the picture, so the picture has to
                    # carry it. The controls are not: they are `button_rect` bodies
                    # from ui.toml, and a label is legible because the button is behind
                    # it. Gating the control column measured 46%-93% of the frame
                    # height, which straddles the horizon of any landscape, and refused
                    # twelve honest paintings over two runs before this comment existed.
                    # The region stays *published* — the host still needs to know where
                    # the controls go — it is simply not a thing the backdrop must
                    # answer for.
                    measured_regions=("mark_band",) if layer.depth == "far" else (),
                    plate=layer.plate,
                )
            )
        if shell.title.emblem is not None:
            roles.append(
                ShellPlateRole(
                    role="title_emblem",
                    screen="title",
                    layout=TITLE_SCREEN,
                    alpha_policy=shell.title.emblem.alpha_policy,
                    measured_regions=(),
                    plate=shell.title.emblem,
                )
            )
    if shell.loading is not None and isinstance(shell.loading.backdrop, ShellPlate):
        roles.append(
            ShellPlateRole(
                role="loading_backdrop",
                screen="loading",
                layout=LOADING_SCREEN,
                alpha_policy=shell.loading.backdrop.alpha_policy,
                measured_regions=("status_strip",),
                plate=shell.loading.backdrop,
            )
        )
    return tuple(roles)


@dataclass(frozen=True, slots=True)
class ShellClipRole:
    """One clip the document declared, resolved to everything its chain needs."""

    role: str
    shot_id: str
    #: The shot's own length. It is what the route is asked for and what the gate
    #: measures against, which is why it is part of the clip's generation identity and
    #: only presentation for a still.
    seconds: float
    clip: ShellClip
    layout: ShellLayout = OPENING_CLIP
    #: True when this is the last shot of an opening that ends on ``match_title``.
    ends_the_opening: bool = False

    def geometry_record(self) -> dict[str, object]:
        return self.layout.geometry_record()

    def generation_identity(self) -> dict[str, object]:
        """The fields that decide whether this clip must be bought again.

        ``reference_ids`` keeps its order: a video route reads the first picture as the
        art direction the rest are judged against, so re-ordering them is a different
        ask. ``draw`` enters only above the first one, so an existing key is undisturbed
        until somebody asks for another.

        Out: the shot's move, its card, its transition, and the opening's ending. They
        change how the clip is presented or what it is checked against, not what was
        asked for, and putting any of them here would re-bill every clip in the document
        when an author changed a fade.
        """

        identity: dict[str, object] = {
            "prompt": self.clip.prompt,
            "reference_ids": list(self.clip.reference_ids),
            "seconds": self.seconds,
            "output_format": "mp4",
        }
        if self.clip.draw != FIRST_SHELL_DRAW:
            identity["draw"] = self.clip.draw
        return identity

    def adoption_identity(self) -> dict[str, object]:
        """What an adopted clip's local copy is, and the length it is admitted against.

        Deliberately not the generation identity: nothing is being asked of a route, so
        the brief, the references and the reroll counter decide nothing here. The file is
        the answer, and the digest is the whole of it - re-briefing an adopted shot
        re-runs a free local node and buys nothing.
        """

        if self.clip.take is None:
            raise ValueError(f"the {self.shot_id} shot adopts no take")
        return {"take": self.clip.take.sha256, "seconds": self.seconds}


def document_clip_roles(shell: GameShell) -> tuple[ShellClipRole, ...]:
    """Every clip one document plans, in the order a player meets it."""

    if shell.opening is None:
        return ()
    shots = shell.opening.shots
    matched = shell.opening.ending == "match_title"
    roles: list[ShellClipRole] = []
    for index, shot in enumerate(shots):
        if not isinstance(shot.plate, ShellClip):
            continue
        roles.append(
            ShellClipRole(
                role=f"opening_{shot.shot_id}",
                shot_id=shot.shot_id,
                seconds=shot.seconds,
                clip=shot.plate,
                ends_the_opening=matched and index == len(shots) - 1,
            )
        )
    return tuple(roles)


# ------------------------------------------------------------------ prompt


def plate_content_task(role: ShellPlateRole) -> str:
    """The instruction for one plate: the authored subject, then the rules it must obey.

    The quiet clause is the prompt lever that matters. Without it the gate refuses good
    paintings over and over inside the retry budget, because nothing told the model that
    part of the frame has to carry text at runtime. It is stated in thirds of the frame
    rather than in pixels, because that is what a painter can act on.
    """

    lines = [role.plate.prompt.strip()]
    if role.alpha_policy == OPAQUE_ALPHA_POLICY:
        lines.append(
            "Fill the whole frame edge to edge: one opaque picture, no transparency, "
            "no border, no vignette frame around it."
        )
    else:
        lines.append(
            "Draw one single shape on a fully transparent background: no plate, no card, "
            "no backdrop, no shadow or glow outside the shape, nothing else on the canvas."
        )
    if role.measured_regions:
        lines.append(_quiet_clause(role))
    lines.append(
        "Draw no text, no letters, no numerals, no signage, no logo, no watermark and "
        "nothing that resembles writing anywhere in the image."
    )
    return " ".join(lines)


#: Where each reserved region sits, in the terms a painter can act on.
_REGION_PLACE = {
    "mark_band": "the upper middle of the frame",
    "control_stack": "the middle of the lower half",
    "status_strip": "the strip across the bottom of the frame",
    "card_band": "the lower third of the frame",
}


def _quiet_clause(role: ShellPlateRole) -> str:
    places = [_REGION_PLACE.get(name, name) for name in role.measured_regions]
    where = places[0] if len(places) == 1 else " and ".join((", ".join(places[:-1]), places[-1]))
    return (
        f"Compose so that {where} stays quiet: even in tone, low in contrast, free of "
        "fine detail, hard edges and bright highlights, because interface text is placed "
        "over that area at runtime. Put the detail and the focal interest elsewhere."
    )


def plate_review_prompt(role: ShellPlateRole, record: Mapping[str, object]) -> str:
    """What the judge is asked, once the gate has already settled the measurable part."""

    measured = ""
    regions = record.get("regions")
    if isinstance(regions, list) and regions:
        measured = (
            " The cyan outlines mark the areas that must read as quiet enough to "
            "set text over; the gate has already measured them numerically."
        )
    return (
        f"Image 1 is a generated {role.screen} screen plate for role '{role.role}', with "
        f"the measured regions outlined. The images after it are the art-direction "
        f"references it was drawn against.{measured}\n\n"
        f"The brief was: {role.plate.prompt.strip()}\n\n"
        "Judge only what a measurement cannot: does it sit in the same world and medium as "
        "the references; is it genuinely free of text, letters, numerals, signage, logos "
        "and watermarks; does it show what the brief asked for; and do the outlined areas "
        "read as calm enough that a title or a button placed there would be legible. "
        "Report each failure as a short specific sentence."
    )


# ------------------------------------------------------------------- graph


def clip_content_task(role: ShellClipRole) -> str:
    """The authored brief, plus the clauses a clip needs and a still does not.

    The no-lettering clause is appended here rather than authored, exactly as it is for a
    plate: the loader refuses a prompt that asks for text, so a document cannot say
    "and no text" without being refused for the word.

    The rest is what the spike measured. A generated clip's tell is not the drawing, it
    is that everything moves on every frame; asking for held drawings and for motion only
    where the shot is about something buys most of that back for nothing. And the style
    has to be restated in full rather than referred to, because the model invents whatever
    the references do not show it and the invented frames are where a drawn look slides
    into a rendered one.
    """

    return (
        f"{role.clip.prompt.strip()} "
        f"The shot runs {role.seconds:g} seconds. "
        "Hold the drawing exactly as the reference images have it and do not restyle, "
        "redraw, sharpen or add detail to any shape. "
        "Animate it as limited hand-drawn animation rather than smooth video: hold each "
        "drawing for two or three frames so the motion steps rather than glides, and move "
        "only the thing the shot is about. "
        "Do not render in 3D, and use no photographic texture, gradient, soft shadow "
        "falloff, volumetric light, lens blur or depth of field. "
        "Add no lettering, caption, subtitle, logo or written mark of any kind anywhere in "
        "the frame."
    )


def clip_review_prompt(role: ShellClipRole, record: Mapping[str, object]) -> str:
    """What a reviewer is asked about a clip, shown its beats as one sheet.

    A reviewer cannot be handed a moving picture, so it is handed an ordered contact
    sheet of the clip's own frames - and it is the *published* clip's frames, because the
    picture a player sees is the one that came through the encoder.
    """

    checks = ", ".join(SHELL_CLIP_REVIEW_CHECKS)
    return (
        f"These frames are sampled in order from one {role.seconds:g}-second clip of a "
        f"game's opening cinematic, drawn against the reference images beside them. "
        f"The brief was: {role.clip.prompt.strip()} "
        f"Judge the sequence as one shot on {checks}. "
        "The style must hold across every frame, including the ones the model invented "
        "between the references; a frame that has slid into rendered 3D or photographic "
        "texture fails style_coherence. Any lettering anywhere in any frame fails "
        "text_free. Measured facts are already known and are not what you are asked "
        f"about: {record}."
    )


def shell_node_ids(role: ShellPlateRole, *, prefix: str = "shell") -> tuple[str, str, str]:
    """The generate, validate and review ids one plate occupies in a host graph."""

    return (
        f"{prefix}-{role.role}-generate",
        f"{prefix}-{role.role}-validate",
        f"{prefix}-{role.role}-review",
    )


def shell_clip_node_ids(role: ShellClipRole, *, prefix: str = "shell") -> tuple[str, ...]:
    """The four ids one clip occupies in a host graph.

    The first is named for how the clip arrives - drawn from the route, or adopted from a
    take the package already carries - because a run's node list is the clearest place to
    read which shots were bought and which were not.
    """

    first = "clip-adopt" if role.clip.take is not None else "clip-generate"
    return tuple(
        f"{prefix}-{role.role}-{stage}"
        for stage in (first, "clip-validate", "clip-publish", "clip-review")
    )


def shell_clip_artifact_refs(role: ShellClipRole) -> tuple[str, str, str, str, str]:
    """Every path one clip writes: response, record, published clip, sheet, and the
    second measurement taken after the transcode.

    The response keeps the ``.raw.`` marker the plate family already uses, which is what
    keeps it out of the host's load closure: a run carries what the route answered so the
    record means something, and the host only ever opens what it can play.
    """

    return (
        f"shell/{role.role}.raw.mp4",
        f"shell/{role.role}.clip.validation.json",
        f"shell/{role.role}.clip.ogv",
        f"shell/{role.role}.contact.png",
        f"shell/{role.role}.clip.published.json",
    )


def shell_artifact_refs(role: ShellPlateRole) -> tuple[str, str, str, str, str]:
    """Every path one plate writes: raw, canonical, validation, evidence, verdict."""

    return (
        f"shell/{role.role}.raw.png",
        f"shell/{role.role}.png",
        f"shell/{role.role}.validation.json",
        f"shell/{role.role}.evidence.png",
        f"shell/{role.role}.review.json",
    )


def add_shell_nodes(
    builder: GraphBuilder,
    *,
    root: str,
    shell: GameShell,
    style_prompt: Callable[[str], str],
    direction_digests: Sequence[str] = (),
    roles: Sequence[ShellPlateRole] | None = None,
    clip_roles: Sequence[ShellClipRole] | None = None,
    domain: str = "shell",
    prefix: str = "shell",
    attempts_port: Callable[[str], Port] | None = None,
    image_workload: Callable[[ImageRouteRequirementsV1], WorkloadRequestV1] | None = None,
) -> list[str]:
    """Add one generate/validate/review chain per declared plate.

    The layout's geometry record is what the cache key hashes, so a change to where a
    region sits re-bills the plate that has to keep it quiet, and a change to how a guide
    is drawn does not. Returns the review node ids, which are the terminals a host adds
    to its own list.
    """

    plate_roles = tuple(roles) if roles is not None else document_plate_roles(shell)
    references = {entry.reference_id: entry for entry in shell.references}
    terminals: list[str] = []
    for role in plate_roles:
        generate_id, validate_id, review_id = shell_node_ids(role, prefix=prefix)
        raw_ref, image_ref, validation_ref, evidence_ref, verdict_ref = shell_artifact_refs(role)
        authored = tuple(
            AuthoredInput(
                label=reference_id,
                ref=references[reference_id].source,
                sha256=references[reference_id].source_sha256,
            )
            for reference_id in role.plate.reference_ids
        )
        geometry_digest = object_digest(role.geometry_record())
        direction_digest = object_digest(role.plate.model_dump(mode="json"))
        prompt = style_prompt(plate_content_task(role))

        generate_ports: list[Port] = [artifact_port("image", raw_ref, SHELL_RAW_KIND)]
        review_ports: list[Port] = [artifact_port("verdict", verdict_ref, SHELL_VERDICT_KIND)]
        if attempts_port is not None:
            generate_ports.append(attempts_port(generate_id))
            review_ports.append(attempts_port(review_id))

        generated = builder.add(
            SHELL_PLATE_GENERATE,
            generate_id,
            domain=domain,
            description=f"Draw the {role.screen} screen's {role.role} plate",
            depends_on=(root,),
            cache_depends_on=(),
            params={"role": role.role},
            input_digests=(
                *direction_digests,
                object_digest({"contract": SHELL_CONTRACT_VERSION}),
                direction_digest,
                *(entry.sha256 for entry in authored),
                geometry_digest,
            ),
            ports=tuple(generate_ports),
            workload=(
                None
                if image_workload is None
                else image_workload(
                    ImageRouteRequirementsV1(
                        operation_variant="edit" if authored else "generation",
                        background=(
                            "transparent" if role.alpha_policy == CUTOUT_ALPHA_POLICY else "opaque"
                        ),
                        output_format="png",
                        size=f"{role.layout.canvas[0]}x{role.layout.canvas[1]}",
                        reference_count=len(authored),
                    )
                )
            ),
            card=NodeCard(prompt=prompt, authored_inputs=authored),
        )
        validated = builder.add(
            SHELL_PLATE_VALIDATE,
            validate_id,
            domain=domain,
            description=f"Admit the {role.role} plate and measure its reserved regions",
            depends_on=(generated.node_id,),
            params={"role": role.role},
            input_digests=(
                object_digest({"contract": SHELL_PLATE_VALIDATION_VERSION}),
                direction_digest,
                geometry_digest,
            ),
            ports=(
                artifact_port("image", image_ref, SHELL_IMAGE_KIND),
                record_port("validation", validation_ref, SHELL_VALIDATION_KIND),
                artifact_port("evidence", evidence_ref, SHELL_EVIDENCE_KIND),
            ),
            card=NodeCard(reference_inputs=(PortRef(node_id=generated.node_id, port_id="image"),)),
            duration_seconds=2.0,
        )
        reviewed = builder.add(
            SHELL_PLATE_REVIEW,
            review_id,
            domain=domain,
            description=f"Review the {role.role} plate against its references",
            depends_on=(validated.node_id,),
            params={"role": role.role},
            input_digests=(
                object_digest({"contract": SHELL_REVIEW_VERSION}),
                direction_digest,
            ),
            ports=tuple(review_ports),
            card=NodeCard(
                prompt=plate_review_prompt(role, {}),
                schema_name=SHELL_REVIEW_SCHEMA_NAME,
                reference_inputs=(PortRef(node_id=validated.node_id, port_id="image"),),
                authored_inputs=authored,
            ),
        )
        terminals.append(reviewed.node_id)

    # Derived from the document unless a host overrides them. Deliberately not tied to
    # ``roles``: a host that names its plates explicitly still means every clip the
    # document declares, and reading one override as a decision about the other would
    # silently drop them.
    clips = tuple(clip_roles) if clip_roles is not None else document_clip_roles(shell)
    ending_inputs: list[PortRef] = []
    for clip_role in clips:
        generate_id, validate_id, publish_id, review_id = shell_clip_node_ids(
            clip_role, prefix=prefix
        )
        (
            raw_ref,
            validation_ref,
            clip_ref,
            contact_ref,
            published_ref,
        ) = shell_clip_artifact_refs(clip_role)
        authored = tuple(
            AuthoredInput(
                label=reference_id,
                ref=references[reference_id].source,
                sha256=references[reference_id].source_sha256,
            )
            for reference_id in clip_role.clip.reference_ids
        )
        geometry_digest = object_digest(clip_role.geometry_record())
        # What this shot IS, for everything downstream of the first node. A drawn clip is
        # its ask; an adopted one is the file, because two takes of one brief are two
        # different pictures and the gate's record has to move with them. Reading the ask
        # for an adopted shot would let a swapped take restore the previous clip's record
        # out of the cache.
        adopted = clip_role.clip.take
        identity_digest = object_digest(
            clip_role.adoption_identity()
            if adopted is not None
            else clip_role.generation_identity()
        )
        prompt = style_prompt(clip_content_task(clip_role))

        clip_generate_ports: list[Port] = [artifact_port("clip", raw_ref, SHELL_CLIP_RAW_KIND)]
        clip_review_ports: list[Port] = [
            artifact_port("verdict", f"shell/{clip_role.role}.clip.review.json", SHELL_VERDICT_KIND)
        ]
        if attempts_port is not None:
            clip_generate_ports.append(attempts_port(generate_id))
            clip_review_ports.append(attempts_port(review_id))

        if adopted is not None:
            # Zero operations, and no reference reaches a provider: the picture is already
            # made. The brief still travels on the card, because a reader of the run wants
            # to know what this shot was asked to be even when nobody asked for it here.
            generated = builder.add(
                SHELL_CLIP_ADOPT,
                generate_id,
                domain=domain,
                description=f"Adopt the auditioned {clip_role.shot_id} clip, chosen by eye",
                depends_on=(root,),
                cache_depends_on=(),
                params={"role": clip_role.role},
                input_digests=(
                    object_digest({"contract": SHELL_CLIP_ADOPT_CONTRACT_VERSION}),
                    identity_digest,
                    geometry_digest,
                ),
                ports=tuple(clip_generate_ports),
                card=NodeCard(prompt=prompt, authored_inputs=authored),
                duration_seconds=5.0,
            )
        else:
            generated = builder.add(
                SHELL_CLIP_GENERATE,
                generate_id,
                domain=domain,
                description=f"Film the opening's {clip_role.shot_id} shot",
                depends_on=(root,),
                cache_depends_on=(),
                params={"role": clip_role.role},
                input_digests=(
                    *direction_digests,
                    object_digest({"contract": SHELL_CLIP_CONTRACT_VERSION}),
                    identity_digest,
                    *(entry.sha256 for entry in authored),
                    geometry_digest,
                ),
                ports=tuple(clip_generate_ports),
                card=NodeCard(prompt=prompt, authored_inputs=authored),
                duration_seconds=180.0,
            )
        validated = builder.add(
            SHELL_CLIP_VALIDATE,
            validate_id,
            domain=domain,
            description=f"Admit the {clip_role.shot_id} clip and measure whether it moves",
            depends_on=(generated.node_id,),
            params={"role": clip_role.role},
            input_digests=(
                object_digest({"contract": SHELL_CLIP_VALIDATION_VERSION}),
                identity_digest,
                geometry_digest,
            ),
            ports=(record_port("validation", validation_ref, SHELL_CLIP_VALIDATION_KIND),),
            card=NodeCard(reference_inputs=(PortRef(node_id=generated.node_id, port_id="clip"),)),
            duration_seconds=20.0,
        )
        published = builder.add(
            SHELL_CLIP_TRANSCODE,
            publish_id,
            domain=domain,
            description=f"Publish the {clip_role.shot_id} clip in the codec the host plays",
            # Both: the gate for ordering, and the response for the bytes it transcodes.
            # A handler reaches its inputs through its own dependencies, so naming only
            # the gate leaves the file it is meant to read unreachable.
            depends_on=(validated.node_id, generated.node_id),
            params={"role": clip_role.role},
            # The encoder is named rather than measured: a plan cannot be keyed on what
            # a binary reports at run time, so the constant is the identity and the
            # version string is recorded beside the artifact.
            input_digests=(object_digest({"encoder": SHELL_CLIP_ENCODER}), identity_digest),
            ports=(
                artifact_port("clip", clip_ref, SHELL_CLIP_KIND),
                artifact_port("contact", contact_ref, SHELL_CLIP_CONTACT_KIND),
                # The second measurement, and the encoder that produced what it read.
                # Declared rather than written beside the clip: an output a node does
                # not declare is an output the cache cannot admit.
                record_port("published", published_ref, SHELL_CLIP_PUBLISHED_KIND),
            ),
            card=NodeCard(reference_inputs=(PortRef(node_id=generated.node_id, port_id="clip"),)),
            duration_seconds=30.0,
        )
        reviewed = builder.add(
            SHELL_CLIP_REVIEW,
            review_id,
            domain=domain,
            description=f"Review the {clip_role.shot_id} clip's own frames",
            # The sheet it judges, and the record it is told not to re-judge.
            depends_on=(published.node_id, validated.node_id),
            params={"role": clip_role.role},
            input_digests=(
                object_digest({"contract": SHELL_CLIP_REVIEW_VERSION}),
                identity_digest,
            ),
            ports=tuple(clip_review_ports),
            card=NodeCard(
                prompt=clip_review_prompt(clip_role, {}),
                schema_name=SHELL_CLIP_REVIEW_SCHEMA_NAME,
                reference_inputs=(PortRef(node_id=published.node_id, port_id="contact"),),
                authored_inputs=authored,
            ),
        )
        terminals.append(reviewed.node_id)
        if clip_role.ends_the_opening:
            ending_inputs.append(PortRef(node_id=published.node_id, port_id="clip"))

    if ending_inputs:
        # The family's only cross-screen edge: the last shot's published clip, and the
        # title backdrop it claims to end on. It reads the *published* clip because the
        # last frame a player sees is the one that came through the encoder.
        backdrop = f"{prefix}-title_backdrop_far-validate"
        ending_inputs.append(PortRef(node_id=backdrop, port_id="image"))
        ended = builder.add(
            SHELL_OPENING_ENDING,
            f"{prefix}-opening-ending",
            domain=domain,
            description="Measure the opening's last frame against the title it ends on",
            depends_on=tuple(ref.node_id for ref in ending_inputs),
            params={"ending": "match_title"},
            input_digests=(object_digest({"contract": SHELL_CLIP_VALIDATION_VERSION}),),
            ports=(record_port("ending", "shell/opening.ending.json", SHELL_OPENING_ENDING_KIND),),
            card=NodeCard(reference_inputs=tuple(ending_inputs)),
            duration_seconds=5.0,
        )
        terminals.append(ended.node_id)

    if shell.typeface is not None:
        face = shell.typeface
        published = builder.add(
            SHELL_TYPEFACE_PUBLISH,
            f"{prefix}-typeface",
            domain=domain,
            description=f"Publish the {face.family} face the shell's strings are set in",
            depends_on=(root,),
            # The lock is a barrier here, not lineage: what this node republishes is one
            # file, and its identity is that file's digest and the record beside it. An
            # edit anywhere else in the package must not re-run it.
            cache_depends_on=(),
            params={"family": face.family},
            input_digests=(face.source_sha256, object_digest(face.model_dump(mode="json"))),
            ports=(artifact_port("typeface", shell_typeface_ref(shell), SHELL_TYPEFACE_KIND),),
            card=NodeCard(
                authored_inputs=(
                    AuthoredInput(label="typeface", ref=face.source, sha256=face.source_sha256),
                )
            ),
            duration_seconds=0.25,
        )
        terminals.append(published.node_id)
    return terminals


# ----------------------------------------------------------------- handler


class _PackageFile(Protocol):
    """The two facts the triplet needs about an authored file, however a host stores it."""

    @property
    def data(self) -> bytes: ...

    @property
    def sha256(self) -> str: ...


@dataclass(frozen=True)
class ShellHost:
    """Everything the shared triplet needs from whichever recipe hosts it."""

    shell: GameShell
    run_dir: Path
    package_id: str
    file: Callable[[str], _PackageFile]
    component: SoftwareIdentity
    tool: SoftwareIdentity
    #: The declared face's bytes. Separate from ``file`` because a typeface is not a
    #: visual reference: it never reaches a provider, and it is republished rather than
    #: attached. Required exactly when the document declares one.
    typeface: Callable[[], _PackageFile] | None = None
    #: An adopted clip's bytes, by the take path the document declared. Separate from
    #: ``file`` because a take is bound by digest rather than loaded with the package: it
    #: may legitimately be absent while the package still loads and plans, and the refusal
    #: for that belongs to whoever knows where the package keeps its media. Required
    #: exactly when some shot declares a take.
    take: Callable[[str], _PackageFile] | None = None


class ShellHandlers:
    """The three coroutines behind the shell node types, owned by no recipe."""

    def __init__(
        self,
        host: ShellHost,
        *,
        graph: Graph,
        image_service: ImageGenerationService,
        structured_service: StructuredGenerationService[object],
        provider_call: ProviderCall | None = None,
        video_service: VideoGenerationService | None = None,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        theora_ffmpeg: str | None = None,
    ) -> None:
        self._host = host
        self._graph = graph
        self._images = image_service
        self._structured = structured_service
        self._provider_call = provider_call
        self._video = video_service
        self._ffmpeg = ffmpeg
        self._ffprobe = ffprobe
        #: The encoder a clip is published through. Separate from ``ffmpeg`` because the
        #: build that measures a clip and the build that can write Ogg Theora are not
        #: the same one on a current machine.
        self._theora_ffmpeg = theora_ffmpeg or ffmpeg
        self._roles = {role.role: role for role in document_plate_roles(host.shell)}
        self._clip_roles = {role.role: role for role in document_clip_roles(host.shell)}

    async def generate(self, node: Node) -> NodeExecutionResult:
        role = self._role(node)
        output = self._host.run_dir / node.port("image").artifact_ref
        prompt = card_prompt(node)
        request = ImageGenerationRequest(
            prompt=prompt,
            artifact_path=output,
            input_references=self._image_references(role.plate.reference_ids),
            quality="max",
            background=("transparent" if role.alpha_policy == CUTOUT_ALPHA_POLICY else "opaque"),
            output_format="png",
            size=f"{role.layout.canvas[0]}x{role.layout.canvas[1]}",
            timeout_seconds=600,
            metadata={
                "checkpoint": "shell",
                "role": role.role,
                "screen": role.screen,
                "layout": role.layout.layout,
                "alpha_policy": role.alpha_policy,
            },
            validate=lambda artifact: validate_shell_plate(
                artifact.data,
                layout=role.layout,
                alpha_policy=role.alpha_policy,
                measured_regions=role.measured_regions,
            ),
        )
        result = await self._call(node, role.role, prompt, lambda: self._images.generate(request))
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def validate(self, node: Node) -> NodeExecutionResult:
        role = self._role(node)
        run_dir = self._host.run_dir
        source = run_dir / self._dependency(node, kind=SHELL_RAW_KIND)
        data = source.read_bytes()
        record = validate_shell_plate(
            data,
            layout=role.layout,
            alpha_policy=role.alpha_policy,
            measured_regions=role.measured_regions,
        )
        canonical_data, rewrite = canonicalize_shell_plate(data, alpha_policy=role.alpha_policy)
        canonical = run_dir / node.port("image").artifact_ref
        await self._write_local_image(
            canonical,
            canonical_data,
            prompt="Clamp the admitted alpha and publish the canonical shell plate.",
            inputs=((source.relative_to(run_dir).as_posix(), data),),
            validation={**record, **rewrite},
            model=SHELL_PLATE_VALIDATION_VERSION,
        )
        atomic_write_json(
            run_dir / node.port("validation").artifact_ref,
            {
                "schema_version": 1,
                "kind": SHELL_VALIDATION_KIND,
                "role": role.role,
                "screen": role.screen,
                **record,
                **rewrite,
            },
        )
        evidence_data = shell_plate_evidence(canonical_data, record)
        await self._write_local_image(
            run_dir / node.port("evidence").artifact_ref,
            evidence_data,
            prompt="Outline every measured region on the canonical plate for the reviewer.",
            inputs=((canonical.relative_to(run_dir).as_posix(), canonical_data),),
            validation={"source_validation": record},
            model=SHELL_EVIDENCE_VERSION,
        )
        return self._result(node, provider_operations=0)

    # -------------------------------------------------------------- clips

    async def generate_clip(self, node: Node) -> NodeExecutionResult:
        """Film one shot, gated on whether it moves before it is ever persisted."""

        role = self._clip_role(node)
        video = self._video
        if video is None:
            raise ValueError("this host was built without a video route")
        output = self._host.run_dir / node.port("clip").artifact_ref
        prompt = card_prompt(node)
        request = VideoGenerationRequest(
            prompt=prompt,
            artifact_path=output,
            references=tuple(
                VideoReference(url=reference.url, provenance_ref=reference.provenance_ref)
                for reference in self._image_references(role.clip.reference_ids)
            ),
            duration_seconds=role.seconds,
            resolution=clip_resolution(role.layout),
            aspect_ratio="16:9",
            # A video attempt is minutes, not seconds. The recipe's own node timeout has
            # to clear six of these plus backoff or the scheduler kills the node and the
            # failure history dies with it.
            timeout_seconds=600,
            metadata={
                "checkpoint": "shell",
                "role": role.role,
                "screen": "opening",
                "layout": role.layout.layout,
            },
            validate=lambda artifact: admit_clip_bytes(
                artifact.data,
                expected_seconds=role.seconds,
                expected_size=role.layout.canvas,
                expected_codec=CLIP_SOURCE_CODEC,
                ffmpeg=self._ffmpeg,
                ffprobe=self._ffprobe,
            ),
        )
        result = await self._call(
            node, f"shell-clip-{role.role}", prompt, lambda: video.generate(request)
        )
        return self._result(node, provider_operations=1, attempts=result.attempts)

    async def adopt_clip(self, node: Node) -> NodeExecutionResult:
        """Copy an auditioned clip into the run through the gate the route's answer meets.

        Nothing is asked of a provider: this shot was drawn once, outside a run, and
        somebody looked at its frames and kept it. What makes that safe is that the copy
        is admitted exactly as a fresh draw is - length, rectangle, codec, motion - so an
        adopted clip cannot enter a run through a door the drawn one could not.

        The one check a draw does not need: the file must match the digest the package
        declared, or the package is describing a clip nobody has.
        """

        role = self._clip_role(node)
        take = role.clip.take
        if take is None:
            raise ValueError(f"the {role.shot_id} shot adopts no take")
        if self._host.take is None:
            raise ValueError("this host was built without a way to read adopted takes")
        package_file = self._host.take(take.path)
        if package_file.sha256 != take.sha256:
            raise ValueError(
                f"the {role.shot_id} take does not match its declared sha256: "
                f"declared {take.sha256}, found {package_file.sha256}"
            )
        facts = await admit_clip_bytes(
            package_file.data,
            expected_seconds=role.seconds,
            expected_size=role.layout.canvas,
            expected_codec=CLIP_SOURCE_CODEC,
            ffmpeg=self._ffmpeg,
            ffprobe=self._ffprobe,
        )
        ref = f"package://{self._host.package_id}/{take.path}#sha256={package_file.sha256}"
        await write_artifact_with_provenance_async(
            self._host.run_dir / node.port("clip").artifact_ref,
            BinaryArtifact(data=package_file.data, media_type="video/mp4"),
            ProvenanceInput(
                provider="local",
                model=SHELL_CLIP_ADOPT_CONTRACT_VERSION,
                prompt=card_prompt(node),
                refs=[take.path],
                inputs=[
                    InputProvenance(
                        ref=ref,
                        sha256=package_file.sha256,
                        source="content",
                        bytes=len(package_file.data),
                        media_type="video/mp4",
                    )
                ],
                params={"role": role.role, "shot_id": role.shot_id},
                validation={
                    "adopted_from": take.path,
                    "adopted_sha256": package_file.sha256,
                    # The pick was made over audition draws of this brief, by somebody
                    # reading the frames; the gate only confirms the file is a clip of the
                    # shape asked for.
                    "accepted_by": "audition_pick",
                    **facts,
                },
                component=self._host.component,
                tool=self._host.tool,
                attempts=1,
            ),
        )
        return self._result(node, provider_operations=0)

    async def validate_clip(self, node: Node) -> NodeExecutionResult:
        """Re-state the admission over the persisted response, as a record.

        The retry owner already refused anything that failed, so this cannot fail on a
        fresh run - it exists so a cache hit clears the same gate, and so the record the
        published pass is compared against is on disk.
        """

        role = self._clip_role(node)
        run_dir = self._host.run_dir
        source = run_dir / self._dependency(node, kind=SHELL_CLIP_RAW_KIND)
        facts = await admit_clip_file(
            source,
            expected_seconds=role.seconds,
            expected_size=role.layout.canvas,
            expected_codec=CLIP_SOURCE_CODEC,
            ffmpeg=self._ffmpeg,
            ffprobe=self._ffprobe,
        )
        atomic_write_json(
            run_dir / node.port("validation").artifact_ref,
            {
                "schema_version": 1,
                "kind": SHELL_CLIP_VALIDATION_KIND,
                "role": role.role,
                "shot_id": role.shot_id,
                **shell_clip_record(facts, layout=role.layout, seconds=role.seconds),
            },
        )
        return self._result(node, provider_operations=0)

    async def publish_clip(self, node: Node) -> NodeExecutionResult:
        """Transcode into the one codec the host plays, then measure it again.

        Measuring the result is what makes this publication rather than repair: the
        transform is fixed - no crop, no trim, no scale, no filter - and everything the
        gate checked before it is checked again after, so nothing it did can hide.
        """

        role = self._clip_role(node)
        run_dir = self._host.run_dir
        source = run_dir / self._dependency(node, kind=SHELL_CLIP_RAW_KIND)

        version = await run_process(self._theora_ffmpeg, ["-version"], 60.0)
        encoder = next((line.strip() for line in version.stdout.splitlines() if line.strip()), "")
        if not encoder.lower().startswith("ffmpeg version"):
            raise ValueError("the theora encoder did not report a recognizable version")

        # The encoder writes to scratch, never to the published path. The artifact lands
        # only after the second measurement passes, and it lands through the provenance
        # writer like everything else in a run: an encoder writing the final path itself
        # publishes a clip nothing checked, under no sidecar, and the cache is right to
        # refuse a node whose outputs do not match the ports it declared.
        async with scratch_clip(b"\0", suffix=".ogv") as scratch:
            await run_process(self._theora_ffmpeg, theora_transcode_args(source, scratch), 900.0)
            published = await admit_clip_file(
                scratch,
                expected_seconds=role.seconds,
                expected_size=role.layout.canvas,
                expected_codec=CLIP_PUBLISHED_CODEC,
                ffmpeg=self._ffmpeg,
                ffprobe=self._ffprobe,
            )
            frames = [
                await extract_frame_png(scratch, at_seconds=at, ffmpeg=self._ffmpeg)
                for at in clip_sample_times(role.seconds)
            ]
            data = scratch.read_bytes()

        target = run_dir / node.port("clip").artifact_ref
        source_bytes = source.read_bytes()
        await write_artifact_with_provenance_async(
            target,
            BinaryArtifact(data=data, media_type="video/ogg"),
            ProvenanceInput(
                provider="local",
                model=SHELL_CLIP_ENCODER,
                prompt="Publish the admitted clip in the one codec the host plays.",
                refs=[source.relative_to(run_dir).as_posix()],
                inputs=[
                    InputProvenance(
                        ref=source.relative_to(run_dir).as_posix(),
                        sha256=content_sha256(source_bytes),
                        source="content",
                        bytes=len(source_bytes),
                        media_type="video/mp4",
                    )
                ],
                params={"encoder": SHELL_CLIP_ENCODER, "encoder_version": encoder},
                validation={**published, "pixel_rewrite": "theora_publication_v1"},
                component=self._host.component,
                tool=self._host.tool,
                attempts=1,
            ),
        )
        await self._write_local_image(
            run_dir / node.port("contact").artifact_ref,
            contact_sheet(frames, columns=CLIP_REVIEW_COLUMNS, cell_width=CLIP_REVIEW_CELL_WIDTH),
            prompt="Lay the published clip's own frames out in order for the reviewer.",
            inputs=((target.relative_to(run_dir).as_posix(), data),),
            validation={"frames": len(frames), "sampled_at": list(clip_sample_times(role.seconds))},
            model=SHELL_CLIP_ENCODER,
        )
        record = shell_clip_record(
            {}, layout=role.layout, seconds=role.seconds, published_facts=published
        )
        atomic_write_json(
            run_dir / node.port("published").artifact_ref,
            {
                "schema_version": 1,
                "kind": SHELL_CLIP_PUBLISHED_KIND,
                "role": role.role,
                "encoder": SHELL_CLIP_ENCODER,
                "encoder_version": encoder,
                **record,
            },
        )
        return self._result(node, provider_operations=0)

    async def measure_ending(self, node: Node) -> NodeExecutionResult:
        """Measure the opening's last frame against the title it claims to end on."""

        run_dir = self._host.run_dir
        clip = run_dir / self._dependency(node, kind=SHELL_CLIP_KIND)
        backdrop = run_dir / self._dependency(node, kind=SHELL_IMAGE_KIND)
        verdict = match_title_verdict(
            await extract_frame_png(clip, from_end=True, ffmpeg=self._ffmpeg),
            backdrop.read_bytes(),
        )
        atomic_write_json(
            run_dir / node.port("ending").artifact_ref,
            {"schema_version": 1, "kind": SHELL_OPENING_ENDING_KIND, **verdict},
        )
        return self._result(node, provider_operations=0)

    def _clip_role(self, node: Node) -> ShellClipRole:
        name = str(node.params["role"])
        try:
            return self._clip_roles[name]
        except KeyError:
            raise ValueError(f"the shell document declares no clip role {name!r}") from None

    async def publish_typeface(self, node: Node) -> NodeExecutionResult:
        """Copy the authored face into the run, with the provenance every artifact carries.

        Nothing is drawn and nothing is asked of a provider: the bytes are the author's,
        and this exists only so the manifest may bind them. A host resolves nothing above
        the run root, so a face that stayed in the package would be unreachable.
        """

        shell = self._host.shell
        if shell.typeface is None or self._host.typeface is None:
            raise ValueError("this shell document declares no typeface to publish")
        face = shell.typeface
        package_file = self._host.typeface()
        if package_file.sha256 != face.source_sha256:
            raise ValueError(
                f"the {face.family} face does not match its declared sha256: "
                f"declared {face.source_sha256}, found {package_file.sha256}"
            )
        await write_artifact_with_provenance_async(
            self._host.run_dir / node.port("typeface").artifact_ref,
            BinaryArtifact(data=package_file.data, media_type="application/octet-stream"),
            ProvenanceInput(
                provider="local",
                model=SHELL_TYPEFACE_KIND,
                prompt="Republish the authored typeface into the run.",
                refs=[face.source],
                inputs=[
                    InputProvenance(
                        ref=(
                            f"package://{self._host.package_id}/{face.source}"
                            f"#sha256={package_file.sha256}"
                        ),
                        sha256=package_file.sha256,
                        source="content",
                        bytes=len(package_file.data),
                        media_type="application/octet-stream",
                    )
                ],
                params={"family": face.family, "license": face.license},
                validation={
                    "family": face.family,
                    "license": face.license,
                    "license_source": face.license_source,
                    "upstream_source": face.upstream_source,
                    "retrieved": face.retrieved,
                },
                component=self._host.component,
                tool=self._host.tool,
                attempts=1,
            ),
        )
        return self._result(node, provider_operations=0)

    async def review(self, node: Node) -> NodeExecutionResult:
        role = self._role(node)
        run_dir = self._host.run_dir
        evidence = run_dir / self._dependency(node, kind=SHELL_EVIDENCE_KIND)
        validation = run_dir / self._dependency(node, kind=SHELL_VALIDATION_KIND)
        record = cast(dict[str, object], json.loads(validation.read_bytes()))
        selected = set(role.plate.reference_ids)
        references = [_structured_reference_from_run(evidence, run_dir)]
        references.extend(
            self._package_structured_reference(reference.source)
            for reference in self._host.shell.references
            if reference.reference_id in selected
        )
        prompt = plate_review_prompt(role, record)
        request: StructuredGenerationRequest[object] = StructuredGenerationRequest(
            prompt=prompt,
            system=(
                "You are a strict independent 2D game-art technical director. Return only the "
                "requested structured review."
            ),
            artifact_path=run_dir / node.port("verdict").artifact_ref,
            schema=StructuredOutputSchema(
                name=SHELL_REVIEW_SCHEMA_NAME,
                json_schema=shell_review_schema(),
            ),
            parse=_parse_review,
            references=tuple(references),
            max_tokens=1800,
            timeout_seconds=600,
            metadata={"checkpoint": "shell", "role": role.role},
        )
        result = await self._call(
            node, role.role, prompt, lambda: self._structured.generate(request)
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def review_clip(self, node: Node) -> NodeExecutionResult:
        """Judge the clip on its own frames, as one sheet, in order.

        The sheet is cut from the **published** clip. Reviewing the response would
        accept a picture the encoder then degrades, and the picture a player sees is the
        published one.
        """

        role = self._clip_role(node)
        run_dir = self._host.run_dir
        contact = run_dir / self._dependency(node, kind=SHELL_CLIP_CONTACT_KIND)
        validation = run_dir / self._dependency(node, kind=SHELL_CLIP_VALIDATION_KIND)
        record = cast(dict[str, object], json.loads(validation.read_bytes()))
        selected = set(role.clip.reference_ids)
        references = [_structured_reference_from_run(contact, run_dir)]
        references.extend(
            self._package_structured_reference(reference.source)
            for reference in self._host.shell.references
            if reference.reference_id in selected
        )
        prompt = clip_review_prompt(role, record)
        request: StructuredGenerationRequest[object] = StructuredGenerationRequest(
            prompt=prompt,
            system=(
                "You are a strict independent 2D game-art technical director. Return only the "
                "requested structured review."
            ),
            artifact_path=run_dir / node.port("verdict").artifact_ref,
            schema=StructuredOutputSchema(
                name=SHELL_CLIP_REVIEW_SCHEMA_NAME,
                json_schema=shell_review_schema(checks=SHELL_CLIP_REVIEW_CHECKS),
            ),
            parse=_parse_review,
            references=tuple(references),
            max_tokens=1800,
            timeout_seconds=600,
            metadata={"checkpoint": "shell", "role": role.role, "kind": "clip"},
        )
        result = await self._call(
            node, role.role, prompt, lambda: self._structured.generate(request)
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    # -- internals --------------------------------------------------------

    def _role(self, node: Node) -> ShellPlateRole:
        name = str(node.params["role"])
        try:
            return self._roles[name]
        except KeyError:
            raise ValueError(f"the shell document declares no plate role {name!r}") from None

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
        by_id = {entry.reference_id: entry for entry in self._host.shell.references}
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
                        sha256=content_sha256(payload),
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
        return node_result(
            self._host.run_dir, node, attempts=attempts, provider_operations=provider_operations
        )


def shell_review_schema(checks: Sequence[str] = SHELL_REVIEW_CHECKS) -> dict[str, object]:
    """The judge's answer shape: the questions the pixel gate cannot decide.

    ``checks`` differs between a still and a clip - a clip has no reserved region to
    keep quiet, and one question a still never has - so the shape is built from whichever
    set is being asked about rather than from a union of both.
    """

    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["accept", "reject", "uncertain"]},
            "confidence": {"type": "number"},
            "checks": {
                "type": "object",
                "properties": {key: {"type": "boolean"} for key in checks},
            },
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
        raise ValueError("shell plate review has an invalid verdict")
    return value


# ---------------------------------------------------------------- manifest


def shell_manifest_block(
    shell: GameShell,
    *,
    read_validation: Callable[[str], bytes],
    publish: Callable[[str], object],
    display_name: str,
) -> dict[str, object]:
    """The ``shell`` block: the screens, their plates, and every string the host sets.

    Geometry is published resolved so a consumer never rediscovers it: each screen names
    its canvas and the rectangles it reserves, in canvas pixels, and a host scales the
    whole canvas to its window and scales the rects by the same factor.

    The typeface is deliberately **not** here yet. A manifest binding must be published
    as an asset of the run, and nothing copies the font file into the run today; naming
    it before its bytes travel would be a binding to a file that is not there. It joins
    when the host that reads it does.
    """

    roles = {role.role: role for role in document_plate_roles(shell)}
    plates: dict[str, dict[str, object]] = {
        name: _plate_projection(role, read_validation=read_validation, publish=publish)
        for name, role in roles.items()
    }
    plates.update(
        {
            role.role: _clip_projection(role, read_validation=read_validation, publish=publish)
            for role in document_clip_roles(shell)
        }
    )

    block: dict[str, object] = {"strings": {"display_name": display_name}}

    if shell.typeface is not None:
        # Bound only now that the run carries the bytes: a manifest binding must be a
        # published asset, and until the publish node existed this block named nothing.
        block["typeface"] = {
            "family": shell.typeface.family,
            "license": shell.typeface.license,
            "asset": publish(shell_typeface_ref(shell)),
        }

    if shell.opening is not None:
        block["opening"] = {
            "layout": shell.opening.layout,
            "skippable": shell.opening.skippable,
            "music_track": shell.opening.music_track,
            "seconds": round(shell.opening.seconds, 3),
            # How the last shot gives way to what follows. Three of the four are the
            # host's own presentation; ``match_title`` is the measured one, and the run
            # carries its verdict beside the clip.
            "ending": shell.opening.ending,
            "canvas": _canvas(OPENING_SHOT),
            "reserved": _reserved(OPENING_SHOT),
            "shots": [
                {
                    "shot_id": shot.shot_id,
                    "move": shot.move,
                    "seconds": shot.seconds,
                    "card": shot.card,
                    "out_transition": shot.out_transition,
                    "plate": plates[f"opening_{shot.shot_id}"],
                }
                for shot in shell.opening.shots
            ],
        }

    if shell.title is not None:
        block["title"] = {
            "layout": shell.title.layout,
            "canvas": _canvas(TITLE_SCREEN),
            "reserved": _reserved(TITLE_SCREEN),
            "drift": TITLE_SCREEN.drift,
            "backdrop": [
                {"depth": layer.depth, "plate": plates[f"title_backdrop_{layer.depth}"]}
                for layer in shell.title.backdrop
            ],
            "emblem": plates.get("title_emblem"),
        }

    if shell.loading is not None:
        backdrop: dict[str, object]
        if isinstance(shell.loading.backdrop, ShellPlate):
            backdrop = {"source": "generated", "plate": plates["loading_backdrop"]}
        else:
            backdrop = {
                "source": "run_artifact",
                "artifact_role": shell.loading.backdrop.artifact_role,
            }
        block["loading"] = {
            "layout": shell.loading.layout,
            "canvas": _canvas(LOADING_SCREEN),
            "reserved": _reserved(LOADING_SCREEN),
            "backdrop": backdrop,
            "tips": list(shell.loading.tips),
        }

    return block


def _plate_projection(
    role: ShellPlateRole,
    *,
    read_validation: Callable[[str], bytes],
    publish: Callable[[str], object],
) -> dict[str, object]:
    _raw, image_ref, validation_ref, _evidence, _verdict = shell_artifact_refs(role)
    record = cast(dict[str, object], json.loads(read_validation(validation_ref)))
    return {
        "role": role.role,
        # Both projections say which they are, so a host reads one key rather than
        # inferring a kind from a file extension.
        "mode": "still",
        "alpha_policy": role.alpha_policy,
        "measured_regions": [
            entry
            for entry in cast(list[object], record.get("regions", []))
            if isinstance(entry, dict)
        ],
        "asset": publish(image_ref),
    }


def _clip_projection(
    role: ShellClipRole,
    *,
    read_validation: Callable[[str], bytes],
    publish: Callable[[str], object],
) -> dict[str, object]:
    """A clip in the manifest, shaped like a plate so a shot reads the same either way.

    ``mode`` is what a host branches on, and it is what stops a host that only knows
    stills from calling its texture loader on a video file and drawing a black frame.
    The published Ogg is the asset: the response the route returned stays in the run for
    the record's sake and is never named here.
    """

    _raw, validation_ref, clip_ref, contact_ref, _published = shell_clip_artifact_refs(role)
    record = cast(dict[str, object], json.loads(read_validation(validation_ref)))
    source = record.get("source")
    measured = source if isinstance(source, dict) else {}
    return {
        "role": role.role,
        "mode": "clip",
        "asset": publish(clip_ref),
        "contact_sheet": publish(contact_ref),
        "canvas": _canvas(role.layout),
        "duration_seconds": measured.get("duration_seconds", role.seconds),
        # Recorded so a host knows to silence it: the opening's sound is the package's
        # own soundtrack, and the publication transcode drops the track a route made.
        "source_audio": measured.get("source_audio"),
    }


def _canvas(layout: ShellLayout) -> dict[str, int]:
    return {"width": layout.canvas[0], "height": layout.canvas[1]}


def _reserved(layout: ShellLayout) -> list[dict[str, object]]:
    return [
        {"region": name, "rect": layout.region(name).record()} for name in layout.region_names()
    ]


def _structured_reference_from_run(path: Path, run_dir: Path) -> StructuredReference:
    data = path.read_bytes()
    return StructuredReference(
        url=data_url(data, "image/png"),
        provenance_ref=f"run://{path.relative_to(run_dir).as_posix()}#sha256={content_sha256(data)}",
    )


def _media_type(source: str) -> str:
    suffix = PurePosixPath(source).suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    return "image/webp" if suffix == ".webp" else "image/png"


__all__ = [
    "IMAGE_FEATURES",
    "SHELL_CONTRACT_VERSION",
    "SHELL_EVIDENCE_KIND",
    "SHELL_IMAGE_KIND",
    "SHELL_NODE_TYPES",
    "SHELL_PLATE_GENERATE",
    "SHELL_PLATE_REVIEW",
    "SHELL_PLATE_VALIDATE",
    "SHELL_RAW_KIND",
    "SHELL_TYPEFACE_KIND",
    "SHELL_TYPEFACE_PUBLISH",
    "SHELL_REVIEW_CHECKS",
    "SHELL_REVIEW_SCHEMA_NAME",
    "SHELL_VALIDATION_KIND",
    "SHELL_VERDICT_KIND",
    "STRUCTURED_FEATURES",
    "ShellHandlers",
    "ShellHost",
    "ShellPlateRole",
    "add_shell_nodes",
    "document_plate_roles",
    "plate_content_task",
    "plate_review_prompt",
    "shell_artifact_refs",
    "shell_node_ids",
    "shell_manifest_block",
    "shell_review_schema",
    "shell_typeface_ref",
]
