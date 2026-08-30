"""Scrolling-preview artifact annotations for the derived execution view.

The recipe owns the assumption that certain artifact paths are motion strips.
Until nodes declare typed payloads, that knowledge exists only as the path
conventions below, so every use is admitted in the view's ``gaps`` list — the
measured case for the typed-payload construct.
"""

from __future__ import annotations

import re

from stage_gen.orchestration.execution_graph import ExecutionNode
from stage_gen.orchestration.execution_view import (
    ArtifactAnnotation,
    ExecutionViewGap,
    ExecutionViewMotion,
    generic_artifact_annotation,
)
from stage_gen.recipes.scrolling_preview.motion_contract import (
    DEFAULT_MOTION_ATLAS_GEOMETRY,
    MotionActorKind,
    motion_atlas_geometry,
)

_MOTION_STATE_PATTERN = re.compile(
    r"^content/(players|mobs|npcs)/[a-z0-9_]+/states/([a-z0-9_]+)(?:\.source)?\.png$"
)
_NPC_WORLD_PATTERN = re.compile(r"^content/npcs/[a-z0-9_]+/world(?:\.source)?\.png$")
_ACTOR_KINDS: dict[str, MotionActorKind] = {"players": "player", "mobs": "mob", "npcs": "npc"}

_CONVENTION_GAP = ExecutionViewGap(
    gap_id="display-by-path-convention",
    detail="artifact display kinds are inferred from recipe path conventions, not typed payloads",
)
_PLAYBACK_GAP = ExecutionViewGap(
    gap_id="motion-playback-not-in-run-documents",
    detail="motion playback policy lives in the prepared package, not in run documents",
)


def annotate_scrolling_preview_artifact(
    artifact_ref: str, node: ExecutionNode
) -> ArtifactAnnotation:
    """Refine the generic annotation with the recipe's motion-strip conventions."""

    state_match = _MOTION_STATE_PATTERN.match(artifact_ref)
    if state_match is not None:
        geometry = motion_atlas_geometry(_ACTOR_KINDS[state_match.group(1)], state_match.group(2))
        return ArtifactAnnotation(
            display="motion_atlas",
            motion=ExecutionViewMotion(frame_count=geometry.columns),
            gaps=(_CONVENTION_GAP, _PLAYBACK_GAP),
        )
    if _NPC_WORLD_PATTERN.match(artifact_ref) is not None:
        return ArtifactAnnotation(
            display="motion_atlas",
            motion=ExecutionViewMotion(frame_count=DEFAULT_MOTION_ATLAS_GEOMETRY.columns),
            gaps=(_CONVENTION_GAP, _PLAYBACK_GAP),
        )
    return generic_artifact_annotation(artifact_ref, node)


__all__ = ["annotate_scrolling_preview_artifact"]
