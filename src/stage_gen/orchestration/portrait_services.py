"""Concrete, opt-in provider composition for the public portrait-motion recipe."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from gnode import (
    AbortError,
    Graph,
    ImageGenerationService,
    ImageModelV1,
    ProviderStructuredOutput,
    RetryPolicy,
    RouteContractV1,
    StructuredGenerationRequest,
    StructuredGenerationService,
    atomic_write_json,
)
from gnode.providers.fal import FalImageBackend
from gnode.providers.openai import OPENAI_BASE_URL, OpenAIImageBackend
from gnode.providers.openrouter import (
    OPENROUTER_BASE_URL,
    OpenRouterImageBackend,
    OpenRouterStructuredBackend,
)
from stage_gen.components.portrait_motion.face_location import COMPONENT as LOCATOR_COMPONENT
from stage_gen.components.portrait_motion.face_location import MAX_ATTEMPTS, _cost
from stage_gen.components.portrait_motion.storage import COMPONENT, RunStore
from stage_gen.config import ConfigError, StageGenConfig
from stage_gen.model_routes import FAL_SUNBURST_EDIT_ENDPOINT, FAL_SUNBURST_TEXT_TO_IMAGE_ENDPOINT
from stage_gen.orchestration.image_routing import RoutedImageGenerationService
from stage_gen.provider_env import load_provider_dotenv
from stage_gen.recipes.portrait_motion.face_location import (
    ATTEMPT_RESERVATION_USD,
    BUDGET_USD,
    TIMEOUT_SECONDS,
    _budget_ledger,
)
from stage_gen.recipes.portrait_motion.pipeline import (
    TOOL,
    RuntimeProfile,
    _Budget,
    _BudgetedImage,
    _image_config,
    request_policy,
)
from stage_gen.recipes.portrait_motion.services import PortraitServices


def _image_backend(route: RouteContractV1, config: StageGenConfig) -> ImageModelV1:
    """Compose only the one-attempt adapter named by the sealed route."""

    if route.model.provider == "openai":
        assert config.openai_api_key is not None
        return OpenAIImageBackend(
            api_key=config.openai_api_key,
            model=route.model.model,
            supports_native_alpha="transparent_background" in route.features,
            base_url=config.openai_base_url or OPENAI_BASE_URL,
            images_per_minute=config.openai_image_ipm,
        )
    if route.model.provider == "fal":
        assert config.fal_key is not None
        return FalImageBackend(
            api_key=config.fal_key,
            model=route.model.model,
            supports_native_alpha="transparent_background" in route.features,
            base_url=config.fal_base_url or "https://fal.run",
            text_to_image_endpoint=FAL_SUNBURST_TEXT_TO_IMAGE_ENDPOINT,
            edit_endpoint=FAL_SUNBURST_EDIT_ENDPOINT,
        )
    if route.model.provider == "openrouter":
        assert config.open_router_api_key is not None
        return OpenRouterImageBackend(
            api_key=config.open_router_api_key,
            model=route.model.model,
            base_url=config.open_router_base_url or OPENROUTER_BASE_URL,
            images_per_minute=config.openrouter_image_ipm,
        )
    raise ValueError(f"Unsupported portrait image provider: {route.model.provider}")


def _budgeted_image_service_factory(
    budget: _Budget,
    retry: RetryPolicy,
) -> Callable[[RouteContractV1, StageGenConfig], ImageGenerationService]:
    def create(route: RouteContractV1, config: StageGenConfig) -> ImageGenerationService:
        return ImageGenerationService(
            _BudgetedImage(budget=budget, backend=_image_backend(route, config)),
            component=COMPONENT,
            tool=TOOL,
            retry_policy=retry,
        )

    return create


def _require_live_credentials(graph: Graph, config: StageGenConfig) -> None:
    credential_by_provider = {
        "openai": ("OPENAI_API_KEY", config.openai_api_key),
        "fal": ("FAL_KEY", config.fal_key),
        "openrouter": ("OPENROUTER_API_KEY", config.open_router_api_key),
    }
    # Structured judging is still an explicit OpenRouter binding. Image keys are
    # derived only from the exact catalog routes carried by this prepared graph.
    providers = dict.fromkeys(
        ("openrouter", *(snapshot.provider for snapshot in graph.resolved_routes))
    )
    missing: list[str] = []
    for provider in providers:
        credential = credential_by_provider.get(provider)
        if credential is None:
            raise ValueError(f"No portrait credential mapping for provider {provider}")
        name, value = credential
        if value is None or not value.strip():
            missing.append(name)
    if missing:
        raise ConfigError(missing)


class _BudgetedStructured(OpenRouterStructuredBackend):
    def __init__(self, *, budget: _Budget, api_key: str, model: str) -> None:
        super().__init__(api_key=api_key, model=model, request_policy=request_policy())
        self.budget = budget

    async def generate_once(
        self, request: StructuredGenerationRequest[object]
    ) -> ProviderStructuredOutput:
        index = self.budget.reserve("structured_generation")
        result = await super().generate_once(request)
        self.budget.settle(index, result.response_metadata.usage)
        return result


class _BudgetedLocatorBackend(OpenRouterStructuredBackend):
    """Reserve before each transport attempt; the structured service owns retries."""

    def __init__(self, store: RunStore, *, api_key: str, model: str) -> None:
        super().__init__(api_key=api_key, model=model, request_policy=request_policy())
        self.store = store

    async def generate_once(
        self, request: StructuredGenerationRequest[object]
    ) -> ProviderStructuredOutput:
        path = self.store.path("budget.json")
        ledger = _budget_ledger(self.store)
        if (
            len(ledger["attempts"]) >= MAX_ATTEMPTS
            or sum(item["charged_usd"] for item in ledger["attempts"]) + ATTEMPT_RESERVATION_USD
            > BUDGET_USD + 1e-9
        ):
            raise AbortError("Face locator budget exhausted before dispatch", provider_operations=0)
        entry = {
            "status": "reserved",
            "charged_usd": ATTEMPT_RESERVATION_USD,
            "reported_cost_usd": None,
        }
        ledger["attempts"].append(entry)
        atomic_write_json(path, ledger)
        generated = await super().generate_once(request)
        cost = _cost((generated.response_metadata.usage or {}).get("cost"))
        entry.update(
            status="returned",
            reported_cost_usd=cost,
            charged_usd=ATTEMPT_RESERVATION_USD if cost is None else cost,
        )
        atomic_write_json(path, ledger)
        return generated


class ConfiguredPortraitServices:
    """Host opt-in and credentials are resolved only when explicitly requested."""

    @staticmethod
    def _credentials(dotenv: Path | None) -> dict[str, str | None]:
        if os.environ.get("STAGE_GEN_RUN_LIVE") != "1":
            raise ValueError("Live execution also requires STAGE_GEN_RUN_LIVE=1")
        loaded = load_provider_dotenv(dotenv) if dotenv is not None else {}
        return {
            "openai_api_key": os.environ.get("OPENAI_API_KEY") or loaded.get("OPENAI_API_KEY"),
            "open_router_api_key": os.environ.get("OPENROUTER_API_KEY")
            or loaded.get("OPENROUTER_API_KEY"),
            "fal_key": os.environ.get("FAL_KEY") or loaded.get("FAL_KEY"),
        }

    def admit(self, plan: dict[str, Any], graph: Graph, dotenv: Path | None) -> None:
        config = _image_config(plan, credentials=self._credentials(dotenv))
        _require_live_credentials(graph, config)

    def motion(
        self,
        store: RunStore,
        plan: dict[str, Any],
        graph: Graph,
        dotenv: Path | None,
    ) -> PortraitServices:
        config = _image_config(plan, credentials=self._credentials(dotenv))
        _require_live_credentials(graph, config)
        profile = RuntimeProfile.model_validate(plan["profile"])
        budget = _Budget(store, profile)
        retry = RetryPolicy(attempt_timeout_s=profile.timeout_seconds)
        image = RoutedImageGenerationService(
            config, service_factory=_budgeted_image_service_factory(budget, retry)
        )
        assert config.open_router_api_key is not None
        structured: StructuredGenerationService[dict[str, Any]] = StructuredGenerationService(
            _BudgetedStructured(
                budget=budget, api_key=config.open_router_api_key, model=profile.structured_model
            ),
            component=COMPONENT,
            tool=TOOL,
            retry_policy=retry,
        )
        return PortraitServices(
            image,
            structured,
            lambda: len(budget._read()["attempts"]) if store.path("budget.json").exists() else 0,
        )

    def locator(
        self,
        store: RunStore,
        plan: dict[str, Any],
        dotenv: Path | None,
    ) -> StructuredGenerationService[dict[str, Any]]:
        key = self._credentials(dotenv)["open_router_api_key"]
        if not key:
            raise ValueError("OPENROUTER_API_KEY is required")
        return StructuredGenerationService(
            _BudgetedLocatorBackend(store, api_key=key, model=plan["model"]),
            component=LOCATOR_COMPONENT,
            tool=TOOL,
            retry_policy=RetryPolicy(attempt_timeout_s=TIMEOUT_SECONDS),
        )
