from __future__ import annotations

from gnode import Node, Port, RetryOwner
from stage_gen.recipes.sideview_platformer.execution_graph import OperationKind
from stage_gen.recipes.sideview_platformer.view_annotations import (
    annotate_sideview_platformer_artifact,
)


def _node(
    *,
    node_id: str = "player-wayfarer-state-idle-generate",
    type_id: str = "2d/sideview/platformer/motion_atlas.generate",
    params: dict[str, str] | None = None,
    ports: tuple[Port, ...] = (),
) -> Node:
    return Node(
        node_id=node_id,
        type_id=type_id,
        domain="player-wayfarer",
        description="generate one motion strip",
        params=params if params is not None else {"actor_kind": "player", "state": "idle"},
        operation=OperationKind.IMAGE_GENERATION,
        resource_id="openai-image",
        provider="openai",
        model="gpt-image-2",
        retry_owner=RetryOwner.COMPONENT,
        max_attempts=6,
        cache_key="0" * 64,
        ports=ports,
        estimated_duration_seconds=120.0,
        estimated_cost_low_usd=0.04,
        estimated_cost_high_usd=0.2,
    )


def _port(ref: str, kind: str) -> Port:
    return Port(port_id="image", artifact_ref=ref, kind=kind, sidecar_ref=f"{ref}.meta.json")


def test_motion_ports_get_frame_geometry_from_the_declared_type() -> None:
    ref = "content/players/wayfarer/states/idle.source.png"
    node = _node(ports=(_port(ref, "motion-source-v1"),))
    annotation = annotate_sideview_platformer_artifact(ref, node)
    assert annotation.display == "motion_atlas"
    assert annotation.motion is not None
    assert annotation.motion.frame_count == 4
    # Ports killed the path-convention guess; only the playback gap remains.
    assert {gap.gap_id for gap in annotation.gaps} == {"motion-playback-not-in-run-documents"}


def test_player_climb_states_use_the_two_cell_geometry() -> None:
    ref = "content/players/wayfarer/states/climb_ladder.png"
    node = _node(
        params={"actor_kind": "player", "actor_id": "wayfarer", "state": "climb_ladder"},
        ports=(_port(ref, "motion-atlas-v1"),),
    )
    annotation = annotate_sideview_platformer_artifact(ref, node)
    assert annotation.motion is not None
    assert annotation.motion.frame_count == 2


def test_npc_world_sprites_are_motion_atlases_with_default_geometry() -> None:
    ref = "content/npcs/brom_copperkeg/world.source.png"
    node = _node(
        node_id="npc-brom_copperkeg-world-generate",
        type_id="2d/sideview/platformer/world_sprite.generate",
        params={"actor_kind": "npc", "actor_id": "brom_copperkeg"},
        ports=(_port(ref, "motion-source-v1"),),
    )
    annotation = annotate_sideview_platformer_artifact(ref, node)
    assert annotation.display == "motion_atlas"
    assert annotation.motion is not None
    assert annotation.motion.frame_count == 4


def test_everything_else_falls_back_to_media_type() -> None:
    node = _node(
        type_id="2d/sideview/platformer/actor_concept.generate",
        params={"actor_kind": "player", "actor_id": "wayfarer"},
        ports=(_port("content/players/wayfarer/concept.png", "actor-concept-v1"),),
    )
    cases = {
        "content/players/wayfarer/states/idle.validation.json": "data",
        "content/players/wayfarer/states/idle.source.png.meta.json": "data",
        "content/players/wayfarer/concept.png": "image",
        "soundtrack/sunpetal_morning.mp3": "audio",
        "package.identity.json": "data",
    }
    for ref, display in cases.items():
        annotation = annotate_sideview_platformer_artifact(ref, node)
        assert annotation.display == display, ref
        assert annotation.motion is None
        assert annotation.gaps == ()
