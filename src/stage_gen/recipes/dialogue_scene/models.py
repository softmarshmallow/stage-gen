"""Versioned, recipe-owned contracts for dialogue-scene generation."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from stage_gen.components.character_profile import CharacterProfileBinding
from stage_gen.components.scenario import ScenarioProgram


class PersistedContractModel(BaseModel):
    """Recipe-local strict base; dialogue vocabulary stays out of shared contracts."""

    model_config = ConfigDict(extra="forbid", strict=True)

    @model_validator(mode="after")
    def trimmed_strings(self) -> PersistedContractModel:
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, str) and value != value.strip():
                raise ValueError(f"{name} must be trimmed")
        return self


#: The recipe's content floor, stated once. policy.py owns the rule; the
#: persisted projections below only have to agree with it.
MINIMUM_AGE = 18
MAXIMUM_AGE = 120

ExpressionState = Literal["neutral", "delighted", "flustered", "concerned"]
TransparencyMode = Literal["native", "ai", "chroma"]
RightsStatus = Literal["unreviewed", "restricted", "redistribution-approved"]

EXPRESSION_STATES: tuple[ExpressionState, ...] = (
    "neutral",
    "delighted",
    "flustered",
    "concerned",
)
_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


def _validate_review_timestamp(value: str) -> str:
    if _UTC_TIMESTAMP.fullmatch(value) is None:
        raise ValueError("reviewed_at must be a UTC ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("reviewed_at must be a valid UTC ISO-8601 timestamp") from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError("reviewed_at must be a UTC ISO-8601 timestamp")
    return value


class BackgroundDirection(PersistedContractModel):
    """What the backdrop should show, in the author's words."""

    description: str | None = Field(default=None, min_length=1, max_length=2000)


class SceneReference(PersistedContractModel):
    """One authored image the scene is drawn against, bound to its exact bytes.

    A reference is a package member, not something a node paints for itself: the
    resolver reads the file and refuses a digest that no longer matches, offline,
    before any spend. The rights decision travels with it, because the run
    republishes these bytes and a consumer must be able to read what it may do
    with them.
    """

    reference_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$", max_length=64)
    source: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rights_status: RightsStatus
    rights_basis: list[str] = Field(min_length=1, max_length=16)

    @field_validator("source")
    @classmethod
    def source_lives_in_the_package(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("scene reference source must be a trimmed relative path")
        if not value.startswith("references/"):
            raise ValueError("scene references must live under references/")
        segments = value.split("/")
        if (
            "\x00" in value
            or value.startswith(("/", "~", "http://", "https://"))
            or "\\" in value
            or any(segment in {"", ".", ".."} for segment in segments)
        ):
            raise ValueError("scene reference source must be a portable relative path")
        if PurePosixPath(value).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("scene reference source must be a png, jpeg, or webp image")
        return value

    @field_validator("rights_basis")
    @classmethod
    def trimmed_basis(cls, value: list[str]) -> list[str]:
        for item in value:
            if not item or item != item.strip():
                raise ValueError("each rights basis line must be a trimmed non-empty string")
        return value


class ScenarioBinding(PersistedContractModel):
    """The narrative this scene plays, bound to exact bytes.

    A scene used to carry its own flat beat list, which could only ever be walked
    from the first line to the last. The narrative is a `scenario-v1` package
    member now, so the same scene admits choices, flags, and endings, and one
    authored shape serves both genres instead of two that can drift apart.
    """

    schema_version: Literal[1] = 1
    kind: Literal["scenario-binding-v1"] = "scenario-binding-v1"
    ref: str = Field(min_length=1, max_length=256)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("ref")
    @classmethod
    def package_relative_toml(cls, value: str) -> str:
        segments = value.split("/")
        if (
            value.startswith(("/", "~"))
            or "\\" in value
            or any(segment in {"", ".", ".."} for segment in segments)
            or not value.endswith(".toml")
        ):
            raise ValueError("scenario ref must be a package-relative TOML member")
        return value


class PresentationRequest(PersistedContractModel):
    framing_zoom: int = Field(default=70, ge=0, le=100)
    source_framing_zoom: int = Field(default=70, ge=0, le=100)


class SceneCastBinding(PersistedContractModel):
    """Which package members draw one actor the scenario names.

    The scenario says an actor exists and which expressions it can wear; it must
    not say which profile or which plate supplies the face, because the same
    scenario is meant to be staged by more than one consumer. This is the scene's
    half of that: actor id to profile, plus an optional authored plate that is
    this actor's own identity of record.
    """

    actor_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    character_profile: CharacterProfileBinding
    #: A declared `[[references]]` id whose bytes ARE this actor. When present the
    #: plate binds identity as well as look; when absent the actor is drawn from
    #: its profile words against the scene's style plate alone.
    reference_id: str | None = Field(
        default=None, pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$", max_length=64
    )


class DialogueSceneDocument(PersistedContractModel):
    """The authored root of one visual-novel scene package.

    One scene = one directory under ``library/games/`` holding this document
    beside the members it names by exact relative path: the character profile it
    binds, and the ``references/`` its art is drawn against. Temporary by
    intent - the standing goal is for every game kind to be declared through
    ``game.toml`` - so this contract owns only what a scene needs today and
    stays easy to absorb.
    """

    schema_version: Literal[3]
    kind: Literal["dialogue-scene-v3"]
    game_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$", max_length=64)
    display_name: str = Field(min_length=1, max_length=96)
    revision: int = Field(ge=1)
    scene_brief: str = Field(min_length=1, max_length=96)
    #: The narrative, as an authored `scenario-v1` member. Proven finishable
    #: offline before any art is paid for.
    scenario: ScenarioBinding
    #: Which package members draw each actor the scenario can show.
    cast: list[SceneCastBinding] = Field(min_length=1, max_length=16)
    #: The declared reference that fixes this scene's look. It is published into
    #: the run as the style plate and attached to every generated image, so
    #: nothing generates the art direction. It fixes medium, palette and light
    #: for the whole scene; an actor whose own plate is bound in `[[cast]]` is
    #: additionally held to that plate's identity.
    style_reference_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$", max_length=64)
    references: list[SceneReference] = Field(min_length=1, max_length=16)
    presentation: PresentationRequest = Field(default_factory=PresentationRequest)
    transparency_mode: TransparencyMode = "native"

    @model_validator(mode="after")
    def closed_package_bindings(self) -> DialogueSceneDocument:
        actor_ids = [member.actor_id for member in self.cast]
        if len(actor_ids) != len(set(actor_ids)):
            raise ValueError("scene cast actor_id values must be unique")
        for member in self.cast:
            ref = member.character_profile.ref
            segments = ref.split("/")
            if (
                ref.startswith(("/", "~"))
                or "\\" in ref
                or any(segment in {"", ".", ".."} for segment in segments)
                or not ref.endswith(".toml")
            ):
                raise ValueError("character_profile ref must be a package-relative TOML member")
        reference_ids = [reference.reference_id for reference in self.references]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("reference_id values must be unique")
        sources = [reference.source for reference in self.references]
        if len(sources) != len(set(sources)):
            raise ValueError("reference sources must be unique")
        if self.style_reference_id not in reference_ids:
            raise ValueError(
                f"style_reference_id names an undeclared reference: {self.style_reference_id}"
            )
        bound = {self.style_reference_id}
        for member in self.cast:
            if member.reference_id is None:
                continue
            if member.reference_id not in reference_ids:
                raise ValueError(
                    f"cast {member.actor_id} names an undeclared reference: {member.reference_id}"
                )
            bound.add(member.reference_id)
        # Every declared reference must be consumed. An unused declaration is a
        # file the run would republish and the manifest would name for nothing.
        unused = set(reference_ids) - bound
        if unused:
            raise ValueError(f"references declared but never used: {sorted(unused)}")
        return self

    def style_reference(self) -> SceneReference:
        return next(
            reference
            for reference in self.references
            if reference.reference_id == self.style_reference_id
        )

    def reference(self, reference_id: str) -> SceneReference:
        return next(
            reference for reference in self.references if reference.reference_id == reference_id
        )


DialogueRequest = DialogueSceneDocument


class SharedLocks(PersistedContractModel):
    identity: str = Field(min_length=1, max_length=2000)
    wardrobe: str = Field(min_length=1, max_length=1000)
    pose: str = Field(min_length=1, max_length=1000)
    lighting: str = Field(min_length=1, max_length=1000)
    style: str = Field(min_length=1, max_length=1000)


class CanvasGeometry(PersistedContractModel):
    width: Literal[1024] = 1024
    height: Literal[1536] = 1536


class SpriteGeometry(PersistedContractModel):
    canvas: CanvasGeometry = Field(default_factory=CanvasGeometry)
    crop: Literal["top-hair-through-waist"] = "top-hair-through-waist"
    slot: Literal["right"] = "right"
    safe_bounds: list[float] = Field(default_factory=lambda: [0.0, 0.0, 1.0, 1.0])

    @field_validator("safe_bounds")
    @classmethod
    def exact_safe_bounds(cls, value: list[float]) -> list[float]:
        if value != [0.0, 0.0, 1.0, 1.0]:
            raise ValueError("safe_bounds must cover the full normalized canvas")
        return value


class ExpressionDirection(PersistedContractModel):
    id: ExpressionState
    direction: str = Field(min_length=1, max_length=1000)


class PromptTemplateBinding(PersistedContractModel):
    id: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ExpressionDirections(PersistedContractModel):
    """The only expression content delegated to structured generation."""

    neutral: str = Field(min_length=1, max_length=1000)
    delighted: str = Field(min_length=1, max_length=1000)
    flustered: str = Field(min_length=1, max_length=1000)
    concerned: str = Field(min_length=1, max_length=1000)

    def for_state(self, state: ExpressionState) -> str:
        if state == "neutral":
            return self.neutral
        if state == "delighted":
            return self.delighted
        if state == "flustered":
            return self.flustered
        return self.concerned


class DialogueScenePlanDraft(PersistedContractModel):
    """Generative plan fields; recipe-owned invariants are composed locally."""

    shared_locks: SharedLocks
    states: ExpressionDirections


class DialogueScenePlan(PersistedContractModel):
    schema_version: Literal[6]
    kind: Literal["dialogue-scene-plan-v6"]
    recipe_version: Literal["dialogue-scene-v7"]
    policy_version: Literal["coming-of-age-nonexplicit-v3"]
    expression_profile: Literal["expression-core-v3"]
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    appearance_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,95}$")
    character_profile_ref: str = Field(min_length=1)
    character_profile_source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    character_profile_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    identity_reference_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    shared_locks: SharedLocks
    geometry: SpriteGeometry
    states: list[ExpressionDirection]
    prompt_templates: list[PromptTemplateBinding]

    @model_validator(mode="after")
    def exact_expression_contract(self) -> DialogueScenePlan:
        if tuple(state.id for state in self.states) != EXPRESSION_STATES:
            raise ValueError("plan states must use the locked taxonomy and order")
        return self

    def direction_for(self, state: ExpressionState) -> str:
        return next(item.direction for item in self.states if item.id == state)


DialoguePlan = DialogueScenePlan


class AttemptRecord(PersistedContractModel):
    stage: str = Field(min_length=1)
    role: str = Field(min_length=1)
    attempt: int = Field(ge=1, le=6)
    outcome: Literal["selected", "rejected"]
    provider: str | None = None
    model: str | None = None
    artifact: str | None = None
    artifact_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    prompt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reference_sha256: list[str] = Field(default_factory=list)
    reason: str | None = None


class AttemptLedger(PersistedContractModel):
    schema_version: Literal[2] = 2
    kind: Literal["dialogue-attempt-ledger-v2"] = "dialogue-attempt-ledger-v2"
    attempts: list[AttemptRecord] = Field(default_factory=list)


class MediaFacts(PersistedContractModel):
    mime_type: Literal["image/png"]
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    alpha: bool


class BundleArtifact(PersistedContractModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    role: Literal["style", "background", "expression"]
    #: Which actor an expression belongs to; None for a style plate or backdrop.
    actor_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    state: ExpressionState | None = None
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(ge=1)
    media: MediaFacts
    provenance_path: str = Field(min_length=1)
    provenance_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    selected_attempt: int = Field(ge=0, le=6)

    @field_validator("path", "provenance_path")
    @classmethod
    def portable_path(cls, value: str) -> str:
        if value.startswith(("/", "~")) or ".." in value.split("/"):
            raise ValueError("bundle paths must be portable relative paths")
        return value

    @model_validator(mode="after")
    def role_media_contract(self) -> BundleArtifact:
        expected = (1672, 941, False) if self.role == "background" else (1024, 1536, False)
        if self.role == "expression":
            expected = (1024, 1536, True)
            if self.state is None:
                raise ValueError("expression asset requires a state")
        elif self.state is not None:
            raise ValueError("only expression assets may name a state")
        actual = (self.media.width, self.media.height, self.media.alpha)
        if actual != expected:
            raise ValueError(f"{self.role} media contract requires {expected}; received {actual}")
        return self


class ReviewState(PersistedContractModel):
    status: Literal["pending", "pass", "fail"] = "pending"
    path: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    provenance_path: str | None = None
    provenance_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @field_validator("path", "provenance_path")
    @classmethod
    def portable_path(cls, value: str | None) -> str | None:
        if value is not None and (value.startswith(("/", "~")) or ".." in value.split("/")):
            raise ValueError("review paths must be portable relative paths")
        return value

    @model_validator(mode="after")
    def evidence_matches_status(self) -> ReviewState:
        bindings = (self.path, self.sha256, self.provenance_path, self.provenance_sha256)
        if self.status == "pending" and any(value is not None for value in bindings):
            raise ValueError("pending review must not bind review evidence")
        if self.status != "pending" and any(value is None for value in bindings):
            raise ValueError("completed review must bind review evidence and provenance")
        return self


class ReviewCastBinding(PersistedContractModel):
    """One reviewed actor, bound to the exact profile bytes the run drew from."""

    actor_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    character_profile_source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    character_profile_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class IndependentReview(PersistedContractModel):
    schema_version: Literal[6]
    kind: Literal["dialogue-scene-review-v6"]
    status: Literal["pass"]
    usage: Literal["local-demo"]
    source_bundle_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    acceptance_spec_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    #: Every actor whose art this verdict covers. A scene has a cast, so a single
    #: pair of profile digests could only ever have vouched for one of them.
    cast: list[ReviewCastBinding] = Field(min_length=1, max_length=16)
    independent_reviewer: Literal[True]
    #: One digest per selected asset: the style plate, every backdrop, and every
    #: expression of every actor. The count is a property of the scene, not a
    #: constant, so it is checked against the bundle rather than pinned here.
    asset_sha256: list[str] = Field(min_length=1, max_length=256)
    publication_authorized: Literal[False]
    reviewed_at: str

    @field_validator("asset_sha256")
    @classmethod
    def valid_asset_digests(cls, value: list[str]) -> list[str]:
        digest = re.compile(r"^[a-f0-9]{64}$")
        if any(digest.fullmatch(item) is None for item in value):
            raise ValueError("asset_sha256 entries must be SHA-256 digests")
        return value

    @field_validator("reviewed_at")
    @classmethod
    def valid_review_timestamp(cls, value: str) -> str:
        return _validate_review_timestamp(value)


class RightsState(PersistedContractModel):
    aggregate: RightsStatus = "unreviewed"
    publication_authorized: bool = False

    @model_validator(mode="after")
    def publication_requires_approved_rights(self) -> RightsState:
        if self.publication_authorized and self.aggregate != "redistribution-approved":
            raise ValueError("publication authorization requires redistribution-approved rights")
        return self


class BundleFile(PersistedContractModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provenance_path: str = Field(min_length=1)
    provenance_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("path", "provenance_path")
    @classmethod
    def portable_path(cls, value: str) -> str:
        if value.startswith(("/", "~")) or ".." in value.split("/"):
            raise ValueError("bundle file paths must be portable relative paths")
        return value


class AttemptLedgerBinding(PersistedContractModel):
    path: Literal["attempts.json"] = "attempts.json"
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class BundleActor(PersistedContractModel):
    """One drawable actor's published members, bound to the package they came from."""

    actor_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    character_profile: BundleFile
    character_profile_binding: CharacterProfileBinding
    character_profile_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    plan: BundleFile


class SceneStage(PersistedContractModel):
    """One generated backdrop, named by the stage the scenario switches to."""

    stage_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    asset_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    alt: str = Field(min_length=1, max_length=160)


class SceneAppearance(PersistedContractModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,47}$")
    label: str = Field(min_length=1, max_length=96)
    #: Kept in step with the recipe's own floor in policy.py; the projection must
    #: not admit anyone the resolver already refused, nor refuse anyone it passed.
    age: int = Field(ge=MINIMUM_AGE, le=MAXIMUM_AGE)
    role: str = Field(min_length=1, max_length=120)
    tagline: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=280)
    visual_identity: str = Field(min_length=1, max_length=320)
    art_direction: str = Field(min_length=1, max_length=200)


class ScenePlacement(PersistedContractModel):
    framing_zoom: int = Field(ge=0, le=100)
    source_framing_zoom: int = Field(ge=0, le=100)


class SceneExpressionVariant(PersistedContractModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    asset_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    appearance_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,47}$")
    state: ExpressionState
    label: str = Field(min_length=1, max_length=96)
    description: str = Field(min_length=1, max_length=200)
    alt: str = Field(min_length=1, max_length=160)


class SceneActor(PersistedContractModel):
    """One drawable actor: who the scenario names, and the plates that draw them."""

    actor_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    appearance: SceneAppearance
    expression_variants: list[SceneExpressionVariant] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def variants_bind_this_appearance(self) -> SceneActor:
        states = [variant.state for variant in self.expression_variants]
        if len(states) != len(set(states)):
            raise ValueError(f"actor {self.actor_id} repeats an expression state")
        if any(item.appearance_id != self.appearance.id for item in self.expression_variants):
            raise ValueError(f"actor {self.actor_id} variants must bind its own appearance")
        return self


class SceneData(PersistedContractModel):
    scene_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    title: str = Field(min_length=1, max_length=96)
    scene_label: str = Field(min_length=1, max_length=160)
    style_asset_id: Literal["style-plate"]
    stages: list[SceneStage] = Field(min_length=1, max_length=16)
    actors: list[SceneActor] = Field(min_length=1, max_length=16)
    placement: ScenePlacement
    available_states: list[ExpressionState]
    #: The compiled narrative, embedded rather than referenced.
    #:
    #: `scene_data` is the consumer's projection of the run, and the narrative is
    #: the substance of it. The run still publishes `scenario.json` as its own
    #: artifact - that is the graph node's port and where the proof points - but a
    #: consumer that had to fetch a second file to know what anybody says would
    #: make every consumer of this bundle, installed themes included, learn a new
    #: retrieval path. The manifest builds this from the published bytes, so the
    #: two are the same content by construction rather than by promise.
    scenario: ScenarioProgram

    @model_validator(mode="after")
    def exact_projection_bindings(self) -> SceneData:
        if tuple(self.available_states) != EXPRESSION_STATES:
            raise ValueError("scene_data available_states must use the locked taxonomy")
        for actor in self.actors:
            variants = tuple(item.state for item in actor.expression_variants)
            if variants != EXPRESSION_STATES:
                raise ValueError(
                    f"scene_data actor {actor.actor_id} must use the locked expression taxonomy"
                )
        actor_ids = [actor.actor_id for actor in self.actors]
        if len(actor_ids) != len(set(actor_ids)):
            raise ValueError("scene_data actor ids must be unique")
        stage_ids = [stage.stage_id for stage in self.stages]
        if len(stage_ids) != len(set(stage_ids)):
            raise ValueError("scene_data stage ids must be unique")
        # The projection must cover exactly what the narrative can ask for: a
        # `stage` or `show` naming something with no plate would surface as a
        # missing texture in a browser rather than as a refused package.
        declared_actors = {member.actor_id for member in self.scenario.cast if member.expressions}
        if declared_actors != set(actor_ids):
            raise ValueError(
                "scene_data actors must be exactly the scenario's drawable cast: "
                f"{sorted(declared_actors)}"
            )
        declared_stages = {stage.stage_id for stage in self.scenario.stages}
        if declared_stages != set(stage_ids):
            raise ValueError(
                "scene_data stages must be exactly the scenario's stages: "
                + ", ".join(sorted(declared_stages))
            )
        return self


class DialogueBundle(PersistedContractModel):
    schema_version: Literal[6]
    kind: Literal["dialogue-scene-bundle-v6"]
    recipe: Literal["dialogue-scene"]
    recipe_version: Literal["dialogue-scene-v7"]
    tag: str = Field(min_length=1)
    game_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$", max_length=64)
    run_identity_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    request: BundleFile
    #: One entry per drawable actor: its profile, its plan, and the package
    #: binding both came from. A scene has a cast now, so a single profile field
    #: could only ever have named one of them.
    actors: list[BundleActor] = Field(min_length=1, max_length=16)
    #: The compiled narrative and the proof that admitted it. A consumer plays
    #: from `scenario`; `scenario_validation` is the evidence, carried because a
    #: run must name everything it contains.
    scenario: BundleFile
    scenario_validation: BundleFile
    scenario_binding: ScenarioBinding
    scenario_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    #: The authored plate every image in the run was drawn against, named by the
    #: package path it came from and the exact bytes the run republished.
    style_reference: BundleFile
    style_reference_source: str = Field(min_length=1)
    assets: list[BundleArtifact]
    scene_data: SceneData
    attempt_ledger: AttemptLedgerBinding
    review: ReviewState = Field(default_factory=ReviewState)
    rights: RightsState = Field(default_factory=RightsState)

    @model_validator(mode="after")
    def unique_roles_and_paths(self) -> DialogueBundle:
        actor_ids = [actor.actor_id for actor in self.actors]
        if len(actor_ids) != len(set(actor_ids)):
            raise ValueError("bundle actor ids must be unique")
        if set(actor_ids) != {actor.actor_id for actor in self.scene_data.actors}:
            raise ValueError("bundle actors and scene_data actors must name the same cast")
        paths = [artifact.path for artifact in self.assets]
        if len(paths) != len(set(paths)):
            raise ValueError("bundle asset paths must be unique")
        if sum(artifact.role == "style" for artifact in self.assets) != 1:
            raise ValueError("bundle must contain exactly one style plate")
        backgrounds = sum(artifact.role == "background" for artifact in self.assets)
        if backgrounds != len(self.scene_data.stages):
            raise ValueError("bundle must contain one background per declared stage")
        expressions = sum(artifact.role == "expression" for artifact in self.assets)
        if expressions != len(self.scene_data.actors) * len(EXPRESSION_STATES):
            raise ValueError("bundle must contain every expression state for every actor")
        asset_ids = {artifact.id for artifact in self.assets}
        scene_asset_ids = {
            self.scene_data.style_asset_id,
            *(stage.asset_id for stage in self.scene_data.stages),
            *(
                variant.asset_id
                for actor in self.scene_data.actors
                for variant in actor.expression_variants
            ),
        }
        if scene_asset_ids != asset_ids:
            raise ValueError("scene_data asset bindings must exactly match selected assets")
        return self


DialogueBundleContract = DialogueBundle
DialogueReview = IndependentReview
