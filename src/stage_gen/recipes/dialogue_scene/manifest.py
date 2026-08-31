"""Portable dialogue-scene bundle assembler."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast

from gnode import (
    ArtifactProvenance,
    ArtifactRights,
    BinaryArtifact,
    ProvenanceInput,
    SoftwareIdentity,
    resolve_relative_path_within_root,
    write_artifact_with_provenance_async,
)
from stage_gen.components import CharacterProfile, character_profile_sha256
from stage_gen.identity import STAGE_GEN_TOOL
from stage_gen.image_style import CanonicalStyleAnchor, canonical_style_anchor_digest
from stage_gen.media import inspect_image
from stage_gen.recipes.dialogue_scene.identity import (
    canonical_json_bytes,
    canonical_sha256,
    content_sha256,
)
from stage_gen.recipes.dialogue_scene.models import (
    EXPRESSION_STATES,
    AttemptLedger,
    AttemptLedgerBinding,
    BundleArtifact,
    BundleFile,
    DialogueBundle,
    DialogueSceneDocument,
    DialogueScenePlan,
    MediaFacts,
    ReviewState,
    RightsState,
    SceneData,
)
from stage_gen.recipes.dialogue_scene.policy import POLICY_DIGEST
from stage_gen.recipes.dialogue_scene.prompts import (
    NATIVE_ALPHA_TEMPLATE_DIGEST,
    TEMPLATE_DIGEST,
)

_COMPONENT = SoftwareIdentity(name="@stage-gen/dialogue-scene", version="5")


async def write_dialogue_bundle(run_dir: Path, *, tag: str) -> tuple[str, ...]:
    """Assemble the portable bundle from one completed run directory."""

    request_bytes = _read(run_dir, "request.json")
    request_provenance = _read(run_dir, "request.json.meta.json")
    _validate_provenance(request_provenance, request_bytes, "request")
    request = DialogueSceneDocument.model_validate_json(request_bytes)
    profile_bytes = _read(run_dir, "character-profile.json")
    profile_provenance = _read(run_dir, "character-profile.json.meta.json")
    _validate_provenance(profile_provenance, profile_bytes, "character profile")
    profile = CharacterProfile.model_validate_json(profile_bytes)
    profile_sha256 = character_profile_sha256(profile)
    if profile_sha256 != content_sha256(profile_bytes):
        raise ValueError("character profile artifact is not canonical")
    plan_bytes = _read(run_dir, "plan.json")
    plan_provenance = _read(run_dir, "plan.json.meta.json")
    _validate_provenance(plan_provenance, plan_bytes, "plan")
    plan = DialogueScenePlan.model_validate_json(plan_bytes)
    if plan.request_sha256 != canonical_sha256(request):
        raise ValueError("bundle plan request digest does not match canonical request")
    expected_profile = (
        request.character_profile.ref,
        request.character_profile.source_sha256,
        profile_sha256,
    )
    actual_profile = (
        plan.character_profile_ref,
        plan.character_profile_source_sha256,
        plan.character_profile_sha256,
    )
    if actual_profile != expected_profile:
        raise ValueError("bundle plan character profile binding mismatch")
    # The run must ship the exact plate the package declared, not a lookalike:
    # the republished bytes are compared to the author's digest, not its path.
    authored_reference = request.identity_reference()
    concept_bytes = _read(run_dir, "assets/concept.png")
    concept_provenance = _read(run_dir, "assets/concept.png.meta.json")
    concept_sha256 = content_sha256(concept_bytes)
    if concept_sha256 != authored_reference.source_sha256:
        raise ValueError("published identity plate does not match the authored reference digest")
    if plan.identity_reference_sha256 != concept_sha256:
        raise ValueError("bundle plan identity reference binding mismatch")
    ledger_bytes = _read(run_dir, "attempts.json")
    ledger = AttemptLedger.model_validate_json(ledger_bytes)
    style_anchor_bytes = _read(run_dir, "style-anchor.json")
    style_anchor_provenance = _read(run_dir, "style-anchor.json.meta.json")
    _validate_provenance(style_anchor_provenance, style_anchor_bytes, "style anchor")
    style_anchor = CanonicalStyleAnchor.model_validate_json(style_anchor_bytes)
    style_binding = _style_binding(style_anchor)
    identity_sha = canonical_sha256(
        {
            "domain": "stage-gen/dialogue-scene/run-identity/v5",
            "recipe": "dialogue-scene-v5",
            "game_id": request.game_id,
            "request_sha256": canonical_sha256(request),
            "identity_reference_source": authored_reference.source,
            "identity_reference_sha256": concept_sha256,
            "character_profile_ref": request.character_profile.ref,
            "character_profile_source_sha256": request.character_profile.source_sha256,
            "character_profile_sha256": profile_sha256,
            "policy_sha256": POLICY_DIGEST,
            "profile": "expression-core-v3",
            "template_sha256": (
                NATIVE_ALPHA_TEMPLATE_DIGEST
                if request.transparency_mode == "native"
                else TEMPLATE_DIGEST
            ),
            "transparency_mode": request.transparency_mode,
            "normalization": "pillow-dialogue-v2",
            **style_binding,
        }
    )
    assets = [
        _asset(run_dir, ledger, "concept", "concept", "assets/concept.png", None),
        _asset(run_dir, ledger, "background", "background", "assets/background.png", None),
        *[
            _asset(
                run_dir,
                ledger,
                f"{profile.profile_id}-{state}",
                "expression",
                f"assets/expression-{state}.png",
                state,
            )
            for state in EXPRESSION_STATES
        ],
    ]
    profile_file = BundleFile(
        path="character-profile.json",
        sha256=content_sha256(profile_bytes),
        provenance_path="character-profile.json.meta.json",
        provenance_sha256=content_sha256(profile_provenance),
    )
    bundle = DialogueBundle(
        schema_version=4,
        kind="dialogue-scene-bundle-v4",
        recipe="dialogue-scene",
        recipe_version="dialogue-scene-v5",
        tag=tag,
        game_id=request.game_id,
        run_identity_sha256=identity_sha,
        request=BundleFile(
            path="request.json",
            sha256=content_sha256(request_bytes),
            provenance_path="request.json.meta.json",
            provenance_sha256=content_sha256(request_provenance),
        ),
        plan=BundleFile(
            path="plan.json",
            sha256=content_sha256(plan_bytes),
            provenance_path="plan.json.meta.json",
            provenance_sha256=content_sha256(plan_provenance),
        ),
        character_profile=profile_file,
        character_profile_binding=request.character_profile,
        character_profile_sha256=profile_sha256,
        identity_reference=BundleFile(
            path="assets/concept.png",
            sha256=concept_sha256,
            provenance_path="assets/concept.png.meta.json",
            provenance_sha256=content_sha256(concept_provenance),
        ),
        identity_reference_source=authored_reference.source,
        assets=assets,
        attempt_ledger=AttemptLedgerBinding(
            path="attempts.json", sha256=content_sha256(ledger_bytes)
        ),
        scene_data=_profile_scene_data(request, profile, style_anchor),
        review=ReviewState(status="pending", path=None, sha256=None),
        rights=RightsState(aggregate="unreviewed", publication_authorized=False),
    )
    data = canonical_json_bytes(bundle) + b"\n"
    provenance = await write_artifact_with_provenance_async(
        run_dir / "bundle.json",
        BinaryArtifact(data=data, media_type="application/json"),
        ProvenanceInput(
            schema_version=2,
            provider="local",
            model="deterministic-dialogue-bundle-v5",
            prompt="Assemble the authored scene package's assets into the portable bundle.",
            refs=[
                "request.json",
                "plan.json",
                "character-profile.json",
                "character-profile.json.meta.json",
                "attempts.json",
                "style-anchor.json",
                "style-anchor.json.meta.json",
            ],
            params={
                "run_identity_sha256": identity_sha,
                "selected_assets": len(assets),
                "character_profile_ref": request.character_profile.ref,
                "character_profile_source_sha256": request.character_profile.source_sha256,
                "identity_reference_source": authored_reference.source,
                "identity_reference_sha256": concept_sha256,
                "character_profile_path": "character-profile.json",
                "character_profile_sha256": profile_sha256,
                "character_profile_provenance_path": "character-profile.json.meta.json",
                "character_profile_provenance_sha256": content_sha256(profile_provenance),
                "style_anchor_path": "style-anchor.json",
                "style_anchor_artifact_sha256": content_sha256(style_anchor_bytes),
                "style_anchor_provenance_path": "style-anchor.json.meta.json",
                "style_anchor_provenance_sha256": content_sha256(style_anchor_provenance),
                **style_binding,
            },
            validation={
                "strict_schema": True,
                "portable_paths": True,
                "profile_source_digest_verified": True,
                "profile_canonical_digest_verified": True,
                "identity_reference_digest_verified": True,
            },
            component=_COMPONENT,
            tool=STAGE_GEN_TOOL,
            attempts=1,
            rights=ArtifactRights(
                status="unreviewed",
                attribution=[],
                basis=[],
                reviewed_at=None,
            ),
        ),
    )
    return ("bundle.json", provenance.relative_to(run_dir).as_posix())


def _profile_scene_data(
    request: DialogueSceneDocument,
    profile: CharacterProfile,
    style_anchor: CanonicalStyleAnchor,
) -> SceneData:
    role = profile.description[:120]
    return SceneData.model_validate(
        {
            "scene_id": f"{profile.profile_id}-scene",
            "title": request.scene_brief[:96],
            "scene_label": request.scene_brief[:160],
            "concept_asset_id": "concept",
            "background": {
                "asset_id": "background",
                "alt": f"Dialogue background for {request.scene_brief}"[:160],
            },
            "appearance": {
                "id": profile.profile_id,
                "label": profile.display_name,
                "age": profile.age_years,
                "role": role,
                "tagline": role,
                "description": profile.description,
                "visual_identity": profile.visual_identity,
                "art_direction": style_anchor.medium_keyword,
            },
            "placement": {
                "slot": request.presentation.slot,
                "framing_zoom": request.presentation.framing_zoom,
                "source_framing_zoom": request.presentation.source_framing_zoom,
            },
            "available_states": list(EXPRESSION_STATES),
            "expression_variants": [
                {
                    "id": f"{profile.profile_id}-{state}",
                    "asset_id": f"{profile.profile_id}-{state}",
                    "appearance_id": profile.profile_id,
                    "state": state,
                    "label": _expression_copy(state)[0],
                    "description": _expression_copy(state)[1],
                    "alt": f"{profile.display_name} with a {state} expression"[:160],
                    "slot": request.presentation.slot,
                }
                for state in EXPRESSION_STATES
            ],
            "dialogue": [beat.model_dump(mode="json") for beat in request.dialogue],
        }
    )


def _asset(
    run_dir: Path,
    ledger: AttemptLedger,
    asset_id: str,
    role: str,
    path: str,
    state: str | None,
) -> BundleArtifact:
    data = _read(run_dir, path)
    provenance_path = f"{path}.meta.json"
    provenance = _read(run_dir, provenance_path)
    _validate_provenance(provenance, data, f"asset {asset_id}")
    facts = inspect_image(data, expected_media_type="image/png")
    selected = [
        attempt
        for attempt in ledger.attempts
        if attempt.outcome == "selected" and attempt.artifact == path
    ]
    selected_attempt = selected[-1].attempt if selected else 0
    return BundleArtifact(
        id=asset_id,
        role=cast(Literal["concept", "background", "expression"], role),
        state=cast(Any, state),
        path=path,
        sha256=content_sha256(data),
        bytes=len(data),
        media=MediaFacts(
            mime_type="image/png",
            width=facts.width,
            height=facts.height,
            alpha=facts.has_alpha,
        ),
        provenance_path=provenance_path,
        provenance_sha256=content_sha256(provenance),
        selected_attempt=selected_attempt,
    )


def _style_binding(anchor: CanonicalStyleAnchor) -> dict[str, object]:
    return {
        "style_anchor_sha256": canonical_style_anchor_digest(anchor),
        "style_compiler_sha256": anchor.compiler_sha256,
        "style_compiler_version": anchor.compiler_version,
        "style_resource_sha256": anchor.resource_sha256,
        "style_skill_sha256": anchor.skill_sha256,
        "style_vocabulary_sha256": anchor.vocabulary_sha256,
    }


def _validate_provenance(data: bytes, artifact: bytes, label: str) -> None:
    record = ArtifactProvenance.model_validate_json(data)
    if record.schema_version != 2:
        raise ValueError(f"{label} provenance must use schema_version 2")
    if record.artifact is None or record.artifact.sha256 != content_sha256(artifact):
        raise ValueError(f"{label} provenance artifact digest mismatch")


def _read(run_dir: Path, relative: str) -> bytes:
    return resolve_relative_path_within_root(run_dir, relative, "dialogue bundle path").read_bytes()


def _expression_copy(state: str) -> tuple[str, str]:
    return {
        "neutral": ("Composed", "Composed and attentive with direct adult eye contact"),
        "delighted": ("Delighted", "Warm open delight with bright eyes and an unguarded smile"),
        "flustered": ("Flustered", "Warmly flustered with a faint blush and shy half-smile"),
        "concerned": ("Concerned", "Focused adult concern with drawn brows and a firm mouth"),
    }[state]
