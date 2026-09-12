"""Injected host services for portrait recipes; no concrete providers are constructed here."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from gnode import Graph, ImageGenerationService, StructuredGenerationService
from stage_gen.components.portrait_motion.storage import RunStore


@dataclass(frozen=True, slots=True)
class PortraitServices:
    image_service: ImageGenerationService
    structured_service: StructuredGenerationService[dict[str, Any]]
    operation_count: Callable[[], int]

    async def aclose(self) -> None:
        try:
            await self.image_service.aclose()
        finally:
            await self.structured_service.aclose()


class PortraitServiceFactory(Protocol):
    """The host supplies explicit live admission and budget-aware service composition."""

    def admit(self, plan: dict[str, Any], graph: Graph, dotenv: Path | None) -> None: ...

    def motion(
        self,
        store: RunStore,
        plan: dict[str, Any],
        graph: Graph,
        dotenv: Path | None,
    ) -> PortraitServices: ...

    def locator(
        self,
        store: RunStore,
        plan: dict[str, Any],
        dotenv: Path | None,
    ) -> StructuredGenerationService[dict[str, Any]]: ...
