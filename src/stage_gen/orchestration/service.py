"""Validated public generation service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from stage_gen.config import (
    CapabilityName,
    StageGenConfig,
    TransparencyMode,
    assert_capabilities,
    parse_transparency_mode,
    transparency_capabilities,
)
from stage_gen.recipes.base import (
    JsonObject,
    Recipe,
    RecipeRuntime,
    RunOptions,
    RunSummary,
    resolve_force_stage_plan,
)
from stage_gen.recipes.registry import get_recipe
from stage_gen.reliability import CancellationToken
from stage_gen.tags import tag_for_transparency_mode


@dataclass(frozen=True, slots=True)
class GenerateRequest:
    input: object
    recipe: str = "scrolling-preview"
    transparency_mode: object | None = None
    force_stages: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PreparedGenerateRequest:
    recipe: Recipe
    input: JsonObject
    tag: str
    required_capabilities: tuple[CapabilityName, ...]
    force_stages: tuple[str, ...] = ()


def prepare_generate_request(
    request: GenerateRequest, config: StageGenConfig
) -> PreparedGenerateRequest:
    recipe = get_recipe(request.recipe)
    input_mode_key = "transparency_mode" if recipe.contract_version == 2 else "transparencyMode"
    nested_mode = request.input.get(input_mode_key) if isinstance(request.input, dict) else None
    parsed_input = recipe.parse_input(request.input)
    parsed_explicit: TransparencyMode | None = (
        None
        if request.transparency_mode is None
        else parse_transparency_mode(request.transparency_mode, "transparencyMode")
    )
    parsed_nested: TransparencyMode | None = (
        None
        if nested_mode is None
        else parse_transparency_mode(nested_mode, f"input.{input_mode_key}")
    )
    if (
        parsed_explicit is not None
        and parsed_nested is not None
        and parsed_explicit != parsed_nested
    ):
        raise ValueError(f"transparencyMode conflicts with input.{input_mode_key}")
    mode = parsed_explicit or parsed_nested or config.transparency_mode
    input_value = {**parsed_input, input_mode_key: mode.value}
    resolve_force_stage_plan(recipe.stages_for(input_value), request.force_stages)
    required = (*recipe.required_capabilities, *transparency_capabilities(mode))
    assert_capabilities(config, required)
    return PreparedGenerateRequest(
        recipe=recipe,
        input=input_value,
        tag=tag_for_transparency_mode(recipe.tag_for(input_value), mode),
        required_capabilities=required,
        force_stages=request.force_stages,
    )


async def generate_prepared(
    prepared: PreparedGenerateRequest,
    config: StageGenConfig,
    *,
    log: Callable[[str], None] | None = None,
    runtime: RecipeRuntime | None = None,
    cancellation: CancellationToken | None = None,
) -> RunSummary:
    from stage_gen.orchestration.runner import run_recipe

    owned_runtime = None
    if runtime is None:
        from stage_gen.orchestration.runtime import create_default_runtime

        owned_runtime = create_default_runtime(config, prepared.recipe.id)
        runtime = owned_runtime

    try:
        return await run_recipe(
            RunOptions(
                recipe=prepared.recipe,
                input=prepared.input,
                tag=prepared.tag,
                config=config,
                log=log,
                runtime=runtime,
                cancellation=cancellation,
                force_stages=prepared.force_stages,
            )
        )
    finally:
        if owned_runtime is not None:
            await owned_runtime.aclose()


async def generate(
    request: GenerateRequest,
    config: StageGenConfig,
    *,
    log: Callable[[str], None] | None = None,
    runtime: RecipeRuntime | None = None,
    cancellation: CancellationToken | None = None,
) -> RunSummary:
    return await generate_prepared(
        prepare_generate_request(request, config),
        config,
        log=log,
        runtime=runtime,
        cancellation=cancellation,
    )
