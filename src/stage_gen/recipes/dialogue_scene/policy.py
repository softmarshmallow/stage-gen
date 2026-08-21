"""Dialogue-recipe policy and expression taxonomy."""

from __future__ import annotations

import re

from stage_gen.components.character_profile import CharacterProfile
from stage_gen.recipes.dialogue_scene.identity import canonical_sha256
from stage_gen.recipes.dialogue_scene.models import (
    EXPRESSION_STATES,
    DialogueRequest,
    DialogueThemeRequest,
)

POLICY_VERSION = 2
CONTENT_POLICY = {
    "version": POLICY_VERSION,
    "minimum_age": 21,
    "content": "adult romantic chemistry; non-explicit; no coercion or incest",
    "expressions": list(EXPRESSION_STATES),
}
POLICY_DIGEST = canonical_sha256(CONTENT_POLICY)

_PROHIBITED = re.compile(
    r"\b(?:minor|underage|child|schoolgirl|schoolboy|incest|rape|nonconsensual|"
    r"explicit sex|nude|nudity|pornographic)\b",
    re.IGNORECASE,
)


def assert_dialogue_policy(
    request: DialogueRequest, profile: CharacterProfile | None = None
) -> None:
    values = [request.scene_brief, *(beat.text for beat in request.dialogue)]
    if isinstance(request, DialogueThemeRequest):
        values.extend((request.appearance.role, request.appearance.description))
    elif profile is not None:
        if profile.age_years is None or not 21 <= profile.age_years <= 120:
            raise ValueError("dialogue character profile requires an adult age from 21 to 120")
        values.extend(
            (
                profile.display_name,
                profile.description,
                profile.visual_identity,
                profile.wardrobe,
                *profile.invariants,
            )
        )
    text = "\n".join(values)
    match = _PROHIBITED.search(text)
    if match:
        raise ValueError(f"dialogue content policy rejected prohibited term: {match.group(0)}")


def assert_character_profile_policy(profile: CharacterProfile) -> None:
    """Validate dialogue-specific adult/content constraints on a shared profile."""

    if profile.age_years is None or not 21 <= profile.age_years <= 120:
        raise ValueError("dialogue character profile requires an adult age from 21 to 120")
    text = "\n".join(
        (
            profile.display_name,
            profile.description,
            profile.visual_identity,
            profile.wardrobe,
            *profile.invariants,
        )
    )
    match = _PROHIBITED.search(text)
    if match:
        raise ValueError(f"dialogue content policy rejected prohibited term: {match.group(0)}")
