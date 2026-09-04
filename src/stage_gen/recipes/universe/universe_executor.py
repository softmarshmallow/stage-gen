"""Thin composition boundary for universe execution.

Resolve the package, plan a phase, and dispatch it. Nothing here generates.

The two phases take different inputs and end at different terminals, so they
get separate entry points rather than one with a mode flag: the semantic phase
needs only the authored package, while the gallery phase also needs the
admission that says how many branches there are.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
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
    validate_plan_types,
    write_graph,
    write_run_summary,
)
from stage_gen.config import CapabilityName, StageGenConfig, assert_capabilities
from stage_gen.orchestration.runtime import create_structured_service
from stage_gen.recipes.universe import gallery_page
from stage_gen.recipes.universe.manifest import finalize_gallery
from stage_gen.recipes.universe.prepared_universe import UniverseNodeHandler
from stage_gen.recipes.universe.universe_graph import (
    GALLERY_IMAGE_ROUTE,
    INPUT_POSTER_PROXY_REF,
    INPUT_UNIVERSE_REF,
    SAMPLE_LEDGER_REF,
    UniverseGraph,
    build_universe_gallery_graph,
    build_universe_semantic_graph,
    universe_graph_profile,
)
from stage_gen.recipes.universe.universe_request import (
    AdmittedUniverse,
    ResolvedUniverseSource,
    load_admitted_universe,
    read_poster_proxy,
    read_universe_document,
    resolve_sample_ledger,
    resolve_universe_source,
)
from stage_gen.recipes.universe.universe_types import universe_type_index

if TYPE_CHECKING:
    from collections.abc import Sequence

    from stage_gen.recipes.universe.models import SampleLedger


@dataclass(frozen=True, slots=True)
class UniversePlan:
    resolved: ResolvedUniverseSource
    graph: UniverseGraph
    projection: Projection
    admitted: AdmittedUniverse | None = None
    samples: SampleLedger | None = None


@dataclass(frozen=True, slots=True)
class UniverseRun:
    plan: UniversePlan
    summary: RunSummary
    run_dir: Path
    manifest: dict[str, object] | None = None


class UniverseExecutor:
    """Resolve, plan, and dispatch one phase of one authored universe."""

    def __init__(self, config: StageGenConfig) -> None:
        self._config = config

    # -- planning -------------------------------------------------------------

    def resolve(self, input_path: Path) -> ResolvedUniverseSource:
        return resolve_universe_source(read_universe_document(input_path), root=input_path)

    def plan_semantic(self, input_path: Path) -> UniversePlan:
        resolved = self.resolve(input_path)
        graph = build_universe_semantic_graph(
            resolved, profile=universe_graph_profile(self._config, images=False)
        )
        validate_plan_types(graph.nodes, universe_type_index())
        return UniversePlan(resolved=resolved, graph=graph, projection=project_schedule(graph))

    def plan_gallery(
        self,
        input_path: Path,
        *,
        semantic_run: Path,
        rerolls: Sequence[str] = (),
        sample_ledger: Path | None = None,
    ) -> UniversePlan:
        resolved = self.resolve(input_path)
        admitted = load_admitted_universe(semantic_run, poster_sha256=resolved.poster_sha256)
        samples = resolve_sample_ledger(
            universe_id=admitted.universe_id,
            entity_ids=admitted.entity_ids(),
            prior=sample_ledger,
            rerolls=rerolls,
        )
        graph = build_universe_gallery_graph(
            resolved,
            admitted,
            samples=samples,
            profile=universe_graph_profile(self._config, images=True),
        )
        validate_plan_types(graph.nodes, universe_type_index())
        return UniversePlan(
            resolved=resolved,
            graph=graph,
            projection=project_schedule(graph),
            admitted=admitted,
            samples=samples,
        )

    # -- semantic phase -------------------------------------------------------

    async def dry_run_semantic(
        self,
        input_path: Path,
        *,
        run_dir: Path,
        cache_dir: Path,
        invocation_id: str,
        failure_node_id: str | None = None,
        time_scale: float = 0.0001,
    ) -> UniverseRun:
        assert_safe_path_segment(invocation_id, "invocation_id")
        plan = self.plan_semantic(input_path)
        await self._open_run(plan, run_dir=run_dir)
        summary = await self._dispatch_dry(
            plan,
            run_dir=run_dir,
            cache_dir=cache_dir,
            invocation_id=invocation_id,
            failure_node_id=failure_node_id,
            time_scale=time_scale,
        )
        return UniverseRun(plan=plan, summary=summary, run_dir=run_dir)

    async def run_semantic(
        self,
        input_path: Path,
        *,
        run_dir: Path,
        cache_dir: Path,
        invocation_id: str,
    ) -> UniverseRun:
        assert_safe_path_segment(invocation_id, "invocation_id")
        assert_capabilities(self._config, (CapabilityName.STRUCTURED_GENERATION,))
        plan = self.plan_semantic(input_path)
        await self._open_run(plan, run_dir=run_dir)
        structured = create_structured_service(
            api_key=self._config.open_router_api_key or "",
            model=self._config.text_model,
            base_url=self._config.open_router_base_url or "https://openrouter.ai/api/v1",
        )
        handler = UniverseNodeHandler(
            plan.graph,
            plan.resolved,
            run_dir=run_dir,
            cache_dir=cache_dir,
            structured_service=structured,
        )
        trace = JsonlTraceSink(run_dir / "execution-trace.jsonl")
        try:
            summary = await self._scheduler(plan).run(
                plan.graph, handler, invocation_id=invocation_id, trace_sink=trace
            )
        finally:
            trace.close()
            await structured.aclose()
        write_run_summary(run_dir / "execution-summary.json", summary)
        return UniverseRun(plan=plan, summary=summary, run_dir=run_dir)

    # -- gallery phase --------------------------------------------------------

    async def dry_run_gallery(
        self,
        input_path: Path,
        *,
        semantic_run: Path,
        run_dir: Path,
        cache_dir: Path,
        invocation_id: str,
        rerolls: Sequence[str] = (),
        sample_ledger: Path | None = None,
        failure_node_id: str | None = None,
        time_scale: float = 0.00001,
    ) -> UniverseRun:
        assert_safe_path_segment(invocation_id, "invocation_id")
        plan = self.plan_gallery(
            input_path,
            semantic_run=semantic_run,
            rerolls=rerolls,
            sample_ledger=sample_ledger,
        )
        await self._open_run(plan, run_dir=run_dir, semantic_run=semantic_run)
        summary = await self._dispatch_dry(
            plan,
            run_dir=run_dir,
            cache_dir=cache_dir,
            invocation_id=invocation_id,
            failure_node_id=failure_node_id,
            time_scale=time_scale,
        )
        manifest = self._close_gallery(plan, summary, run_dir=run_dir, render=False)
        return UniverseRun(plan=plan, summary=summary, run_dir=run_dir, manifest=manifest)

    async def run_gallery(
        self,
        input_path: Path,
        *,
        semantic_run: Path,
        run_dir: Path,
        cache_dir: Path,
        invocation_id: str,
        rerolls: Sequence[str] = (),
        sample_ledger: Path | None = None,
    ) -> UniverseRun:
        assert_safe_path_segment(invocation_id, "invocation_id")
        # The image capability follows the bound route rather than being assumed:
        # the opaque route needs an OpenRouter key, the native-alpha route OpenAI.
        assert_capabilities(
            self._config,
            (CapabilityName.STRUCTURED_GENERATION, GALLERY_IMAGE_ROUTE.capability),
        )
        plan = self.plan_gallery(
            input_path,
            semantic_run=semantic_run,
            rerolls=rerolls,
            sample_ledger=sample_ledger,
        )
        await self._open_run(plan, run_dir=run_dir, semantic_run=semantic_run)
        structured = create_structured_service(
            api_key=self._config.open_router_api_key or "",
            model=self._config.text_model,
            base_url=self._config.open_router_base_url or "https://openrouter.ai/api/v1",
        )
        images = GALLERY_IMAGE_ROUTE.service(self._config)
        handler = UniverseNodeHandler(
            plan.graph,
            plan.resolved,
            run_dir=run_dir,
            cache_dir=cache_dir,
            structured_service=structured,
            image_service=images,
            admitted=plan.admitted,
        )
        trace = JsonlTraceSink(run_dir / "execution-trace.jsonl")
        try:
            summary = await self._scheduler(plan).run(
                plan.graph, handler, invocation_id=invocation_id, trace_sink=trace
            )
        finally:
            trace.close()
            await images.aclose()
            await structured.aclose()
        write_run_summary(run_dir / "execution-summary.json", summary)
        manifest = self._close_gallery(plan, summary, run_dir=run_dir, render=True)
        return UniverseRun(plan=plan, summary=summary, run_dir=run_dir, manifest=manifest)

    # -- shared ---------------------------------------------------------------

    async def _open_run(
        self, plan: UniversePlan, *, run_dir: Path, semantic_run: Path | None = None
    ) -> None:
        await asyncio.to_thread(run_dir.mkdir, parents=True, exist_ok=False)
        write_graph(run_dir / "execution-plan.json", plan.graph)
        atomic_write_json(
            run_dir / "execution-projection.json", plan.projection.model_dump(mode="json")
        )
        atomic_write_json(run_dir / "universe-identity.json", plan.resolved.identity())
        if plan.admitted is None or semantic_run is None:
            return
        # A gallery run carries its own copy of what it was planned from, so the
        # run is a closed set of bytes and the consumer page never has to follow
        # a path out of the run directory to render.
        inputs = run_dir / "inputs"
        inputs.mkdir(parents=True, exist_ok=True)
        (run_dir / INPUT_UNIVERSE_REF).write_bytes(plan.admitted.universe_bytes)
        (run_dir / INPUT_POSTER_PROXY_REF).write_bytes(read_poster_proxy(semantic_run))
        if plan.samples is not None:
            atomic_write_json(run_dir / SAMPLE_LEDGER_REF, plan.samples.model_dump(mode="json"))

    def _scheduler(self, plan: UniversePlan) -> Scheduler:
        return Scheduler(
            plan.graph.resources,
            node_timeout_seconds=max(self._config.stage_timeout_s, 2_400),
            secrets=self._secrets(),
        )

    async def _dispatch_dry(
        self,
        plan: UniversePlan,
        *,
        run_dir: Path,
        cache_dir: Path,
        invocation_id: str,
        failure_node_id: str | None,
        time_scale: float,
    ) -> RunSummary:
        trace = JsonlTraceSink(run_dir / "execution-trace.jsonl")
        try:
            summary = await self._scheduler(plan).run(
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
        return summary

    def _close_gallery(
        self, plan: UniversePlan, summary: RunSummary, *, run_dir: Path, render: bool
    ) -> dict[str, object] | None:
        if plan.admitted is None:
            return None
        manifest = finalize_gallery(run_dir, plan.graph, summary, plan.admitted)
        if render:
            gallery_page.render(run_dir)
        return manifest

    def _secrets(self) -> tuple[str, ...]:
        return self._config.secret_values()


__all__ = ["UniverseExecutor", "UniversePlan", "UniverseRun"]
