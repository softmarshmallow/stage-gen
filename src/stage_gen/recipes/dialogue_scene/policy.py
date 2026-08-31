"""Visual-novel recipe policy and expression taxonomy.

The recipe began as an adult dating-sim generator and refused anyone under 21 as
the cheapest way to guarantee that no minor was ever depicted romantically. The
first-party category it now serves is coming-of-age drama, where a final-year
student in a classroom is the ordinary subject, so the age floor is the legal
adult line rather than an arbitrary one. Everything that actually protects the
subject is unchanged and stays unconditional: no minors, no sexualization, no
nudity, no coercion.
"""

from __future__ import annotations

import re

from stage_gen.components.character_profile import CharacterProfile
from stage_gen.components.scenario import ScenarioProgram
from stage_gen.recipes.dialogue_scene.identity import canonical_sha256
from stage_gen.recipes.dialogue_scene.models import (
    EXPRESSION_STATES,
    MAXIMUM_AGE,
    MINIMUM_AGE,
    DialogueRequest,
)

POLICY_VERSION = 3
CONTENT_POLICY = {
    "version": POLICY_VERSION,
    "minimum_age": MINIMUM_AGE,
    "content": "coming-of-age drama; non-explicit; no coercion or incest",
    "expressions": list(EXPRESSION_STATES),
}
POLICY_DIGEST = canonical_sha256(CONTENT_POLICY)

_PROHIBITED = re.compile(
    r"\b(?:minor|underage|child|schoolgirl|schoolboy|incest|rape|nonconsensual|"
    r"explicit sex|nude|nudity|pornographic)\b",
    re.IGNORECASE,
)


def _assert_adult(profile: CharacterProfile) -> None:
    if profile.age_years is None or not MINIMUM_AGE <= profile.age_years <= MAXIMUM_AGE:
        raise ValueError(
            f"dialogue character profile requires an adult age from {MINIMUM_AGE} to {MAXIMUM_AGE}"
        )


def _assert_permitted_text(*values: str) -> None:
    match = _PROHIBITED.search("\n".join(values))
    if match:
        raise ValueError(f"dialogue content policy rejected prohibited term: {match.group(0)}")


def assert_dialogue_policy(
    request: DialogueRequest, profile: CharacterProfile | None = None
) -> None:
    values = [request.scene_brief]
    if request.background.description is not None:
        values.append(request.background.description)
    if profile is not None:
        _assert_adult(profile)
        values.extend(
            (
                profile.display_name,
                profile.description,
                profile.visual_identity,
                profile.wardrobe,
                *profile.invariants,
            )
        )
    _assert_permitted_text(*values)


def assert_scenario_policy(program: ScenarioProgram) -> None:
    """Screen every authored word the scenario can put on screen.

    The narrative moved out of the scene document and into a scenario, so the
    policy follows it rather than staying behind on a field that no longer
    exists. Every reachable line, every choice, and the briefs that will be sent
    to an image or music model are screened - a branch the player might never
    take is still a line this recipe would have generated art for.
    """

    values: list[str] = [program.display_name]
    for block in program.blocks:
        for statement in block.statements:
            if statement.kind == "line":
                values.append(statement.text)
            elif statement.kind == "choice":
                values.extend(option.text for option in statement.options)
    values.extend(stage.brief for stage in program.stages)
    values.extend(track.brief for track in program.tracks)
    values.extend(ending.label for ending in program.endings)
    _assert_permitted_text(*values)


def assert_character_profile_policy(profile: CharacterProfile) -> None:
    """Validate dialogue-specific adult/content constraints on a shared profile."""

    _assert_adult(profile)
    _assert_permitted_text(
        profile.display_name,
        profile.description,
        profile.visual_identity,
        profile.wardrobe,
        *profile.invariants,
    )
