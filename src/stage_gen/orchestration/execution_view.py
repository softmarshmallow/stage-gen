"""The prepared-game run view: this application's derived read-only document.

The engine performs the plan-and-trace join and owns the state vocabulary. This
module owns the document's name, its hard-drop version, the header fields that
bind a view to one game, and which recipe annotates an artifact for display.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from gnode import RunView, build_run_view
from stage_gen.orchestration.execution_graph import ExecutionGraph

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from gnode import ArtifactAnnotator

EXECUTION_VIEW_SCHEMA_VERSION: Literal[2] = 2
EXECUTION_VIEW_KIND: Literal["prepared-game-execution-view-v1"] = "prepared-game-execution-view-v1"


class ExecutionView(RunView):
    """One prepared-game run, read back as the graph it was."""

    recipe: str
    game_id: str


def build_execution_view(
    run_dir: Path,
    *,
    annotators: Mapping[str, ArtifactAnnotator] | None = None,
) -> ExecutionView:
    """Export one run directory, letting its recipe say what each artifact is for."""

    return build_run_view(
        run_dir,
        graph_type=ExecutionGraph,
        view_type=ExecutionView,
        annotators=annotators,
    )


__all__ = [
    "EXECUTION_VIEW_KIND",
    "EXECUTION_VIEW_SCHEMA_VERSION",
    "ExecutionView",
    "build_execution_view",
]
