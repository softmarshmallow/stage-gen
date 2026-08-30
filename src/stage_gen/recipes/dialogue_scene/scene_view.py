"""The dialogue-scene run view: this recipe's derived read-only document.

The engine performs the plan-and-trace join and owns the state vocabulary. This module
owns the document's name, its hard-drop version, and the header fields that bind a view
to one authored scene.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from gnode import RunView, build_run_view
from stage_gen.recipes.dialogue_scene.scene_graph import DialogueSceneGraph
from stage_gen.recipes.dialogue_scene.scene_types import dialogue_type_index

if TYPE_CHECKING:
    from pathlib import Path

DIALOGUE_VIEW_SCHEMA_VERSION: Literal[3] = 3
DIALOGUE_VIEW_KIND: Literal["dialogue-scene-execution-view-v1"] = "dialogue-scene-execution-view-v1"


class DialogueSceneView(RunView):
    """One dialogue-scene run, read back as the graph it was."""

    recipe: str
    scene_id: str


def build_dialogue_scene_view(run_dir: Path) -> DialogueSceneView:
    """Export one dialogue run directory into its derived view document."""

    return build_run_view(
        run_dir,
        graph_type=DialogueSceneGraph,
        view_type=DialogueSceneView,
        types=dialogue_type_index(),
    )


__all__ = [
    "DIALOGUE_VIEW_KIND",
    "DIALOGUE_VIEW_SCHEMA_VERSION",
    "DialogueSceneView",
    "build_dialogue_scene_view",
]
