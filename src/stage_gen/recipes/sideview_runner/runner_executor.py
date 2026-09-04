"""Thin composition boundary for sideview-runner execution.

Resolve the package's runner member, plan the graph, and dispatch it -
single-shot, the room and scene precedent: the runner's fan-out is small
enough that its cheapest gate is admission, not a checkpoint cut.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from gnode import NodeType, assert_safe_path_segment
from stage_gen.config import CapabilityName
from stage_gen.recipes.executor import RecipeExecutor, RecipePlan, RecipeRun
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
from stage_gen.recipes.sideview_runner.runner_types import runner_type_index

SideviewRunnerPlan = RecipePlan[ResolvedRunnerPackage, SideviewRunnerGraph]
SideviewRunnerRun = RecipeRun[SideviewRunnerPlan]


class SideviewRunnerExecutor(RecipeExecutor[ResolvedRunnerPackage, SideviewRunnerGraph]):
    """Resolve, plan, and dispatch one package's runner member."""

    IDENTITY_DOCUMENT = "runner-identity.json"

    def _resolve(self, input_path: Path) -> ResolvedRunnerPackage:
        return resolve_runner_package(input_path)

    def _build(self, resolved: ResolvedRunnerPackage) -> SideviewRunnerGraph:
        return build_runner_execution_graph(resolved, profile=runner_graph_profile(self._config))

    def _type_index(self) -> Mapping[str, NodeType]:
        return runner_type_index()

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
        self.require(CapabilityName.NATIVE_IMAGE_GENERATION, CapabilityName.STRUCTURED_GENERATION)
        plan = self.plan(input_path)
        audio = plan.resolved.runner.audio
        needs_sound_effects = bool(audio.bought_generated_effects())
        needs_speech = bool(audio.bought_spoken_lines())
        if needs_sound_effects:
            self.require(CapabilityName.SOUND_EFFECT_GENERATION)
        if needs_speech:
            self.require(CapabilityName.SPEECH_GENERATION)
        await self.open_run(plan, run_dir=run_dir)
        async with self.services() as services:
            handler = SideviewRunnerNodeHandler(
                plan.graph,
                plan.resolved,
                run_dir=run_dir,
                cache_dir=cache_dir,
                image_service=services.image(),
                structured_service=services.structured(),
                tool_loop_service=services.tool_loop(),
                music_service=(
                    services.music() if plan.resolved.runner.soundtrack is not None else None
                ),
                sound_effect_service=services.sound_effect() if needs_sound_effects else None,
                speech_service=services.speech() if needs_speech else None,
                capability_timeout_s=self._config.capability_timeout_s,
            )
            summary = await self.dispatch(
                plan, handler, run_dir=run_dir, invocation_id=invocation_id
            )
        return RecipeRun(plan=plan, summary=summary, run_dir=run_dir)


__all__ = ["SideviewRunnerExecutor", "SideviewRunnerPlan", "SideviewRunnerRun"]
