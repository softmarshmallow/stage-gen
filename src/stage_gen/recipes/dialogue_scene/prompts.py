"""Provider-neutral prompt templates owned by the dialogue recipe."""

from __future__ import annotations

from stage_gen.components.character_profile import (
    CharacterProfile,
    canonical_character_profile_json,
)
from stage_gen.recipes.dialogue_scene.identity import canonical_sha256
from stage_gen.recipes.dialogue_scene.models import (
    DialogueRequest,
    DialogueScenePlan,
    DialogueScenePlanV3,
    DialogueThemeRequestV3,
    ExpressionState,
    GenerateSource,
)
from stage_gen.recipes.dialogue_scene.policy import POLICY_DIGEST

PROMPT_TEMPLATE_VERSION = 5
_BASE = (
    "All depicted people are adults age 21 or older. Romantic chemistry may be confident "
    "but must remain non-explicit, consensual, and fully clothed. No text, logos, or watermark."
)
TEMPLATES = {
    "version": PROMPT_TEMPLATE_VERSION,
    "plan": "Convert a strict adult dating-sim request into the locked dialogue scene plan.",
    "concept": "Create one identity anchor for the named adult character.",
    "background": "Create an opaque background without people.",
    "neutral": "Create a full-body neutral sprite on flat chroma magenta.",
    "expression": "Edit only the face to the requested expression.",
    "base_policy": _BASE,
}
TEMPLATE_DIGEST = canonical_sha256(TEMPLATES)
PROFILE_TEMPLATE_DIGEST = canonical_sha256(
    {
        "base": TEMPLATES,
        "profile_contract": "character-profile-v1",
        "profile_precedence": "authored-identity-wardrobe-invariants-override",
    }
)
NATIVE_ALPHA_PROMPT_VERSION = 1
NATIVE_ALPHA_TEMPLATE_DIGEST = canonical_sha256(
    {
        "version": NATIVE_ALPHA_PROMPT_VERSION,
        "base_template_sha256": TEMPLATE_DIGEST,
        "neutral_background": "native-transparent-alpha-no-shadow-v1",
        "expression_background": "preserve-native-transparent-alpha-v1",
    }
)
PROFILE_NATIVE_ALPHA_TEMPLATE_DIGEST = canonical_sha256(
    {
        "version": NATIVE_ALPHA_PROMPT_VERSION,
        "base_template_sha256": PROFILE_TEMPLATE_DIGEST,
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
        PROFILE_NATIVE_ALPHA_TEMPLATE_DIGEST
        if isinstance(request, DialogueThemeRequestV3) and request.transparency_mode == "native"
        else PROFILE_TEMPLATE_DIGEST
        if isinstance(request, DialogueThemeRequestV3)
        else NATIVE_ALPHA_TEMPLATE_DIGEST
        if request.transparency_mode == "native"
        else TEMPLATE_DIGEST
    )
    profile_line = ""
    if isinstance(request, DialogueThemeRequestV3):
        if profile is None:
            raise ValueError("profile-enabled plan prompt requires the resolved profile")
        profile_line = (
            "\nAUTHORITATIVE CHARACTER PROFILE: "
            f"{canonical_character_profile_json(profile).decode('utf-8')}"
        )
    return (
        f"{TEMPLATES['plan']} {_BASE}\n"
        f"Request SHA-256: {request_sha256}. Policy digest: {POLICY_DIGEST}. "
        f"Template digest: {template_digest}. Preserve the four expression states exactly.\n"
        f"REQUEST: {payload}{profile_line}"
    )


def concept_prompt(request: DialogueRequest, profile: CharacterProfile | None = None) -> str:
    if isinstance(request, DialogueThemeRequestV3):
        if profile is None:
            raise ValueError("profile-enabled concept prompt requires the resolved profile")
        background_direction = getattr(request.background, "description", None)
        world_staging = (
            request.scene_brief
            if not background_direction or background_direction == request.scene_brief
            else f"{request.scene_brief}. Environment direction: {background_direction}"
        )
        invariants = "; ".join(profile.invariants)
        return (
            f"{TEMPLATES['concept']} {_BASE}\nAdult: {profile.display_name}, age "
            f"{profile.age_years}. Authoritative visual identity: {profile.visual_identity}. "
            f"Authoritative wardrobe: {profile.wardrobe}. Character description: "
            f"{profile.description}. Required durable acceptance invariants: {invariants}. "
            "These authored identity, appearance, wardrobe, and invariant facts override any "
            "conflicting inferred direction. "
            f"Requested world staging: {world_staging}. "
            "Polished character-and-world concept art: keep the full or three-quarter adult "
            "character primary, with a clear silhouette and separable edges suitable as the "
            "identity reference for later sprite extraction, but visibly stage them in the "
            "requested world with enough readable environment to anchor its setting and style. "
            "Do not use a blank, white, neutral studio, seamless, or design-sheet field. Opaque "
            "environmental background."
        )
    creative_direction = (
        request.appearance.concept.description
        if isinstance(request.appearance.concept, GenerateSource)
        and request.appearance.concept.description
        else "Use the required appearance and wardrobe without adding role-associated attire."
    )
    background_direction = getattr(request.background, "description", None)
    world_staging = (
        request.scene_brief
        if not background_direction or background_direction == request.scene_brief
        else f"{request.scene_brief}. Environment direction: {background_direction}"
    )
    return (
        f"{TEMPLATES['concept']} {_BASE}\nAdult: {request.appearance.label}, age "
        f"{request.appearance.age}. Required appearance and wardrobe: "
        f"{request.appearance.description}. Creative direction: {creative_direction}. "
        f"Occupation or role context only: {request.appearance.role}; never replace the "
        "specified clothing, hair, accessories, or body details with occupation-associated "
        f"attire. Requested world staging: {world_staging}. "
        "Polished character-and-world concept art: keep the full or three-quarter adult "
        "character primary, with a clear silhouette and separable edges suitable as the "
        "identity reference for later sprite extraction, but visibly stage them in the "
        "requested world with enough readable environment to anchor its setting and style. "
        "Do not use a blank, white, neutral studio, seamless, or design-sheet field. Opaque "
        "environmental background."
    )


def background_prompt(
    request: DialogueRequest, plan: DialogueScenePlan | DialogueScenePlanV3
) -> str:
    description = getattr(request.background, "description", None) or request.scene_brief
    return (
        f"{TEMPLATES['background']} {_BASE}\nScene: {description}. "
        f"Lighting: {plan.shared_locks.lighting}. "
        "Wide dating-sim dialogue backdrop, no people, no characters, fully opaque."
    )


def neutral_prompt(request: DialogueRequest, plan: DialogueScenePlan | DialogueScenePlanV3) -> str:
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
        f"{plan.shared_locks.wardrobe}. Preserve those locks from the sole reference. "
        "Full body, isolated character with a clear silhouette and separable edges for a "
        "cutout-friendly composition; no environmental staging. Fixed pose and crop, "
        f"{background_direction}"
    )


def expression_prompt(
    state: ExpressionState,
    plan: DialogueScenePlan | DialogueScenePlanV3,
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
