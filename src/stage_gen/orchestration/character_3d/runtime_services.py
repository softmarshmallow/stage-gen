"""Application composition for provider-backed character execution."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from gnode import BindingTable, ModelRef
from gnode.providers.openrouter import OpenRouterImageBackend, OpenRouterToolLoopBackend
from stage_gen.components.character_3d.agent_backend import (
    AgentBudget,
    MeteredToolLoopBackend,
    ModelPricing,
    create_metered_backend,
)
from stage_gen.orchestration.character_3d.bindings import application_bindings
from stage_gen.orchestration.character_3d.provider_execution import ProviderRigExecutor
from stage_gen.orchestration.character_3d.upstream import ProviderRun, UpstreamExecutor
from stage_gen.provider_env import load_provider_dotenv


class EpisodeBackendFactory(Protocol):
    def __call__(
        self, run: ProviderRun, episode_id: str, *, limits: AgentBudget, pricing: ModelPricing
    ) -> MeteredToolLoopBackend: ...


@dataclass
class RuntimeServices:
    episode_backend_factory: EpisodeBackendFactory
    upstream_executor_factory: Callable[[ProviderRun], UpstreamExecutor]
    rig_executor_factory: Callable[[ProviderRun], ProviderRigExecutor]
    upstream_bindings: Callable[[], BindingTable]
    credential_provider: Callable[[str], str]


def create_services(*, live: bool = False, dotenv: Path | None = None) -> RuntimeServices:
    keys: dict[str, str] | None = None

    def credential(name: str) -> str:
        nonlocal keys
        if not live:
            raise ValueError("Credentials are unavailable in offline execution")
        if name not in {"OPENROUTER_API_KEY", "TRIPO_API_KEY"}:
            raise ValueError("Provider credential is outside the declared character routes")
        if keys is None:
            keys = (
                {str(key): value for key, value in load_provider_dotenv(dotenv).items()}
                if dotenv
                else {}
            )
        value = os.environ.get(name) or keys.get(name)
        if not value:
            raise ValueError("Required provider credential is unavailable: " + name)
        return value

    def bindings() -> BindingTable:
        return application_bindings()

    def backend(
        run: ProviderRun, episode_id: str, *, limits: AgentBudget, pricing: ModelPricing
    ) -> MeteredToolLoopBackend:
        route = ModelRef.parse(run.experiment["agent_route"])
        if route.provider != "openrouter":
            raise ValueError("This application composition admits OpenRouter agent calls only")
        return create_metered_backend(
            backend_factory=OpenRouterToolLoopBackend,
            api_key=credential("OPENROUTER_API_KEY"),
            model=route.model,
            ledger_dir=run.run_root / "ledger",
            limits=limits,
            pricing=pricing,
            episode_id=episode_id,
        )

    return RuntimeServices(
        episode_backend_factory=backend,
        upstream_executor_factory=lambda run: UpstreamExecutor(
            run, bindings=bindings(), image_backend_factory=OpenRouterImageBackend
        ),
        rig_executor_factory=lambda run: ProviderRigExecutor(run, bindings=bindings()),
        upstream_bindings=bindings,
        credential_provider=credential,
    )
