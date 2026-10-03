"""What a dialogue scene's build asks for, what it accepts back, and how it finishes each image.

Pure: the builder states the plan-time parts (the plan's frame, every static brief), and the
judges and finishing steps call the rest over bytes and records. A plan's staging locks come
from the model; its identity and wardrobe locks, expressions and bindings come from the
actor's own authored profile, so a provider is never asked to invent who somebody is.
"""

from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from PIL import Image

from stage_gen.media import (
    NATIVE_ALPHA_OPAQUE_THRESHOLD,
    apply_chroma_transparency,
    decontaminate_magenta_edges,
    inspect_image,
    normalize_png,
    normalize_png_cover,
)
from the_grain_pipeline.dialogue_scene.models import (
    DialogueScenePlan,
    DialogueScenePlanDraft,
    ExpressionDirection,
    PromptTemplateBinding,
    SharedLocks,
    SpriteGeometry,
)
from the_grain_pipeline.dialogue_scene.prompts import base_plate_prompt, expression_prompt
from the_grain_pipeline.dialogue_scene.scene_request import (
    ResolvedDialogueScene,
    ResolvedSceneActor,
    profile_lock_values,
)

#: The runtime canvases, and the provider canvas a backdrop is drawn at before it is fitted.
SPRITE_WIDTH = 1024
SPRITE_HEIGHT = 1536
BACKGROUND_WIDTH = 1672
BACKGROUND_HEIGHT = 941
PROVIDER_BACKGROUND_WIDTH = 1680
PROVIDER_BACKGROUND_HEIGHT = 944
#: The plan answer's instruction, as the scene recipe has always sent it.
PLAN_SYSTEM = (
    "Return only the strict dialogue-scene-plan JSON. Do not add story, "
    "dialogue, provider instructions, paths, or policy exceptions."
)
TransparencyMode = Literal["native", "chroma", "ai"]


def plan_frame(scene: ResolvedDialogueScene, actor: ResolvedSceneActor) -> dict[str, Any]:
    """Every field of an actor's plan the model does not write, known while planning."""

    native = scene.request.transparency_mode == "native"
    profile = actor.profile
    identity, wardrobe = profile_lock_values(profile.profile)
    return {
        "schema_version": 8,
        "kind": "dialogue-scene-plan-v8",
        "recipe_version": "dialogue-scene-v8",
        "policy_version": "coming-of-age-nonexplicit-v3",
        "expression_profile": "expression-core-v3",
        "art_request_sha256": scene.art_request_sha256,
        "appearance_id": profile.profile.profile_id,
        "character_profile_ref": profile.ref,
        "character_profile_source_sha256": profile.source_sha256,
        "character_profile_sha256": profile.canonical_sha256,
        "identity_reference_sha256": (
            actor.identity_reference.sha256
            if actor.identity_reference is not None
            else scene.style_reference.sha256
        ),
        "identity": identity,
        "wardrobe": wardrobe,
        "geometry": SpriteGeometry().model_dump(mode="json"),
        # Copied from the actor's own profile: the faces are authored.
        "states": [
            ExpressionDirection(
                id=expression.expression_id,
                label=expression.label,
                description=expression.description,
                direction=expression.direction,
            ).model_dump(mode="json")
            for expression in actor.expressions
        ],
        "prompt_templates": [
            PromptTemplateBinding(
                id="profile-native-neutral-v1" if native else "profile-neutral-v1",
                sha256=scene.template_digest,
            ).model_dump(mode="json"),
            PromptTemplateBinding(
                id="profile-native-expression-edit-v1" if native else "profile-expression-edit-v1",
                sha256=scene.template_digest,
            ).model_dump(mode="json"),
        ],
    }


def complete_plan(frame: Mapping[str, Any], draft: object) -> DialogueScenePlan:
    """The model's staging locks inside the authored frame, or a refusal."""

    staged = DialogueScenePlanDraft.model_validate(draft)
    fields = {key: value for key, value in frame.items() if key not in {"identity", "wardrobe"}}
    return DialogueScenePlan.model_validate(
        {
            **fields,
            "shared_locks": SharedLocks(
                identity=frame["identity"],
                wardrobe=frame["wardrobe"],
                pose=staged.shared_locks.pose,
                lighting=staged.shared_locks.lighting,
                style=staged.shared_locks.style,
            ).model_dump(mode="json"),
        }
    )


def expression_brief(
    plan: DialogueScenePlan,
    *,
    base: bool,
    expression_id: str,
    transparency_mode: str,
    has_identity_plate: bool,
) -> str:
    """The base face drawn from scratch, or one face-only edit of it."""

    if base:
        return base_plate_prompt(
            transparency_mode,
            plan,
            expression_id=expression_id,
            has_identity_plate=has_identity_plate,
        )
    return expression_prompt(expression_id, plan, transparency_mode=transparency_mode)


def _native_alpha_counts(data: bytes) -> tuple[int, int]:
    facts = inspect_image(data, expected_media_type="image/png")
    if not facts.has_alpha:
        raise ValueError("dialogue image requires native alpha")
    with Image.open(BytesIO(data)) as opened:
        alpha = opened.convert("RGBA").getchannel("A").tobytes()
    transparent_pixels = sum(value < 255 for value in alpha)
    nontransparent_pixels = sum(value > 0 for value in alpha)
    if (
        transparent_pixels == 0
        or nontransparent_pixels == 0
        or min(alpha) != 0
        or max(alpha) < NATIVE_ALPHA_OPAQUE_THRESHOLD
    ):
        raise ValueError(
            "dialogue native alpha must contain fully transparent and substantially opaque "
            "visible pixels"
        )
    return transparent_pixels, nontransparent_pixels


def check_scene_image(
    data: bytes, *, width: int, height: int, alpha: bool, chroma: bool, recipe_contract: str
) -> dict[str, object]:
    """The provider canvas, chroma that keys, and native alpha that is really there."""

    facts = inspect_image(data, expected_media_type="image/png")
    if (facts.width, facts.height) != (width, height):
        raise ValueError(
            f"dialogue image dimensions must be {width}x{height}; "
            f"received {facts.width}x{facts.height}"
        )
    validation: dict[str, object] = {
        "width": facts.width,
        "height": facts.height,
        "alpha": facts.has_alpha,
        "recipe_contract": recipe_contract,
    }
    if chroma:
        _output, chroma_facts = apply_chroma_transparency(data)
        validation["chroma_transparent_pixels"] = chroma_facts.transparent_pixels
        validation["chroma_nontransparent_pixels"] = chroma_facts.nontransparent_pixels
    if alpha:
        transparent_pixels, nontransparent_pixels = _native_alpha_counts(data)
        validation["transparent_pixels"] = transparent_pixels
        validation["nontransparent_pixels"] = nontransparent_pixels
    return validation


def canonical_sprite(source: bytes, *, transparency_mode: str) -> bytes:
    """The runtime sprite: native alpha covered onto the canvas, or chroma keyed and cleaned."""

    if transparency_mode == "native":
        _native_alpha_counts(source)
        data, _normalization = normalize_png_cover(source, width=SPRITE_WIDTH, height=SPRITE_HEIGHT)
        return data
    if transparency_mode != "chroma":
        raise ValueError("ai transparency needs a background-removal route")
    keyed, _facts = apply_chroma_transparency(source)
    cleaned, _edge = decontaminate_magenta_edges(keyed)
    return cleaned


def normalize_backdrop(raw: bytes) -> bytes:
    """The provider's opaque backdrop, normalized to the runtime canvas."""

    data, _record = normalize_png(raw, width=BACKGROUND_WIDTH, height=BACKGROUND_HEIGHT)
    return data


def scene_files(scene: ResolvedDialogueScene, root: Path) -> list[str]:
    """Every package file the package step reads the scene from again."""

    references = {scene.style_reference.source, *scene.ui_references}
    for actor in scene.actors:
        if actor.identity_reference is not None:
            references.add(actor.identity_reference.source)
    scenarios = {
        path.relative_to(root).as_posix()
        for path in (root / "scenarios").rglob("*")
        if path.is_file()
    }
    return sorted(
        {
            "scene.toml",
            "ui.toml",
            *scenarios,
            *(actor.profile.ref for actor in scene.actors),
            *references,
        }
    )


__all__ = [
    "BACKGROUND_HEIGHT",
    "BACKGROUND_WIDTH",
    "PLAN_SYSTEM",
    "PROVIDER_BACKGROUND_HEIGHT",
    "PROVIDER_BACKGROUND_WIDTH",
    "SPRITE_HEIGHT",
    "SPRITE_WIDTH",
    "TransparencyMode",
    "canonical_sprite",
    "check_scene_image",
    "complete_plan",
    "expression_brief",
    "normalize_backdrop",
    "plan_frame",
    "scene_files",
]
