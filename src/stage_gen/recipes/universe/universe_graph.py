"""Universe execution documents and the two graphs one universe implies.

Two sealed graphs, not one, because the size of the second is a result of the
first: how many entities exist — and therefore how many image branches the
gallery has — is only known once a proposal has been admitted. The semantic
graph ends at that admission; the gallery graph starts from it.

Identity is split along what each node actually consumes. The spike hashed the
medium's compile, render and review prose into a single digest bound to every
direction, image and review node, so recalibrating the reviewer re-billed the
whole gallery. Here the direction tier binds the compile digest, the image tier
binds the render digest and its own draw index, and the review tier binds the
review digest — changing how an image is judged no longer changes how it is
drawn.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, Final, Literal

from pydantic import Field

from gnode import (
    SHA256_PATTERN,
    AuthoredInput,
    Binding,
    BindingTable,
    Graph,
    GraphBuilder,
    ImageGenerationService,
    ModelRef,
    NodeCard,
    Port,
    PortRef,
    seal_graph,
)
from stage_gen.canonical import canonical_json_bytes, content_sha256
from stage_gen.config import CapabilityName, StageGenConfig
from stage_gen.orchestration.runtime import create_image_service, create_openai_image_service
from stage_gen.recipes.universe.models import GalleryPlan, SampleLedger, UniverseProposal
from stage_gen.recipes.universe.ontology import SIZE_BY_MODE
from stage_gen.recipes.universe.universe_prompts import (
    IMAGE_REVIEW_INSTRUCTIONS,
    REVIEW_INSTRUCTIONS,
    entity_direction_instructions,
    global_direction_instructions,
    plan_instructions,
    proposal_instructions,
)
from stage_gen.recipes.universe.universe_types import (
    ADMISSION_KIND,
    ADMIT,
    ADMITTED_KIND,
    ATTEMPT_LEDGER_KIND,
    CONCEPT_IMAGE,
    CONCEPT_IMAGE_KIND,
    CONCEPT_PROXY,
    CONCEPT_REVIEW,
    DIRECTION_WARNINGS_KIND,
    ENTITY_DIRECTION,
    ENTITY_DIRECTION_KIND,
    ENTITY_MARKDOWN_KIND,
    ENTITY_RECORD,
    ENTITY_RECORD_KIND,
    EVALUATE,
    EVALUATION_KIND,
    GALLERY_CLOSE,
    GALLERY_PLAN_KIND,
    GLOBAL_DIRECTION,
    GLOBAL_DIRECTION_KIND,
    IMAGE_REVIEW_KIND,
    INVENTORY_KIND,
    PLAN,
    POSTER_PROXY_KIND,
    PROPOSAL_KIND,
    PROPOSE,
    REVIEW,
    REVIEW_PROXY_KIND,
    SEMANTIC_REVIEW_KIND,
    SOURCE_LOCK,
    SOURCE_LOCK_KIND,
)

if TYPE_CHECKING:
    from stage_gen.recipes.universe.universe_request import (
        AdmittedUniverse,
        ResolvedUniverseSource,
    )

UNIVERSE_GRAPH_SCHEMA_VERSION = 1
UNIVERSE_TRACE_SCHEMA_VERSION = 1
UNIVERSE_CACHE_NAMESPACE = "universe-nodes-v1"
UNIVERSE_CACHE_RECORD_KIND = "universe-node-cache-v1"

POSTER_PROXY_LONG_EDGE = 1600
REVIEW_PROXY_LONG_EDGE = 1280

#: Run-relative refs written by the semantic phase.
SOURCE_LOCK_REF = "production/source-lock/source-lock.json"
POSTER_PROXY_REF = "production/source-lock/poster-proxy.jpg"
PROPOSAL_REF = "semantic/evidence/proposal.json"
PLAN_REF = "semantic/evidence/plan.json"
EVALUATION_REF = "semantic/evaluation.json"
SEMANTIC_REVIEW_REF = "semantic/evidence/review.json"
UNIVERSE_REF = "semantic/universe.json"
ADMISSION_REF = "semantic/admission.json"

#: Run-relative refs written or carried by the gallery phase.
GLOBAL_DIRECTION_REF = "production/direction/global.json"
INVENTORY_REF = "package/inventory.json"
MANIFEST_REF = "manifest.json"
INPUT_UNIVERSE_REF = "inputs/universe.json"
INPUT_POSTER_PROXY_REF = "inputs/poster-proxy.jpg"
SAMPLE_LEDGER_REF = "sample-ledger.json"


class UniverseOperationKind(StrEnum):
    """The capabilities a universe node is allowed to use."""

    LOCAL = "local"
    IMAGE_GENERATION = "image_generation"
    STRUCTURED_GENERATION = "structured_generation"


class UniverseGraph(Graph):
    """One phase of one universe, bound to the source package that produced it."""

    TRACE_SCHEMA_VERSION: ClassVar[int] = UNIVERSE_TRACE_SCHEMA_VERSION
    TRACE_EVENT_KIND: ClassVar[str] = "universe-execution-event-v1"
    RUN_SUMMARY_KIND: ClassVar[str] = "universe-execution-summary-v1"
    PROJECTION_KIND: ClassVar[str] = "universe-execution-projection-v1"
    VIEW_KIND: ClassVar[str] = "universe-execution-view-v1"
    # The run-view document contract is shared and owned by gnode; this is
    # its version, not a per-recipe counter. Declaring 1 emitted the ring-0
    # v3 shape under a version every consumer refuses, so universe runs were
    # invisible to the run viewer.
    VIEW_SCHEMA_VERSION: ClassVar[int] = 3

    schema_version: Literal[1]
    kind: Literal["universe-execution-graph-v1"]
    recipe: Literal["universe"]
    phase: Literal["semantic", "gallery"]
    universe_id: str
    medium_id: str
    entity_count: int
    poster_sha256: str = Field(pattern=SHA256_PATTERN)
    #: Which draw of each concept image this plan asks for. Absent in the
    #: semantic phase, which draws nothing.
    sample_ledger_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    #: Generation is exploration; publication is a separate human decision.
    publication_authorized: Literal[False]

    def operation_vocabulary(self) -> tuple[str, ...]:
        return tuple(operation.value for operation in UniverseOperationKind)

    def identity_header(self) -> dict[str, object]:
        """Structure only, because this feeds ``topology_sha256``.

        The phase is here because the two phases really are different shapes.
        The poster digest and the sample ledger are deliberately not: rerolling
        one image, or swapping the poster, changes what the graph draws and so
        moves ``graph_sha256`` and the affected cache keys, but it does not
        change the shape of the graph, and the checked doc snapshot should not
        move for it.
        """

        return {**super().identity_header(), "recipe": self.recipe, "phase": self.phase}

    def annotator_key(self) -> str:
        return self.recipe

    def view_header(self) -> dict[str, object]:
        return {
            "recipe": self.recipe,
            "phase": self.phase,
            "universe_id": self.universe_id,
            "medium_id": self.medium_id,
            "entity_count": self.entity_count,
        }


class ImageRoute:
    """Which provider route an image capability binds to.

    The model is the same on both routes; what differs is whether the route can
    return native alpha. Work that does not need transparency binds the opaque
    route, which this recipe sends through OpenRouter — the same picture at the
    same price, but with the upstream cost actually reported, which is how a
    36-image gallery turned out to cost eleven dollars rather than the two the
    structured calls alone had been showing. Work that needs alpha binds OpenAI
    direct, which is the only route that returns it.
    """

    __slots__ = ("capability", "provider", "route_id")

    def __init__(
        self,
        *,
        route_id: Literal["opaque", "native_transparency"],
        provider: Literal["openrouter", "openai"],
        capability: CapabilityName,
    ) -> None:
        self.route_id = route_id
        self.provider = provider
        self.capability = capability

    def model(self, config: StageGenConfig) -> str:
        return config.image_model if self.provider == "openrouter" else config.openai_image_model

    def service(self, config: StageGenConfig) -> ImageGenerationService:
        if self.provider == "openrouter":
            return create_image_service(
                api_key=config.open_router_api_key or "",
                model=config.image_model,
                base_url=config.open_router_base_url or "https://openrouter.ai/api/v1",
            )
        return create_openai_image_service(
            api_key=config.openai_api_key or "",
            model=config.openai_image_model,
            base_url=config.openai_base_url or "https://api.openai.com/v1",
            images_per_minute=config.openai_image_ipm,
        )


OPAQUE_IMAGE_ROUTE: Final = ImageRoute(
    route_id="opaque",
    provider="openrouter",
    capability=CapabilityName.IMAGE_GENERATION,
)
NATIVE_TRANSPARENCY_IMAGE_ROUTE: Final = ImageRoute(
    route_id="native_transparency",
    provider="openai",
    capability=CapabilityName.NATIVE_IMAGE_GENERATION,
)


def image_route(*, transparency_required: bool) -> ImageRoute:
    return NATIVE_TRANSPARENCY_IMAGE_ROUTE if transparency_required else OPAQUE_IMAGE_ROUTE


#: Concept images are opaque compositions; nothing in the gallery needs alpha.
GALLERY_IMAGE_ROUTE: Final = image_route(transparency_required=False)

STRUCTURED_FEATURES = ("structured_output", "image_input")
IMAGE_FEATURES = ("flexible_size",)


def universe_graph_profile(config: StageGenConfig, *, images: bool) -> BindingTable:
    """Declare the provider routes a universe plan may use, credentials untouched.

    The semantic phase draws nothing, so its table omits the image route
    entirely rather than declaring a capability it will never call.
    """

    routes = [
        Binding(
            operation=UniverseOperationKind.STRUCTURED_GENERATION,
            model=ModelRef(model=config.text_model, provider="openrouter"),
            features=frozenset(STRUCTURED_FEATURES),
            resource_id="openrouter-structured",
            max_in_flight=4,
            requests_per_minute=20,
            rate_limit_owner="provider_adapter",
            estimated_duration_seconds=180.0,
            estimated_cost_low_usd=0.02,
            estimated_cost_high_usd=0.60,
            verified_on="2026-09-02",
        )
    ]
    if images:
        routes.append(
            Binding(
                operation=UniverseOperationKind.IMAGE_GENERATION,
                model=ModelRef(
                    model=GALLERY_IMAGE_ROUTE.model(config),
                    provider=GALLERY_IMAGE_ROUTE.provider,
                ),
                features=frozenset(IMAGE_FEATURES),
                resource_id=f"universe-{GALLERY_IMAGE_ROUTE.provider}-image",
                max_in_flight=4,
                requests_per_minute=config.openai_image_ipm,
                rate_limit_owner="provider_adapter",
                estimated_duration_seconds=240.0,
                # A measured 2560-class high-quality frame, not an estimate.
                estimated_cost_low_usd=0.30,
                estimated_cost_high_usd=0.34,
                verified_on="2026-09-03",
            )
        )
    return BindingTable(routes)


def _artifact(port_id: str, ref: str, kind: str) -> Port:
    return Port(port_id=port_id, artifact_ref=ref, kind=kind, sidecar_ref=f"{ref}.meta.json")


def _attempts(node_id: str) -> Port:
    return Port(
        port_id="attempts", artifact_ref=f"attempts/{node_id}.json", kind=ATTEMPT_LEDGER_KIND
    )


def _text_digest(value: str) -> str:
    return content_sha256(value.encode("utf-8"))


def _schema_digest(model_type: type[UniverseProposal] | type[GalleryPlan]) -> str:
    return content_sha256(canonical_json_bytes(model_type.model_json_schema()))


def node_safe(entity_id: str) -> str:
    """Entity ids are snake_case; node ids are hyphenated by house convention."""

    return entity_id.replace("_", "-")


def _sample_digest(entity_id: str, sample: int) -> str:
    """The one input that exists to be changed by hand.

    Deterministic keys mean a rejected image cannot be redrawn by running
    again — the same key restores the same picture. Naming the draw index in
    the image node's identity makes a reroll a one-branch miss instead of a
    whole-gallery one.
    """

    return content_sha256(f"{entity_id}:sample:{sample}".encode())


def build_universe_semantic_graph(
    resolved: ResolvedUniverseSource,
    *,
    profile: BindingTable,
) -> UniverseGraph:
    """Compile one authored universe package into the proposal-and-admission graph."""

    source = resolved.source
    builder = GraphBuilder(profile=profile, local_max_in_flight=2)
    authored = (
        AuthoredInput(label="package", ref="universe.toml", sha256=resolved.source_sha256),
        AuthoredInput(
            label="synopsis", ref=source.synopsis.source, sha256=resolved.synopsis_sha256
        ),
        AuthoredInput(
            label="expansion_direction",
            ref=source.expansion_direction.source,
            sha256=resolved.direction_sha256,
        ),
        AuthoredInput(label="poster", ref=source.poster.source, sha256=resolved.poster_sha256),
    )
    source_digests = (
        resolved.source_sha256,
        resolved.synopsis_sha256,
        resolved.direction_sha256,
        resolved.poster_sha256,
    )
    builder.add(
        SOURCE_LOCK,
        "source-lock",
        domain="universe",
        description="Bind source bytes, derive evidence ids, and make the poster observation proxy",
        params={
            "medium": resolved.medium.medium_id,
            "poster_proxy_long_edge": str(POSTER_PROXY_LONG_EDGE),
        },
        input_digests=(*source_digests, _text_digest(str(POSTER_PROXY_LONG_EDGE))),
        ports=(
            _artifact("source_lock", SOURCE_LOCK_REF, SOURCE_LOCK_KIND),
            _artifact("poster_proxy", POSTER_PROXY_REF, POSTER_PROXY_KIND),
        ),
        card=NodeCard(
            prompt="Lock the source package and derive the evidence ledger.",
            authored_inputs=authored,
        ),
    )
    proposal_prompt = proposal_instructions(
        title=resolved.title,
        universe_id=source.universe_id,
        min_entities=source.census.min_entities,
        max_entities=source.census.max_entities,
    )
    builder.add(
        PROPOSE,
        "universe-propose",
        domain="universe",
        description="One multimodal universe proposal under the V0 ontology",
        params={
            "min_entities": str(source.census.min_entities),
            "max_entities": str(source.census.max_entities),
            "poster_reference_count": "1",
        },
        depends_on=("source-lock",),
        input_digests=(
            *source_digests,
            _text_digest(proposal_prompt),
            _schema_digest(UniverseProposal),
        ),
        ports=(
            _artifact("proposal", PROPOSAL_REF, PROPOSAL_KIND),
            _attempts("universe-propose"),
        ),
        card=NodeCard(
            prompt=proposal_prompt,
            schema_name="UniverseProposal",
            authored_inputs=authored,
            reference_inputs=(PortRef(node_id="source-lock", port_id="poster_proxy"),),
        ),
    )
    plan_prompt = plan_instructions(title=resolved.title)
    builder.add(
        PLAN,
        "gallery-plan",
        domain="universe",
        description="Set-level concept plan: purposes, modes, motifs, and registers across the set",
        params={"poster_reference_count": "0"},
        depends_on=("universe-propose",),
        input_digests=(_text_digest(plan_prompt), _schema_digest(GalleryPlan)),
        ports=(
            _artifact("plan", PLAN_REF, GALLERY_PLAN_KIND),
            _attempts("gallery-plan"),
        ),
        card=NodeCard(
            prompt=plan_prompt,
            schema_name="GalleryPlan",
            reference_inputs=(PortRef(node_id="universe-propose", port_id="proposal"),),
        ),
    )
    builder.add(
        EVALUATE,
        "universe-evaluate",
        domain="universe",
        description="Deterministic taxonomy, lineage, graph, and set-diversity evaluation",
        depends_on=("source-lock", "universe-propose", "gallery-plan"),
        ports=(_artifact("evaluation", EVALUATION_REF, EVALUATION_KIND),),
        card=NodeCard(
            prompt="Re-run every deterministic evaluator on the persisted proposal and plan.",
            reference_inputs=(
                PortRef(node_id="universe-propose", port_id="proposal"),
                PortRef(node_id="gallery-plan", port_id="plan"),
            ),
        ),
    )
    builder.add(
        REVIEW,
        "universe-review",
        domain="universe",
        description="Independent semantic review of proposal and plan with the poster as evidence",
        params={"poster_reference_count": "1"},
        depends_on=("source-lock", "universe-propose", "gallery-plan", "universe-evaluate"),
        input_digests=(_text_digest(REVIEW_INSTRUCTIONS),),
        ports=(
            _artifact("review", SEMANTIC_REVIEW_REF, SEMANTIC_REVIEW_KIND),
            _attempts("universe-review"),
        ),
        card=NodeCard(
            prompt=REVIEW_INSTRUCTIONS,
            schema_name="SemanticReview",
            reference_inputs=(
                PortRef(node_id="source-lock", port_id="poster_proxy"),
                PortRef(node_id="universe-propose", port_id="proposal"),
                PortRef(node_id="gallery-plan", port_id="plan"),
                PortRef(node_id="universe-evaluate", port_id="evaluation"),
            ),
        ),
    )
    builder.add(
        ADMIT,
        "universe-admit",
        domain="universe",
        description="Bind digests, require a passing review, and seal the admitted universe",
        depends_on=(
            "source-lock",
            "universe-propose",
            "gallery-plan",
            "universe-evaluate",
            "universe-review",
        ),
        ports=(
            _artifact("universe", UNIVERSE_REF, ADMITTED_KIND),
            _artifact("admission", ADMISSION_REF, ADMISSION_KIND),
        ),
        card=NodeCard(
            prompt="Admit only when evaluation and review both pass on the exact persisted bytes.",
            reference_inputs=(
                PortRef(node_id="universe-review", port_id="review"),
                PortRef(node_id="universe-evaluate", port_id="evaluation"),
            ),
        ),
    )
    return seal_graph(
        UniverseGraph,
        resources=builder.resources(),
        nodes=builder.nodes,
        terminal_node_id="universe-admit",
        schema_version=UNIVERSE_GRAPH_SCHEMA_VERSION,
        kind="universe-execution-graph-v1",
        recipe="universe",
        phase="semantic",
        universe_id=source.universe_id,
        medium_id=resolved.medium.medium_id,
        entity_count=0,
        poster_sha256=resolved.poster_sha256,
        sample_ledger_sha256=None,
        publication_authorized=False,
    )


def build_universe_gallery_graph(
    resolved: ResolvedUniverseSource,
    admitted: AdmittedUniverse,
    *,
    samples: SampleLedger,
    profile: BindingTable,
) -> UniverseGraph:
    """Compile one admitted universe into the exact per-entity gallery it implies."""

    medium = resolved.medium
    if admitted.medium_id != medium.medium_id:
        raise ValueError(
            f"admitted universe was compiled for medium {admitted.medium_id!r}, "
            f"but the source package declares {medium.medium_id!r}"
        )
    if admitted.universe_id != resolved.universe_id:
        raise ValueError(
            f"admitted universe {admitted.universe_id!r} does not belong to "
            f"the source package {resolved.universe_id!r}"
        )
    if samples.universe_id != resolved.universe_id:
        raise ValueError(f"sample ledger is for {samples.universe_id!r}, not this universe")

    reserved = sorted(
        entity_id for entity_id in admitted.entity_ids() if node_safe(entity_id) == "global"
    )
    if reserved:
        raise ValueError(
            f"entity id {reserved[0]!r} collides with the gallery's global direction node; "
            "rename the entity in the admitted universe"
        )
    builder = GraphBuilder(profile=profile, local_max_in_flight=4)
    compile_digest = medium.compile_digest()
    render_digest = medium.render_digest()
    review_digest = medium.review_digest()
    # The gallery run carries its own copy of the admitted universe and of the
    # poster proxy, so the run is a closed set of bytes rather than a pointer at
    # the semantic run that produced it.
    universe_input = AuthoredInput(
        label="admitted_universe", ref=INPUT_UNIVERSE_REF, sha256=admitted.universe_sha256
    )
    # The source poster, not the proxy: the proxy is a re-encode, so binding it
    # would make every image's identity depend on the imaging library's encoder.
    poster_input = AuthoredInput(
        label="poster", ref=resolved.source.poster.source, sha256=resolved.poster_sha256
    )
    global_prompt = global_direction_instructions(
        title=admitted.title, medium=medium, universe_id=admitted.universe_id
    )
    builder.add(
        GLOBAL_DIRECTION,
        "direction-global",
        domain="gallery",
        description="Medium-aware global visual grammar compiled once as text",
        params={"medium": medium.medium_id, "poster_reference_count": "1"},
        input_digests=(
            admitted.universe_sha256,
            compile_digest,
            _text_digest(global_prompt),
            resolved.poster_sha256,
        ),
        ports=(
            _artifact("global", GLOBAL_DIRECTION_REF, GLOBAL_DIRECTION_KIND),
            _attempts("direction-global"),
        ),
        card=NodeCard(
            prompt=global_prompt,
            schema_name="GlobalDirection",
            authored_inputs=(universe_input, poster_input),
        ),
    )
    entity_prompt = entity_direction_instructions(medium=medium)
    record_nodes: list[str] = []
    with builder.within_template("entity-concept-pipeline@v1"):
        for entity in admitted.proposal.entities:
            entity_id = entity.entity_id
            safe = node_safe(entity_id)
            plan = admitted.plan.plan(entity_id)
            size = SIZE_BY_MODE[plan.concept_mode]
            direction_id = f"direction-{safe}"
            image_id = f"image-{safe}"
            proxy_id = f"proxy-{safe}"
            review_id = f"review-{safe}"
            record_id = f"record-{safe}"
            builder.add(
                ENTITY_DIRECTION,
                direction_id,
                domain="gallery",
                description=f"Compile the text concept direction for {entity.display_name}",
                params={
                    "entity_id": entity_id,
                    "primary_class": entity.primary_class,
                    "concept_mode": plan.concept_mode,
                    "poster_reference_count": "0",
                },
                depends_on=("direction-global",),
                input_digests=(
                    admitted.universe_sha256,
                    _text_digest(entity_id),
                    compile_digest,
                    _text_digest(entity_prompt),
                ),
                ports=(
                    _artifact(
                        "direction",
                        f"production/direction/entities/{entity_id}.json",
                        ENTITY_DIRECTION_KIND,
                    ),
                    Port(
                        port_id="warnings",
                        artifact_ref=f"production/direction/entities/{entity_id}.warnings.json",
                        kind=DIRECTION_WARNINGS_KIND,
                    ),
                    _attempts(direction_id),
                ),
                card=NodeCard(
                    prompt=entity_prompt,
                    schema_name="EntityDirection",
                    authored_inputs=(universe_input,),
                    reference_inputs=(PortRef(node_id="direction-global", port_id="global"),),
                ),
            )
            builder.add(
                CONCEPT_IMAGE,
                image_id,
                domain="gallery",
                description=f"Fresh text-to-image concept for {entity.display_name}",
                params={
                    "entity_id": entity_id,
                    "size": size,
                    "sample": str(samples.sample(entity_id)),
                    "input_reference_count": "0",
                    "mask_reference_count": "0",
                },
                depends_on=(direction_id,),
                # The size is the one number that decides what the provider is
                # asked to draw and what the package ships, so it belongs to the
                # node's identity rather than only to its params: an image drawn
                # to a superseded canvas is not a valid answer to this question.
                input_digests=(
                    render_digest,
                    _text_digest(size),
                    _sample_digest(entity_id, samples.sample(entity_id)),
                ),
                ports=(
                    _artifact("image", f"package/entities/{entity_id}.png", CONCEPT_IMAGE_KIND),
                ),
                card=NodeCard(
                    prompt=(
                        "Render the sealed entity direction under the medium render "
                        "contract; zero references, zero masks."
                    ),
                    reference_inputs=(
                        PortRef(node_id=direction_id, port_id="direction"),
                        PortRef(node_id="direction-global", port_id="global"),
                    ),
                ),
            )
            builder.add(
                CONCEPT_PROXY,
                proxy_id,
                domain="gallery",
                description=f"Downscaled review proxy for {entity.display_name}",
                params={"entity_id": entity_id, "long_edge": str(REVIEW_PROXY_LONG_EDGE)},
                depends_on=(image_id,),
                input_digests=(_text_digest(str(REVIEW_PROXY_LONG_EDGE)),),
                ports=(
                    _artifact(
                        "proxy",
                        f"production/review/proxies/{entity_id}.png",
                        REVIEW_PROXY_KIND,
                    ),
                ),
                card=NodeCard(
                    prompt=(
                        "Make the review proxy; it is a review instrument, never a package asset."
                    ),
                    reference_inputs=(PortRef(node_id=image_id, port_id="image"),),
                ),
            )
            builder.add(
                CONCEPT_REVIEW,
                review_id,
                domain="gallery",
                description=f"Independent review of the {entity.display_name} image",
                params={"entity_id": entity_id, "proxy_reference_count": "1"},
                depends_on=(proxy_id, direction_id),
                input_digests=(_text_digest(IMAGE_REVIEW_INSTRUCTIONS), review_digest),
                ports=(
                    _artifact(
                        "review",
                        f"production/review/reviews/{entity_id}.json",
                        IMAGE_REVIEW_KIND,
                    ),
                    _attempts(review_id),
                ),
                card=NodeCard(
                    prompt=IMAGE_REVIEW_INSTRUCTIONS,
                    schema_name="ImageReview",
                    reference_inputs=(
                        PortRef(node_id=proxy_id, port_id="proxy"),
                        PortRef(node_id=direction_id, port_id="direction"),
                    ),
                ),
            )
            builder.add(
                ENTITY_RECORD,
                record_id,
                domain="gallery",
                description=f"Paired JSON and Markdown record for {entity.display_name}",
                params={"entity_id": entity_id},
                depends_on=(review_id, image_id, direction_id),
                ports=(
                    _artifact("record", f"package/entities/{entity_id}.json", ENTITY_RECORD_KIND),
                    _artifact("markdown", f"package/entities/{entity_id}.md", ENTITY_MARKDOWN_KIND),
                ),
                card=NodeCard(
                    prompt="Materialize the entity record with its review outcome.",
                    reference_inputs=(
                        PortRef(node_id=review_id, port_id="review"),
                        PortRef(node_id=image_id, port_id="image"),
                    ),
                ),
            )
            record_nodes.append(record_id)
    builder.add(
        GALLERY_CLOSE,
        "gallery-close",
        domain="gallery",
        description="Closed image inventory: exactly one image per entity, statuses recorded",
        depends_on=tuple(record_nodes),
        ports=(_artifact("inventory", INVENTORY_REF, INVENTORY_KIND),),
        card=NodeCard(
            prompt="Enumerate the closed image inventory from the entity records.",
            reference_inputs=tuple(
                PortRef(node_id=node_id, port_id="record") for node_id in record_nodes
            ),
        ),
    )
    return seal_graph(
        UniverseGraph,
        resources=builder.resources(),
        nodes=builder.nodes,
        terminal_node_id="gallery-close",
        schema_version=UNIVERSE_GRAPH_SCHEMA_VERSION,
        kind="universe-execution-graph-v1",
        recipe="universe",
        phase="gallery",
        universe_id=admitted.universe_id,
        medium_id=medium.medium_id,
        entity_count=len(admitted.proposal.entities),
        poster_sha256=resolved.poster_sha256,
        sample_ledger_sha256=content_sha256(canonical_json_bytes(samples.model_dump(mode="json"))),
        publication_authorized=False,
    )


__all__ = [
    "ADMISSION_REF",
    "EVALUATION_REF",
    "GALLERY_IMAGE_ROUTE",
    "GLOBAL_DIRECTION_REF",
    "INPUT_POSTER_PROXY_REF",
    "INPUT_UNIVERSE_REF",
    "INVENTORY_REF",
    "MANIFEST_REF",
    "NATIVE_TRANSPARENCY_IMAGE_ROUTE",
    "OPAQUE_IMAGE_ROUTE",
    "PLAN_REF",
    "POSTER_PROXY_LONG_EDGE",
    "POSTER_PROXY_REF",
    "PROPOSAL_REF",
    "REVIEW_PROXY_LONG_EDGE",
    "SAMPLE_LEDGER_REF",
    "SEMANTIC_REVIEW_REF",
    "SOURCE_LOCK_REF",
    "UNIVERSE_CACHE_NAMESPACE",
    "UNIVERSE_CACHE_RECORD_KIND",
    "UNIVERSE_GRAPH_SCHEMA_VERSION",
    "UNIVERSE_REF",
    "UNIVERSE_TRACE_SCHEMA_VERSION",
    "ImageRoute",
    "UniverseGraph",
    "UniverseOperationKind",
    "build_universe_gallery_graph",
    "build_universe_semantic_graph",
    "image_route",
    "node_safe",
    "universe_graph_profile",
]
