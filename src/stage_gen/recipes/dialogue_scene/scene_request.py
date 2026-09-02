"""Resolve one authored scene package into everything the plan is built from.

Planning must be able to state the whole graph - and refuse a bad package - without
reaching a provider. Every digest a node's cache key needs is settled here: the
canonical scene document, the policy, the prompt templates, the transparency
derivation, the packaged style resources, the authored character profile, and the
authored reference images the scene is drawn against.

A scene binds several scenarios. Everything the graph fans out over - stages,
drawable cast, tracks - is the **union** across them, computed here, so the same
room, actor or track named by three scenarios resolves to one entry and is drawn
once. Two scenarios that name one id with different content are refused rather
than silently reconciled: which of the two briefs the one backdrop should be
drawn from is not a question the pipeline may answer for the author.

A scene is a directory, not a loose request file. Every member it names is read from
inside that directory, confined to it, following no symlink, and matched against the
digest the author recorded.
"""

from __future__ import annotations

import re
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
    CharacterExpression,
    CharacterProfile,
    CharacterProfileBinding,
    resolve_character_profile_binding,
)
from stage_gen.components.game_ui import GameUi, UiReference, load_game_ui_bytes
from stage_gen.components.scenario import (
    CastMember,
    ResolvedScenario,
    StageDeclaration,
    TrackDeclaration,
    resolve_scenario,
)
from stage_gen.image_prompting import load_image_style_resources
from stage_gen.media import (
    CHROMA_MATTE_VERSION,
    MAGENTA_EDGE_DECONTAMINATION_VERSION,
    inspect_image,
)
from stage_gen.recipes.dialogue_scene.identity import (
    canonical_json_bytes,
    canonical_sha256,
)
from stage_gen.recipes.dialogue_scene.models import (
    MAXIMUM_EXPRESSIONS,
    MINIMUM_EXPRESSIONS,
    DialogueRequest,
    DialogueSceneDocument,
    RightsStatus,
    ScenarioBinding,
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
UI_DOCUMENT_NAME = "ui.toml"
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
class ResolvedSceneActor:
    """One drawable actor, with the profile and optional plate that draw it."""

    actor_id: str
    display_name: str
    #: The faces this actor can wear, in the profile's authored drawing order.
    #: The first is the base plate; the rest are face-only edits of it.
    expressions: tuple[CharacterExpression, ...]
    profile: ResolvedSceneProfile
    #: This actor's own authored plate, when the scene bound one. Absent means the
    #: actor is drawn from its profile words against the scene style plate alone.
    identity_reference: ResolvedSceneReference | None

    @property
    def asset_prefix(self) -> str:
        return self.actor_id.replace("_", "-")

    @property
    def base(self) -> CharacterExpression:
        """The face generated from scratch; every other one is an edit of it."""

        return self.expressions[0]

    @property
    def edits(self) -> tuple[CharacterExpression, ...]:
        return self.expressions[1:]


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
    #: Every drawable actor any bound scenario names, once, in binding order.
    actors: tuple[ResolvedSceneActor, ...]
    #: The scene's art direction of record: medium, palette and light for every
    #: generated image, actor plates included.
    style_reference: ResolvedSceneReference
    #: The bound narratives, in the order the scene declared them.
    scenarios: tuple[ResolvedScenario, ...]
    #: The union the graph fans out over: one entry per distinct id, in first-
    #: declaration order, already proven identical wherever two scenarios agree.
    stages: tuple[StageDeclaration, ...]
    tracks: tuple[TrackDeclaration, ...]
    #: The scene's screen-fixed interface art direction. Separate from the narrative on
    #: purpose: the dialogue box knows nothing about what is said inside it, and the
    #: nine-slice roles it names are the same ones every other genre draws.
    ui: GameUi
    ui_sha256: str
    #: Every reference the UI roles select, by its declared source path.
    ui_references: dict[str, ResolvedSceneReference]

    def actor(self, actor_id: str) -> ResolvedSceneActor:
        return next(actor for actor in self.actors if actor.actor_id == actor_id)

    def scenario(self, scenario_id: str) -> ResolvedScenario:
        return next(item for item in self.scenarios if item.declarations.scenario_id == scenario_id)

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
            "cast": [
                {
                    "actor_id": actor.actor_id,
                    "character_profile_ref": actor.profile.ref,
                    "character_profile_sha256": actor.profile.canonical_sha256,
                    "character_profile_source_sha256": actor.profile.source_sha256,
                    "identity_reference_sha256": (
                        None
                        if actor.identity_reference is None
                        else actor.identity_reference.sha256
                    ),
                    "expressions": [item.expression_id for item in actor.expressions],
                }
                for actor in self.actors
            ],
            "style_reference_source": self.style_reference.source,
            "style_reference_sha256": self.style_reference.sha256,
            "scenarios": [
                {
                    "scenario_id": scenario.declarations.scenario_id,
                    "scenario_ref": binding.ref,
                    "scenario_source_sha256": binding.source_sha256,
                    "scenario_program_sha256": scenario.program_sha256,
                }
                for binding, scenario in zip(self.request.scenarios, self.scenarios, strict=True)
            ],
            "ui_sha256": self.ui_sha256,
        }


def _read_ui_document(root: Path) -> bytes:
    """Read the scene's UI contract, following no symlink, as its own document."""

    path = (root / UI_DOCUMENT_NAME).resolve()
    return read_absolute_regular_file(path, label="scene UI document")


def _read_ui_reference(root: Path, reference: UiReference) -> ResolvedSceneReference:
    """One UI reference, read under the same confinement and digest binding as the scene's."""

    data = read_digest_bound_member(
        root,
        reference.source,
        expected_sha256=reference.source_sha256,
        label="scene UI reference",
    )
    return ResolvedSceneReference(
        reference_id=reference.reference_id,
        source=reference.source,
        sha256=reference.source_sha256,
        media_type=_MEDIA_TYPES[PurePosixPath(reference.source).suffix.lower()],
        data=data,
        rights_status=reference.rights_status,
        rights_basis=tuple(reference.rights_basis),
    )


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
        raise ValueError(f"invalid dialogue-scene-v5: {error}") from None
    assert_dialogue_policy(request)
    return request


def resolve_dialogue_scene(document: object, *, root: Path) -> ResolvedDialogueScene:
    """Validate and materialize everything the plan needs, touching no provider."""

    request = parse_dialogue_request(document)
    # The model, not a pre-dumped dict: canonical form drops nulls, and a cast
    # entry that binds no plate carries one. Dumping first would publish bytes
    # that no longer hash to the canonical digest the plan and bundle compare
    # against, which is exactly the mismatch the bundle refuses.
    request_bytes = canonical_json_bytes(request)
    # Every narrative is admitted before anything else is materialized, so a scene
    # holding one scenario that cannot be finished costs nothing.
    scenarios = _resolve_scenarios(request, root=root)
    stages = _union_stages(scenarios)
    tracks = _union_tracks(scenarios)
    style_reference = _read_style_plate(root, request)
    actors = _resolve_actors(request, scenarios, root=root)
    resources = load_image_style_resources()
    ui = load_game_ui_bytes(_read_ui_document(root))
    if ui.game_id != request.game_id:
        raise ValueError(f"scene {request.game_id} declares a UI contract for {ui.game_id}")
    return ResolvedDialogueScene(
        request=request,
        request_bytes=request_bytes,
        request_sha256=canonical_sha256(request),
        art_request_sha256=art_request_sha256(request),
        scene_id=_scene_id(request),
        recipe_version=recipe_version(request),
        policy_digest=POLICY_DIGEST,
        template_digest=template_digest(request),
        transparency_digest=_transparency_digest(request),
        style_resource_sha256=resources.resource_sha256,
        style_compiler_sha256=resources.compiler_sha256,
        style_selection_brief=style_selection_brief(request, actors),
        actors=actors,
        style_reference=style_reference,
        scenarios=scenarios,
        stages=stages,
        tracks=tracks,
        ui=ui,
        ui_sha256=canonical_sha256(ui.model_dump(mode="json")),
        ui_references={entry.source: _read_ui_reference(root, entry) for entry in ui.references},
    )


def recipe_version(request: DialogueRequest) -> str:
    return "dialogue-scene-v8"


def template_digest(request: DialogueRequest) -> str:
    return (
        NATIVE_ALPHA_TEMPLATE_DIGEST if request.transparency_mode == "native" else TEMPLATE_DIGEST
    )


def style_selection_brief(request: DialogueRequest, actors: tuple[ResolvedSceneActor, ...]) -> str:
    """One anchor for the whole scene, briefed on every actor that appears in it.

    The anchor is scene-wide, so a brief written from one character would let the
    others drift out of the look the first one set.
    """

    return canonical_json_bytes(
        {
            "scene_brief": request.scene_brief,
            "cast": [
                {
                    "actor_id": actor.actor_id,
                    "appearance_description": actor.profile.profile.visual_identity,
                    "wardrobe": actor.profile.profile.wardrobe,
                    "invariants": actor.profile.profile.invariants,
                    "character_profile_sha256": actor.profile.canonical_sha256,
                }
                for actor in actors
            ],
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


#: What an authored style plate may be, checked offline before any spend.
#:
#: Not a canvas: the plate is attached to provider calls as a reference for
#: medium, palette and light, and nothing composites it, so its aspect ratio is
#: the author's business - a portrait of one character and a landscape
#: establishing shot are both legitimate art direction. These are the bounds that
#: catch a mistake instead: a thumbnail pasted in by accident, or a file so large
#: it would be rejected by the provider after the run had started.
STYLE_PLATE_MINIMUM_EDGE = 512
STYLE_PLATE_MAXIMUM_EDGE = 4096


def _read_style_plate(root: Path, request: DialogueRequest) -> ResolvedSceneReference:
    """Read the scene's art direction of record and hold it to what a plate must be.

    The bundle used to require the plate be exactly 1024x1536, which is the canvas
    of a character sprite rather than anything the plate itself is - and it
    checked it at the terminal node, so a scene whose plate was a wide
    establishing shot drew every image, paid for all of them, and was then
    refused. Whatever the rule is, it belongs here: offline, before the first
    provider call, alongside every other thing this package must get right.
    """

    plate = _read_reference(root, request.style_reference())
    facts = inspect_image(plate.data, expected_media_type=plate.media_type)
    for edge, name in ((facts.width, "width"), (facts.height, "height")):
        if not STYLE_PLATE_MINIMUM_EDGE <= edge <= STYLE_PLATE_MAXIMUM_EDGE:
            raise ValueError(
                f"scene style plate {plate.source} has a {name} of {edge}px, outside the "
                f"{STYLE_PLATE_MINIMUM_EDGE}..{STYLE_PLATE_MAXIMUM_EDGE}px an art-direction "
                "reference must be"
            )
    return plate


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


def art_request_sha256(request: DialogueRequest) -> str:
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
                "presentation": document["presentation"],
                "transparency_mode": document["transparency_mode"],
                "cast": document["cast"],
                "style_reference_id": document["style_reference_id"],
                "references": document["references"],
            }
        )
    ).hexdigest()


#: `scenarios/<id>.toml`, with the id held to the scenario contract's own spelling.
_SCENARIO_REF = re.compile(r"scenarios/([a-z][a-z0-9]*(?:_[a-z0-9]+)*)\.toml")


def scenario_id_from_ref(ref: str) -> str:
    """`scenarios/<id>.toml` -> `<id>`, refusing anything else."""

    match = _SCENARIO_REF.fullmatch(ref)
    if match is None:
        raise ValueError("dialogue scene scenario ref must be scenarios/<scenario_id>.toml")
    return match.group(1)


def _resolve_scenarios(request: DialogueRequest, *, root: Path) -> tuple[ResolvedScenario, ...]:
    """Admit every bound narrative, each held to the digest the scene recorded.

    A scene binds one or more `scenarios/<id>.toml`, and each in turn binds its
    script by digest, so one recorded hash per entry closes over the whole
    narrative. Which scenarios a scene plays is the scene's to say - a game holds
    a catalog - so each ref is read for its id rather than pinned to a fixed
    filename.
    """

    scenarios = tuple(
        _resolve_one_scenario(request, binding, root=root) for binding in request.scenarios
    )
    ids = [scenario.declarations.scenario_id for scenario in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("dialogue scene binds the same scenario_id twice: " + ", ".join(ids))
    return scenarios


def _resolve_one_scenario(
    request: DialogueRequest, binding: ScenarioBinding, *, root: Path
) -> ResolvedScenario:
    """Admit one bound narrative, held to the digest the scene recorded.

    The expressions a scenario asks for are no longer checked against a fixed
    recipe taxonomy - there is none. They are checked against the actor's own
    authored character profile in `_resolve_actors`, which is where the words
    that draw each face live.
    """

    scenario_id = scenario_id_from_ref(binding.ref)
    declared = sha256(
        read_absolute_regular_file((root / binding.ref).resolve(), label="dialogue scene scenario")
    ).hexdigest()
    if declared != binding.source_sha256:
        raise ValueError(
            f"dialogue scene scenario {binding.ref} does not match its authored digest: "
            f"declared {binding.source_sha256}, found {declared}"
        )
    scenario = resolve_scenario(root, scenario_id)
    assert_scenario_policy(scenario.program)
    if scenario.declarations.game_id != request.game_id:
        raise ValueError("dialogue scene scenario game_id must match the scene document")
    return scenario


def _union_stages(scenarios: tuple[ResolvedScenario, ...]) -> tuple[StageDeclaration, ...]:
    """One backdrop per distinct stage, in first-declaration order.

    Three scenarios set in the same drawing room are one drawing room, and the
    graph draws it once. Two scenarios that give one stage_id different briefs
    are refused: a backdrop is generated from its brief, so keeping the first one
    seen would let the binding order in `scene.toml` decide which writer's brief
    is drawn and silently discard the other. The refusal names both scenarios and
    both briefs, because the author has to be able to see what collided.
    """

    union: dict[str, tuple[str, StageDeclaration]] = {}
    for scenario in scenarios:
        owner = scenario.declarations.scenario_id
        for stage in scenario.program.stages:
            existing = union.get(stage.stage_id)
            if existing is None:
                union[stage.stage_id] = (owner, stage)
                continue
            first_owner, first = existing
            if first != stage:
                raise ValueError(
                    _collision_message(
                        "stage",
                        stage.stage_id,
                        first_owner,
                        first.brief,
                        owner,
                        stage.brief,
                        "one stage is one backdrop",
                    )
                )
    return tuple(stage for _owner, stage in union.values())


def _union_tracks(scenarios: tuple[ResolvedScenario, ...]) -> tuple[TrackDeclaration, ...]:
    """One track per distinct track identity, on the same terms as the stages."""

    union: dict[str, tuple[str, TrackDeclaration]] = {}
    for scenario in scenarios:
        owner = scenario.declarations.scenario_id
        for track in scenario.program.tracks:
            existing = union.get(track.track_id)
            if existing is None:
                union[track.track_id] = (owner, track)
                continue
            first_owner, first = existing
            if first != track:
                raise ValueError(
                    _collision_message(
                        "track",
                        track.track_id,
                        first_owner,
                        first.brief,
                        owner,
                        track.brief,
                        "one track is one recording",
                    )
                )
    return tuple(track for _owner, track in union.values())


def _collision_message(
    kind: str,
    declared_id: str,
    first_owner: str,
    first_brief: str,
    second_owner: str,
    second_brief: str,
    rule: str,
) -> str:
    """Name both sides of a union collision, so the author can see what to change."""

    return (
        f"bound scenarios declare {kind} {declared_id} differently, and {rule}, so the "
        f"declarations must agree rather than one of them being discarded:\n"
        f"  {first_owner}: {first_brief!r}\n"
        f"  {second_owner}: {second_brief!r}"
    )


def _union_drawable_cast(scenarios: tuple[ResolvedScenario, ...]) -> tuple[CastMember, ...]:
    """Every actor any bound scenario can show, once, in first-declaration order.

    The expressions merge rather than clash: a scenario that only ever shows an
    actor concerned and one that shows her delighted are the same person, and the
    recipe draws the whole locked taxonomy for anyone drawable at all. The display
    name is identity, though, so two scenarios that disagree about it are refused.
    """

    union: dict[str, CastMember] = {}
    for scenario in scenarios:
        for member in scenario.program.cast:
            if not member.drawable:
                continue
            existing = union.get(member.actor_id)
            if existing is None:
                union[member.actor_id] = member
                continue
            if (
                existing.display_name is not None
                and member.display_name is not None
                and existing.display_name != member.display_name
            ):
                raise ValueError(
                    f"bound scenarios give actor {member.actor_id} different display names: "
                    f"{existing.display_name} and {member.display_name}"
                )
            union[member.actor_id] = existing.model_copy(
                update={
                    "display_name": existing.display_name or member.display_name,
                    "expressions": sorted(set(existing.expressions) | set(member.expressions)),
                }
            )
    return tuple(union.values())


def _resolve_actors(
    request: DialogueRequest,
    scenarios: tuple[ResolvedScenario, ...],
    *,
    root: Path,
) -> tuple[ResolvedSceneActor, ...]:
    """Bind every drawable actor the bound scenarios name to the members that draw it.

    Checked in both directions, the way the scenario's own two halves are: a
    drawable actor with no scene binding could not be drawn, and a binding for an
    actor no bound narrative ever shows would pay for plates nobody sees. Over the
    union, so an actor that only the fourth scenario shows is still bound, and
    each actor is resolved once however many scenarios name her.
    """

    bindings = {member.actor_id: member for member in request.cast}
    drawable = _union_drawable_cast(scenarios)
    missing = sorted({member.actor_id for member in drawable} - set(bindings))
    if missing:
        raise ValueError(
            "scene cast does not bind every drawable actor the scenarios show: "
            + ", ".join(missing)
        )
    unused = sorted(set(bindings) - {member.actor_id for member in drawable})
    if unused:
        raise ValueError("scene cast binds actors no bound scenario draws: " + ", ".join(unused))
    profiles = {
        member.actor_id: _resolve_profile(bindings[member.actor_id].character_profile, root=root)
        for member in drawable
    }
    return tuple(
        ResolvedSceneActor(
            actor_id=member.actor_id,
            display_name=member.display_name or member.actor_id,
            expressions=_bind_expressions(member, profiles[member.actor_id]),
            profile=profiles[member.actor_id],
            identity_reference=(
                None
                if bindings[member.actor_id].reference_id is None
                else _read_reference(
                    root, request.reference(str(bindings[member.actor_id].reference_id))
                )
            ),
        )
        for member in drawable
    )


def _bind_expressions(
    member: CastMember, profile: ResolvedSceneProfile
) -> tuple[CharacterExpression, ...]:
    """Hold one actor's narrative expression ids to the profile that draws them.

    The scenario says which faces the script may ask for; the profile says what
    each one looks like. Neither half may be a superset of the other: an id the
    script uses and the profile does not describe would be a missing plate, and
    one the profile describes and no script ever asks for is a plate paid for and
    never shown. Exactly the same two-directional rule the cast and the stage list
    are already held to, applied one level down.

    Order is the profile's, not the scenario's, because order is a drawing
    decision: the first entry is generated from scratch and the rest are edits of
    it, so the resting face has to lead and only the profile knows which that is.
    """

    declared = [item.expression_id for item in profile.profile.expressions]
    if not MINIMUM_EXPRESSIONS <= len(declared) <= MAXIMUM_EXPRESSIONS:
        raise ValueError(
            f"character profile {profile.ref} must declare "
            f"{MINIMUM_EXPRESSIONS}..{MAXIMUM_EXPRESSIONS} expressions to be drawn, "
            f"and declares {len(declared)}"
        )
    asked = set(member.expressions)
    missing = sorted(asked - set(declared))
    if missing:
        raise ValueError(
            f"the scenarios show {member.actor_id} wearing expressions the character "
            f"profile {profile.ref} does not describe: {', '.join(missing)}"
        )
    unused = sorted(set(declared) - asked)
    if unused:
        raise ValueError(
            f"character profile {profile.ref} describes expressions no bound scenario "
            f"ever shows {member.actor_id} wearing: {', '.join(unused)}"
        )
    return tuple(profile.profile.expressions)


def _resolve_profile(binding: CharacterProfileBinding, *, root: Path) -> ResolvedSceneProfile:
    resolved = resolve_character_profile_binding(binding, package_root=root)
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


def _scene_id(request: DialogueRequest) -> str:
    """Named for the game rather than for one character, now that a scene has a cast."""

    return f"{request.game_id.replace('_', '-')}-{canonical_sha256(request)[:12]}"


__all__ = [
    "SCENE_DOCUMENT_NAME",
    "UI_DOCUMENT_NAME",
    "SCENE_ID_MAX_LENGTH",
    "STYLE_PLATE_MAXIMUM_EDGE",
    "STYLE_PLATE_MINIMUM_EDGE",
    "ResolvedDialogueScene",
    "ResolvedSceneActor",
    "art_request_sha256",
    "ResolvedSceneProfile",
    "ResolvedSceneReference",
    "parse_dialogue_request",
    "profile_lock_values",
    "read_scene_document",
    "recipe_version",
    "scenario_id_from_ref",
    "resolve_dialogue_scene",
    "style_selection_brief",
    "template_digest",
]
