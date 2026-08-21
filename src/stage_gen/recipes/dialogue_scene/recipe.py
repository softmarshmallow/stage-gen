"""Public dialogue-scene recipe definition."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from stage_gen.config import CapabilityName
from stage_gen.recipes.base import JsonObject, Recipe
from stage_gen.recipes.dialogue_scene.identity import canonical_sha256
from stage_gen.recipes.dialogue_scene.models import (
    DialogueRequest,
    DialogueThemeRequest,
    DialogueThemeRequestV3,
)
from stage_gen.recipes.dialogue_scene.policy import assert_dialogue_policy
from stage_gen.recipes.dialogue_scene.review import transition_dialogue_review
from stage_gen.recipes.dialogue_scene.stages import STAGES, dialogue_scene_stages
from stage_gen.tags import tag_for


def parse_dialogue_scene_input(value: object) -> JsonObject:
    if not isinstance(value, Mapping):
        raise ValueError("dialogue-scene input requires a versioned JSON or TOML object")
    raw = dict(value)
    request_type = (
        DialogueThemeRequestV3 if raw.get("schema_version") == 3 else DialogueThemeRequest
    )
    try:
        request = request_type.model_validate(raw)
    except ValidationError as error:
        version = "v3" if request_type is DialogueThemeRequestV3 else "v2"
        raise ValueError(f"invalid dialogue-theme-request-{version}: {error}") from None
    assert_dialogue_policy(request)
    return request.model_dump(mode="json", exclude_none=True)


def dialogue_scene_tag(input_value: Mapping[str, Any]) -> str:
    request = _parse_request(input_value)
    return f"{tag_for(request.scene_brief)}-{canonical_sha256(request)[:12]}"


def _parse_request(input_value: Mapping[str, Any]) -> DialogueRequest:
    if input_value.get("schema_version") == 3:
        return DialogueThemeRequestV3.model_validate(input_value)
    return DialogueThemeRequest.model_validate(input_value)


dialogue_scene_recipe = Recipe(
    id="dialogue-scene",
    description="Strict adult, non-explicit dialogue-scene asset bundle pipeline",
    required_capabilities=(
        CapabilityName.STRUCTURED_GENERATION,
        CapabilityName.IMAGE_GENERATION,
    ),
    parse_input=parse_dialogue_scene_input,
    tag_for=dialogue_scene_tag,
    stages=STAGES,
    stage_resolver=dialogue_scene_stages,
    contract_version=2,
    actions={"review": transition_dialogue_review},
)
