"""The universe run view: this recipe's derived read-only document."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from gnode import RunView, build_run_view
from stage_gen.recipes.universe.universe_graph import UniverseGraph
from stage_gen.recipes.universe.universe_types import universe_type_index

if TYPE_CHECKING:
    from pathlib import Path

UNIVERSE_VIEW_SCHEMA_VERSION: Literal[1] = 1
UNIVERSE_VIEW_KIND: Literal["universe-execution-view-v1"] = "universe-execution-view-v1"


class UniverseView(RunView):
    """One universe run, read back as the graph it was."""

    recipe: str
    phase: str
    universe_id: str
    medium_id: str
    entity_count: int


def build_universe_view(run_dir: Path) -> UniverseView:
    return build_run_view(
        run_dir,
        graph_type=UniverseGraph,
        view_type=UniverseView,
        types=universe_type_index(),
    )


__all__ = [
    "UNIVERSE_VIEW_KIND",
    "UNIVERSE_VIEW_SCHEMA_VERSION",
    "UniverseView",
    "build_universe_view",
]
