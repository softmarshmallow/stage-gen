"""Thin prepared-package composition boundary for scrolling-preview execution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from stage_gen.config import StageGenConfig
from stage_gen.orchestration.execution_graph import (
    DependencyExecutor,
    ExecutionGraph,
    ExecutionProjection,
    ExecutionSummary,
    JsonlTraceSink,
    project_execution,
    write_execution_plan,
    write_execution_summary,
)
from stage_gen.orchestration.fake_execution import FakeNodeHandler
from stage_gen.orchestration.game_package import ResolvedGamePackage, resolve_game_package
from stage_gen.recipes.scrolling_preview.package_graph import (
    build_package_execution_graph,
    package_graph_profile,
)
from stage_gen.reliability import assert_safe_path_segment, atomic_write_json


@dataclass(frozen=True, slots=True)
class PreparedPackagePlan:
    package: ResolvedGamePackage
    graph: ExecutionGraph
    projection: ExecutionProjection


@dataclass(frozen=True, slots=True)
class PreparedPackageDryRun:
    plan: PreparedPackagePlan
    summary: ExecutionSummary
    run_dir: Path


class PreparedPackageExecutor:
    """Resolve, plan, and dispatch; leaf generation remains component-owned."""

    def __init__(self, config: StageGenConfig) -> None:
        self._config = config

    def plan(self, input_path: Path) -> PreparedPackagePlan:
        package = resolve_game_package(input_path)
        graph = build_package_execution_graph(
            package,
            profile=package_graph_profile(self._config),
        )
        return PreparedPackagePlan(
            package=package,
            graph=graph,
            projection=project_execution(graph),
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
    ) -> PreparedPackageDryRun:
        assert_safe_path_segment(invocation_id, "invocation_id")
        plan = self.plan(input_path)
        await asyncio.to_thread(run_dir.mkdir, parents=True, exist_ok=False)
        write_execution_plan(run_dir / "execution-plan.json", plan.graph)
        atomic_write_json(
            run_dir / "execution-projection.json",
            plan.projection.model_dump(mode="json"),
        )
        atomic_write_json(run_dir / "package.json", plan.package.identity())
        trace = JsonlTraceSink(run_dir / "execution-trace.jsonl")
        executor = DependencyExecutor(
            plan.graph.resources,
            node_timeout_seconds=self._config.stage_timeout_s,
            secrets=tuple(
                value
                for value in (
                    self._config.openai_api_key,
                    self._config.open_router_api_key,
                    self._config.fal_key,
                )
                if value is not None
            ),
        )
        try:
            summary = await executor.run(
                plan.graph,
                FakeNodeHandler(
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
        write_execution_summary(run_dir / "execution-summary.json", summary)
        return PreparedPackageDryRun(plan=plan, summary=summary, run_dir=run_dir)


__all__ = [
    "PreparedPackageDryRun",
    "PreparedPackageExecutor",
    "PreparedPackagePlan",
]
