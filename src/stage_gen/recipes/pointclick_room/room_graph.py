"""Point-and-click room execution documents and the exact DAG one room implies.

Third recipe, same engine: a room is not a game package and not a dialogue
scene, so it carries its own document kinds. Every generation node's full
static prompt rides its card — the plan states what each node will be told.
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
from stage_gen.components.game_ui.nodes import add_ui_atlas_nodes
from stage_gen.recipes.graph_document import RecipeGraph
from stage_gen.recipes.pointclick_room.room_prompts import (
    backdrop_prompt,
    hotspot_sprite_prompt,
    item_icon_prompt,
    narration_ids,
    narration_prompt,
    style_clause,
    ui_atlas_prompt,
)
from stage_gen.recipes.pointclick_room.room_types import (
    ATTEMPT_LEDGER_KIND,
    BACKDROP_GENERATE,
    BACKDROP_KIND,
    COVER_KIND,
    HOTSPOT_SPRITE_GENERATE,
    HOTSPOT_SPRITE_KIND,
    HOTSPOT_SPRITE_VALIDATE,
    ITEM_ICON_GENERATE,
    ITEM_ICON_KIND,
    ITEM_ICON_VALIDATE,
    MANIFEST_KIND,
    MERGED_ATTEMPTS_KIND,
    NARRATION_COMPILE,
    NARRATION_KIND,
    PUZZLE_KIND,
    PUZZLE_VALIDATE,
    ROOM_BUNDLE,
    ROOM_KIND,
    ROOM_RESOLVE,
    SOLVABILITY_KIND,
    SPRITE_VALIDATION_KIND,
    STYLE_ANCHOR_KIND,
    STYLE_SELECT,
)
from stage_gen.recipes.ports import artifact_port, attempts_port, record_port, text_digest

if TYPE_CHECKING:
    from stage_gen.config import StageGenConfig
    from stage_gen.recipes.pointclick_room.room_request import ResolvedPointClickRoom

POINTCLICK_GRAPH_SCHEMA_VERSION = 1
POINTCLICK_TRACE_SCHEMA_VERSION = 1
POINTCLICK_CACHE_NAMESPACE = "pointclick-room-nodes-v1"
POINTCLICK_CACHE_RECORD_KIND = "pointclick-room-node-cache-v1"


class RoomOperationKind(StrEnum):
    """The capabilities a room node is allowed to use."""

    LOCAL = "local"
    IMAGE_GENERATION = "image_generation"
    STRUCTURED_GENERATION = "structured_generation"


class PointClickRoomGraph(RecipeGraph):
    """One room plan of record, bound to the authored document that produced it."""

    OPERATIONS = RoomOperationKind
    VIEW_FIELDS = ("room_id",)

    schema_version: Literal[1]
    kind: Literal["pointclick-room-execution-graph-v1"]
    recipe: Literal["pointclick-room"]
    room_id: str
    room_sha256: str = Field(pattern=SHA256_PATTERN)


IMAGE_FEATURES = ("transparent_background", "reference_images")
#: What the bound route can do, which is not the same as what any one node asks of it:
#: narration needs only structured output, while the UI atlas judge is handed the evidence
#: sheet and so needs image input from the same model.
STRUCTURED_FEATURES = ("structured_output", "image_input")


def room_graph_profile(config: StageGenConfig) -> BindingTable:
    """Declare the provider routes a room plan may use, credentials untouched."""

    return BindingTable(
        [
            Binding(
                operation=RoomOperationKind.IMAGE_GENERATION,
                model=ModelRef(model=config.openai_image_model, provider="openai"),
                features=frozenset(IMAGE_FEATURES),
                resource_id="openai-image",
                estimated_duration_seconds=120.0,
                estimated_cost_low_usd=0.04,
                estimated_cost_high_usd=0.20,
                requests_per_minute=config.openai_image_ipm,
                rate_limit_owner="provider_adapter",
                verified_on="2026-08-25",
            ),
            Binding(
                operation=RoomOperationKind.STRUCTURED_GENERATION,
                model=ModelRef(model=config.text_model, provider="openrouter"),
                features=frozenset(STRUCTURED_FEATURES),
                resource_id="openrouter-structured",
                estimated_duration_seconds=30.0,
                estimated_cost_low_usd=0.005,
                estimated_cost_high_usd=0.08,
                verified_on="2026-08-20",
            ),
        ]
    )


def build_pointclick_room_graph(
    resolved: ResolvedPointClickRoom,
    *,
    profile: BindingTable,
) -> PointClickRoomGraph:
    """Compile one authored room into the exact node graph it implies."""

    room = resolved.room
    builder = GraphBuilder(profile=profile)
    anchor_ref = PortRef(node_id="room-style-select", port_id="anchor")

    builder.add(
        ROOM_RESOLVE,
        "room-resolve",
        domain="room",
        description="Canonicalize and admit the authored room document",
        input_digests=(resolved.room_sha256,),
        ports=(artifact_port("room", "room.json", ROOM_KIND),),
    )
    builder.add(
        STYLE_SELECT,
        "room-style-select",
        domain="room",
        description="Select and materialize the canonical image style anchor",
        depends_on=("room-resolve",),
        # room-resolve is a barrier: this node's real inputs are its digested
        # brief and the packaged style resources, so an unrelated authored
        # edit never chains into every image's cache key through here.
        cache_depends_on=(),
        input_digests=(
            text_digest(resolved.style_selection_brief),
            resolved.style_resource_sha256,
            resolved.style_compiler_sha256,
        ),
        ports=(
            artifact_port("anchor", "style-anchor.json", STYLE_ANCHOR_KIND),
            attempts_port("room-style-select", ATTEMPT_LEDGER_KIND),
        ),
        card=NodeCard(prompt=resolved.style_selection_brief, schema_name="canonical_style_anchor"),
    )

    # Every image is drawn against the room's authored style references. Their
    # digests ride each image node's identity — swapping the cover in the package
    # is a new look, and the whole room re-bills on purpose — and each card names
    # them as authored inputs, so a reader of the plan sees the file that will be
    # attached to the call rather than an unexplained digest.
    style_digests = tuple(reference.sha256 for reference in resolved.style_references)
    style_inputs = tuple(
        AuthoredInput(label=reference.reference_id, ref=reference.source, sha256=reference.sha256)
        for reference in resolved.style_references
    )

    builder.add(
        BACKDROP_GENERATE,
        "room-backdrop",
        domain="room",
        description="Paint the full-frame room backdrop",
        depends_on=("room-style-select",),
        input_digests=(
            text_digest(backdrop_prompt(room)),
            text_digest(f"{room.scene.width}x{room.scene.height}"),
            *style_digests,
        ),
        ports=(
            artifact_port("image", "assets/backdrop.png", BACKDROP_KIND),
            attempts_port("room-backdrop", ATTEMPT_LEDGER_KIND),
        ),
        card=NodeCard(
            prompt=backdrop_prompt(room),
            reference_inputs=(anchor_ref,),
            authored_inputs=style_inputs,
        ),
    )

    sprite_validations: list[str] = []
    with builder.within_template("hotspot-pipeline@v1"):
        for hotspot in room.hotspots:
            if hotspot.art != "sprite":
                continue
            generate_id = f"hotspot-{hotspot.hotspot_id}-generate"
            generated = builder.add(
                HOTSPOT_SPRITE_GENERATE,
                generate_id,
                domain="hotspots",
                description=f"generate the {hotspot.label} hotspot object",
                params={"hotspot_id": hotspot.hotspot_id},
                depends_on=("room-style-select",),
                input_digests=(
                    text_digest(hotspot_sprite_prompt(room, hotspot)),
                    *style_digests,
                ),
                ports=(
                    artifact_port(
                        "image", f"assets/hotspots/{hotspot.hotspot_id}.png", HOTSPOT_SPRITE_KIND
                    ),
                    attempts_port(generate_id, ATTEMPT_LEDGER_KIND),
                ),
                card=NodeCard(
                    prompt=hotspot_sprite_prompt(room, hotspot),
                    reference_inputs=(anchor_ref,),
                    authored_inputs=style_inputs,
                ),
            )
            validated = builder.add(
                HOTSPOT_SPRITE_VALIDATE,
                f"hotspot-{hotspot.hotspot_id}-validate",
                domain="hotspots",
                description=f"validate isolated alpha for the {hotspot.label} object",
                params={"hotspot_id": hotspot.hotspot_id},
                depends_on=(generated.node_id,),
                input_digests=(resolved.room_sha256,),
                ports=(
                    record_port(
                        "validation",
                        f"assets/hotspots/{hotspot.hotspot_id}.validation.json",
                        SPRITE_VALIDATION_KIND,
                    ),
                ),
                card=NodeCard(
                    reference_inputs=(PortRef(node_id=generated.node_id, port_id="image"),)
                ),
            )
            sprite_validations.append(validated.node_id)

    item_validations: list[str] = []
    with builder.within_template("item-icon-pipeline@v1"):
        for item in room.items:
            generate_id = f"item-{item.item_id}-generate"
            generated = builder.add(
                ITEM_ICON_GENERATE,
                generate_id,
                domain="items",
                description=f"generate the {item.label} inventory icon",
                params={"item_id": item.item_id},
                depends_on=("room-style-select",),
                input_digests=(
                    text_digest(item_icon_prompt(room, item)),
                    *style_digests,
                ),
                ports=(
                    artifact_port("image", f"assets/items/{item.item_id}.png", ITEM_ICON_KIND),
                    attempts_port(generate_id, ATTEMPT_LEDGER_KIND),
                ),
                card=NodeCard(
                    prompt=item_icon_prompt(room, item),
                    reference_inputs=(anchor_ref,),
                    authored_inputs=style_inputs,
                ),
            )
            validated = builder.add(
                ITEM_ICON_VALIDATE,
                f"item-{item.item_id}-validate",
                domain="items",
                description=f"validate isolated alpha for the {item.label} icon",
                params={"item_id": item.item_id},
                depends_on=(generated.node_id,),
                input_digests=(resolved.room_sha256,),
                ports=(
                    record_port(
                        "validation",
                        f"assets/items/{item.item_id}.validation.json",
                        SPRITE_VALIDATION_KIND,
                    ),
                ),
                card=NodeCard(
                    reference_inputs=(PortRef(node_id=generated.node_id, port_id="image"),)
                ),
            )
            item_validations.append(validated.node_id)

    # A fully authored room owes generation nothing: the narration node exists
    # only when the document leaves at least one line to write.
    narration_nodes: tuple[str, ...] = ()
    if narration_ids(room):
        builder.add(
            NARRATION_COMPILE,
            "room-narration",
            domain="room",
            description="Write every narration line the author left to generation",
            depends_on=("room-resolve",),
            cache_depends_on=(),
            input_digests=(text_digest(narration_prompt(room)),),
            ports=(
                artifact_port("document", "narration.json", NARRATION_KIND),
                attempts_port("room-narration", ATTEMPT_LEDGER_KIND),
            ),
            card=NodeCard(prompt=narration_prompt(room), schema_name="pointclick_narration_v1"),
        )
        narration_nodes = ("room-narration",)

    builder.add(
        PUZZLE_VALIDATE,
        "room-puzzle-validate",
        domain="room",
        description="Prove the room finishable and project the runtime puzzle document",
        depends_on=("room-resolve",),
        input_digests=(resolved.room_sha256,),
        ports=(
            record_port("puzzle", "puzzle.json", PUZZLE_KIND),
            record_port("solvability", "puzzle.validation.json", SOLVABILITY_KIND),
        ),
    )

    # Panels and buttons are the one thing every genre draws the same way, so the room
    # plans the shared nine-slice triplet rather than a fourth private copy of it. Its
    # identity is the room's own art direction: repaint the look and the interface
    # re-bills with everything else it has to sit beside.
    ui_terminals = add_ui_atlas_nodes(
        builder,
        root="room-resolve",
        ui=resolved.ui,
        style_prompt=lambda task: ui_atlas_prompt(room, task),
        direction_digests=(text_digest(style_clause(room)),),
        attempts_port=lambda node_id: attempts_port(node_id, ATTEMPT_LEDGER_KIND),
    )

    builder.add(
        ROOM_BUNDLE,
        "room-bundle",
        domain="room",
        description="Assemble the playable room runtime manifest",
        depends_on=(
            "room-backdrop",
            *sprite_validations,
            *item_validations,
            *narration_nodes,
            "room-puzzle-validate",
            *ui_terminals,
        ),
        input_digests=(resolved.room_sha256,),
        ports=(
            # The bundle republishes the authored style references into the run:
            # the manifest names them, so the run must carry the bytes it names.
            *(
                artifact_port(f"reference_{reference.reference_id}", reference.source, COVER_KIND)
                for reference in resolved.style_references
            ),
            record_port("manifest", "manifest.json", MANIFEST_KIND),
            Port(
                port_id="merged_attempts",
                artifact_ref="attempts.json",
                kind=MERGED_ATTEMPTS_KIND,
            ),
        ),
    )

    return PointClickRoomGraph.seal(
        resources=builder.resources(),
        nodes=builder.nodes,
        terminal_node_id="room-bundle",
        room_id=room.room_id,
        room_sha256=resolved.room_sha256,
    )


__all__ = [
    "POINTCLICK_CACHE_NAMESPACE",
    "POINTCLICK_CACHE_RECORD_KIND",
    "POINTCLICK_GRAPH_SCHEMA_VERSION",
    "POINTCLICK_TRACE_SCHEMA_VERSION",
    "PointClickRoomGraph",
    "RoomOperationKind",
    "build_pointclick_room_graph",
    "room_graph_profile",
]
