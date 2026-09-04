"""Thin composition boundary for point-and-click room execution.

Resolve the room, plan the graph, and dispatch it. Nothing here generates:
leaf work stays inside the node handler, every provider operation inside a
component.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from gnode import NodeType, assert_safe_path_segment
from stage_gen.config import CapabilityName
from stage_gen.recipes.executor import RecipeExecutor, RecipePlan, RecipeRun
from stage_gen.recipes.pointclick_room.prepared_room import PointClickRoomNodeHandler
from stage_gen.recipes.pointclick_room.room_graph import (
    PointClickRoomGraph,
    build_pointclick_room_graph,
    room_graph_profile,
)
from stage_gen.recipes.pointclick_room.room_request import (
    ResolvedPointClickRoom,
    read_room_document,
    resolve_pointclick_room,
)
from stage_gen.recipes.pointclick_room.room_types import pointclick_type_index

PointClickRoomPlan = RecipePlan[ResolvedPointClickRoom, PointClickRoomGraph]
PointClickRoomRun = RecipeRun[PointClickRoomPlan]


class PointClickRoomExecutor(RecipeExecutor[ResolvedPointClickRoom, PointClickRoomGraph]):
    """Resolve, plan, and dispatch one authored room."""

    IDENTITY_DOCUMENT = "room-identity.json"

    def _resolve(self, input_path: Path) -> ResolvedPointClickRoom:
        return resolve_pointclick_room(read_room_document(input_path), root=input_path)

    def _build(self, resolved: ResolvedPointClickRoom) -> PointClickRoomGraph:
        return build_pointclick_room_graph(resolved, profile=room_graph_profile(self._config))

    def _type_index(self) -> Mapping[str, NodeType]:
        return pointclick_type_index()

    async def run(
        self,
        input_path: Path,
        *,
        run_dir: Path,
        cache_dir: Path,
        invocation_id: str,
    ) -> PointClickRoomRun:
        """Execute the whole room, including the terminal bundle."""

        assert_safe_path_segment(invocation_id, "invocation_id")
        self.require(CapabilityName.NATIVE_IMAGE_GENERATION, CapabilityName.STRUCTURED_GENERATION)
        plan = self.plan(input_path)
        await self.open_run(plan, run_dir=run_dir)
        async with self.services() as services:
            handler = PointClickRoomNodeHandler(
                plan.graph,
                plan.resolved,
                run_dir=run_dir,
                cache_dir=cache_dir,
                image_service=services.image(),
                structured_service=services.structured(),
                capability_timeout_s=self._config.capability_timeout_s,
            )
            summary = await self.dispatch(
                plan, handler, run_dir=run_dir, invocation_id=invocation_id
            )
        return RecipeRun(plan=plan, summary=summary, run_dir=run_dir)


__all__ = ["PointClickRoomExecutor", "PointClickRoomPlan", "PointClickRoomRun"]
