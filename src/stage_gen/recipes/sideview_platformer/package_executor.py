"""Thin prepared-package composition boundary for side-view platformer execution."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
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
    validate_plan_types,
    write_graph,
    write_run_summary,
)
from stage_gen.config import StageGenConfig
from stage_gen.orchestration.game_package import ResolvedGamePackage, resolve_game_package
from stage_gen.orchestration.runtime import (
    create_music_service,
    create_openai_image_service,
    create_structured_service,
)
from stage_gen.recipes.sideview_platformer.execution_graph import ExecutionGraph
from stage_gen.recipes.sideview_platformer.package_graph import (
    build_package_execution_graph,
    package_graph_profile,
)
from stage_gen.recipes.sideview_platformer.package_types import platformer_type_index
from stage_gen.recipes.sideview_platformer.prepared_content import (
    PreparedContentNodeHandler,
    content_target_node_ids,
)
from stage_gen.recipes.sideview_platformer.prepared_integration import (
    PreparedIntegrationNodeHandler,
)
from stage_gen.recipes.sideview_platformer.prepared_manifest import PreparedManifestResult
from stage_gen.recipes.sideview_platformer.prepared_world import (
    PreparedWorldNodeHandler,
    world_target_node_ids,
)
from stage_gen.resources import (
    terrain_atlas_template_path,
    terrain_atlas_topology_reference_path,
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
    summary: RunSummary
    #: The published run, or ``None`` when the closure could not be restored and the
    #: terminal node never ran; ``summary`` names the node that stopped it.
    result: PreparedManifestResult | None
    run_dir: Path
    output_dir: Path
    #: Paid nodes the cache lacked and an ``--artifact-root`` supplied. Non-empty means the
    #: cache cannot republish this run alone; ``package plan --cache-dir`` prices the gap.
    adopted_node_ids: tuple[str, ...] = ()


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
        validate_plan_types(graph.nodes, platformer_type_index())
        return PreparedPackagePlan(
            package=package,
            graph=graph,
            projection=project_schedule(graph),
        )

    async def run_integration(
        self,
        input_path: Path,
        *,
        run_dir: Path,
        output_dir: Path,
        cache_dir: Path,
        invocation_id: str,
        artifact_roots: tuple[Path, ...] = (),
        replace_output: bool = False,
    ) -> PreparedPackageIntegrationRun:
        """Run the manifest node's closure from the cache and publish the runtime.

        Provider-free by construction: every handler holds a backend that refuses, so a
        paid artifact the cache does not hold stops the run rather than spending. The
        graph, projection, trace and summary land in ``run_dir``; the published closure
        - manifest and exactly the bytes it binds - lands in ``output_dir``.
        """

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
            node_timeout_seconds=max(self._config.stage_timeout_s, 900),
            secrets=self._config.secret_values(),
        )
        handler = PreparedIntegrationNodeHandler(
            plan.graph,
            plan.package,
            run_dir=run_dir,
            cache_dir=cache_dir,
            output_dir=output_dir,
            terrain_template_path=terrain_atlas_template_path(),
            terrain_topology_reference_path=terrain_atlas_topology_reference_path(),
            artifact_roots=artifact_roots,
            replace_output=replace_output,
        )
        try:
            summary = await executor.run(
                plan.graph,
                handler,
                invocation_id=invocation_id,
                trace_sink=trace,
                target_node_ids=(plan.graph.terminal_node_id,),
            )
        finally:
            trace.close()
        write_run_summary(run_dir / "execution-summary.json", summary)
        return PreparedPackageIntegrationRun(
            plan=plan,
            summary=summary,
            result=handler.result,
            run_dir=run_dir,
            output_dir=output_dir,
            adopted_node_ids=tuple(handler.adopted_node_ids),
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
            secrets=self._config.secret_values(),
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
        targets: Callable[[ExecutionGraph], tuple[str, ...]] = world_target_node_ids,
    ) -> PreparedPackageWorldRun:
        """Execute exactly the named world targets and their dependency closure."""

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
            secrets=self._config.secret_values(),
        )
        handler = PreparedWorldNodeHandler(
            plan.graph,
            plan.package,
            run_dir=run_dir,
            cache_dir=cache_dir,
            image_service=image_service,
            structured_service=structured_service,
            terrain_template_path=terrain_atlas_template_path(),
            terrain_topology_reference_path=terrain_atlas_topology_reference_path(),
        )
        try:
            summary = await executor.run(
                plan.graph,
                handler,
                invocation_id=invocation_id,
                trace_sink=trace,
                target_node_ids=targets(plan.graph),
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
        targets: Callable[[ExecutionGraph], tuple[str, ...]] = content_target_node_ids,
    ) -> PreparedPackageContentRun:
        """Execute exactly the named content targets and their dependency closure.

        `targets` is how a caller asks for a narrower slice than the whole content
        checkpoint -- the soundtrack alone, say -- without a second copy of this method's
        service wiring. It selects targets from the plan rather than taking node ids,
        because the ids are derived from the package and only the plan knows them.
        """

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
            secrets=self._config.secret_values(),
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
                target_node_ids=targets(plan.graph),
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
