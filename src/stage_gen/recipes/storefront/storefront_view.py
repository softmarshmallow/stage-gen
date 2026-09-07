"""The storefront run view: this recipe's derived read-only document."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from gnode import RunView, build_run_view
from stage_gen.recipes.storefront.storefront_graph import StorefrontGraph
from stage_gen.recipes.storefront.storefront_types import storefront_type_index

if TYPE_CHECKING:
    from pathlib import Path

#: The engine's shared version, not this recipe's. A private number here is how a
#: recipe's runs vanish from the run viewer while the document shape has not moved.
STOREFRONT_VIEW_SCHEMA_VERSION: Literal[3] = 3
STOREFRONT_VIEW_KIND: Literal["storefront-execution-view-v1"] = "storefront-execution-view-v1"


class StorefrontView(RunView):
    """One storefront run, read back as the graph it was."""

    recipe: str
    storefront_id: str
    surface_count: int


def build_storefront_view(run_dir: Path) -> StorefrontView:
    return build_run_view(
        run_dir,
        graph_type=StorefrontGraph,
        view_type=StorefrontView,
        types=storefront_type_index(),
    )


__all__ = [
    "STOREFRONT_VIEW_KIND",
    "STOREFRONT_VIEW_SCHEMA_VERSION",
    "StorefrontView",
    "build_storefront_view",
]
