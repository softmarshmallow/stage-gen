"""Portable dialogue-scene bundle assembler."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
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
from stage_gen.components.game_ui.nodes import ui_atlas_manifest_block
from stage_gen.components.scenario import (
    CastMember as ScenarioCastMember,
)
from stage_gen.components.scenario import (
    ScenarioAdmissionReport,
    ScenarioProgram,
)
from stage_gen.identity import STAGE_GEN_TOOL
from stage_gen.image_style import CanonicalStyleAnchor, canonical_style_anchor_digest
from stage_gen.media import inspect_image, probe_audio
from stage_gen.recipes.dialogue_scene.identity import (
    canonical_json_bytes,
    canonical_sha256,
    content_sha256,
)
from stage_gen.recipes.dialogue_scene.models import (
    EXPRESSION_STATES,
    AttemptLedger,
    AttemptLedgerBinding,
    AudioFacts,
    BundleActor,
    BundleArtifact,
    BundleFile,
    DialogueBundle,
    DialogueSceneDocument,
    DialogueScenePlan,
    MediaFacts,
    ReviewState,
    RightsState,
    SceneCastBinding,
    SceneData,
)
from stage_gen.recipes.dialogue_scene.policy import POLICY_DIGEST
from stage_gen.recipes.dialogue_scene.prompts import (
    NATIVE_ALPHA_TEMPLATE_DIGEST,
    TEMPLATE_DIGEST,
)
from stage_gen.recipes.dialogue_scene.scene_request import art_request_sha256

_COMPONENT = SoftwareIdentity(name="@stage-gen/dialogue-scene", version="5")


async def write_dialogue_bundle(run_dir: Path, *, tag: str) -> tuple[str, ...]:
    """Assemble the portable bundle from one completed run directory."""

    request_bytes = _read(run_dir, "request.json")
    request_provenance = _read(run_dir, "request.json.meta.json")
    _validate_provenance(request_provenance, request_bytes, "request")
    request = DialogueSceneDocument.model_validate_json(request_bytes)
    # The published file must be the canonical document, not merely parse to it,
    # so a consumer holding the bundle and the file can compare the two digests.
    if content_sha256(request_bytes) != canonical_sha256(request):
        raise ValueError("request artifact is not canonical")
    # The run must ship the exact plate the package declared, not a lookalike:
    # the republished bytes are compared to the author's digest, not its path.
    authored_reference = request.style_reference()
    style_bytes = _read(run_dir, "assets/style-plate.png")
    style_provenance = _read(run_dir, "assets/style-plate.png.meta.json")
    style_sha256 = content_sha256(style_bytes)
    if style_sha256 != authored_reference.source_sha256:
        raise ValueError("published style plate does not match the authored reference digest")
    # The narrative the run publishes must be the narrative the package declared:
    # the program names the script digest, and the scene named the scenario's.
    scenario_bytes = _read(run_dir, "scenario.json")
    scenario_provenance = _read(run_dir, "scenario.json.meta.json")
    _validate_provenance(scenario_provenance, scenario_bytes, "scenario")
    scenario_program = ScenarioProgram.model_validate_json(scenario_bytes)
    if scenario_program.game_id != request.game_id:
        raise ValueError("published scenario game_id does not match the request")
    scenario_proof_bytes = _read(run_dir, "scenario.validation.json")
    scenario_proof_provenance = _read(run_dir, "scenario.validation.json.meta.json")
    _validate_provenance(scenario_proof_provenance, scenario_proof_bytes, "scenario proof")
    scenario_proof = ScenarioAdmissionReport.model_validate_json(scenario_proof_bytes)
    if not scenario_proof.admitted:
        raise ValueError("bundle refuses a scenario its own proof did not admit")
    if scenario_proof.scenario_id != scenario_program.scenario_id:
        raise ValueError("scenario proof does not describe the published scenario")
    ledger_bytes = _read(run_dir, "attempts.json")
    ledger = AttemptLedger.model_validate_json(ledger_bytes)
    style_anchor_bytes = _read(run_dir, "style-anchor.json")
    style_anchor_provenance = _read(run_dir, "style-anchor.json.meta.json")
    _validate_provenance(style_anchor_provenance, style_anchor_bytes, "style anchor")
    style_anchor = CanonicalStyleAnchor.model_validate_json(style_anchor_bytes)
    style_binding = _style_binding(style_anchor)
    # One profile and one plan per drawable actor, each held to the same rules the
    # single-character run always applied - the fan-out widened the count, not the
    # standard of proof.
    bound = {member.actor_id: member for member in request.cast}
    resolved_actors = [
        _read_actor(run_dir, request, bound[member.actor_id], member)
        for member in scenario_program.cast
        if member.expressions
    ]
    identity_sha = canonical_sha256(
        {
            "domain": "stage-gen/dialogue-scene/run-identity/v6",
            "recipe": "dialogue-scene-v7",
            "game_id": request.game_id,
            "request_sha256": canonical_sha256(request),
            "style_reference_source": authored_reference.source,
            "style_reference_sha256": style_sha256,
            "cast": [
                {
                    "actor_id": actor.actor_id,
                    "character_profile_sha256": actor.profile_sha256,
                }
                for actor in resolved_actors
            ],
            "scenario_ref": request.scenario.ref,
            "scenario_source_sha256": request.scenario.source_sha256,
            "scenario_sha256": content_sha256(scenario_bytes),
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
    # The interface geometry is read from the gate's own record, so the bundle publishes
    # what was measured on the artwork rather than what the template declared.
    ui_roles = ui_atlas_manifest_block(
        read_validation=lambda path: _read(run_dir, path),
        publish=_ui_asset_id,
        publish_provenance=lambda _path: None,
    )
    assets = [
        _asset(run_dir, ledger, "style-plate", "style", "assets/style-plate.png", None, None),
        *[
            _asset(
                run_dir,
                ledger,
                _slug(stage.stage_id),
                "background",
                f"assets/stage-{_slug(stage.stage_id)}.png",
                None,
                None,
            )
            for stage in scenario_program.stages
        ],
        *[
            _asset(
                run_dir,
                ledger,
                f"{actor.slug}-{state}",
                "expression",
                f"assets/{actor.slug}-{state}.png",
                state,
                actor.actor_id,
            )
            for actor in resolved_actors
            for state in EXPRESSION_STATES
        ],
        *[await _track_asset(run_dir, ledger, track.track_id) for track in scenario_program.tracks],
        *[
            _asset(run_dir, ledger, _ui_asset_id(role), "ui", f"ui/{role}.png", None, None)
            for role in ui_roles
        ],
    ]
    bundle = DialogueBundle(
        schema_version=7,
        kind="dialogue-scene-bundle-v7",
        recipe="dialogue-scene",
        recipe_version="dialogue-scene-v7",
        tag=tag,
        game_id=request.game_id,
        run_identity_sha256=identity_sha,
        request=BundleFile(
            path="request.json",
            sha256=content_sha256(request_bytes),
            provenance_path="request.json.meta.json",
            provenance_sha256=content_sha256(request_provenance),
        ),
        actors=[actor.binding for actor in resolved_actors],
        scenario=BundleFile(
            path="scenario.json",
            sha256=content_sha256(scenario_bytes),
            provenance_path="scenario.json.meta.json",
            provenance_sha256=content_sha256(scenario_provenance),
        ),
        scenario_validation=BundleFile(
            path="scenario.validation.json",
            sha256=content_sha256(scenario_proof_bytes),
            provenance_path="scenario.validation.json.meta.json",
            provenance_sha256=content_sha256(scenario_proof_provenance),
        ),
        scenario_binding=request.scenario,
        scenario_sha256=content_sha256(scenario_bytes),
        style_reference=BundleFile(
            path="assets/style-plate.png",
            sha256=style_sha256,
            provenance_path="assets/style-plate.png.meta.json",
            provenance_sha256=content_sha256(style_provenance),
        ),
        style_reference_source=authored_reference.source,
        assets=assets,
        attempt_ledger=AttemptLedgerBinding(
            path="attempts.json", sha256=content_sha256(ledger_bytes)
        ),
        scene_data=_scene_data(request, resolved_actors, style_anchor, scenario_program, ui_roles),
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
                "style_reference_source": authored_reference.source,
                "style_reference_sha256": style_sha256,
                "cast": [actor.actor_id for actor in resolved_actors],
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


@dataclass(frozen=True, slots=True)
class _ResolvedActorFiles:
    """One drawable actor's published members, already held to their digests."""

    actor_id: str
    slug: str
    profile: CharacterProfile
    profile_sha256: str
    binding: BundleActor


def _read_actor(
    run_dir: Path,
    request: DialogueSceneDocument,
    binding: SceneCastBinding,
    member: ScenarioCastMember,
) -> _ResolvedActorFiles:
    """Read and verify one actor's published profile and plan.

    Every check the single-character run made is made here per actor: the profile
    artifact must be canonical, the plan must bind that profile, and both must be
    the members the authored scene named.
    """

    slug = _slug(member.actor_id)
    profile_path = f"characters/{slug}.json"
    profile_bytes = _read(run_dir, profile_path)
    profile_provenance = _read(run_dir, f"{profile_path}.meta.json")
    _validate_provenance(profile_provenance, profile_bytes, f"{member.actor_id} profile")
    profile = CharacterProfile.model_validate_json(profile_bytes)
    profile_sha256 = character_profile_sha256(profile)
    if profile_sha256 != content_sha256(profile_bytes):
        raise ValueError(f"{member.actor_id} profile artifact is not canonical")

    plan_path = f"plans/{slug}.json"
    plan_bytes = _read(run_dir, plan_path)
    plan_provenance = _read(run_dir, f"{plan_path}.meta.json")
    _validate_provenance(plan_provenance, plan_bytes, f"{member.actor_id} plan")
    plan = DialogueScenePlan.model_validate_json(plan_bytes)
    if plan.art_request_sha256 != art_request_sha256(request):
        raise ValueError(f"{member.actor_id} plan art-request digest does not match the request")
    expected = (
        binding.character_profile.ref,
        binding.character_profile.source_sha256,
        profile_sha256,
    )
    actual = (
        plan.character_profile_ref,
        plan.character_profile_source_sha256,
        plan.character_profile_sha256,
    )
    if actual != expected:
        raise ValueError(f"{member.actor_id} plan character profile binding mismatch")

    return _ResolvedActorFiles(
        actor_id=member.actor_id,
        slug=slug,
        profile=profile,
        profile_sha256=profile_sha256,
        binding=BundleActor(
            actor_id=member.actor_id,
            character_profile=BundleFile(
                path=profile_path,
                sha256=content_sha256(profile_bytes),
                provenance_path=f"{profile_path}.meta.json",
                provenance_sha256=content_sha256(profile_provenance),
            ),
            character_profile_binding=binding.character_profile,
            character_profile_sha256=profile_sha256,
            plan=BundleFile(
                path=plan_path,
                sha256=content_sha256(plan_bytes),
                provenance_path=f"{plan_path}.meta.json",
                provenance_sha256=content_sha256(plan_provenance),
            ),
        ),
    )


def _slug(value: str) -> str:
    return value.replace("_", "-")


def _ui_asset_id(relative_path: str) -> str:
    """The bundle asset id for one atlas role's sheet, from its published path."""

    return f"ui-{PurePosixPath(relative_path).stem.replace('_', '-')}"


def _scene_data(
    request: DialogueSceneDocument,
    actors: list[_ResolvedActorFiles],
    style_anchor: CanonicalStyleAnchor,
    scenario: ScenarioProgram,
    ui_roles: dict[str, object],
) -> SceneData:
    return SceneData.model_validate(
        {
            "scene_id": f"{_slug(request.game_id)}-scene",
            "title": scenario.display_name[:96],
            "scene_label": request.scene_brief[:160],
            "style_asset_id": "style-plate",
            "stages": [
                {
                    "stage_id": stage.stage_id,
                    "asset_id": _slug(stage.stage_id),
                    "alt": stage.brief[:160],
                }
                for stage in scenario.stages
            ],
            "tracks": [
                {"track_id": track.track_id, "asset_id": f"track-{_slug(track.track_id)}"}
                for track in scenario.tracks
            ],
            "actors": [
                {
                    "actor_id": actor.actor_id,
                    "appearance": {
                        "id": actor.profile.profile_id,
                        "label": actor.profile.display_name,
                        "age": actor.profile.age_years,
                        "role": actor.profile.description[:120],
                        "tagline": actor.profile.description[:120],
                        "description": actor.profile.description,
                        "visual_identity": actor.profile.visual_identity,
                        "art_direction": style_anchor.medium_keyword,
                    },
                    "expression_variants": [
                        {
                            "id": f"{actor.slug}-{state}",
                            "asset_id": f"{actor.slug}-{state}",
                            "appearance_id": actor.profile.profile_id,
                            "state": state,
                            "label": _expression_copy(state)[0],
                            "description": _expression_copy(state)[1],
                            "alt": f"{actor.profile.display_name} looking {state}"[:160],
                        }
                        for state in EXPRESSION_STATES
                    ],
                }
                for actor in actors
            ],
            "placement": {
                "framing_zoom": request.presentation.framing_zoom,
                "source_framing_zoom": request.presentation.source_framing_zoom,
            },
            "available_states": list(EXPRESSION_STATES),
            # The shared projection names the sheet by path; a bundle names everything by
            # asset id instead, so the path is replaced rather than carried beside it.
            "ui": {
                role: {
                    **{
                        key: value
                        for key, value in cast(dict[str, object], layout).items()
                        if key != "asset"
                    },
                    "asset_id": _ui_asset_id(f"{role}.png"),
                }
                for role, layout in ui_roles.items()
            },
            "scenario": scenario,
        }
    )


async def _track_asset(
    run_dir: Path,
    ledger: AttemptLedger,
    track_id: str,
) -> BundleArtifact:
    """One generated track, with its duration probed from the decoded stream."""

    asset_id = f"track-{_slug(track_id)}"
    path = f"assets/{asset_id}.mp3"
    data = _read(run_dir, path)
    provenance_path = f"{path}.meta.json"
    provenance = _read(run_dir, provenance_path)
    _validate_provenance(provenance, data, f"asset {asset_id}")
    probe = await probe_audio(run_dir / path, timeout_seconds=120)
    selected = [
        attempt
        for attempt in ledger.attempts
        if attempt.outcome == "selected" and attempt.artifact == path
    ]
    return BundleArtifact(
        id=asset_id,
        role="track",
        track_id=track_id,
        path=path,
        sha256=content_sha256(data),
        bytes=len(data),
        media=AudioFacts(mime_type="audio/mpeg", duration_seconds=round(probe.duration_seconds, 3)),
        provenance_path=provenance_path,
        provenance_sha256=content_sha256(provenance),
        selected_attempt=selected[-1].attempt if selected else 0,
    )


def _asset(
    run_dir: Path,
    ledger: AttemptLedger,
    asset_id: str,
    role: str,
    path: str,
    state: str | None,
    actor_id: str | None,
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
        role=cast(Literal["style", "background", "expression"], role),
        state=cast(Any, state),
        actor_id=actor_id,
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
