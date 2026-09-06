"""The oblique-survival run view: this recipe's derived read-only document."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from gnode import RunView, build_run_view
from stage_gen.recipes.oblique_survival.survival_graph import ObliqueSurvivalGraph
from stage_gen.recipes.oblique_survival.survival_types import survival_type_index

if TYPE_CHECKING:
    from pathlib import Path

#: Matches ``ObliqueSurvivalGraph.VIEW_SCHEMA_VERSION``: the shared run-view
#: document version, which gnode owns and every recipe emits.
OBLIQUE_SURVIVAL_VIEW_SCHEMA_VERSION: Literal[3] = 3
OBLIQUE_SURVIVAL_VIEW_KIND: Literal["oblique-survival-execution-view-v1"] = (
    "oblique-survival-execution-view-v1"
)


class ObliqueSurvivalView(RunView):
    """One oblique-survival run, read back as the graph it was."""

    recipe: str
    scope: str
    package_id: str
    presentation_profile: str
    source_digest: str


def build_oblique_survival_view(run_dir: Path) -> ObliqueSurvivalView:
    return build_run_view(
        run_dir,
        graph_type=ObliqueSurvivalGraph,
        view_type=ObliqueSurvivalView,
        types=survival_type_index(),
    )


__all__ = [
    "OBLIQUE_SURVIVAL_VIEW_KIND",
    "OBLIQUE_SURVIVAL_VIEW_SCHEMA_VERSION",
    "ObliqueSurvivalView",
    "build_oblique_survival_view",
]
