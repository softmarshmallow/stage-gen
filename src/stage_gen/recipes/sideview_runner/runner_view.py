"""The sideview-runner run view: this recipe's derived read-only document."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from gnode import RunView, build_run_view
from stage_gen.recipes.sideview_runner.runner_graph import SideviewRunnerGraph
from stage_gen.recipes.sideview_runner.runner_types import runner_type_index

if TYPE_CHECKING:
    from pathlib import Path

RUNNER_VIEW_SCHEMA_VERSION: Literal[3] = 3
RUNNER_VIEW_KIND: Literal["sideview-runner-execution-view-v1"] = "sideview-runner-execution-view-v1"


class SideviewRunnerView(RunView):
    """One runner run, read back as the graph it was."""

    recipe: str
    game_id: str
    track_id: str


def build_sideview_runner_view(run_dir: Path) -> SideviewRunnerView:
    return build_run_view(
        run_dir,
        graph_type=SideviewRunnerGraph,
        view_type=SideviewRunnerView,
        types=runner_type_index(),
    )


__all__ = [
    "RUNNER_VIEW_KIND",
    "RUNNER_VIEW_SCHEMA_VERSION",
    "SideviewRunnerView",
    "build_sideview_runner_view",
]
