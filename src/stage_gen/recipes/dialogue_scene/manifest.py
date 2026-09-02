"""Portable dialogue-scene bundle assembler."""

from __future__ import annotations

from collections.abc import Iterable
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
    StageDeclaration,
    TrackDeclaration,
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
    AttemptLedger,
    AttemptLedgerBinding,
    AudioFacts,
    BundleActor,
    BundleArtifact,
    BundleFile,
    BundleScenario,
    DialogueBundle,
    DialogueSceneDocument,
    DialogueScenePlan,
    MediaFacts,
    ReviewState,
    RightsState,
    ScenarioBinding,
    SceneCastBinding,
    SceneData,
)
from stage_gen.recipes.dialogue_scene.policy import POLICY_DIGEST
from stage_gen.recipes.dialogue_scene.prompts import (
    NATIVE_ALPHA_TEMPLATE_DIGEST,
    TEMPLATE_DIGEST,
)
from stage_gen.recipes.dialogue_scene.scene_request import (
    art_request_sha256,
    scenario_id_from_ref,
)

_COMPONENT = SoftwareIdentity(name="@stage-gen/dialogue-scene", version="6")


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
    # Every narrative the run publishes must be one the package declared: the
    # program names the script digest, and the scene named the scenario's. One
    # entry per binding, read in the scene's own order, so the bundle lists the
    # episode's beats the way the author wrote them down.
    scenarios = [_read_scenario(run_dir, request, binding) for binding in request.scenarios]
    for entry in scenarios:
        if entry.program.game_id != request.game_id:
            raise ValueError("published scenario game_id does not match the request")
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
    # The union across every published scenario, once each: the whole point of a
    # scene binding several is that an actor three of them show is one set of
    # plates. `_union_members` preserves first-declaration order, which is the
    # order the graph fanned out in, so the bundle lists what the run produced.
    _union_drawable_cast_checked(entry.program for entry in scenarios)
    resolved_actors = [
        _read_actor(run_dir, request, bound[member.actor_id], member)
        for member in _union_drawable_cast(entry.program for entry in scenarios)
    ]
    identity_sha = canonical_sha256(
        {
            "domain": "stage-gen/dialogue-scene/run-identity/v7",
            "recipe": "dialogue-scene-v8",
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
            "scenarios": [
                {
                    "scenario_id": entry.program.scenario_id,
                    "scenario_ref": entry.binding.ref,
                    "scenario_source_sha256": entry.binding.source_sha256,
                    "scenario_sha256": entry.program_sha256,
                }
                for entry in scenarios
            ],
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
            for stage in _union_stages(entry.program for entry in scenarios)
        ],
        # One plate per face the actor's own profile declares, not per fixed
        # state: nine people in a murder mystery do not share four expressions.
        *[
            _asset(
                run_dir,
                ledger,
                f"{actor.slug}-{_slug(expression.expression_id)}",
                "expression",
                f"assets/{actor.slug}-{_slug(expression.expression_id)}.png",
                expression.expression_id,
                actor.actor_id,
            )
            for actor in resolved_actors
            for expression in actor.profile.expressions
        ],
        *[
            await _track_asset(run_dir, ledger, track_id)
            for track_id in _union_tracks(entry.program for entry in scenarios)
        ],
        *[
            _asset(run_dir, ledger, _ui_asset_id(role), "ui", f"ui/{role}.png", None, None)
            for role in ui_roles
        ],
    ]
    bundle = DialogueBundle(
        schema_version=8,
        kind="dialogue-scene-bundle-v8",
        recipe="dialogue-scene",
        recipe_version="dialogue-scene-v8",
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
        scenarios=[entry.binding_record for entry in scenarios],
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
        scene_data=_scene_data(
            request,
            resolved_actors,
            style_anchor,
            [entry.program for entry in scenarios],
            ui_roles,
        ),
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
            model="deterministic-dialogue-bundle-v6",
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
                "scenarios": [entry.program.scenario_id for entry in scenarios],
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
class _ResolvedScenarioFiles:
    """One published narrative, its proof, and the binding both came from."""

    program: ScenarioProgram
    binding: ScenarioBinding
    program_sha256: str
    binding_record: BundleScenario


def _read_scenario(
    run_dir: Path, request: DialogueSceneDocument, binding: ScenarioBinding
) -> _ResolvedScenarioFiles:
    """Read and verify one published program and the proof that admitted it.

    Every check the single-scenario run made is made here per scenario: the
    published id must be the one the ref names, the proof must describe that same
    program, and it must actually admit it.
    """

    scenario_id = scenario_id_from_ref(binding.ref)
    slug = _slug(scenario_id)
    program_path = f"scenarios/{slug}.json"
    proof_path = f"scenarios/{slug}.validation.json"
    program_bytes = _read(run_dir, program_path)
    program_provenance = _read(run_dir, f"{program_path}.meta.json")
    _validate_provenance(program_provenance, program_bytes, f"{scenario_id} scenario")
    program = ScenarioProgram.model_validate_json(program_bytes)
    if program.scenario_id != scenario_id:
        raise ValueError(f"published scenario at {program_path} is not {scenario_id}")
    proof_bytes = _read(run_dir, proof_path)
    proof_provenance = _read(run_dir, f"{proof_path}.meta.json")
    _validate_provenance(proof_provenance, proof_bytes, f"{scenario_id} scenario proof")
    proof = ScenarioAdmissionReport.model_validate_json(proof_bytes)
    if not proof.admitted:
        raise ValueError(
            f"bundle refuses scenario {scenario_id}, which its own proof did not admit"
        )
    if proof.scenario_id != program.scenario_id:
        raise ValueError(f"scenario proof at {proof_path} does not describe {scenario_id}")
    if request.game_id != program.game_id:
        raise ValueError("published scenario game_id does not match the request")
    return _ResolvedScenarioFiles(
        program=program,
        binding=binding,
        program_sha256=content_sha256(program_bytes),
        binding_record=BundleScenario(
            scenario_id=scenario_id,
            binding=binding,
            program=BundleFile(
                path=program_path,
                sha256=content_sha256(program_bytes),
                provenance_path=f"{program_path}.meta.json",
                provenance_sha256=content_sha256(program_provenance),
            ),
            validation=BundleFile(
                path=proof_path,
                sha256=content_sha256(proof_bytes),
                provenance_path=f"{proof_path}.meta.json",
                provenance_sha256=content_sha256(proof_provenance),
            ),
            program_sha256=content_sha256(program_bytes),
        ),
    )


def _union_drawable_cast(programs: Iterable[ScenarioProgram]) -> list[ScenarioCastMember]:
    """Every actor any published scenario shows, once, in first-declaration order."""

    union: dict[str, ScenarioCastMember] = {}
    for program in programs:
        for member in program.cast:
            if member.expressions and member.actor_id not in union:
                union[member.actor_id] = member
    return list(union.values())


def _union_stages(programs: Iterable[ScenarioProgram]) -> list[StageDeclaration]:
    """One backdrop per distinct stage, refusing a collision rather than resolving it.

    `setdefault` would have been enough to make the counts come out right, and
    that is exactly the bug: two scenarios declaring one stage_id with different
    briefs would have had the first-bound one silently win, and a writer's brief
    would have vanished into the binding order of `scene.toml` with no error and
    no log line. The resolver refuses this before any spend; the bundle refuses
    it again over the published bytes, because the manifest re-proves what it
    reads rather than trusting that resolution happened.
    """

    union: dict[str, StageDeclaration] = {}
    for program in programs:
        for stage in program.stages:
            existing = union.get(stage.stage_id)
            if existing is not None and existing != stage:
                raise ValueError(
                    f"published scenarios declare stage {stage.stage_id} with different "
                    f"briefs: {existing.brief!r} and {stage.brief!r}"
                )
            union[stage.stage_id] = stage
    return list(union.values())


def _union_tracks(programs: Iterable[ScenarioProgram]) -> list[str]:
    """One recording per distinct track identity, on the same terms as the stages."""

    union: dict[str, TrackDeclaration] = {}
    for program in programs:
        for track in program.tracks:
            existing = union.get(track.track_id)
            if existing is not None and existing != track:
                raise ValueError(
                    f"published scenarios declare track {track.track_id} with different "
                    f"briefs or generation intent: {existing.brief!r} and {track.brief!r}"
                )
            union[track.track_id] = track
    return list(union)


def _union_drawable_cast_checked(programs: Iterable[ScenarioProgram]) -> None:
    """Refuse two published scenarios that disagree about who an actor is."""

    seen: dict[str, str | None] = {}
    for program in programs:
        for member in program.cast:
            if not member.expressions:
                continue
            if member.actor_id in seen:
                first = seen[member.actor_id]
                if (
                    first is not None
                    and member.display_name is not None
                    and first != member.display_name
                ):
                    raise ValueError(
                        f"published scenarios give actor {member.actor_id} different display "
                        f"names: {first} and {member.display_name}"
                    )
                continue
            seen[member.actor_id] = member.display_name


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


def _fit(value: str, limit: int) -> str:
    """Cut authored prose to a projection's limit without leaving a ragged edge.

    A bare slice is a latent refusal. Every persisted string in this contract must
    be trimmed, so an author whose sentence happens to put a space at exactly
    character `limit` produced a value the bundle then refused - at the terminal
    node, after every image in the scene had been drawn and paid for. The length
    of somebody's prose is not something they should have to think about, and it
    is certainly not something they should discover after a run.

    Cutting back to the last word boundary as well, because these fields are
    titles and alt text: a reader may hear `alt`, and a word severed mid-syllable
    is worse than a slightly shorter sentence. The boundary is only honoured when
    it keeps most of the budget, so a single very long word still gets cut rather
    than collapsing the field to nothing.
    """

    text = value.strip()
    if len(text) <= limit:
        return text
    head = text[:limit].rstrip()
    boundary = head.rfind(" ")
    if boundary > limit // 2:
        head = head[:boundary]
    trimmed = head.rstrip(" ,;:-").strip()
    return trimmed or text[:limit].strip()


def _slug(value: str) -> str:
    return value.replace("_", "-")


def _ui_asset_id(relative_path: str) -> str:
    """The bundle asset id for one atlas role's sheet, from its published path."""

    return f"ui-{PurePosixPath(relative_path).stem.replace('_', '-')}"


def _scene_data(
    request: DialogueSceneDocument,
    actors: list[_ResolvedActorFiles],
    style_anchor: CanonicalStyleAnchor,
    scenarios: list[ScenarioProgram],
    ui_roles: dict[str, object],
) -> SceneData:
    return SceneData.model_validate(
        {
            "scene_id": f"{_slug(request.game_id)}-scene",
            # The scene's own name, not the first scenario's: a scene that binds
            # six beats of one episode is not called after whichever beat happens
            # to be bound first.
            "title": _fit(request.display_name, 96),
            "scene_label": _fit(request.scene_brief, 160),
            "style_asset_id": "style-plate",
            "stages": [
                {
                    "stage_id": stage.stage_id,
                    "asset_id": _slug(stage.stage_id),
                    "alt": _fit(stage.brief, 160),
                }
                for stage in _union_stages(scenarios)
            ],
            "tracks": [
                {"track_id": track_id, "asset_id": f"track-{_slug(track_id)}"}
                for track_id in _union_tracks(scenarios)
            ],
            "actors": [
                {
                    "actor_id": actor.actor_id,
                    "appearance": {
                        "id": actor.profile.profile_id,
                        "label": actor.profile.display_name,
                        "age": actor.profile.age_years,
                        "role": _fit(actor.profile.description, 120),
                        "tagline": _fit(actor.profile.description, 120),
                        "description": actor.profile.description,
                        "visual_identity": actor.profile.visual_identity,
                        "art_direction": style_anchor.medium_keyword,
                    },
                    # Label and description come from the character's author, not
                    # from a table in this module: a fixed table could only ever
                    # have described one genre's four faces.
                    "expression_variants": [
                        {
                            "id": f"{actor.slug}-{_slug(expression.expression_id)}",
                            "asset_id": f"{actor.slug}-{_slug(expression.expression_id)}",
                            "appearance_id": actor.profile.profile_id,
                            "state": expression.expression_id,
                            "label": expression.label,
                            "description": expression.description,
                            "alt": _fit(
                                f"{actor.profile.display_name}, {expression.label.lower()}", 160
                            ),
                        }
                        for expression in actor.profile.expressions
                    ],
                }
                for actor in actors
            ],
            "placement": {
                "framing_zoom": request.presentation.framing_zoom,
                "source_framing_zoom": request.presentation.source_framing_zoom,
            },
            "available_states": sorted(
                {
                    expression.expression_id
                    for actor in actors
                    for expression in actor.profile.expressions
                }
            ),
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
            "scenarios": scenarios,
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
