"""Headless generation preparation and execution."""

from stage_gen.orchestration.runner import run_recipe
from stage_gen.orchestration.runtime import (
    DefaultHeadlessRuntime,
    create_background_removal_service,
    create_default_runtime,
    create_headless_runtime,
    create_image_service,
    create_music_service,
    create_structured_service,
)
from stage_gen.orchestration.service import (
    GenerateRequest,
    PreparedGenerateRequest,
    generate,
    generate_prepared,
    prepare_generate_request,
)

__all__ = [
    "DefaultHeadlessRuntime",
    "GenerateRequest",
    "PreparedGenerateRequest",
    "create_background_removal_service",
    "create_default_runtime",
    "create_headless_runtime",
    "create_image_service",
    "create_music_service",
    "create_structured_service",
    "generate",
    "generate_prepared",
    "prepare_generate_request",
    "run_recipe",
]
