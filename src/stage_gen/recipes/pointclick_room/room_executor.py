"""Thin composition boundary for point-and-click room execution.

Resolve the room, plan the graph, and dispatch it. Nothing here generates:
leaf work stays inside the node handler, every provider operation inside a
component.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from gnode import (
    DryRunNodeHandler,
    JsonlTraceSink,
    Projection,
    RunSummary,
    Scheduler,
    assert_safe_path_segment,
    atomic_write_json,
    project_schedule,
    write_graph,
    write_run_summary,
)
from stage_gen.config import StageGenConfig
from stage_gen.orchestration.runtime import (
    create_openai_image_service,
    create_structured_service,
)
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


@dataclass(frozen=True, slots=True)
class PointClickRoomPlan:
    resolved: ResolvedPointClickRoom
    graph: PointClickRoomGraph
    projection: Projection


@dataclass(frozen=True, slots=True)
class PointClickRoomRun:
    plan: PointClickRoomPlan
    summary: RunSummary
    run_dir: Path


class PointClickRoomExecutor:
    """Resolve, plan, and dispatch one authored room."""

    def __init__(self, config: StageGenConfig) -> None:
        self._config = config

    def plan(self, input_path: Path) -> PointClickRoomPlan:
        resolved = resolve_pointclick_room(read_room_document(input_path))
        graph = build_pointclick_room_graph(resolved, profile=room_graph_profile(self._config))
        return PointClickRoomPlan(
            resolved=resolved, graph=graph, projection=project_schedule(graph)
        )

    async def dry_run(
        self,
        input_path: Path,
        *,
        run_dir: Path,
        cache_dir: Path,
        invocation_id: str,
        failure_node_id: str | None = None,
        time_scale: float = 0.0001,
    ) -> PointClickRoomRun:
        assert_safe_path_segment(invocation_id, "invocation_id")
        plan = await self._open_run(input_path, run_dir=run_dir)
        trace = JsonlTraceSink(run_dir / "execution-trace.jsonl")
        scheduler = Scheduler(
            plan.graph.resources,
            node_timeout_seconds=self._config.stage_timeout_s,
            secrets=self._secrets(),
        )
        try:
            summary = await scheduler.run(
                plan.graph,
                DryRunNodeHandler(
                    plan.graph,
                    run_dir=run_dir,
                    cache_dir=cache_dir,
                    failure_node_id=failure_node_id,
                    time_scale=time_scale,
                ),
                invocation_id=invocation_id,
                trace_sink=trace,
            )
        finally:
            trace.close()
        write_run_summary(run_dir / "execution-summary.json", summary)
        return PointClickRoomRun(plan=plan, summary=summary, run_dir=run_dir)

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
        if self._config.openai_api_key is None:
            raise ValueError("pointclick-room execution requires OPENAI_API_KEY")
        if self._config.open_router_api_key is None:
            raise ValueError("pointclick-room execution requires OPENROUTER_API_KEY")
        plan = await self._open_run(input_path, run_dir=run_dir)
        trace = JsonlTraceSink(run_dir / "execution-trace.jsonl")
        image_service = create_openai_image_service(
            api_key=self._config.openai_api_key,
            model=self._config.openai_image_model,
            base_url=self._config.openai_base_url or "https://api.openai.com/v1",
            images_per_minute=self._config.openai_image_ipm,
        )
        structured_service = create_structured_service(
            api_key=self._config.open_router_api_key,
            model=self._config.text_model,
            base_url=self._config.open_router_base_url or "https://openrouter.ai/api/v1",
        )
        scheduler = Scheduler(
            plan.graph.resources,
            node_timeout_seconds=max(self._config.stage_timeout_s, 900),
            secrets=self._secrets(),
        )
        handler = PointClickRoomNodeHandler(
            plan.graph,
            plan.resolved,
            run_dir=run_dir,
            cache_dir=cache_dir,
            image_service=image_service,
            structured_service=structured_service,
            capability_timeout_s=self._config.capability_timeout_s,
        )
        try:
            summary = await scheduler.run(
                plan.graph,
                handler,
                invocation_id=invocation_id,
                trace_sink=trace,
            )
        finally:
            trace.close()
            await image_service.aclose()
            await structured_service.aclose()
        write_run_summary(run_dir / "execution-summary.json", summary)
        return PointClickRoomRun(plan=plan, summary=summary, run_dir=run_dir)

    async def _open_run(self, input_path: Path, *, run_dir: Path) -> PointClickRoomPlan:
        plan = self.plan(input_path)
        await asyncio.to_thread(run_dir.mkdir, parents=True, exist_ok=False)
        write_graph(run_dir / "execution-plan.json", plan.graph)
        atomic_write_json(
            run_dir / "execution-projection.json",
            plan.projection.model_dump(mode="json"),
        )
        atomic_write_json(run_dir / "room-identity.json", plan.resolved.identity())
        return plan

    def _secrets(self) -> tuple[str, ...]:
        return tuple(
            value
            for value in (self._config.openai_api_key, self._config.open_router_api_key)
            if value is not None
        )


__all__ = ["PointClickRoomExecutor", "PointClickRoomPlan", "PointClickRoomRun"]
