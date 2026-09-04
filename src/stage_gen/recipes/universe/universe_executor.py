"""Thin composition boundary for universe execution.

Resolve the package, plan a phase, and dispatch it. Nothing here generates.

The two phases take different inputs and end at different terminals, so they
get separate entry points rather than one with a mode flag: the semantic phase
needs only the authored package, while the gallery phase also needs the
admission that says how many branches there are.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from gnode import NodeType, RunSummary, assert_safe_path_segment, atomic_write_json
from stage_gen.config import CapabilityName
from stage_gen.recipes.executor import RecipeExecutor, RecipePlan, RecipeRun
from stage_gen.recipes.universe import gallery_page
from stage_gen.recipes.universe.manifest import finalize_gallery
from stage_gen.recipes.universe.models import SampleLedger
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


@dataclass(frozen=True, slots=True)
class UniversePlan(RecipePlan[ResolvedUniverseSource, UniverseGraph]):
    #: The gallery phase's extra inputs; a semantic plan carries neither.
    admitted: AdmittedUniverse | None = None
    samples: SampleLedger | None = None
    #: The semantic run a gallery plan was admitted from; its poster proxy is copied in.
    semantic_run: Path | None = None


@dataclass(frozen=True, slots=True)
class UniverseRun(RecipeRun[UniversePlan]):
    manifest: dict[str, object] | None = None


class UniverseExecutor(RecipeExecutor[ResolvedUniverseSource, UniverseGraph]):
    """Resolve, plan, and dispatch one phase of one authored universe."""

    IDENTITY_DOCUMENT = "universe-identity.json"
    #: A gallery draw is a native-size frame on a slow route; forty minutes, not fifteen.
    NODE_TIMEOUT_FLOOR_S = 2_400.0

    # -- planning -------------------------------------------------------------

    def _resolve(self, input_path: Path) -> ResolvedUniverseSource:
        return resolve_universe_source(read_universe_document(input_path), root=input_path)

    def _build(self, resolved: ResolvedUniverseSource) -> UniverseGraph:
        return build_universe_semantic_graph(
            resolved, profile=universe_graph_profile(self._config, images=False)
        )

    def _type_index(self) -> Mapping[str, NodeType]:
        return universe_type_index()

    def resolve(self, input_path: Path) -> ResolvedUniverseSource:
        return self._resolve(input_path)

    def plan_semantic(self, input_path: Path) -> UniversePlan:
        plan = self.plan(input_path)
        return UniversePlan(resolved=plan.resolved, graph=plan.graph, projection=plan.projection)

    def plan_gallery(
        self,
        input_path: Path,
        *,
        semantic_run: Path,
        rerolls: Sequence[str] = (),
        sample_ledger: Path | None = None,
    ) -> UniversePlan:
        resolved = self._resolve(input_path)
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
        plan = self.plan_graph(resolved, graph)
        return UniversePlan(
            resolved=plan.resolved,
            graph=plan.graph,
            projection=plan.projection,
            admitted=admitted,
            samples=samples,
            semantic_run=semantic_run,
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
        await self.open_run(plan, run_dir=run_dir)
        summary = await self.dry_dispatch(
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
        self.require(CapabilityName.STRUCTURED_GENERATION)
        plan = self.plan_semantic(input_path)
        await self.open_run(plan, run_dir=run_dir)
        async with self.services() as services:
            handler = UniverseNodeHandler(
                plan.graph,
                plan.resolved,
                run_dir=run_dir,
                cache_dir=cache_dir,
                structured_service=services.structured(),
            )
            summary = await self.dispatch(
                plan, handler, run_dir=run_dir, invocation_id=invocation_id
            )
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
        await self.open_run(plan, run_dir=run_dir)
        summary = await self.dry_dispatch(
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
        self.require(CapabilityName.STRUCTURED_GENERATION, GALLERY_IMAGE_ROUTE.capability)
        plan = self.plan_gallery(
            input_path,
            semantic_run=semantic_run,
            rerolls=rerolls,
            sample_ledger=sample_ledger,
        )
        await self.open_run(plan, run_dir=run_dir)
        async with self.services() as services:
            handler = UniverseNodeHandler(
                plan.graph,
                plan.resolved,
                run_dir=run_dir,
                cache_dir=cache_dir,
                structured_service=services.structured(),
                image_service=services.adopt(GALLERY_IMAGE_ROUTE.service(self._config)),
                admitted=plan.admitted,
            )
            summary = await self.dispatch(
                plan, handler, run_dir=run_dir, invocation_id=invocation_id
            )
        manifest = self._close_gallery(plan, summary, run_dir=run_dir, render=True)
        return UniverseRun(plan=plan, summary=summary, run_dir=run_dir, manifest=manifest)

    # -- shared ---------------------------------------------------------------

    async def open_run(
        self, plan: RecipePlan[ResolvedUniverseSource, UniverseGraph], *, run_dir: Path
    ) -> None:
        await super().open_run(plan, run_dir=run_dir)
        if not isinstance(plan, UniversePlan) or plan.admitted is None or plan.semantic_run is None:
            return
        # A gallery run carries its own copy of what it was planned from, so the
        # run is a closed set of bytes and the consumer page never has to follow
        # a path out of the run directory to render.
        inputs = run_dir / "inputs"
        inputs.mkdir(parents=True, exist_ok=True)
        (run_dir / INPUT_UNIVERSE_REF).write_bytes(plan.admitted.universe_bytes)
        (run_dir / INPUT_POSTER_PROXY_REF).write_bytes(read_poster_proxy(plan.semantic_run))
        if plan.samples is not None:
            atomic_write_json(run_dir / SAMPLE_LEDGER_REF, plan.samples.model_dump(mode="json"))

    def _close_gallery(
        self, plan: UniversePlan, summary: RunSummary, *, run_dir: Path, render: bool
    ) -> dict[str, object] | None:
        if plan.admitted is None:
            return None
        manifest = finalize_gallery(run_dir, plan.graph, summary, plan.admitted)
        if render:
            gallery_page.render(run_dir)
        return manifest


__all__ = ["UniverseExecutor", "UniversePlan", "UniverseRun"]
