"""The composition boundary every recipe runs through.

Resolve, plan, open a run directory, dispatch a handler under a scheduler, close what
was opened, write the summary. Five executors wrote that bootstrap five times - the run
directory inlined three times per recipe, the secrets rebuilt in each, the provider
services constructed with their default base URLs at fifteen call sites - and that is
how one credential once escaped redaction in two of them. The base owns the bootstrap;
a recipe owns what it resolves, how it builds its graph, and which handler runs it.
Nothing here generates.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Protocol

from gnode import (
    BackgroundRemovalService,
    DryRunNodeHandler,
    Graph,
    ImageGenerationService,
    JsonlTraceSink,
    MusicGenerationService,
    NodeHandler,
    NodeType,
    Projection,
    RunSummary,
    Scheduler,
    SoundEffectGenerationService,
    SpeechGenerationService,
    StructuredGenerationService,
    ToolLoopService,
    assert_safe_path_segment,
    atomic_write_json,
    project_schedule,
    validate_plan_types,
    write_graph,
    write_run_summary,
)
from stage_gen.config import CapabilityName, StageGenConfig, assert_capabilities
from stage_gen.orchestration.runtime import (
    create_background_removal_service,
    create_music_service,
    create_openai_image_service,
    create_sound_effect_service,
    create_speech_service,
    create_structured_service,
    create_tool_loop_service,
)

OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"


class Identified(Protocol):
    """What a resolved input must offer: the identity document its run directory records."""

    def identity(self) -> Mapping[str, object]: ...


class _Closable(Protocol):
    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RecipePlan[R: Identified, G: Graph]:
    """One resolved input, the graph it expands to, and the schedule the graph projects."""

    resolved: R
    graph: G
    projection: Projection


@dataclass(frozen=True, slots=True)
class RecipeRun[P]:
    plan: P
    summary: RunSummary
    run_dir: Path


class RunServices:
    """Provider services opened for one run and closed together after it.

    Each accessor composes the configured backend behind the shared retry owner. A
    service a recipe composes itself - the universe's route-bound image service - is
    ``adopt``ed so it closes with the rest. Credentials are the config's; a missing one
    is refused before a run opens, by ``RecipeExecutor.require``.
    """

    def __init__(self, config: StageGenConfig) -> None:
        self._config = config
        self._opened: list[_Closable] = []

    def adopt[S: _Closable](self, service: S) -> S:
        self._opened.append(service)
        return service

    def image(self) -> ImageGenerationService:
        """The direct OpenAI image route: the only one that returns native alpha."""

        config = self._config
        return self.adopt(
            create_openai_image_service(
                api_key=config.openai_api_key or "",
                model=config.openai_image_model,
                base_url=config.openai_base_url or OPENAI_BASE_URL,
                images_per_minute=config.openai_image_ipm,
            )
        )

    def structured(self) -> StructuredGenerationService[object]:
        config = self._config
        return self.adopt(
            create_structured_service(
                api_key=config.open_router_api_key or "",
                model=config.text_model,
                base_url=config.open_router_base_url or OPENROUTER_BASE_URL,
            )
        )

    def tool_loop(self) -> ToolLoopService[dict[str, object]]:
        config = self._config
        return self.adopt(
            create_tool_loop_service(
                api_key=config.open_router_api_key or "",
                model=config.text_model,
                base_url=config.open_router_base_url or OPENROUTER_BASE_URL,
            )
        )

    def music(self) -> MusicGenerationService:
        config = self._config
        return self.adopt(
            create_music_service(
                api_key=config.open_router_api_key or "",
                model=config.music_model,
                base_url=config.open_router_base_url or OPENROUTER_BASE_URL,
            )
        )

    def background_removal(self) -> BackgroundRemovalService:
        config = self._config
        return self.adopt(
            create_background_removal_service(
                api_key=config.fal_key or "",
                model=config.background_removal_model,
            )
        )

    def sound_effect(self) -> SoundEffectGenerationService:
        config = self._config
        return self.adopt(
            create_sound_effect_service(
                api_key=config.elevenlabs_api_key or "",
                model=config.sound_effect_model,
                base_url=config.elevenlabs_base_url or ELEVENLABS_BASE_URL,
            )
        )

    def speech(self) -> SpeechGenerationService:
        config = self._config
        return self.adopt(
            create_speech_service(
                api_key=config.elevenlabs_api_key or "",
                model=config.speech_model,
                base_url=config.elevenlabs_base_url or ELEVENLABS_BASE_URL,
            )
        )

    async def aclose(self) -> None:
        opened, self._opened = self._opened, []
        for service in reversed(opened):
            await service.aclose()

    async def __aenter__(self) -> RunServices:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()


class RecipeExecutor[R: Identified, G: Graph](ABC):
    """Resolve, plan, and dispatch one authored input; leaf work stays in the handler."""

    #: The identity document written beside the plan; its name is part of the run layout.
    IDENTITY_DOCUMENT: ClassVar[str] = "identity.json"
    #: A live run's node timeout never drops below this, whatever the stage timeout says:
    #: an image node's six attempts at two minutes each are longer than a short stage.
    NODE_TIMEOUT_FLOOR_S: ClassVar[float] = 900.0

    def __init__(self, config: StageGenConfig) -> None:
        self._config = config

    # ------------------------------------------------------------ the recipe's

    @abstractmethod
    def _resolve(self, input_path: Path) -> R:
        """Read and admit the authored input at ``input_path``."""

    @abstractmethod
    def _build(self, resolved: R) -> G:
        """Expand one resolved input into its sealed graph."""

    @abstractmethod
    def _type_index(self) -> Mapping[str, NodeType]:
        """Every node type the recipe's plan may contain."""

    # --------------------------------------------------------------- planning

    def plan(self, input_path: Path) -> RecipePlan[R, G]:
        """Resolve one authored input into its exact plan, offline."""

        return self.plan_resolved(self._resolve(input_path))

    def plan_resolved(self, resolved: R) -> RecipePlan[R, G]:
        return self.plan_graph(resolved, self._build(resolved))

    def plan_graph(self, resolved: R, graph: G) -> RecipePlan[R, G]:
        """Admit a graph built some other way - a second phase, say - as a plan."""

        validate_plan_types(graph.nodes, self._type_index())
        return RecipePlan(resolved=resolved, graph=graph, projection=project_schedule(graph))

    # ------------------------------------------------------------------- runs

    def require(self, *capabilities: CapabilityName) -> None:
        """Refuse before opening a run when a needed credential is absent."""

        assert_capabilities(self._config, capabilities)

    def services(self) -> RunServices:
        return RunServices(self._config)

    async def open_run(self, plan: RecipePlan[R, G], *, run_dir: Path) -> None:
        """Create the run directory and write the plan, the projection and the identity."""

        await asyncio.to_thread(run_dir.mkdir, parents=True, exist_ok=False)
        write_graph(run_dir / "execution-plan.json", plan.graph)
        atomic_write_json(
            run_dir / "execution-projection.json", plan.projection.model_dump(mode="json")
        )
        atomic_write_json(run_dir / self.IDENTITY_DOCUMENT, dict(plan.resolved.identity()))

    async def dispatch(
        self,
        plan: RecipePlan[R, G],
        handler: NodeHandler,
        *,
        run_dir: Path,
        invocation_id: str,
        targets: Sequence[str] | None = None,
        floor_timeout: bool = True,
    ) -> RunSummary:
        """Run ``handler`` over the plan under the trace, and write the summary."""

        timeout = self._config.stage_timeout_s
        if floor_timeout:
            timeout = max(timeout, self.NODE_TIMEOUT_FLOOR_S)
        scheduler = Scheduler(
            plan.graph.resources,
            node_timeout_seconds=timeout,
            secrets=self._config.secret_values(),
        )
        trace = JsonlTraceSink(run_dir / "execution-trace.jsonl")
        try:
            summary = await scheduler.run(
                plan.graph,
                handler,
                invocation_id=invocation_id,
                trace_sink=trace,
                target_node_ids=tuple(targets) if targets is not None else None,
            )
        finally:
            trace.close()
        write_run_summary(run_dir / "execution-summary.json", summary)
        return summary

    async def dry_dispatch(
        self,
        plan: RecipePlan[R, G],
        *,
        run_dir: Path,
        cache_dir: Path,
        invocation_id: str,
        failure_node_id: str | None = None,
        time_scale: float = 0.0001,
    ) -> RunSummary:
        """Run the engine's dry-run handler over an opened run: no provider, no spend."""

        return await self.dispatch(
            plan,
            DryRunNodeHandler(
                plan.graph,
                run_dir=run_dir,
                cache_dir=cache_dir,
                failure_node_id=failure_node_id,
                time_scale=time_scale,
            ),
            run_dir=run_dir,
            invocation_id=invocation_id,
            floor_timeout=False,
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
    ) -> RecipeRun[RecipePlan[R, G]]:
        assert_safe_path_segment(invocation_id, "invocation_id")
        plan = self.plan(input_path)
        await self.open_run(plan, run_dir=run_dir)
        summary = await self.dry_dispatch(
            plan,
            run_dir=run_dir,
            cache_dir=cache_dir,
            invocation_id=invocation_id,
            failure_node_id=failure_node_id,
            time_scale=time_scale,
        )
        return RecipeRun(plan=plan, summary=summary, run_dir=run_dir)


__all__ = [
    "ELEVENLABS_BASE_URL",
    "OPENAI_BASE_URL",
    "OPENROUTER_BASE_URL",
    "Identified",
    "RecipeExecutor",
    "RecipePlan",
    "RecipeRun",
    "RunServices",
]
