"""Public scrolling-preview recipe definition."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from stage_gen.config import CapabilityName
from stage_gen.recipes.base import JsonObject, Recipe
from stage_gen.recipes.scrolling_preview.stages import STAGES
from stage_gen.tags import tag_for


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
    return {"prompt": prompt}


def scrolling_preview_tag(input_value: Mapping[str, Any]) -> str:
    return tag_for(str(input_value["prompt"]))


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
)
