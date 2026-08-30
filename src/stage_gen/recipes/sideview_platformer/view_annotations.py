"""Side-view platformer artifact annotations for the derived execution view.

Nodes declare typed ports now, so an artifact's payload kind and its motion
geometry come from the plan itself: the annotator resolves the artifact back to
the port that declared it and reads the node's typed params. The old
path-convention regexes — and the ``display-by-path-convention`` gap they
admitted — are gone. What still cannot come from run documents is authored
playback policy (frames per second, loop mode), which lives in the prepared
package; that remaining gap stays declared.
"""

from __future__ import annotations

from gnode import (
    ArtifactAnnotation,
    Node,
    RunViewGap,
    RunViewMotion,
    generic_artifact_annotation,
)
from stage_gen.recipes.sideview_platformer.motion_contract import (
    DEFAULT_MOTION_ATLAS_GEOMETRY,
    MotionActorKind,
    motion_atlas_geometry,
)

_MOTION_KINDS = {"motion-source-v1", "motion-atlas-v1"}
_ACTOR_KINDS: dict[str, MotionActorKind] = {"player": "player", "mob": "mob", "npc": "npc"}

_PLAYBACK_GAP = RunViewGap(
    gap_id="motion-playback-not-in-run-documents",
    detail="motion playback policy lives in the prepared package, not in run documents",
)


def annotate_sideview_platformer_artifact(artifact_ref: str, node: Node) -> ArtifactAnnotation:
    """Refine the generic annotation from the artifact's declared port."""

    for port in node.ports:
        if port.artifact_ref != artifact_ref:
            continue
        if port.kind not in _MOTION_KINDS:
            break
        actor_kind = _ACTOR_KINDS.get(node.params.get("actor_kind", ""))
        state = node.params.get("state")
        geometry = (
            motion_atlas_geometry(actor_kind, state)
            if actor_kind is not None and state is not None
            else DEFAULT_MOTION_ATLAS_GEOMETRY
        )
        return ArtifactAnnotation(
            display="motion_atlas",
            motion=RunViewMotion(frame_count=geometry.columns),
            gaps=(_PLAYBACK_GAP,),
        )
    return generic_artifact_annotation(artifact_ref, node)


__all__ = ["annotate_sideview_platformer_artifact"]
