"""Resolve one authored dialogue request into everything the plan is built from.

Planning must be able to state the whole graph - and refuse a bad request - without
reaching a provider. Every digest a node's cache key needs is settled here: the
canonical request, the policy, the prompt templates, the transparency derivation, the
packaged style resources, the authored character profile, and any reused source image.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from pydantic import ValidationError

from gnode import InputProvenance
from stage_gen.components._secure_fs import read_absolute_regular_file
from stage_gen.components.character_profile import (
    CharacterProfile,
    resolve_character_profile_binding,
)
from stage_gen.image_prompting import load_image_style_resources
from stage_gen.media import CHROMA_MATTE_VERSION, MAGENTA_EDGE_DECONTAMINATION_VERSION
from stage_gen.recipes.dialogue_scene.identity import (
    canonical_json_bytes,
    canonical_sha256,
    content_sha256,
)
from stage_gen.recipes.dialogue_scene.models import (
    DialogueRequest,
    DialogueThemeRequest,
    DialogueThemeRequestV3,
    ReuseSource,
)
from stage_gen.recipes.dialogue_scene.policy import (
    POLICY_DIGEST,
    assert_character_profile_policy,
    assert_dialogue_policy,
)
from stage_gen.recipes.dialogue_scene.prompts import (
    NATIVE_ALPHA_TEMPLATE_DIGEST,
    PROFILE_NATIVE_ALPHA_TEMPLATE_DIGEST,
    PROFILE_TEMPLATE_DIGEST,
    TEMPLATE_DIGEST,
)

SCENE_ID_MAX_LENGTH = 48


@dataclass(frozen=True, slots=True)
class ResolvedSceneProfile:
    """One authored character profile, already validated against scene limits."""

    profile: CharacterProfile
    ref: str
    source_sha256: str
    canonical_sha256: str
    canonical_bytes: bytes
    source_provenance: InputProvenance


@dataclass(frozen=True, slots=True)
class IngestedSource:
    """One caller-supplied image the request reuses instead of generating."""

    role: str
    ref: str
    sha256: str
    data: bytes


@dataclass(frozen=True, slots=True)
class ResolvedDialogueScene:
    """One authored request, resolved offline into a plannable scene."""

    request: DialogueRequest
    request_bytes: bytes
    request_sha256: str
    scene_id: str
    recipe_version: str
    policy_digest: str
    template_digest: str
    transparency_digest: str
    style_resource_sha256: str
    style_compiler_sha256: str
    style_selection_brief: str
    profile: ResolvedSceneProfile | None
    concept_reuse: IngestedSource | None
    background_reuse: IngestedSource | None

    def identity(self) -> dict[str, object]:
        """The portable record of exactly which request this run was planned from."""

        identity: dict[str, object] = {
            "schema_version": 1,
            "kind": "dialogue-scene-request-identity-v1",
            "scene_id": self.scene_id,
            "recipe_version": self.recipe_version,
            "request_sha256": self.request_sha256,
            "request_schema_version": self.request.schema_version,
            "policy_digest": self.policy_digest,
            "template_digest": self.template_digest,
            "transparency_mode": self.request.transparency_mode,
            "style_compiler_sha256": self.style_compiler_sha256,
            "style_resource_sha256": self.style_resource_sha256,
        }
        if self.profile is not None:
            identity["character_profile_ref"] = self.profile.ref
            identity["character_profile_sha256"] = self.profile.canonical_sha256
            identity["character_profile_source_sha256"] = self.profile.source_sha256
        return identity


def read_dialogue_request_document(input_path: Path) -> dict[str, object]:
    """Read one authored request from a JSON or TOML file, following no symlink."""

    data = read_absolute_regular_file(input_path.resolve(), label="dialogue request")
    if input_path.suffix == ".toml":
        document = tomllib.loads(data.decode("utf-8"))
    else:
        document = json.loads(data.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("dialogue request document must be a JSON or TOML object")
    return document


def parse_dialogue_request(document: object) -> DialogueRequest:
    """Parse the exact declared contract version; V2 is never reinterpreted as V3."""

    if not isinstance(document, Mapping):
        raise ValueError("dialogue-scene input requires a versioned JSON or TOML object")
    raw = dict(document)
    request_type = (
        DialogueThemeRequestV3 if raw.get("schema_version") == 3 else DialogueThemeRequest
    )
    try:
        request = request_type.model_validate(raw)
    except ValidationError as error:
        version = "v3" if request_type is DialogueThemeRequestV3 else "v2"
        raise ValueError(f"invalid dialogue-theme-request-{version}: {error}") from None
    assert_dialogue_policy(request)
    return request


def resolve_dialogue_scene(
    document: object,
    *,
    character_library_root: Path | None = None,
) -> ResolvedDialogueScene:
    """Validate and materialize everything the plan needs, touching no provider."""

    request = parse_dialogue_request(document)
    request_bytes = canonical_json_bytes(request.model_dump(mode="json"))
    profile = (
        _resolve_profile(request, character_library_root=character_library_root)
        if isinstance(request, DialogueThemeRequestV3)
        else None
    )
    resources = load_image_style_resources()
    return ResolvedDialogueScene(
        request=request,
        request_bytes=request_bytes,
        request_sha256=canonical_sha256(request),
        scene_id=_scene_id(request, profile),
        recipe_version=recipe_version(request),
        policy_digest=POLICY_DIGEST,
        template_digest=template_digest(request),
        transparency_digest=_transparency_digest(request),
        style_resource_sha256=resources.resource_sha256,
        style_compiler_sha256=resources.compiler_sha256,
        style_selection_brief=style_selection_brief(request, profile),
        profile=profile,
        concept_reuse=_ingest(request, "concept"),
        background_reuse=_ingest(request, "background"),
    )


def recipe_version(request: DialogueRequest) -> str:
    return (
        "dialogue-scene-v4" if isinstance(request, DialogueThemeRequestV3) else "dialogue-scene-v3"
    )


def template_digest(request: DialogueRequest) -> str:
    return (
        PROFILE_NATIVE_ALPHA_TEMPLATE_DIGEST
        if isinstance(request, DialogueThemeRequestV3) and request.transparency_mode == "native"
        else PROFILE_TEMPLATE_DIGEST
        if isinstance(request, DialogueThemeRequestV3)
        else NATIVE_ALPHA_TEMPLATE_DIGEST
        if request.transparency_mode == "native"
        else TEMPLATE_DIGEST
    )


def style_selection_brief(request: DialogueRequest, profile: ResolvedSceneProfile | None) -> str:
    background_direction = getattr(request.background, "description", None)
    if isinstance(request, DialogueThemeRequestV3):
        if profile is None:
            raise ValueError("profile-enabled dialogue requests require a resolved profile")
        authored = profile.profile
        return canonical_json_bytes(
            {
                "scene_brief": request.scene_brief,
                "appearance_description": authored.visual_identity,
                "wardrobe": authored.wardrobe,
                "invariants": authored.invariants,
                "background_direction": background_direction,
                "character_profile_sha256": profile.canonical_sha256,
            }
        ).decode("utf-8")
    return canonical_json_bytes(
        {
            "scene_brief": request.scene_brief,
            "appearance_description": request.appearance.description,
            "concept_direction": getattr(request.appearance.concept, "description", None),
            "background_direction": background_direction,
        }
    ).decode("utf-8")


def profile_lock_values(profile: CharacterProfile) -> tuple[str, str]:
    """Compile the two deterministic identity locks every prompt repeats verbatim."""

    invariants = "; ".join(profile.invariants)
    identity = (
        f"{profile.display_name}, adult age {profile.age_years}. Authoritative appearance: "
        f"{profile.visual_identity}. Character description: {profile.description}. "
        f"Required durable acceptance invariants: {invariants}."
    )
    wardrobe = (
        f"Authoritative wardrobe: {profile.wardrobe}. Required durable acceptance invariants: "
        f"{invariants}. Do not replace authored clothing with role-associated attire."
    )
    if len(identity) > 2000 or len(wardrobe) > 1000:
        raise ValueError("dialogue character_profile exceeds deterministic lock limits")
    return identity, wardrobe


def _resolve_profile(
    request: DialogueThemeRequestV3,
    *,
    character_library_root: Path | None,
) -> ResolvedSceneProfile:
    if character_library_root is None:
        raise ValueError("profile-enabled dialogue generation requires character_library_root")
    resolved = resolve_character_profile_binding(
        request.character_profile,
        character_library_root=character_library_root,
    )
    profile = resolved.profile
    if len(profile.profile_id) > SCENE_ID_MAX_LENGTH:
        raise ValueError("dialogue character_profile profile_id exceeds the scene binding limit")
    if len(profile.display_name) > 96:
        raise ValueError("dialogue character_profile display_name exceeds the scene binding limit")
    if len(profile.description) > 280 or len(profile.visual_identity) > 320:
        raise ValueError("dialogue character_profile descriptive fields exceed scene limits")
    assert_character_profile_policy(profile)
    profile_lock_values(profile)
    return ResolvedSceneProfile(
        profile=profile,
        ref=resolved.binding.ref,
        source_sha256=resolved.binding.source_sha256,
        canonical_sha256=resolved.canonical_sha256,
        canonical_bytes=resolved.canonical_bytes,
        source_provenance=resolved.source_provenance,
    )


def _ingest(request: DialogueRequest, role: str) -> IngestedSource | None:
    source = (
        request.background
        if role == "background"
        else request.appearance.concept
        if isinstance(request, DialogueThemeRequest)
        else None
    )
    if not isinstance(source, ReuseSource):
        return None
    if source.ref.startswith(("http://", "https://")):
        raise ValueError("dialogue reuse currently requires a caller-accessible local file")
    path = Path(source.ref).expanduser().resolve()
    data = read_absolute_regular_file(path, label=f"{role} reuse")
    if content_sha256(data) != source.sha256:
        raise ValueError(f"{role} reuse digest mismatch")
    return IngestedSource(role=role, ref=source.ref, sha256=source.sha256, data=data)


def _transparency_digest(request: DialogueRequest) -> str:
    """Bind the exact derivation the canonicalize nodes will apply."""

    parts: dict[str, object] = {"transparency_mode": request.transparency_mode}
    if request.transparency_mode != "native":
        parts["magenta_edge_decontamination_version"] = MAGENTA_EDGE_DECONTAMINATION_VERSION
    if request.transparency_mode == "chroma":
        parts["chroma_matte_version"] = CHROMA_MATTE_VERSION
    return sha256(canonical_json_bytes(parts)).hexdigest()


def _scene_id(request: DialogueRequest, profile: ResolvedSceneProfile | None) -> str:
    subject = (
        profile.profile.profile_id
        if profile is not None
        else request.appearance.id
        if isinstance(request, DialogueThemeRequest)
        else "scene"
    )
    return f"{subject}-{canonical_sha256(request)[:12]}"


__all__ = [
    "SCENE_ID_MAX_LENGTH",
    "IngestedSource",
    "ResolvedDialogueScene",
    "ResolvedSceneProfile",
    "parse_dialogue_request",
    "profile_lock_values",
    "read_dialogue_request_document",
    "recipe_version",
    "resolve_dialogue_scene",
    "style_selection_brief",
    "template_digest",
]
