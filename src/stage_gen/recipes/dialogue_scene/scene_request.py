"""Resolve one authored scene package into everything the plan is built from.

Planning must be able to state the whole graph - and refuse a bad package - without
reaching a provider. Every digest a node's cache key needs is settled here: the
canonical scene document, the policy, the prompt templates, the transparency
derivation, the packaged style resources, the authored character profile, and the
authored reference images the scene is drawn against.

A scene is a directory, not a loose request file. Every member it names is read from
inside that directory, confined to it, following no symlink, and matched against the
digest the author recorded.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from gnode import InputProvenance
from stage_gen.components._authored_package import read_digest_bound_member
from stage_gen.components._secure_fs import read_absolute_regular_file
from stage_gen.components.character_profile import (
    CharacterProfile,
    resolve_character_profile_binding,
)
from stage_gen.components.scenario import (
    SCENARIO_DOCUMENT_NAME,
    ResolvedScenario,
    resolve_scenario,
)
from stage_gen.image_prompting import load_image_style_resources
from stage_gen.media import CHROMA_MATTE_VERSION, MAGENTA_EDGE_DECONTAMINATION_VERSION
from stage_gen.recipes.dialogue_scene.identity import (
    canonical_json_bytes,
    canonical_sha256,
)
from stage_gen.recipes.dialogue_scene.models import (
    EXPRESSION_STATES,
    DialogueRequest,
    DialogueSceneDocument,
    RightsStatus,
    SceneReference,
)
from stage_gen.recipes.dialogue_scene.policy import (
    POLICY_DIGEST,
    assert_character_profile_policy,
    assert_dialogue_policy,
    assert_scenario_policy,
)
from stage_gen.recipes.dialogue_scene.prompts import (
    NATIVE_ALPHA_TEMPLATE_DIGEST,
    TEMPLATE_DIGEST,
)

SCENE_ID_MAX_LENGTH = 48
#: The authored root every scene package is read from.
SCENE_DOCUMENT_NAME = "scene.toml"
_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


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
class ResolvedSceneReference:
    """One authored package image, read and matched against its declared digest."""

    reference_id: str
    source: str
    sha256: str
    media_type: str
    data: bytes
    rights_status: RightsStatus
    rights_basis: tuple[str, ...]

    @property
    def provenance_ref(self) -> str:
        return f"{self.source}#sha256={self.sha256}"


@dataclass(frozen=True, slots=True)
class ResolvedDialogueScene:
    """One authored scene package, resolved offline into a plannable scene."""

    request: DialogueRequest
    request_bytes: bytes
    request_sha256: str
    #: The request digest with the narrative removed, for image cache identity.
    #: Every generated plate depends on the look, the profile, and the backdrop
    #: direction; none of them depends on what anybody says. Digesting the whole
    #: document into an image node would re-bill five provider images every time
    #: a line of dialogue is reworded, which would make editing prose expensive
    #: for no reason. The ground node already excludes placement fields from its
    #: cache identity for exactly this reason.
    art_request_sha256: str
    scene_id: str
    recipe_version: str
    policy_digest: str
    template_digest: str
    transparency_digest: str
    style_resource_sha256: str
    style_compiler_sha256: str
    style_selection_brief: str
    profile: ResolvedSceneProfile
    identity_reference: ResolvedSceneReference
    scenario: ResolvedScenario

    def identity(self) -> dict[str, object]:
        """The portable record of exactly which package this run was planned from."""

        return {
            "schema_version": 1,
            "kind": "dialogue-scene-request-identity-v1",
            "scene_id": self.scene_id,
            "game_id": self.request.game_id,
            "recipe_version": self.recipe_version,
            "request_sha256": self.request_sha256,
            "request_schema_version": self.request.schema_version,
            "policy_digest": self.policy_digest,
            "template_digest": self.template_digest,
            "transparency_mode": self.request.transparency_mode,
            "style_compiler_sha256": self.style_compiler_sha256,
            "style_resource_sha256": self.style_resource_sha256,
            "character_profile_ref": self.profile.ref,
            "character_profile_sha256": self.profile.canonical_sha256,
            "character_profile_source_sha256": self.profile.source_sha256,
            "identity_reference_source": self.identity_reference.source,
            "identity_reference_sha256": self.identity_reference.sha256,
            "scenario_ref": self.request.scenario.ref,
            "scenario_source_sha256": self.request.scenario.source_sha256,
            "scenario_program_sha256": self.scenario.program_sha256,
        }


def read_scene_document(root: Path) -> dict[str, object]:
    """Read one authored scene package's root document, following no symlink."""

    path = (root / SCENE_DOCUMENT_NAME).resolve()
    data = read_absolute_regular_file(path, label="dialogue scene document")
    document = tomllib.loads(data.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("dialogue scene document must be a TOML object")
    return document


def parse_dialogue_request(document: object) -> DialogueRequest:
    """Parse the exact declared contract; no other version is reinterpreted as this one."""

    if not isinstance(document, Mapping):
        raise ValueError("dialogue-scene input requires a versioned TOML object")
    try:
        request = DialogueSceneDocument.model_validate(dict(document))
    except ValidationError as error:
        raise ValueError(f"invalid dialogue-scene-v2: {error}") from None
    assert_dialogue_policy(request)
    return request


def resolve_dialogue_scene(document: object, *, root: Path) -> ResolvedDialogueScene:
    """Validate and materialize everything the plan needs, touching no provider."""

    request = parse_dialogue_request(document)
    request_bytes = canonical_json_bytes(request.model_dump(mode="json"))
    # The narrative is admitted before anything else is materialized, so a scene
    # whose scenario cannot be finished costs nothing.
    scenario = _resolve_scenario(request, root=root)
    profile = _resolve_profile(request, root=root)
    identity_reference = _read_reference(root, request.identity_reference())
    resources = load_image_style_resources()
    return ResolvedDialogueScene(
        request=request,
        request_bytes=request_bytes,
        request_sha256=canonical_sha256(request),
        art_request_sha256=_art_request_sha256(request),
        scene_id=_scene_id(request, profile),
        recipe_version=recipe_version(request),
        policy_digest=POLICY_DIGEST,
        template_digest=template_digest(request),
        transparency_digest=_transparency_digest(request),
        style_resource_sha256=resources.resource_sha256,
        style_compiler_sha256=resources.compiler_sha256,
        style_selection_brief=style_selection_brief(request, profile),
        profile=profile,
        identity_reference=identity_reference,
        scenario=scenario,
    )


def recipe_version(request: DialogueRequest) -> str:
    return "dialogue-scene-v6"


def template_digest(request: DialogueRequest) -> str:
    return (
        NATIVE_ALPHA_TEMPLATE_DIGEST if request.transparency_mode == "native" else TEMPLATE_DIGEST
    )


def style_selection_brief(request: DialogueRequest, profile: ResolvedSceneProfile) -> str:
    authored = profile.profile
    return canonical_json_bytes(
        {
            "scene_brief": request.scene_brief,
            "appearance_description": authored.visual_identity,
            "wardrobe": authored.wardrobe,
            "invariants": authored.invariants,
            "background_direction": request.background.description,
            "character_profile_sha256": profile.canonical_sha256,
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


def _read_reference(root: Path, reference: SceneReference) -> ResolvedSceneReference:
    """Read one authored reference and hold it to the digest the author recorded."""

    source = reference.source
    data = read_digest_bound_member(
        root,
        source,
        expected_sha256=reference.source_sha256,
        label="scene reference",
    )
    media_type = _MEDIA_TYPES[PurePosixPath(source).suffix.lower()]
    return ResolvedSceneReference(
        reference_id=reference.reference_id,
        source=source,
        sha256=reference.source_sha256,
        media_type=media_type,
        data=data,
        rights_status=reference.rights_status,
        rights_basis=tuple(reference.rights_basis),
    )


def _art_request_sha256(request: DialogueRequest) -> str:
    """Digest exactly the authored fields a generated image depends on.

    An allowlist rather than "the whole document minus the narrative", because
    the point is to name what the art is a function of. Every plate depends on
    the look, the profile, the backdrop direction, the framing, and the
    transparency mode; none depends on what anybody says, on the schema version,
    or on any field a future revision adds for a consumer's benefit. Digesting
    the whole document here would re-bill five provider images on every contract
    bump and on every reworded line, which is a cost with nothing to show for it.
    """

    document = request.model_dump(mode="json")
    return sha256(
        canonical_json_bytes(
            {
                "domain": "stage-gen/dialogue-scene/art-identity/v1",
                "game_id": document["game_id"],
                "scene_brief": document["scene_brief"],
                "background": document["background"],
                "presentation": document["presentation"],
                "transparency_mode": document["transparency_mode"],
                "character_profile": document["character_profile"],
                "identity_reference_id": document["identity_reference_id"],
                "references": document["references"],
            }
        )
    ).hexdigest()


def _resolve_scenario(request: DialogueRequest, *, root: Path) -> ResolvedScenario:
    """Admit the authored narrative and hold it to the digest the scene recorded.

    The scene binds `scenario.toml`, which in turn binds its script by digest, so
    one recorded hash in the scene document closes over the whole narrative. The
    expressions the scenario asks for must exist in this recipe's locked taxonomy:
    art the pipeline cannot draw is refused here rather than discovered as a
    missing texture in the browser.
    """

    binding = request.scenario
    if binding.ref != SCENARIO_DOCUMENT_NAME:
        raise ValueError(f"dialogue scene scenario ref must be {SCENARIO_DOCUMENT_NAME}")
    declared = sha256(
        read_absolute_regular_file((root / binding.ref).resolve(), label="dialogue scene scenario")
    ).hexdigest()
    if declared != binding.source_sha256:
        raise ValueError(
            f"dialogue scene scenario {binding.ref} does not match its authored digest: "
            f"declared {binding.source_sha256}, found {declared}"
        )
    scenario = resolve_scenario(root)
    assert_scenario_policy(scenario.program)
    if scenario.declarations.game_id != request.game_id:
        raise ValueError("dialogue scene scenario game_id must match the scene document")
    for member in scenario.declarations.cast:
        unknown = sorted(set(member.expressions) - set(EXPRESSION_STATES))
        if unknown:
            raise ValueError(
                f"scenario cast member {member.actor_id} asks for expressions this recipe "
                f"cannot draw: {', '.join(unknown)}"
            )
    return scenario


def _resolve_profile(request: DialogueRequest, *, root: Path) -> ResolvedSceneProfile:
    resolved = resolve_character_profile_binding(
        request.character_profile,
        package_root=root,
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


def _transparency_digest(request: DialogueRequest) -> str:
    """Bind the exact derivation the canonicalize nodes will apply."""

    parts: dict[str, object] = {"transparency_mode": request.transparency_mode}
    if request.transparency_mode != "native":
        parts["magenta_edge_decontamination_version"] = MAGENTA_EDGE_DECONTAMINATION_VERSION
    if request.transparency_mode == "chroma":
        parts["chroma_matte_version"] = CHROMA_MATTE_VERSION
    return sha256(canonical_json_bytes(parts)).hexdigest()


def _scene_id(request: DialogueRequest, profile: ResolvedSceneProfile) -> str:
    return f"{profile.profile.profile_id}-{canonical_sha256(request)[:12]}"


__all__ = [
    "SCENE_DOCUMENT_NAME",
    "SCENE_ID_MAX_LENGTH",
    "ResolvedDialogueScene",
    "ResolvedSceneProfile",
    "ResolvedSceneReference",
    "parse_dialogue_request",
    "profile_lock_values",
    "read_scene_document",
    "recipe_version",
    "resolve_dialogue_scene",
    "style_selection_brief",
    "template_digest",
]
