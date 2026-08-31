"""Provider-neutral prompt templates owned by the visual-novel recipe."""

from __future__ import annotations

from stage_gen.components.character_profile import (
    CharacterProfile,
    canonical_character_profile_json,
)
from stage_gen.recipes.dialogue_scene.identity import canonical_sha256
from stage_gen.recipes.dialogue_scene.models import (
    DialogueRequest,
    DialogueScenePlan,
    ExpressionState,
)
from stage_gen.recipes.dialogue_scene.policy import POLICY_DIGEST

PROMPT_TEMPLATE_VERSION = 7
_BASE = (
    "Coming-of-age drama, not romance. All depicted people are adults age 18 or older, fully "
    "clothed and presented non-sexually. No text, logos, or watermark."
)
#: Two clauses, because one plate cannot mean two things once a scene has a cast.
#:
#: The style plate is the scene's art direction of record and every image is drawn
#: against it. It used to also assert "match its character identity exactly", which
#: was true while a scene had exactly one character and became a bug the moment it
#: had three: a plate showing one actor would have pulled the whole cast toward that
#: face. Identity is asserted only where a plate genuinely IS that actor.
STYLE_REFERENCE_CLAUSE = (
    "One attached reference is this scene's authored style plate. It is the art direction of "
    "record: match its rendering medium, palette, line quality and light exactly. It is NOT a "
    "reference for who this character is - do not copy any person depicted in it. Where it "
    "disagrees with the instructions above, the instructions win."
)
IDENTITY_REFERENCE_CLAUSE = (
    "One attached reference is this character's own authored identity plate. Match the person "
    "in it exactly: face, hair, build, and wardrobe. Where it disagrees with the instructions "
    "above, the instructions win."
)
TEMPLATES = {
    "version": PROMPT_TEMPLATE_VERSION,
    "plan": "Convert a strict coming-of-age scene package into the locked dialogue scene plan.",
    "background": "Create an opaque background without people.",
    "neutral": "Create a full-body neutral sprite on flat chroma magenta.",
    "expression": "Edit only the face to the requested expression.",
    "base_policy": _BASE,
    "style_reference": STYLE_REFERENCE_CLAUSE,
    "identity_reference": IDENTITY_REFERENCE_CLAUSE,
    "profile_contract": "character-profile-v1",
    "profile_precedence": "authored-identity-wardrobe-invariants-override",
}
TEMPLATE_DIGEST = canonical_sha256(TEMPLATES)
NATIVE_ALPHA_PROMPT_VERSION = 2
NATIVE_ALPHA_TEMPLATE_DIGEST = canonical_sha256(
    {
        "version": NATIVE_ALPHA_PROMPT_VERSION,
        "base_template_sha256": TEMPLATE_DIGEST,
        "neutral_background": "native-transparent-alpha-no-shadow-v1",
        "expression_background": "preserve-native-transparent-alpha-v1",
    }
)


def plan_prompt(
    request: DialogueRequest,
    request_sha256: str,
    profile: CharacterProfile | None = None,
) -> str:
    payload = request.model_dump_json(exclude_none=True)
    template_digest = (
        NATIVE_ALPHA_TEMPLATE_DIGEST if request.transparency_mode == "native" else TEMPLATE_DIGEST
    )
    if profile is None:
        raise ValueError("the dialogue plan prompt requires the resolved character profile")
    profile_line = (
        "\nAUTHORITATIVE CHARACTER PROFILE: "
        f"{canonical_character_profile_json(profile).decode('utf-8')}"
    )
    return (
        f"{TEMPLATES['plan']} {_BASE}\n"
        f"Request SHA-256: {request_sha256}. Policy digest: {POLICY_DIGEST}. "
        f"Template digest: {template_digest}. Preserve the four expression states exactly.\n"
        f"{STYLE_REFERENCE_CLAUSE}\n"
        f"REQUEST: {payload}{profile_line}"
    )


def background_prompt(brief: str) -> str:
    """One backdrop, from the stage's own authored brief.

    Plan-time known, because a stage is declared by the scenario rather than
    derived from a generated plan: the whole instruction rides the node's card, so
    `execution-plan.json` states what each backdrop will be told before a cent is
    spent.
    """

    return (
        f"{TEMPLATES['background']} {_BASE}\nScene: {brief}. "
        "Wide visual-novel dialogue backdrop, no people, no characters, fully opaque.\n"
        f"{STYLE_REFERENCE_CLAUSE}"
    )


def neutral_prompt(
    request: DialogueRequest,
    plan: DialogueScenePlan,
    *,
    has_identity_plate: bool = False,
) -> str:
    identity_clause = f"\n{IDENTITY_REFERENCE_CLAUSE}" if has_identity_plate else ""
    template = (
        "Create a full-body neutral sprite with native alpha."
        if request.transparency_mode == "native"
        else TEMPLATES["neutral"]
    )
    background_direction = (
        "native transparent background with clean, naturally antialiased alpha edges; no "
        "environment, backdrop, floor, cast shadow, or contact shadow."
        if request.transparency_mode == "native"
        else "perfectly flat #ff00ff background."
    )
    return (
        f"{template} {_BASE}\n{plan.direction_for('neutral')}. "
        f"Required identity: {plan.shared_locks.identity}. Required wardrobe: "
        f"{plan.shared_locks.wardrobe}. Those locks are authoritative for who this is. "
        "Full body, isolated character with a clear silhouette and separable edges for a "
        "cutout-friendly composition; no environmental staging. Fixed pose and crop, "
        f"{background_direction}\n"
        f"{STYLE_REFERENCE_CLAUSE}"
        f"{identity_clause}"
    )


def expression_prompt(
    state: ExpressionState,
    plan: DialogueScenePlan,
    *,
    transparency_mode: str = "ai",
) -> str:
    if transparency_mode != "native":
        return (
            f"{TEMPLATES['expression']} {_BASE}\nTarget expression: {state}. "
            f"Direction: {plan.direction_for(state)}. Required identity: "
            f"{plan.shared_locks.identity}. Required wardrobe: {plan.shared_locks.wardrobe}. "
            "Preserve identity, hair, wardrobe, body, pose, crop, palette, rendering, and flat "
            "#ff00ff background exactly."
        )
    background_direction = (
        "Preserve the native transparent background and clean alpha edge exactly; do not add "
        "an environment, backdrop, floor, cast shadow, or contact shadow."
    )
    return (
        f"{TEMPLATES['expression']} {_BASE}\nTarget expression: {state}. "
        f"Direction: {plan.direction_for(state)}. Required identity: "
        f"{plan.shared_locks.identity}. Required wardrobe: {plan.shared_locks.wardrobe}. "
        "Preserve identity, hair, wardrobe, body, pose, crop, palette, and rendering exactly. "
        f"{background_direction}"
    )
