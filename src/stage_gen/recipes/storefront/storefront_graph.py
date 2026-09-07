"""Storefront execution documents and the exact DAG one package implies.

Seventh recipe, same engine, and the simplest graph any of them has: one
direction compiled once, one listing written from it, and a fan-out of
independent surfaces that share only that direction and the authored art. There
is no composition contract here, no layout identity and no runtime consumer —
each branch is one picture at one canvas, drawn from one brief.

Identity is split along what each node actually consumes. The direction tier
binds the references and the instruction that reads them; the image tier binds
its own brief, its surface geometry and its draw index; the review tier binds the
review instruction. Recalibrating the reviewer must not re-bill the pictures,
and swapping one surface's brief must not re-bill the others.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from gnode import (
    SHA256_PATTERN,
    AuthoredInput,
    Binding,
    BindingTable,
    GraphBuilder,
    ModelRef,
    NodeCard,
    Port,
    PortRef,
)
from stage_gen.recipes.graph_document import RecipeGraph
from stage_gen.recipes.ports import artifact_port, attempts_port, record_port, text_digest
from stage_gen.recipes.storefront.storefront_prompts import (
    direction_instructions,
    listing_instructions,
    review_instructions,
)
from stage_gen.recipes.storefront.storefront_request import (
    DIRECTION_REF,
    INVENTORY_REF,
    LISTING_REF,
    drawn_ref,
    proxy_ref,
    record_ref,
    review_ref,
    shipped_ref,
    validation_ref,
)
from stage_gen.recipes.storefront.storefront_types import (
    DIRECTION_COMPILE,
    DIRECTION_KIND,
    DRAWN_SURFACE_KIND,
    INVENTORY_KIND,
    LISTING_COMPILE,
    LISTING_KIND,
    REFERENCE_KIND,
    SHIPPED_SURFACE_KIND,
    STOREFRONT_CLOSE,
    STOREFRONT_KIND,
    STOREFRONT_RESOLVE,
    SURFACE_GENERATE,
    SURFACE_NORMALIZE,
    SURFACE_PROXY,
    SURFACE_PROXY_KIND,
    SURFACE_RECORD,
    SURFACE_RECORD_KIND,
    SURFACE_REVIEW,
    SURFACE_REVIEW_KIND,
    SURFACE_VALIDATE,
    SURFACE_VALIDATION_KIND,
)
from stage_gen.recipes.storefront.surfaces import surface
from stage_gen.recipes.structured_transport import ATTEMPT_LEDGER_KIND

if TYPE_CHECKING:
    from stage_gen.config import StageGenConfig
    from stage_gen.recipes.storefront.storefront_request import ResolvedStorefront

STOREFRONT_GRAPH_SCHEMA_VERSION = 1
STOREFRONT_TRACE_SCHEMA_VERSION = 1
STOREFRONT_CACHE_NAMESPACE = "storefront-nodes-v1"
STOREFRONT_CACHE_RECORD_KIND = "storefront-node-cache-v1"

#: Long edge of the picture the reviewer is shown. A review instrument, never a
#: package asset and never an image-generation reference.
REVIEW_PROXY_LONG_EDGE = 1280


class StorefrontOperationKind(StrEnum):
    """The capabilities a storefront node is allowed to use."""

    LOCAL = "local"
    IMAGE_GENERATION = "image_generation"
    STRUCTURED_GENERATION = "structured_generation"


class StorefrontGraph(RecipeGraph):
    """One storefront plan of record, bound to the package that produced it."""

    OPERATIONS = StorefrontOperationKind
    VIEW_FIELDS = ("storefront_id", "surface_count")

    schema_version: Literal[1]
    kind: Literal["storefront-execution-graph-v1"]
    recipe: Literal["storefront"]
    storefront_id: str
    storefront_sha256: str = Field(pattern=SHA256_PATTERN)
    surface_count: int
    draw_ledger_sha256: str = Field(pattern=SHA256_PATTERN)
    publication_authorized: Literal[False]


IMAGE_FEATURES = ("reference_images",)
STRUCTURED_FEATURES = ("structured_output", "image_input")


def storefront_graph_profile(config: StageGenConfig) -> BindingTable:
    """Declare the provider routes a storefront plan may use, credentials untouched."""

    return BindingTable(
        [
            Binding(
                operation=StorefrontOperationKind.IMAGE_GENERATION,
                # Every surface is opaque, so the route is the opaque one. Native
                # alpha is the reason to reach for the direct provider, and no
                # storefront surface has any use for it.
                model=ModelRef(model=config.openai_image_model, provider="openrouter"),
                features=frozenset(IMAGE_FEATURES),
                resource_id="openrouter-image",
                estimated_duration_seconds=120.0,
                estimated_cost_low_usd=0.04,
                estimated_cost_high_usd=0.20,
                requests_per_minute=config.openai_image_ipm,
                rate_limit_owner="provider_adapter",
                verified_on="2026-09-07",
            ),
            Binding(
                operation=StorefrontOperationKind.STRUCTURED_GENERATION,
                model=ModelRef(model=config.text_model, provider="openrouter"),
                features=frozenset(STRUCTURED_FEATURES),
                resource_id="openrouter-structured",
                estimated_duration_seconds=30.0,
                estimated_cost_low_usd=0.005,
                estimated_cost_high_usd=0.08,
                verified_on="2026-09-07",
            ),
        ]
    )


def node_safe(surface_id: str) -> str:
    return surface_id.replace("_", "-")


def build_storefront_graph(
    resolved: ResolvedStorefront,
    *,
    profile: BindingTable,
) -> StorefrontGraph:
    """Compile one authored storefront package into the exact node graph it implies."""

    source = resolved.source
    builder = GraphBuilder(profile=profile, local_max_in_flight=4)
    direction_ref = PortRef(node_id="storefront-direction", port_id="direction")

    # The references are the whole look. Their digests ride the direction's identity
    # and every image's identity — swapping the art in the package is a different
    # product, and the whole storefront re-bills on purpose — and each card names
    # them as authored inputs, so a reader of the plan sees the files that will be
    # attached to the call rather than an unexplained digest.
    reference_digests = resolved.reference_digests()
    reference_inputs = tuple(
        AuthoredInput(label=reference.reference_id, ref=reference.source, sha256=reference.sha256)
        for reference in resolved.references
    )

    builder.add(
        STOREFRONT_RESOLVE,
        "storefront-resolve",
        domain="storefront",
        description="Canonicalize and admit the authored storefront document",
        input_digests=(resolved.source_sha256, resolved.positioning_sha256),
        ports=(artifact_port("storefront", "storefront.json", STOREFRONT_KIND),),
    )

    direction_prompt = direction_instructions(
        storefront_id=resolved.storefront_id,
        display_name=resolved.title,
        surface_count=len(source.surfaces),
    )
    builder.add(
        DIRECTION_COMPILE,
        "storefront-direction",
        domain="storefront",
        description="Read the authored art once and seal the look every surface inherits",
        params={"reference_count": str(len(resolved.references))},
        depends_on=("storefront-resolve",),
        # storefront-resolve is a barrier: this node's real inputs are its
        # instruction, the positioning note and the reference bytes, so an
        # unrelated authored edit never chains into every picture through here.
        cache_depends_on=(),
        input_digests=(
            text_digest(direction_prompt),
            resolved.positioning_sha256,
            *reference_digests,
        ),
        ports=(
            artifact_port("direction", DIRECTION_REF, DIRECTION_KIND),
            attempts_port("storefront-direction", ATTEMPT_LEDGER_KIND),
        ),
        card=NodeCard(
            prompt=direction_prompt,
            schema_name="StorefrontDirection",
            authored_inputs=reference_inputs,
        ),
    )

    listing_prompt = listing_instructions(
        storefront_id=resolved.storefront_id, display_name=resolved.title
    )
    builder.add(
        LISTING_COMPILE,
        "storefront-listing",
        domain="storefront",
        description="Write the store listing copy from the sealed direction",
        depends_on=("storefront-direction",),
        input_digests=(text_digest(listing_prompt), resolved.positioning_sha256),
        ports=(
            artifact_port("listing", LISTING_REF, LISTING_KIND),
            attempts_port("storefront-listing", ATTEMPT_LEDGER_KIND),
        ),
        card=NodeCard(
            prompt=listing_prompt,
            schema_name="StoreListing",
            reference_inputs=(direction_ref,),
        ),
    )

    record_nodes: list[str] = []
    with builder.within_template("storefront-surface-pipeline@v1"):
        for authored in source.surfaces:
            surface_id = authored.surface_id
            declared = surface(authored.kind.value)
            safe = node_safe(surface_id)
            draw = resolved.draws.draw(surface_id)
            generate_id = f"surface-{safe}-generate"
            normalize_id = f"surface-{safe}-normalize"
            validate_id = f"surface-{safe}-validate"
            proxy_id = f"surface-{safe}-proxy"
            review_id = f"surface-{safe}-review"
            record_id = f"surface-{safe}-record"
            drawn = drawn_ref(surface_id)
            shipped = shipped_ref(surface_id)

            builder.add(
                SURFACE_GENERATE,
                generate_id,
                domain="surfaces",
                description=f"Draw the {declared.title.lower()} for {surface_id}",
                params={
                    "surface_id": surface_id,
                    "surface_kind": declared.kind.value,
                    "draw_size": declared.draw_size,
                    "ship_size": declared.ship_size,
                    "draw": str(draw),
                    "input_reference_count": str(len(resolved.references)),
                    "mask_reference_count": "0",
                },
                depends_on=("storefront-direction",),
                # The two canvases and the draw index belong to identity, not only
                # to params: a picture drawn to a superseded canvas is not a valid
                # answer to this question, and the draw index exists to be changed
                # by hand so that one surface — and only one — is redrawn.
                input_digests=(
                    text_digest(authored.brief),
                    text_digest(
                        f"{declared.kind.value}:{declared.draw_size}->{declared.ship_size}"
                    ),
                    text_digest(f"draw:{surface_id}:{draw}"),
                    *reference_digests,
                ),
                ports=(artifact_port("image", drawn, DRAWN_SURFACE_KIND),),
                card=NodeCard(
                    prompt=authored.brief,
                    reference_inputs=(direction_ref,),
                    authored_inputs=reference_inputs,
                ),
            )
            builder.add(
                SURFACE_NORMALIZE,
                normalize_id,
                domain="surfaces",
                description=f"Cut {surface_id} to the exact {declared.ship_size} ship canvas",
                params={"surface_id": surface_id, "ship_size": declared.ship_size},
                depends_on=(generate_id,),
                input_digests=(
                    text_digest(
                        f"{declared.ship_size}:alpha={int(declared.forbids_alpha_channel)}"
                    ),
                ),
                ports=(artifact_port("image", shipped, SHIPPED_SURFACE_KIND),),
                card=NodeCard(
                    prompt=(
                        "Resize without distortion and centre-crop to the exact ship "
                        "canvas; the storefront refuses anything else."
                    ),
                    reference_inputs=(PortRef(node_id=generate_id, port_id="image"),),
                ),
            )
            builder.add(
                SURFACE_VALIDATE,
                validate_id,
                domain="surfaces",
                description=f"Prove {surface_id} meets its exact canvas, alpha and byte contract",
                params={"surface_id": surface_id},
                depends_on=(normalize_id,),
                input_digests=(
                    text_digest(
                        f"{declared.ship_size}:alpha={int(declared.forbids_alpha_channel)}"
                        f":bytes={declared.max_bytes}"
                    ),
                ),
                ports=(
                    record_port("validation", validation_ref(surface_id), SURFACE_VALIDATION_KIND),
                ),
                card=NodeCard(reference_inputs=(PortRef(node_id=normalize_id, port_id="image"),)),
            )
            builder.add(
                SURFACE_PROXY,
                proxy_id,
                domain="surfaces",
                description=f"Downscaled review proxy for {surface_id}",
                params={"surface_id": surface_id, "long_edge": str(REVIEW_PROXY_LONG_EDGE)},
                depends_on=(validate_id,),
                input_digests=(text_digest(str(REVIEW_PROXY_LONG_EDGE)),),
                ports=(artifact_port("proxy", proxy_ref(surface_id), SURFACE_PROXY_KIND),),
                card=NodeCard(
                    prompt=(
                        "Make the review proxy; it is a review instrument, never a "
                        "package asset and never a generation reference."
                    ),
                    reference_inputs=(PortRef(node_id=normalize_id, port_id="image"),),
                ),
            )
            review_prompt = review_instructions(surface_id=surface_id, declared=declared)
            builder.add(
                SURFACE_REVIEW,
                review_id,
                domain="surfaces",
                description=f"Independent review of the {surface_id} picture",
                params={"surface_id": surface_id, "proxy_reference_count": "1"},
                depends_on=(proxy_id,),
                input_digests=(text_digest(review_prompt),),
                ports=(
                    artifact_port("review", review_ref(surface_id), SURFACE_REVIEW_KIND),
                    attempts_port(review_id, ATTEMPT_LEDGER_KIND),
                ),
                card=NodeCard(
                    prompt=review_prompt,
                    schema_name="SurfaceReview",
                    reference_inputs=(
                        PortRef(node_id=proxy_id, port_id="proxy"),
                        direction_ref,
                    ),
                ),
            )
            builder.add(
                SURFACE_RECORD,
                record_id,
                domain="surfaces",
                description=f"What {surface_id} is, what it cost, and how it was judged",
                params={"surface_id": surface_id},
                depends_on=(review_id,),
                ports=(record_port("record", record_ref(surface_id), SURFACE_RECORD_KIND),),
                card=NodeCard(
                    prompt="Materialize the surface record with its review outcome.",
                    reference_inputs=(
                        PortRef(node_id=review_id, port_id="review"),
                        PortRef(node_id=normalize_id, port_id="image"),
                    ),
                ),
            )
            record_nodes.append(record_id)

    builder.add(
        STOREFRONT_CLOSE,
        "storefront-close",
        domain="storefront",
        description="Closed inventory: exactly one picture per declared surface, statuses recorded",
        depends_on=("storefront-listing", *record_nodes),
        input_digests=(resolved.source_sha256,),
        ports=(
            # The package republishes the authored references into the run: the
            # inventory names them, so the run must carry the bytes it names.
            *(
                artifact_port(
                    f"reference_{reference.reference_id}", reference.source, REFERENCE_KIND
                )
                for reference in resolved.references
            ),
            record_port("inventory", INVENTORY_REF, INVENTORY_KIND),
            Port(port_id="merged_attempts", artifact_ref="attempts.json", kind=ATTEMPT_LEDGER_KIND),
        ),
    )

    return StorefrontGraph.seal(
        resources=builder.resources(),
        nodes=builder.nodes,
        terminal_node_id="storefront-close",
        storefront_id=resolved.storefront_id,
        storefront_sha256=resolved.source_sha256,
        surface_count=len(source.surfaces),
        draw_ledger_sha256=text_digest(
            ":".join(f"{key}={value}" for key, value in sorted(resolved.draws.draws.items()))
        ),
        publication_authorized=False,
    )


__all__ = [
    "REVIEW_PROXY_LONG_EDGE",
    "STOREFRONT_CACHE_NAMESPACE",
    "STOREFRONT_CACHE_RECORD_KIND",
    "STOREFRONT_GRAPH_SCHEMA_VERSION",
    "STOREFRONT_TRACE_SCHEMA_VERSION",
    "StorefrontGraph",
    "StorefrontOperationKind",
    "build_storefront_graph",
    "node_safe",
    "storefront_graph_profile",
]
