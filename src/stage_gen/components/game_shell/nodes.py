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
    ViewArchetype,
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
from stage_gen.components.game_shell.layouts import (
    CUTOUT_ALPHA_POLICY,
    LOADING_SCREEN,
    OPAQUE_ALPHA_POLICY,
    OPENING_SHOT,
    TITLE_SCREEN,
    ShellLayout,
)
from stage_gen.components.game_shell.models import GameShell, ShellPlate
from stage_gen.components.game_shell.plates import (
    SHELL_PLATE_VALIDATION_VERSION,
    canonicalize_shell_plate,
    shell_plate_evidence,
    validate_shell_plate,
)
from stage_gen.media import data_url

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
    contract_version="shell-plate-v1",
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

#: Every type this module owns, for a recipe's own type census and registry checks.
SHELL_NODE_TYPES = (
    SHELL_PLATE_GENERATE,
    SHELL_PLATE_VALIDATE,
    SHELL_PLATE_REVIEW,
    SHELL_TYPEFACE_PUBLISH,
)

SHELL_TYPEFACE_KIND = "shell-typeface-v1"


def shell_typeface_ref(shell: GameShell) -> str:
    """Where the run carries the face, keyed by the name the package gave it."""

    if shell.typeface is None:
        raise ValueError("this shell document declares no typeface")
    return f"shell/typeface/{PurePosixPath(shell.typeface.source).name}"


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


def shell_node_ids(role: ShellPlateRole, *, prefix: str = "shell") -> tuple[str, str, str]:
    """The generate, validate and review ids one plate occupies in a host graph."""

    return (
        f"{prefix}-{role.role}-generate",
        f"{prefix}-{role.role}-validate",
        f"{prefix}-{role.role}-review",
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
    domain: str = "shell",
    prefix: str = "shell",
    attempts_port: Callable[[str], Port] | None = None,
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
    ) -> None:
        self._host = host
        self._graph = graph
        self._images = image_service
        self._structured = structured_service
        self._provider_call = provider_call
        self._roles = {role.role: role for role in document_plate_roles(host.shell)}

    async def generate(self, node: Node) -> NodeExecutionResult:
        role = self._role(node)
        output = self._host.run_dir / node.port("image").artifact_ref
        prompt = card_prompt(node)
        request = ImageGenerationRequest(
            prompt=prompt,
            artifact_path=output,
            input_references=self._image_references(role.plate.reference_ids),
            quality="high",
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


def shell_review_schema() -> dict[str, object]:
    """The judge's answer shape: the questions the pixel gate cannot decide."""

    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["accept", "reject", "uncertain"]},
            "confidence": {"type": "number"},
            "checks": {
                "type": "object",
                "properties": {key: {"type": "boolean"} for key in SHELL_REVIEW_CHECKS},
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
    plates = {
        name: _plate_projection(role, read_validation=read_validation, publish=publish)
        for name, role in roles.items()
    }

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
        "alpha_policy": role.alpha_policy,
        "measured_regions": [
            entry
            for entry in cast(list[object], record.get("regions", []))
            if isinstance(entry, dict)
        ],
        "asset": publish(image_ref),
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
