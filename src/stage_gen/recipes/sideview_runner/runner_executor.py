"""Thin composition boundary for sideview-runner execution.

Resolve the package's runner member, plan the graph, and dispatch it -
single-shot, the room and scene precedent: the runner's fan-out is small
enough that its cheapest gate is admission, not a checkpoint cut.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

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
from stage_gen.orchestration.runtime import (
    create_music_service,
    create_openai_image_service,
    create_sound_effect_service,
    create_speech_service,
    create_structured_service,
    create_tool_loop_service,
)
from stage_gen.recipes.sideview_runner.prepared_runner import SideviewRunnerNodeHandler
from stage_gen.recipes.sideview_runner.runner_graph import (
    SideviewRunnerGraph,
    build_runner_execution_graph,
    runner_graph_profile,
)
from stage_gen.recipes.sideview_runner.runner_request import (
    ResolvedRunnerPackage,
    resolve_runner_package,
)

if TYPE_CHECKING:
    from pathlib import Path

    from stage_gen.config import StageGenConfig


@dataclass(frozen=True, slots=True)
class SideviewRunnerPlan:
    resolved: ResolvedRunnerPackage
    graph: SideviewRunnerGraph
    projection: Projection


@dataclass(frozen=True, slots=True)
class SideviewRunnerRun:
    plan: SideviewRunnerPlan
    summary: RunSummary
    run_dir: Path


class SideviewRunnerExecutor:
    """Resolve, plan, and dispatch one package's runner member."""

    def __init__(self, config: StageGenConfig) -> None:
        self._config = config

    def plan(self, input_path: Path) -> SideviewRunnerPlan:
        resolved = resolve_runner_package(input_path)
        graph = build_runner_execution_graph(resolved, profile=runner_graph_profile(self._config))
        return SideviewRunnerPlan(
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
    ) -> SideviewRunnerRun:
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
        return SideviewRunnerRun(plan=plan, summary=summary, run_dir=run_dir)

    async def run(
        self,
        input_path: Path,
        *,
        run_dir: Path,
        cache_dir: Path,
        invocation_id: str,
    ) -> SideviewRunnerRun:
        """Execute the whole runner member, including the terminal manifest."""

        assert_safe_path_segment(invocation_id, "invocation_id")
        if self._config.openai_api_key is None:
            raise ValueError("sideview-runner execution requires OPENAI_API_KEY")
        if self._config.open_router_api_key is None:
            raise ValueError("sideview-runner execution requires OPENROUTER_API_KEY")
        plan = await self._open_run(input_path, run_dir=run_dir)
        needs_sound_effects = bool(plan.resolved.runner.audio.generated_effects())
        needs_speech = bool(plan.resolved.runner.audio.spoken_lines())
        if (needs_sound_effects or needs_speech) and self._config.elevenlabs_api_key is None:
            raise ValueError(
                "sideview-runner execution requires ELEVENLABS_API_KEY for generated clips "
                "and spoken lines"
            )
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
        tool_loop_service = create_tool_loop_service(
            api_key=self._config.open_router_api_key,
            model=self._config.text_model,
            base_url=self._config.open_router_base_url or "https://openrouter.ai/api/v1",
        )
        music_service = (
            create_music_service(
                api_key=self._config.open_router_api_key,
                model=self._config.music_model,
                base_url=self._config.open_router_base_url or "https://openrouter.ai/api/v1",
            )
            if plan.resolved.runner.soundtrack is not None
            else None
        )
        sound_effect_service = (
            create_sound_effect_service(
                api_key=self._config.elevenlabs_api_key,
                model=self._config.sound_effect_model,
                base_url=self._config.elevenlabs_base_url or "https://api.elevenlabs.io/v1",
            )
            if needs_sound_effects and self._config.elevenlabs_api_key is not None
            else None
        )
        speech_service = (
            create_speech_service(
                api_key=self._config.elevenlabs_api_key,
                model=self._config.speech_model,
                base_url=self._config.elevenlabs_base_url or "https://api.elevenlabs.io/v1",
            )
            if needs_speech and self._config.elevenlabs_api_key is not None
            else None
        )
        scheduler = Scheduler(
            plan.graph.resources,
            node_timeout_seconds=max(self._config.stage_timeout_s, 900),
            secrets=self._secrets(),
        )
        handler = SideviewRunnerNodeHandler(
            plan.graph,
            plan.resolved,
            run_dir=run_dir,
            cache_dir=cache_dir,
            image_service=image_service,
            structured_service=structured_service,
            tool_loop_service=tool_loop_service,
            music_service=music_service,
            sound_effect_service=sound_effect_service,
            speech_service=speech_service,
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
            await tool_loop_service.aclose()
            if music_service is not None:
                await music_service.aclose()
            if sound_effect_service is not None:
                await sound_effect_service.aclose()
            if speech_service is not None:
                await speech_service.aclose()
        write_run_summary(run_dir / "execution-summary.json", summary)
        return SideviewRunnerRun(plan=plan, summary=summary, run_dir=run_dir)

    async def _open_run(self, input_path: Path, *, run_dir: Path) -> SideviewRunnerPlan:
        plan = self.plan(input_path)
        await asyncio.to_thread(run_dir.mkdir, parents=True, exist_ok=False)
        write_graph(run_dir / "execution-plan.json", plan.graph)
        atomic_write_json(
            run_dir / "execution-projection.json",
            plan.projection.model_dump(mode="json"),
        )
        atomic_write_json(run_dir / "runner-identity.json", plan.resolved.identity())
        return plan

    def _secrets(self) -> tuple[str, ...]:
        return tuple(
            value
            for value in (self._config.openai_api_key, self._config.open_router_api_key)
            if value is not None
        )


__all__ = ["SideviewRunnerExecutor", "SideviewRunnerPlan", "SideviewRunnerRun"]
