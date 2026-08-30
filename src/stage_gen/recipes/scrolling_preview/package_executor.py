"""Thin prepared-package composition boundary for scrolling-preview execution."""

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
from stage_gen.orchestration.execution_graph import ExecutionGraph
from stage_gen.orchestration.game_package import ResolvedGamePackage, resolve_game_package
from stage_gen.orchestration.runtime import (
    create_music_service,
    create_openai_image_service,
    create_structured_service,
)
from stage_gen.recipes.scrolling_preview.package_graph import (
    build_package_execution_graph,
    package_graph_profile,
)
from stage_gen.recipes.scrolling_preview.prepared_content import (
    PreparedContentNodeHandler,
    content_target_node_ids,
)
from stage_gen.recipes.scrolling_preview.prepared_manifest import (
    PreparedManifestResult,
    assemble_prepared_runtime,
)
from stage_gen.recipes.scrolling_preview.prepared_world import (
    PreparedWorldNodeHandler,
    world_target_node_ids,
)


@dataclass(frozen=True, slots=True)
class PreparedPackagePlan:
    package: ResolvedGamePackage
    graph: ExecutionGraph
    projection: Projection


@dataclass(frozen=True, slots=True)
class PreparedPackageDryRun:
    plan: PreparedPackagePlan
    summary: RunSummary
    run_dir: Path


@dataclass(frozen=True, slots=True)
class PreparedPackageWorldRun:
    plan: PreparedPackagePlan
    summary: RunSummary
    run_dir: Path


@dataclass(frozen=True, slots=True)
class PreparedPackageContentRun:
    plan: PreparedPackagePlan
    summary: RunSummary
    run_dir: Path


@dataclass(frozen=True, slots=True)
class PreparedPackageIntegrationRun:
    plan: PreparedPackagePlan
    result: PreparedManifestResult
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
            projection=project_schedule(graph),
        )

    def run_integration(
        self,
        input_path: Path,
        *,
        run_dir: Path,
        artifact_roots: tuple[Path, ...],
        replace_output: bool = False,
    ) -> PreparedPackageIntegrationRun:
        """Assemble the provider-free terminal runtime closure from accepted artifacts."""

        plan = self.plan(input_path)
        result = assemble_prepared_runtime(
            plan.package,
            artifact_roots=artifact_roots,
            output_dir=run_dir,
            replace_output=replace_output,
        )
        return PreparedPackageIntegrationRun(plan=plan, result=result, run_dir=run_dir)

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
        write_graph(run_dir / "execution-plan.json", plan.graph)
        atomic_write_json(
            run_dir / "execution-projection.json",
            plan.projection.model_dump(mode="json"),
        )
        atomic_write_json(run_dir / "package.json", plan.package.identity())
        trace = JsonlTraceSink(run_dir / "execution-trace.jsonl")
        executor = Scheduler(
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
        return PreparedPackageDryRun(plan=plan, summary=summary, run_dir=run_dir)

    async def run_world(
        self,
        input_path: Path,
        *,
        run_dir: Path,
        cache_dir: Path,
        invocation_id: str,
    ) -> PreparedPackageWorldRun:
        """Execute exactly the map review targets and their dependency closure."""

        assert_safe_path_segment(invocation_id, "invocation_id")
        if self._config.openai_api_key is None:
            raise ValueError("world execution requires OPENAI_API_KEY")
        if self._config.open_router_api_key is None:
            raise ValueError("world execution requires OPENROUTER_API_KEY")
        plan = self.plan(input_path)
        await asyncio.to_thread(run_dir.mkdir, parents=True, exist_ok=False)
        write_graph(run_dir / "execution-plan.json", plan.graph)
        atomic_write_json(
            run_dir / "execution-projection.json",
            plan.projection.model_dump(mode="json"),
        )
        atomic_write_json(run_dir / "package.json", plan.package.identity())
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
        executor = Scheduler(
            plan.graph.resources,
            node_timeout_seconds=self._config.stage_timeout_s,
            secrets=(self._config.openai_api_key, self._config.open_router_api_key),
        )
        handler = PreparedWorldNodeHandler(
            plan.graph,
            plan.package,
            run_dir=run_dir,
            cache_dir=cache_dir,
            image_service=image_service,
            structured_service=structured_service,
            terrain_template_path=Path(__file__).parents[2]
            / "resources/fixtures/image_gen_templates/terrain_atlas_12x4_template.png",
            terrain_topology_reference_path=Path(__file__).parents[2]
            / ("resources/fixtures/image_gen_templates/terrain_atlas_godot_topology_reference.png"),
        )
        try:
            summary = await executor.run(
                plan.graph,
                handler,
                invocation_id=invocation_id,
                trace_sink=trace,
                target_node_ids=world_target_node_ids(plan.package),
            )
        finally:
            trace.close()
            await image_service.aclose()
            await structured_service.aclose()
        write_run_summary(run_dir / "execution-summary.json", summary)
        return PreparedPackageWorldRun(plan=plan, summary=summary, run_dir=run_dir)

    async def run_content(
        self,
        input_path: Path,
        *,
        run_dir: Path,
        cache_dir: Path,
        invocation_id: str,
    ) -> PreparedPackageContentRun:
        """Execute exactly the content review/validation targets and dependency closure."""

        assert_safe_path_segment(invocation_id, "invocation_id")
        if self._config.openai_api_key is None:
            raise ValueError("content execution requires OPENAI_API_KEY")
        if self._config.open_router_api_key is None:
            raise ValueError("content execution requires OPENROUTER_API_KEY")
        plan = self.plan(input_path)
        await asyncio.to_thread(run_dir.mkdir, parents=True, exist_ok=False)
        write_graph(run_dir / "execution-plan.json", plan.graph)
        atomic_write_json(
            run_dir / "execution-projection.json",
            plan.projection.model_dump(mode="json"),
        )
        atomic_write_json(run_dir / "package.json", plan.package.identity())
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
        music_service = create_music_service(
            api_key=self._config.open_router_api_key,
            model=self._config.music_model,
            base_url=self._config.open_router_base_url or "https://openrouter.ai/api/v1",
        )
        executor = Scheduler(
            plan.graph.resources,
            node_timeout_seconds=max(self._config.stage_timeout_s, 900),
            secrets=(self._config.openai_api_key, self._config.open_router_api_key),
        )
        handler = PreparedContentNodeHandler(
            plan.graph,
            plan.package,
            run_dir=run_dir,
            cache_dir=cache_dir,
            image_service=image_service,
            structured_service=structured_service,
            music_service=music_service,
        )
        try:
            summary = await executor.run(
                plan.graph,
                handler,
                invocation_id=invocation_id,
                trace_sink=trace,
                target_node_ids=content_target_node_ids(plan.package),
            )
        finally:
            trace.close()
            await image_service.aclose()
            await structured_service.aclose()
            await music_service.aclose()
        write_run_summary(run_dir / "execution-summary.json", summary)
        return PreparedPackageContentRun(plan=plan, summary=summary, run_dir=run_dir)


__all__ = [
    "PreparedPackageDryRun",
    "PreparedPackageContentRun",
    "PreparedPackageIntegrationRun",
    "PreparedPackageExecutor",
    "PreparedPackagePlan",
    "PreparedPackageWorldRun",
]
