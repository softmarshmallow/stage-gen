"""Public scrolling-preview recipe definition."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from stage_gen.config import CapabilityName
from stage_gen.recipes.base import JsonObject, Recipe
from stage_gen.recipes.scrolling_preview.stages import STAGES, scrolling_preview_stages
from stage_gen.tags import tag_for
from stage_gen.theme import parse_theme_handles, theme_digest


def parse_scrolling_preview_input(value: object) -> JsonObject:
    if isinstance(value, str):
        prompt = value.strip()
    elif isinstance(value, Mapping):
        raw_prompt = value.get("prompt")
        prompt = str(raw_prompt if raw_prompt is not None else "").strip()
    else:
        prompt = ""
    if not prompt:
        raise ValueError("scrolling-preview input requires a non-empty prompt")
    parsed: JsonObject = {"prompt": prompt}
    if isinstance(value, Mapping) and "theme" in value:
        parsed["theme"] = parse_theme_handles(value["theme"]).model_dump(mode="json")
    return parsed


def scrolling_preview_tag(input_value: Mapping[str, Any]) -> str:
    prompt_tag = tag_for(str(input_value["prompt"]))
    if "theme" not in input_value:
        return prompt_tag
    digest = theme_digest(parse_theme_handles(input_value["theme"]))
    return f"{prompt_tag}-theme-{digest}"


scrolling_preview_recipe = Recipe(
    id="scrolling-preview",
    description="Reference 2D scrolling preview asset pipeline",
    required_capabilities=(
        CapabilityName.STRUCTURED_GENERATION,
        CapabilityName.IMAGE_GENERATION,
    ),
    parse_input=parse_scrolling_preview_input,
    tag_for=scrolling_preview_tag,
    stages=STAGES,
    stage_resolver=scrolling_preview_stages,
)
