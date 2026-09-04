"""Thin prepared-package composition boundary for side-view platformer execution.

One plan, four ways to run it: the world and content checkpoints each execute a named
slice of the graph with live providers; integration runs the terminal's closure over
the cache with every provider refusing; the dry run exercises the schedule alone.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from gnode import NodeType, assert_safe_path_segment
from stage_gen.config import CapabilityName
from stage_gen.orchestration.game_package import ResolvedGamePackage, resolve_game_package
from stage_gen.recipes.executor import RecipeExecutor, RecipePlan, RecipeRun
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

PreparedPackagePlan = RecipePlan[ResolvedGamePackage, ExecutionGraph]
PreparedPackageRun = RecipeRun[PreparedPackagePlan]


@dataclass(frozen=True, slots=True)
class PreparedPackageIntegrationRun(RecipeRun[PreparedPackagePlan]):
    #: The published run, or ``None`` when the closure could not be restored and the
    #: terminal node never ran; ``summary`` names the node that stopped it.
    result: PreparedManifestResult | None
    output_dir: Path
    #: Paid nodes the cache lacked and an ``--artifact-root`` supplied. Non-empty means the
    #: cache cannot republish this run alone; ``package plan --cache-dir`` prices the gap.
    adopted_node_ids: tuple[str, ...] = ()


class PreparedPackageExecutor(RecipeExecutor[ResolvedGamePackage, ExecutionGraph]):
    """Resolve, plan, and dispatch; leaf generation remains component-owned."""

    IDENTITY_DOCUMENT = "package.json"

    def _resolve(self, input_path: Path) -> ResolvedGamePackage:
        return resolve_game_package(input_path)

    def _build(self, resolved: ResolvedGamePackage) -> ExecutionGraph:
        return build_package_execution_graph(resolved, profile=package_graph_profile(self._config))

    def _type_index(self) -> Mapping[str, NodeType]:
        return platformer_type_index()

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
        await self.open_run(plan, run_dir=run_dir)
        handler = PreparedIntegrationNodeHandler(
            plan.graph,
            plan.resolved,
            run_dir=run_dir,
            cache_dir=cache_dir,
            output_dir=output_dir,
            terrain_template_path=terrain_atlas_template_path(),
            terrain_topology_reference_path=terrain_atlas_topology_reference_path(),
            artifact_roots=artifact_roots,
            replace_output=replace_output,
        )
        summary = await self.dispatch(
            plan,
            handler,
            run_dir=run_dir,
            invocation_id=invocation_id,
            targets=(plan.graph.terminal_node_id,),
        )
        return PreparedPackageIntegrationRun(
            plan=plan,
            summary=summary,
            run_dir=run_dir,
            result=handler.result,
            output_dir=output_dir,
            adopted_node_ids=tuple(handler.adopted_node_ids),
        )

    async def run_world(
        self,
        input_path: Path,
        *,
        run_dir: Path,
        cache_dir: Path,
        invocation_id: str,
        targets: Callable[[ExecutionGraph], tuple[str, ...]] = world_target_node_ids,
    ) -> PreparedPackageRun:
        """Execute exactly the named world targets and their dependency closure."""

        assert_safe_path_segment(invocation_id, "invocation_id")
        self.require(CapabilityName.NATIVE_IMAGE_GENERATION, CapabilityName.STRUCTURED_GENERATION)
        plan = self.plan(input_path)
        await self.open_run(plan, run_dir=run_dir)
        async with self.services() as services:
            handler = PreparedWorldNodeHandler(
                plan.graph,
                plan.resolved,
                run_dir=run_dir,
                cache_dir=cache_dir,
                image_service=services.image(),
                structured_service=services.structured(),
                terrain_template_path=terrain_atlas_template_path(),
                terrain_topology_reference_path=terrain_atlas_topology_reference_path(),
            )
            summary = await self.dispatch(
                plan,
                handler,
                run_dir=run_dir,
                invocation_id=invocation_id,
                targets=targets(plan.graph),
            )
        return RecipeRun(plan=plan, summary=summary, run_dir=run_dir)

    async def run_content(
        self,
        input_path: Path,
        *,
        run_dir: Path,
        cache_dir: Path,
        invocation_id: str,
        targets: Callable[[ExecutionGraph], tuple[str, ...]] = content_target_node_ids,
    ) -> PreparedPackageRun:
        """Execute exactly the named content targets and their dependency closure.

        `targets` is how a caller asks for a narrower slice than the whole content
        checkpoint -- the soundtrack alone, say -- without a second copy of this method's
        service wiring. It selects targets from the plan rather than taking node ids,
        because the ids are derived from the package and only the plan knows them.
        """

        assert_safe_path_segment(invocation_id, "invocation_id")
        self.require(CapabilityName.NATIVE_IMAGE_GENERATION, CapabilityName.STRUCTURED_GENERATION)
        plan = self.plan(input_path)
        await self.open_run(plan, run_dir=run_dir)
        async with self.services() as services:
            handler = PreparedContentNodeHandler(
                plan.graph,
                plan.resolved,
                run_dir=run_dir,
                cache_dir=cache_dir,
                image_service=services.image(),
                structured_service=services.structured(),
                music_service=services.music(),
            )
            summary = await self.dispatch(
                plan,
                handler,
                run_dir=run_dir,
                invocation_id=invocation_id,
                targets=targets(plan.graph),
            )
        return RecipeRun(plan=plan, summary=summary, run_dir=run_dir)


__all__ = [
    "PreparedPackageExecutor",
    "PreparedPackageIntegrationRun",
    "PreparedPackagePlan",
    "PreparedPackageRun",
]
