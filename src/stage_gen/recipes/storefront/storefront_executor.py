"""Thin composition boundary for storefront execution.

Resolve the package, plan the graph, and dispatch it. Nothing here generates:
leaf work stays inside the node handler, every provider operation inside the
component that owns its retry.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from gnode import NodeType, assert_safe_path_segment
from stage_gen.config import CapabilityName, StageGenConfig
from stage_gen.recipes.executor import RecipeExecutor, RecipePlan, RecipeRun
from stage_gen.recipes.storefront.models import DrawLedger
from stage_gen.recipes.storefront.prepared_storefront import StorefrontNodeHandler
from stage_gen.recipes.storefront.storefront_graph import (
    StorefrontGraph,
    build_storefront_graph,
    storefront_graph_profile,
)
from stage_gen.recipes.storefront.storefront_request import (
    DRAW_LEDGER_REF,
    ResolvedStorefront,
    ledger_bytes,
    read_storefront_document,
    resolve_storefront,
)
from stage_gen.recipes.storefront.storefront_types import storefront_type_index

StorefrontPlan = RecipePlan[ResolvedStorefront, StorefrontGraph]
StorefrontRun = RecipeRun[StorefrontPlan]


class StorefrontExecutor(RecipeExecutor[ResolvedStorefront, StorefrontGraph]):
    """Resolve, plan, and dispatch one authored storefront package."""

    IDENTITY_DOCUMENT = "storefront-identity.json"

    def __init__(self, config: StageGenConfig, *, draws: DrawLedger | None = None) -> None:
        """``draws`` carries a prior run's ledger forward, with any reroll applied."""

        super().__init__(config)
        self._draws = draws

    def _resolve(self, input_path: Path) -> ResolvedStorefront:
        return resolve_storefront(
            read_storefront_document(input_path), root=input_path, draws=self._draws
        )

    def _build(self, resolved: ResolvedStorefront) -> StorefrontGraph:
        return build_storefront_graph(
            resolved,
            config=self._config,
            profile=storefront_graph_profile(self._config),
        )

    def _type_index(self) -> Mapping[str, NodeType]:
        return storefront_type_index()

    async def open_run(self, plan: StorefrontPlan, *, run_dir: Path) -> None:
        """Open the run, and write the ledger it was planned against beside the plan.

        Here rather than in ``run`` so a rehearsal carries it too: the reroll flow
        starts from a prior run's ``draw-ledger.json``, and a dry run that wrote
        none would leave the cheapest way to try the flow with nothing to point at.
        Reconstructing a ledger by hand is how a redraw silently becomes a cache hit.
        """

        await super().open_run(plan, run_dir=run_dir)
        (run_dir / DRAW_LEDGER_REF).write_bytes(ledger_bytes(plan.resolved.draws))

    async def run(
        self,
        input_path: Path,
        *,
        run_dir: Path,
        cache_dir: Path,
        invocation_id: str,
    ) -> StorefrontRun:
        """Execute the whole storefront, including the terminal package."""

        assert_safe_path_segment(invocation_id, "invocation_id")
        self.require(CapabilityName.STRUCTURED_GENERATION)
        plan = self.plan(input_path)
        self.require_route_credentials(plan.graph)
        await self.open_run(plan, run_dir=run_dir)
        async with self.services() as services:
            handler = StorefrontNodeHandler(
                plan.graph,
                plan.resolved,
                run_dir=run_dir,
                cache_dir=cache_dir,
                image_service=services.image(),
                structured_service=services.structured(),
            )
            summary = await self.dispatch(
                plan, handler, run_dir=run_dir, invocation_id=invocation_id
            )
        return RecipeRun(plan=plan, summary=summary, run_dir=run_dir)


__all__ = ["StorefrontExecutor", "StorefrontPlan", "StorefrontRun"]
