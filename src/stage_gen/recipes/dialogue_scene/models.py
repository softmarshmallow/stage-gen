"""Versioned, recipe-owned contracts for dialogue-scene generation."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from stage_gen.components.character_profile import CharacterProfileBinding


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


class GenerateSource(PersistedContractModel):
    mode: Literal["generate"] = "generate"
    description: str | None = Field(default=None, min_length=1, max_length=2000)


class ReuseSource(PersistedContractModel):
    mode: Literal["reuse"]
    ref: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rights: RightsStatus = "unreviewed"

    @field_validator("ref")
    @classmethod
    def portable_reference(cls, value: str) -> str:
        segments = value.split("/")
        if (
            "\x00" in value
            or value.startswith(("/", "~", "http://", "https://"))
            or "\\" in value
            or any(segment in {"", ".", ".."} for segment in segments)
        ):
            raise ValueError("reuse ref must be a portable relative path")
        return value


AssetSource = Annotated[GenerateSource | ReuseSource, Field(discriminator="mode")]
BackgroundSource = AssetSource


class AppearanceRequest(PersistedContractModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,47}$")
    label: str = Field(min_length=1, max_length=96)
    age: int = Field(ge=21, le=120)
    role: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=280)
    concept: AssetSource = Field(default_factory=GenerateSource)


class DialogueBeat(PersistedContractModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,47}$")
    speaker: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=320)
    expression_state: ExpressionState


class PresentationRequest(PersistedContractModel):
    slot: Literal["right"] = "right"
    framing_zoom: int = Field(default=70, ge=0, le=100)
    source_framing_zoom: int = Field(default=70, ge=0, le=100)


class DialogueThemeRequest(PersistedContractModel):
    schema_version: Literal[2]
    kind: Literal["dialogue-theme-request-v2"]
    scene_brief: str = Field(min_length=1, max_length=96)
    appearance: AppearanceRequest
    background: BackgroundSource
    dialogue: list[DialogueBeat] = Field(min_length=1, max_length=12)
    presentation: PresentationRequest = Field(default_factory=PresentationRequest)
    transparency_mode: TransparencyMode = "native"

    @model_validator(mode="after")
    def unique_beats_and_known_speaker(self) -> DialogueThemeRequest:
        ids = [beat.id for beat in self.dialogue]
        if len(ids) != len(set(ids)):
            raise ValueError("dialogue beat ids must be unique")
        return self


class DialogueThemeRequestV3(PersistedContractModel):
    """Profile-enabled request; V2 is intentionally not reinterpreted."""

    schema_version: Literal[3]
    kind: Literal["dialogue-theme-request-v3"]
    scene_brief: str = Field(min_length=1, max_length=96)
    character_profile: CharacterProfileBinding
    background: BackgroundSource
    dialogue: list[DialogueBeat] = Field(min_length=1, max_length=12)
    presentation: PresentationRequest = Field(default_factory=PresentationRequest)
    transparency_mode: TransparencyMode = "native"

    @model_validator(mode="after")
    def unique_beats(self) -> DialogueThemeRequestV3:
        ids = [beat.id for beat in self.dialogue]
        if len(ids) != len(set(ids)):
            raise ValueError("dialogue beat ids must be unique")
        parts = self.character_profile.ref.split("/")
        if len(parts) != 4 or parts[:2] != ["library", "characters"] or parts[3] != "profile.toml":
            raise ValueError(
                "character_profile ref must equal library/characters/<profile_id>/profile.toml"
            )
        return self


DialogueRequest = DialogueThemeRequest | DialogueThemeRequestV3


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
    schema_version: Literal[2]
    kind: Literal["dialogue-scene-plan-v2"]
    recipe_version: Literal["dialogue-scene-v3"]
    policy_version: Literal["adult-romance-nonexplicit-v2"]
    expression_profile: Literal["romance-core-v2"]
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    appearance_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,47}$")
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


class DialogueScenePlanV3(PersistedContractModel):
    schema_version: Literal[3]
    kind: Literal["dialogue-scene-plan-v3"]
    recipe_version: Literal["dialogue-scene-v4"]
    policy_version: Literal["adult-romance-nonexplicit-v2"]
    expression_profile: Literal["romance-core-v2"]
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    appearance_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,95}$")
    character_profile_ref: str = Field(min_length=1)
    character_profile_source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    character_profile_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    shared_locks: SharedLocks
    geometry: SpriteGeometry
    states: list[ExpressionDirection]
    prompt_templates: list[PromptTemplateBinding]

    @model_validator(mode="after")
    def exact_expression_contract(self) -> DialogueScenePlanV3:
        if tuple(state.id for state in self.states) != EXPRESSION_STATES:
            raise ValueError("plan states must use the locked taxonomy and order")
        return self

    def direction_for(self, state: ExpressionState) -> str:
        return next(item.direction for item in self.states if item.id == state)


DialoguePlan = DialogueScenePlan | DialogueScenePlanV3


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
    role: Literal["concept", "background", "expression"]
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


class IndependentReview(PersistedContractModel):
    schema_version: Literal[2]
    kind: Literal["dialogue-scene-review-v2"]
    status: Literal["pass"]
    usage: Literal["local-demo"]
    source_bundle_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    acceptance_spec_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    independent_reviewer: Literal[True]
    asset_sha256: list[str] = Field(min_length=6, max_length=6)
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


class IndependentReviewV3(PersistedContractModel):
    schema_version: Literal[3]
    kind: Literal["dialogue-scene-review-v3"]
    status: Literal["pass"]
    usage: Literal["local-demo"]
    source_bundle_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    acceptance_spec_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    character_profile_source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    character_profile_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    independent_reviewer: Literal[True]
    asset_sha256: list[str] = Field(min_length=6, max_length=6)
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


class SceneBackground(PersistedContractModel):
    asset_id: Literal["background"]
    alt: str = Field(min_length=1, max_length=160)


class SceneAppearance(PersistedContractModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,47}$")
    label: str = Field(min_length=1, max_length=96)
    age: int = Field(ge=21, le=120)
    role: str = Field(min_length=1, max_length=120)
    tagline: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=280)
    visual_identity: str = Field(min_length=1, max_length=320)
    art_direction: str = Field(min_length=1, max_length=200)


class ScenePlacement(PersistedContractModel):
    slot: Literal["right"]
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
    slot: Literal["right"]


class SceneData(PersistedContractModel):
    scene_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    title: str = Field(min_length=1, max_length=96)
    scene_label: str = Field(min_length=1, max_length=160)
    concept_asset_id: Literal["concept"]
    background: SceneBackground
    appearance: SceneAppearance
    placement: ScenePlacement
    available_states: list[ExpressionState]
    expression_variants: list[SceneExpressionVariant]
    dialogue: list[DialogueBeat] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def exact_projection_bindings(self) -> SceneData:
        if tuple(self.available_states) != EXPRESSION_STATES:
            raise ValueError("scene_data available_states must use the locked taxonomy")
        variants = tuple(item.state for item in self.expression_variants)
        if variants != EXPRESSION_STATES:
            raise ValueError("scene_data expression_variants must use the locked taxonomy")
        if any(item.appearance_id != self.appearance.id for item in self.expression_variants):
            raise ValueError("scene_data expression appearance binding must match appearance")
        if any(beat.expression_state not in self.available_states for beat in self.dialogue):
            raise ValueError("scene_data dialogue references an unavailable expression")
        return self


class DialogueBundle(PersistedContractModel):
    schema_version: Literal[2]
    kind: Literal["dialogue-scene-bundle-v2"]
    recipe: Literal["dialogue-scene"]
    recipe_version: Literal["dialogue-scene-v3"]
    tag: str = Field(min_length=1)
    run_identity_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    request: BundleFile
    plan: BundleFile
    assets: list[BundleArtifact]
    scene_data: SceneData
    attempt_ledger: AttemptLedgerBinding
    review: ReviewState = Field(default_factory=ReviewState)
    rights: RightsState = Field(default_factory=RightsState)

    @model_validator(mode="after")
    def unique_roles_and_paths(self) -> DialogueBundle:
        paths = [artifact.path for artifact in self.assets]
        if len(paths) != len(set(paths)):
            raise ValueError("bundle asset paths must be unique")
        expressions = [artifact.state for artifact in self.assets if artifact.role == "expression"]
        if tuple(expressions) != EXPRESSION_STATES:
            raise ValueError("bundle must contain each expression state in locked order")
        if sum(artifact.role == "concept" for artifact in self.assets) != 1:
            raise ValueError("bundle must contain exactly one concept")
        if sum(artifact.role == "background" for artifact in self.assets) != 1:
            raise ValueError("bundle must contain exactly one background")
        asset_ids = {artifact.id for artifact in self.assets}
        scene_asset_ids = {
            self.scene_data.concept_asset_id,
            self.scene_data.background.asset_id,
            *(variant.asset_id for variant in self.scene_data.expression_variants),
        }
        if scene_asset_ids != asset_ids:
            raise ValueError("scene_data asset bindings must exactly match selected assets")
        return self


class DialogueBundleV3(PersistedContractModel):
    schema_version: Literal[3]
    kind: Literal["dialogue-scene-bundle-v3"]
    recipe: Literal["dialogue-scene"]
    recipe_version: Literal["dialogue-scene-v4"]
    tag: str = Field(min_length=1)
    run_identity_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    request: BundleFile
    plan: BundleFile
    character_profile: BundleFile
    character_profile_binding: CharacterProfileBinding
    character_profile_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    assets: list[BundleArtifact]
    scene_data: SceneData
    attempt_ledger: AttemptLedgerBinding
    review: ReviewState = Field(default_factory=ReviewState)
    rights: RightsState = Field(default_factory=RightsState)

    @model_validator(mode="after")
    def unique_roles_and_paths(self) -> DialogueBundleV3:
        paths = [artifact.path for artifact in self.assets]
        if len(paths) != len(set(paths)):
            raise ValueError("bundle asset paths must be unique")
        expressions = [artifact.state for artifact in self.assets if artifact.role == "expression"]
        if tuple(expressions) != EXPRESSION_STATES:
            raise ValueError("bundle must contain each expression state in locked order")
        if sum(artifact.role == "concept" for artifact in self.assets) != 1:
            raise ValueError("bundle must contain exactly one concept")
        if sum(artifact.role == "background" for artifact in self.assets) != 1:
            raise ValueError("bundle must contain exactly one background")
        asset_ids = {artifact.id for artifact in self.assets}
        scene_asset_ids = {
            self.scene_data.concept_asset_id,
            self.scene_data.background.asset_id,
            *(variant.asset_id for variant in self.scene_data.expression_variants),
        }
        if scene_asset_ids != asset_ids:
            raise ValueError("scene_data asset bindings must exactly match selected assets")
        return self


DialogueBundleContract = DialogueBundle | DialogueBundleV3
DialogueReview = IndependentReview | IndependentReviewV3
