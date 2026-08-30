"""The point-and-click room run view: this recipe's derived read-only document."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from gnode import RunView, build_run_view
from stage_gen.recipes.pointclick_room.room_graph import PointClickRoomGraph
from stage_gen.recipes.pointclick_room.room_types import pointclick_type_index

if TYPE_CHECKING:
    from pathlib import Path

POINTCLICK_VIEW_SCHEMA_VERSION: Literal[3] = 3
POINTCLICK_VIEW_KIND: Literal["pointclick-room-execution-view-v1"] = (
    "pointclick-room-execution-view-v1"
)


class PointClickRoomView(RunView):
    """One room run, read back as the graph it was."""

    recipe: str
    room_id: str


def build_pointclick_room_view(run_dir: Path) -> PointClickRoomView:
    return build_run_view(
        run_dir,
        graph_type=PointClickRoomGraph,
        view_type=PointClickRoomView,
        types=pointclick_type_index(),
    )


__all__ = [
    "POINTCLICK_VIEW_KIND",
    "POINTCLICK_VIEW_SCHEMA_VERSION",
    "PointClickRoomView",
    "build_pointclick_room_view",
]
