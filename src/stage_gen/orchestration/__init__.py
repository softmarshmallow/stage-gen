"""Headless generation preparation and execution."""

from stage_gen.orchestration.runtime import (
    DefaultHeadlessRuntime,
    create_background_removal_service,
    create_headless_runtime,
    create_image_service,
    create_music_service,
    create_openai_image_service,
    create_structured_service,
)

__all__ = [
    "DefaultHeadlessRuntime",
    "create_background_removal_service",
    "create_headless_runtime",
    "create_image_service",
    "create_music_service",
    "create_openai_image_service",
    "create_structured_service",
]
