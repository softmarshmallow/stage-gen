"""Compatibility entrypoint; workflow ownership moved to the portrait-motion recipe."""

from typing import Any

from stage_gen.recipes.portrait_motion import pipeline as _implementation


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


async def run_pipeline(*args: Any, **kwargs: Any) -> dict[str, Any]:
    if kwargs.get("live") and kwargs.get("service_factory") is None:
        from stage_gen.orchestration.portrait_services import ConfiguredPortraitServices

        kwargs["service_factory"] = ConfiguredPortraitServices()
    return await _implementation.run_pipeline(*args, **kwargs)
