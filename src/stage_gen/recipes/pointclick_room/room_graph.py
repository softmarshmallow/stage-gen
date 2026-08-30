"""Point-and-click room execution documents and the exact DAG one room implies.

Third recipe, same engine: a room is not a game package and not a dialogue
scene, so it carries its own document kinds. Every generation node's full
static prompt rides its card — the plan states what each node will be told.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import Field

from gnode import (
    SHA256_PATTERN,
    Binding,
    BindingTable,
    Graph,
    GraphBuilder,
    ModelRef,
    NodeCard,
    Port,
    PortRef,
    seal_graph,
)
from stage_gen.recipes.pointclick_room.room_prompts import (
    backdrop_prompt,
    hotspot_sprite_prompt,
    item_icon_prompt,
    narration_prompt,
)
from stage_gen.recipes.pointclick_room.room_types import (
    ATTEMPT_LEDGER_KIND,
    BACKDROP_GENERATE,
    BACKDROP_KIND,
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


class PointClickRoomGraph(Graph):
    """One room plan of record, bound to the authored document that produced it."""

    TRACE_SCHEMA_VERSION: ClassVar[int] = POINTCLICK_TRACE_SCHEMA_VERSION
    TRACE_EVENT_KIND: ClassVar[str] = "pointclick-room-execution-event-v1"
    RUN_SUMMARY_KIND: ClassVar[str] = "pointclick-room-execution-summary-v1"
    PROJECTION_KIND: ClassVar[str] = "pointclick-room-execution-projection-v1"
    VIEW_KIND: ClassVar[str] = "pointclick-room-execution-view-v1"
    VIEW_SCHEMA_VERSION: ClassVar[int] = 3

    schema_version: Literal[1]
    kind: Literal["pointclick-room-execution-graph-v1"]
    recipe: Literal["pointclick-room"]
    room_id: str
    room_sha256: str = Field(pattern=SHA256_PATTERN)

    def identity_header(self) -> dict[str, object]:
        return {**super().identity_header(), "recipe": self.recipe}

    def annotator_key(self) -> str:
        return self.recipe

    def view_header(self) -> dict[str, object]:
        return {"recipe": self.recipe, "room_id": self.room_id}

    def operation_vocabulary(self) -> tuple[str, ...]:
        return tuple(operation.value for operation in RoomOperationKind)


IMAGE_FEATURES = ("transparent_background", "reference_images")
STRUCTURED_FEATURES = ("structured_output",)


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


def _artifact(port_id: str, ref: str, kind: str) -> Port:
    return Port(port_id=port_id, artifact_ref=ref, kind=kind, sidecar_ref=f"{ref}.meta.json")


def _record(port_id: str, ref: str, kind: str) -> Port:
    return Port(port_id=port_id, artifact_ref=ref, kind=kind)


def _attempts(node_id: str) -> Port:
    return Port(
        port_id="attempts", artifact_ref=f"attempts/{node_id}.json", kind=ATTEMPT_LEDGER_KIND
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
        ports=(_artifact("room", "room.json", ROOM_KIND),),
    )
    builder.add(
        STYLE_SELECT,
        "room-style-select",
        domain="room",
        description="Select and materialize the canonical image style anchor",
        depends_on=("room-resolve",),
        input_digests=(
            resolved.room_sha256,
            resolved.style_resource_sha256,
            resolved.style_compiler_sha256,
        ),
        ports=(
            _artifact("anchor", "style-anchor.json", STYLE_ANCHOR_KIND),
            _attempts("room-style-select"),
        ),
        card=NodeCard(prompt=resolved.style_selection_brief, schema_name="canonical_style_anchor"),
    )

    builder.add(
        BACKDROP_GENERATE,
        "room-backdrop",
        domain="room",
        description="Paint the full-frame room backdrop",
        depends_on=("room-style-select",),
        input_digests=(resolved.room_sha256,),
        ports=(
            _artifact("image", "assets/backdrop.png", BACKDROP_KIND),
            _attempts("room-backdrop"),
        ),
        card=NodeCard(prompt=backdrop_prompt(room), reference_inputs=(anchor_ref,)),
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
                input_digests=(resolved.room_sha256,),
                ports=(
                    _artifact(
                        "image", f"assets/hotspots/{hotspot.hotspot_id}.png", HOTSPOT_SPRITE_KIND
                    ),
                    _attempts(generate_id),
                ),
                card=NodeCard(
                    prompt=hotspot_sprite_prompt(room, hotspot), reference_inputs=(anchor_ref,)
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
                    _record(
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
                input_digests=(resolved.room_sha256,),
                ports=(
                    _artifact("image", f"assets/items/{item.item_id}.png", ITEM_ICON_KIND),
                    _attempts(generate_id),
                ),
                card=NodeCard(prompt=item_icon_prompt(room, item), reference_inputs=(anchor_ref,)),
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
                    _record(
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

    builder.add(
        NARRATION_COMPILE,
        "room-narration",
        domain="room",
        description="Write every narration line the author left to generation",
        depends_on=("room-resolve",),
        input_digests=(resolved.room_sha256,),
        ports=(
            _artifact("document", "narration.json", NARRATION_KIND),
            _attempts("room-narration"),
        ),
        card=NodeCard(prompt=narration_prompt(room), schema_name="pointclick_narration_v1"),
    )

    builder.add(
        PUZZLE_VALIDATE,
        "room-puzzle-validate",
        domain="room",
        description="Prove the room finishable and project the runtime puzzle document",
        depends_on=("room-resolve",),
        input_digests=(resolved.room_sha256,),
        ports=(
            _record("puzzle", "puzzle.json", PUZZLE_KIND),
            _record("solvability", "puzzle.validation.json", SOLVABILITY_KIND),
        ),
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
            "room-narration",
            "room-puzzle-validate",
        ),
        input_digests=(resolved.room_sha256,),
        ports=(
            _record("manifest", "manifest.json", MANIFEST_KIND),
            Port(
                port_id="merged_attempts",
                artifact_ref="attempts.json",
                kind=MERGED_ATTEMPTS_KIND,
            ),
        ),
    )

    return seal_graph(
        PointClickRoomGraph,
        resources=builder.resources(),
        nodes=builder.nodes,
        terminal_node_id="room-bundle",
        schema_version=POINTCLICK_GRAPH_SCHEMA_VERSION,
        kind="pointclick-room-execution-graph-v1",
        recipe="pointclick-room",
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
