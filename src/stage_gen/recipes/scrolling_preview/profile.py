"""Scrolling-preview binding and resolution of shared character profiles."""

from __future__ import annotations

import hashlib

from stage_gen.components.character_profile import (
    CharacterProfile,
    CharacterProfileBinding,
)

PROFILE_RESOLUTION_VERSION = "scrolling-character-profile-resolution-v1"


def parse_character_profile_binding(value: object) -> dict[str, object]:
    """Validate the shared binding without adding recipe-local aliases."""

    return CharacterProfileBinding.model_validate(value).model_dump(mode="json")


def character_profile_prompt(profile: CharacterProfile) -> str:
    """Render only durable identity facts for the player concept prompt."""

    age = f"Age in years: {profile.age_years}.\n" if profile.age_years is not None else ""
    invariants = "\n".join(f"- {item}" for item in profile.invariants)
    return (
        "Durable player character profile:\n"
        f"Display name: {profile.display_name}.\n"
        f"{age}"
        f"Description: {profile.description}\n"
        f"Visual identity: {profile.visual_identity}\n"
        f"Wardrobe: {profile.wardrobe}\n"
        f"Invariants:\n{invariants}"
    )


def character_profile_tag_suffix(binding_value: object) -> str:
    """Keep a stable run directory across revisions at one authored ref."""

    binding = CharacterProfileBinding.model_validate(binding_value)
    ref_sha256 = hashlib.sha256(binding.ref.encode("utf-8")).hexdigest()
    return f"profile-v1-{ref_sha256[:12]}"
