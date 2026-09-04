"""Thin composition boundary for dialogue-scene execution.

Resolve the request, plan the graph, and dispatch it. Nothing here generates: leaf
work stays inside the node handler, and every provider operation inside a component.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from gnode import NodeType, assert_safe_path_segment
from stage_gen.config import CapabilityName
from stage_gen.recipes.dialogue_scene.prepared_scene import DialogueSceneNodeHandler
from stage_gen.recipes.dialogue_scene.scene_graph import (
    DialogueSceneGraph,
    build_dialogue_scene_graph,
    dialogue_graph_profile,
)
from stage_gen.recipes.dialogue_scene.scene_request import (
    ResolvedDialogueScene,
    read_scene_document,
    resolve_dialogue_scene,
)
from stage_gen.recipes.dialogue_scene.scene_types import dialogue_type_index
from stage_gen.recipes.executor import RecipeExecutor, RecipePlan, RecipeRun

DialogueScenePlan = RecipePlan[ResolvedDialogueScene, DialogueSceneGraph]
DialogueSceneRun = RecipeRun[DialogueScenePlan]


class DialogueSceneExecutor(RecipeExecutor[ResolvedDialogueScene, DialogueSceneGraph]):
    """Resolve, plan, and dispatch one authored scene package."""

    IDENTITY_DOCUMENT = "scene.json"

    def _resolve(self, input_path: Path) -> ResolvedDialogueScene:
        root = input_path.absolute()
        return resolve_dialogue_scene(read_scene_document(root), root=root)

    def _build(self, resolved: ResolvedDialogueScene) -> DialogueSceneGraph:
        return build_dialogue_scene_graph(resolved, profile=dialogue_graph_profile(self._config))

    def _type_index(self) -> Mapping[str, NodeType]:
        return dialogue_type_index()

    async def run(
        self,
        package_root: Path,
        *,
        run_dir: Path,
        cache_dir: Path,
        invocation_id: str,
    ) -> DialogueSceneRun:
        """Execute the whole scene, including the terminal bundle."""

        assert_safe_path_segment(invocation_id, "invocation_id")
        self.require(CapabilityName.NATIVE_IMAGE_GENERATION, CapabilityName.STRUCTURED_GENERATION)
        plan = self.plan(package_root)
        await self.open_run(plan, run_dir=run_dir)
        # The AI matte route is bound only when the request asks for it and a key exists;
        # without one the scene falls back to the local matte, as the profile declares.
        wants_ai_matte = (
            plan.resolved.request.transparency_mode == "ai" and self._config.fal_key is not None
        )
        async with self.services() as services:
            handler = DialogueSceneNodeHandler(
                plan.graph,
                plan.resolved,
                run_dir=run_dir,
                cache_dir=cache_dir,
                image_service=services.image(),
                structured_service=services.structured(),
                background_service=services.background_removal() if wants_ai_matte else None,
                music_service=services.music(),
                capability_timeout_s=self._config.capability_timeout_s,
            )
            summary = await self.dispatch(
                plan, handler, run_dir=run_dir, invocation_id=invocation_id
            )
        return RecipeRun(plan=plan, summary=summary, run_dir=run_dir)


__all__ = ["DialogueSceneExecutor", "DialogueScenePlan", "DialogueSceneRun"]
