from __future__ import annotations

from stage_gen.orchestration.execution_graph import ExecutionNode, OperationKind, RetryOwner
from stage_gen.recipes.scrolling_preview.view_annotations import (
    annotate_scrolling_preview_artifact,
)


def _node() -> ExecutionNode:
    return ExecutionNode(
        node_id="player-wayfarer-state-idle-generate",
        domain="player-wayfarer",
        description="generate one motion strip",
        operation=OperationKind.IMAGE_GENERATION,
        resource_id="openai-image",
        provider="openai",
        model="gpt-image-2",
        retry_owner=RetryOwner.COMPONENT,
        max_attempts=6,
        cache_key="0" * 64,
        estimated_duration_seconds=120.0,
        estimated_cost_low_usd=0.04,
        estimated_cost_high_usd=0.2,
    )


def test_motion_state_strips_get_frame_geometry_and_admit_the_convention() -> None:
    node = _node()
    for ref in (
        "content/players/wayfarer/states/idle.source.png",
        "content/players/wayfarer/states/idle.png",
        "content/mobs/petal_puff/states/attack.png",
    ):
        annotation = annotate_scrolling_preview_artifact(ref, node)
        assert annotation.display == "motion_atlas"
        assert annotation.motion is not None
        assert annotation.motion.frame_count == 4
        assert {gap.gap_id for gap in annotation.gaps} == {
            "display-by-path-convention",
            "motion-playback-not-in-run-documents",
        }


def test_player_climb_states_use_the_two_cell_geometry() -> None:
    annotation = annotate_scrolling_preview_artifact(
        "content/players/wayfarer/states/climb_ladder.png", _node()
    )
    assert annotation.motion is not None
    assert annotation.motion.frame_count == 2


def test_npc_world_strips_are_motion_atlases() -> None:
    annotation = annotate_scrolling_preview_artifact(
        "content/npcs/brom_copperkeg/world.source.png", _node()
    )
    assert annotation.display == "motion_atlas"
    assert annotation.motion is not None
    assert annotation.motion.frame_count == 4


def test_everything_else_falls_back_to_media_type() -> None:
    node = _node()
    cases = {
        "content/players/wayfarer/states/idle.validation.json": "data",
        "content/players/wayfarer/states/idle.source.png.meta.json": "data",
        "content/players/wayfarer/concept.png": "image",
        "soundtrack/sunpetal_morning.mp3": "audio",
        "package.identity.json": "data",
    }
    for ref, display in cases.items():
        annotation = annotate_scrolling_preview_artifact(ref, node)
        assert annotation.display == display, ref
        assert annotation.motion is None
        assert annotation.gaps == ()
