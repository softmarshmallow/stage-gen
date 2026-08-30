"""Exact-current prepared player, mob, NPC, prop, item, and projectile catalogs."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Annotated, Literal, Protocol

from pydantic import Field, ValidationInfo, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    GAME_ID_PATTERN,
    SHA256_PATTERN,
    SNAKE_ID_PATTERN,
    canonical_contract_json,
    normalized_text,
    parse_toml_contract,
    portable_relative_path,
    unique_values,
)

GAME_CONTENT_SCHEMA_VERSION = 2
NPC_CONTENT_SCHEMA_VERSION = 3
#: The player catalog versions on its own, as the NPC catalog already does. It gained a required
#: `equipment` declaration that the other content families have no counterpart for, and bumping the
#: shared constant would have re-versioned mob, prop, and item catalogs that did not change.
PLAYER_CONTENT_SCHEMA_VERSION = 3

MotionPlaybackMode = Literal["hold", "loop", "once", "gameplay_driven"]
NpcWorldOrientation = Literal["front"]
CanonicalFrameIndex = Annotated[int, Field(ge=0, le=63)]

#: Which edge of its cell a motion's frames register against. Vertical only: horizontal placement is
#: unconditionally centered by both the repacker and the runtime origin.
#:
#: `center` is deliberately not admitted. The repacker supports it, but the runtime origin is
#: correct only for these two, so admitting it would publish a value that does not work.
MotionAnchor = Literal["bottom", "top"]
DEFAULT_MOTION_ANCHOR: MotionAnchor = "bottom"
#: One climbable role to the one player motion state that depicts climbing it. Climbing a ladder
#: and climbing a rope are one intent and one movement, but not one pose: a ladder is gripped at
#: shoulder width with the feet on separate rungs, a rope on a single centerline with the feet
#: pinched together. The map declares the role, so nothing has to infer which pose to play.
PLAYER_CLIMB_STATE_BY_CLIMBABLE_ROLE = {
    "ladder": "climb_ladder",
    "rope": "climb_rope",
}

#: Climb states advance frame by frame from the player's position on the climbable rather than on
#: a clock, so they are the only states whose playback the runtime drives.
PLAYER_GAMEPLAY_DRIVEN_STATES = frozenset(PLAYER_CLIMB_STATE_BY_CLIMBABLE_ROLE.values())

#: What the character is drawn carrying. A closed name, not free text, for one reason: the way the
#: character fights is also a closed name, and two closed names can be checked against each other.
#:
#: The authored prompt still says *which* object - a wooden training sword, a folded paper dart -
#: exactly as a projectile's prompt describes the dart whose `silhouette` is `axial_v1`. This names
#: only the class of thing, which is the part a validator can hold against `weapon_class`.
PlayerEquipment = Literal[
    "hand_weapon_v1",
    "unarmed_v1",
    "thrown_kit_v1",
    "focus_implement_v1",
]

#: The one place that knows which kit each drawn equipment can actually fight with.
#:
#: The single declaration site, in the shape `PLAYER_CLIMB_STATE_BY_CLIMBABLE_ROLE` established
#: above. Its keys are gated against `PlayerEquipment` and its values against the gameplay
#: contract's `weapon_class` vocabulary by test, because a member added to either side and not
#: here would otherwise widen or silently forbid a pairing with nothing reporting it.
#:
#: A character who visibly carries a blade does not throw darts, and one who carries a bandolier of
#: darts does not swing. That disagreement was previously unrepresentable: the equipment lived in
#: free prose in this catalog and the kit in `gameplay.toml`, two files describing one fact.
WEAPON_CLASSES_BY_PLAYER_EQUIPMENT: dict[PlayerEquipment, frozenset[str]] = {
    "hand_weapon_v1": frozenset({"melee_dps_v1"}),
    "unarmed_v1": frozenset({"melee_dps_v1"}),
    "thrown_kit_v1": frozenset({"ranged_dps_v1"}),
    "focus_implement_v1": frozenset({"ranged_dps_v1"}),
}

PLAYER_MOTION_STATES = frozenset(
    {
        "idle",
        "walk",
        "run",
        "jump",
        "crouch",
        "basic_attack",
        "skill_cast",
        "hurt",
        "death",
    }
    | PLAYER_GAMEPLAY_DRIVEN_STATES
)


class MotionPresentation(PersistedContractModel):
    """Authored runtime playback for one independently generated motion state."""

    state: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    playback_mode: MotionPlaybackMode
    canonical_frame_indices: list[CanonicalFrameIndex] = Field(min_length=1, max_length=64)
    frames_per_second: int | None = Field(default=None, ge=1, le=60)
    #: Which edge every frame of this motion registers against.
    #:
    #: Authored rather than recipe-owned because, unlike facing, it is not knowable before
    #: generation. Facing follows from the camera and is decided up front; the anchor depends on
    #: what the model actually drew - whether a climb tucked to hip height or to the chest, whether
    #: the feet left the bounding box's extreme. That is a per-artifact property, so it needs a knob
    #: at the point where a human has seen the output.
    #:
    #: A grounded actor registers on its feet, which is why the default is `bottom` and why nothing
    #: needed this until now. An actor hanging from its hands does not: bottom-anchoring pins its
    #: feet and throws its head up and down instead, which reads as bouncing.
    #:
    #: This is a deliberate stopgap. It pins a bounding-box extreme, so it cannot express a
    #: registration point inside the figure, and it is one value for the whole motion rather than
    #: one per frame. `TODO.md` `## Sprite anchoring` owns the replacement; when that lands this
    #: field is renamed or retired rather than extended.
    anchor: MotionAnchor = DEFAULT_MOTION_ANCHOR

    @field_validator("canonical_frame_indices")
    @classmethod
    def validate_frame_indices(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("canonical frame indices must be unique")
        return value

    @model_validator(mode="after")
    def validate_playback_shape(self) -> MotionPresentation:
        if self.playback_mode == "hold":
            if len(self.canonical_frame_indices) != 1:
                raise ValueError("hold playback requires exactly one canonical frame index")
            if self.frames_per_second is not None:
                raise ValueError("hold playback must not declare frames_per_second")
        elif self.playback_mode in {"loop", "once"}:
            if self.frames_per_second is None:
                raise ValueError(f"{self.playback_mode} playback requires frames_per_second")
        elif self.frames_per_second is not None:
            raise ValueError("gameplay_driven playback must not declare frames_per_second")
        return self


def _validate_motion_states(
    motions: Sequence[MotionPresentation],
    *,
    allowed_states: set[str],
    label: str,
) -> None:
    states = [entry.state for entry in motions]
    unique_values(states, f"{label} motion state")
    unknown = sorted(set(states) - allowed_states)
    if unknown:
        raise ValueError(f"{label} declares unsupported motion states: " + ", ".join(unknown))


class ContentReference(PersistedContractModel):
    reference_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    source: str
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    rights_status: Literal["unreviewed", "restricted", "redistribution-approved"]
    rights_basis: list[str] = Field(min_length=1, max_length=16)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        source = portable_relative_path(value, "content reference source")
        if not source.startswith("references/"):
            raise ValueError("content references must live under references/")
        if PurePosixPath(source).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("content references must use PNG, JPEG, or WebP")
        return source

    @field_validator("rights_basis")
    @classmethod
    def validate_rights_basis(cls, value: list[str]) -> list[str]:
        normalized = [normalized_text(entry, "content reference rights basis") for entry in value]
        unique_values(normalized, "content reference rights basis")
        return normalized


class _ReferencesContent(Protocol):
    reference_ids: list[str]


def _validate_reference_closure(
    references: Sequence[ContentReference],
    entries: Sequence[_ReferencesContent],
) -> None:
    unique_values((entry.reference_id for entry in references), "content reference_id")
    unique_values((entry.source for entry in references), "content reference source")
    declared = {entry.reference_id for entry in references}
    selected = {reference_id for entry in entries for reference_id in entry.reference_ids}
    unknown = sorted(selected - declared)
    if unknown:
        raise ValueError("content entries reference unknown IDs: " + ", ".join(unknown))
    unused = sorted(declared - selected)
    if unused:
        raise ValueError("content declares unused reference IDs: " + ", ".join(unused))


class DialogueArtDirection(PersistedContractModel):
    enabled: Literal[True]
    subject_view: Literal["front_three_quarter"]
    expressions: list[str] = Field(min_length=1, max_length=16)

    @field_validator("expressions")
    @classmethod
    def validate_expressions(cls, value: list[str]) -> list[str]:
        unique_values(value, "player dialogue expression")
        return value


#: Authored magnitude bounds. The floor a package actually enforces is its own `[scale] minimum`;
#: these are the outer limits any declaration must sit inside before that check runs.
MINIMUM_HEIGHT_UNITS = 0.05
MAXIMUM_HEIGHT_UNITS = 32.0


def _validated_height_units(value: float | None, label: str) -> float | None:
    """Bound and round one authored magnitude, in multiples of the canonical player height."""

    if value is None:
        return None
    if value < MINIMUM_HEIGHT_UNITS or value > MAXIMUM_HEIGHT_UNITS:
        raise ValueError(
            f"{label} must be between {MINIMUM_HEIGHT_UNITS} and {MAXIMUM_HEIGHT_UNITS} "
            "player heights"
        )
    return round(value, 2)


class PlayerContent(PersistedContractModel):
    player_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    display_name: str
    body_kind: str
    age: int = Field(ge=18, le=130)
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    prompt: str
    #: Required rather than defaulted. Any default here would be a claim about artwork nobody
    #: authored, and the whole value of the field is that it cannot silently disagree with the kit.
    equipment: PlayerEquipment
    motions: list[MotionPresentation] = Field(min_length=1)
    dialogue_art: DialogueArtDirection

    @field_validator("display_name", "body_kind")
    @classmethod
    def validate_scalar_text(cls, value: str, info: ValidationInfo) -> str:
        return normalized_text(value, f"player {info.field_name}")

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "player prompt", multiline=True)

    @field_validator("reference_ids")
    @classmethod
    def validate_lists(cls, value: list[str], info: ValidationInfo) -> list[str]:
        unique_values(value, f"player {info.field_name}")
        return value

    @model_validator(mode="after")
    def validate_motions(self) -> PlayerContent:
        _validate_motion_states(
            self.motions,
            allowed_states=set(PLAYER_MOTION_STATES),
            label="player",
        )
        for motion in self.motions:
            if (motion.state in PLAYER_GAMEPLAY_DRIVEN_STATES) != (
                motion.playback_mode == "gameplay_driven"
            ):
                raise ValueError(
                    "player climb states must use gameplay_driven playback "
                    "and no other state may use it"
                )
        return self


class PlayerContentCatalog(PersistedContractModel):
    schema_version: Literal[3]
    kind: Literal["player-content-v3"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    references: list[ContentReference] = Field(min_length=1, max_length=32)
    players: list[PlayerContent] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def validate_catalog(self) -> PlayerContentCatalog:
        _validate_reference_closure(self.references, self.players)
        return self


class MobContent(PersistedContractModel):
    mob_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    display_name: str
    body_kind: str
    rank: Literal["common", "uncommon", "elite", "boss"]
    #: Silhouette shape within this mob's rank tier. `rank` remains the magnitude authority,
    #: so a declaration here adjusts the drawn shape and never reorders the threat ladder.
    height_units: float | None = None
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    prompt: str
    motions: list[MotionPresentation] = Field(min_length=1)

    @field_validator("display_name", "body_kind")
    @classmethod
    def validate_scalar_text(cls, value: str, info: ValidationInfo) -> str:
        return normalized_text(value, f"mob {info.field_name}")

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "mob prompt", multiline=True)

    @field_validator("reference_ids")
    @classmethod
    def validate_lists(cls, value: list[str], info: ValidationInfo) -> list[str]:
        unique_values(value, f"mob {info.field_name}")
        return value

    @model_validator(mode="after")
    def validate_motions(self) -> MobContent:
        _validate_motion_states(
            self.motions,
            allowed_states={"idle", "move", "attack", "hurt", "death"},
            label=f"mob {self.mob_id}",
        )
        if any(motion.playback_mode == "gameplay_driven" for motion in self.motions):
            raise ValueError("mob motions must not use gameplay_driven playback")
        return self

    @field_validator("height_units")
    @classmethod
    def validate_height_units(cls, value: float | None) -> float | None:
        return _validated_height_units(value, "mob height_units")


class MobContentCatalog(PersistedContractModel):
    schema_version: Literal[2]
    kind: Literal["mob-content-v2"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    references: list[ContentReference] = Field(min_length=1, max_length=32)
    mobs: list[MobContent] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_catalog(self) -> MobContentCatalog:
        unique_values((entry.mob_id for entry in self.mobs), "mob_id")
        _validate_reference_closure(self.references, self.mobs)
        return self


class NpcContent(PersistedContractModel):
    npc_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    #: How tall this resident is, as a multiple of the player.
    height_units: float | None = None
    display_name: str
    role: str
    body_kind: str
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    prompt: str
    motions: list[MotionPresentation] = Field(min_length=1, max_length=1)
    dialogue_expressions: list[str] = Field(min_length=1, max_length=16)

    @field_validator("display_name", "role", "body_kind")
    @classmethod
    def validate_scalar_text(cls, value: str, info: ValidationInfo) -> str:
        return normalized_text(value, f"npc {info.field_name}")

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "npc prompt", multiline=True)

    @field_validator("reference_ids", "dialogue_expressions")
    @classmethod
    def validate_lists(cls, value: list[str], info: ValidationInfo) -> list[str]:
        unique_values(value, f"npc {info.field_name}")
        return value

    @model_validator(mode="after")
    def validate_motions(self) -> NpcContent:
        _validate_motion_states(
            self.motions,
            allowed_states={"idle"},
            label=f"NPC {self.npc_id}",
        )
        if self.motions[0].playback_mode == "gameplay_driven":
            raise ValueError("NPC motion must not use gameplay_driven playback")
        return self

    @field_validator("height_units")
    @classmethod
    def validate_height_units(cls, value: float | None) -> float | None:
        return _validated_height_units(value, "NPC height_units")


class NpcContentCatalog(PersistedContractModel):
    schema_version: Literal[3]
    kind: Literal["npc-content-v3"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    world_orientation: NpcWorldOrientation
    references: list[ContentReference] = Field(min_length=1, max_length=32)
    npcs: list[NpcContent] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_catalog(self) -> NpcContentCatalog:
        unique_values((entry.npc_id for entry in self.npcs), "npc_id")
        _validate_reference_closure(self.references, self.npcs)
        return self


class PropContent(PersistedContractModel):
    prop_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    display_name: str
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    prompt: str
    #: How tall this subject is, as a multiple of the player.
    height_units: float | None = None

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalized_text(value, "prop display_name")

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "prop prompt", multiline=True)

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "prop reference_id")
        return value

    @field_validator("height_units")
    @classmethod
    def validate_height_units(cls, value: float | None) -> float | None:
        return _validated_height_units(value, "prop height_units")


class PropContentCatalog(PersistedContractModel):
    schema_version: Literal[2]
    kind: Literal["prop-content-v2"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    references: list[ContentReference] = Field(min_length=1, max_length=32)
    props: list[PropContent] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_catalog(self) -> PropContentCatalog:
        unique_values((entry.prop_id for entry in self.props), "prop_id")
        _validate_reference_closure(self.references, self.props)
        return self


class ItemContent(PersistedContractModel):
    item_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    display_name: str
    item_kind: Literal[
        "currency",
        "healing_consumable",
        "traversal_tool",
        "key_item",
        "quest_collectible",
        "throwable_ammo",
    ]
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    #: How tall this subject is, as a multiple of the player.
    height_units: float | None = None
    prompt: str

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalized_text(value, "item display_name")

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "item prompt", multiline=True)

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "item reference_id")
        return value

    @field_validator("height_units")
    @classmethod
    def validate_height_units(cls, value: float | None) -> float | None:
        return _validated_height_units(value, "item height_units")


class ItemContentCatalog(PersistedContractModel):
    schema_version: Literal[2]
    kind: Literal["item-content-v2"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    references: list[ContentReference] = Field(min_length=1, max_length=32)
    items: list[ItemContent] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_catalog(self) -> ItemContentCatalog:
        unique_values((entry.item_id for entry in self.items), "item_id")
        _validate_reference_closure(self.references, self.items)
        return self


#: What the artwork looks like, and therefore what the pipeline must draw and the runtime may do
#: with it. The one facet that crosses the Python/consumer boundary, and it crosses for a reason
#: the others do not: it is a statement about the published pixels, which is the single artifact
#: both sides share. `radial` has no leading end and may be spun; `axial` has one and is drawn
#: pointing along its travel; `irregular` has neither a clean axis nor symmetry and tumbles.
ProjectileSilhouette = Literal["radial_v1", "axial_v1", "irregular_v1"]

#: How the object travels. Named rather than numbered, exactly as the aggression archetype and the
#: critical rate are: speed, gravity, range and collision box are how the game feels, which the
#: consumer owns. Nothing in this package branches on the value.
ProjectileFlight = Literal["flat_bolt_v1", "lobbed_arc_v1", "drifting_orb_v1"]

#: What arrival resolves against, and how it reads. Same split and same reason: this names a kind,
#: never a count, a radius, or a duration.
ProjectileImpact = Literal["single_target_v1", "burst_v1", "piercing_v1"]


class ProjectileContent(PersistedContractModel):
    """One thrown, fired, or cast object a weapon can put in the air.

    Three named facets rather than one conflated class, for a reason the graph makes concrete:
    `_MAGNITUDE_FIELDS` excludes a field from the generate node's cache digest when it changes
    nothing the image model can draw. `flight` and `impact` are exactly that, and half of a single
    conflated string cannot be excluded - so conflating them would price every gameplay retune as a
    full re-render of artwork that cannot change.

    They also grow at different costs. A new silhouette is a leading prompt directive, a validation
    rule and a review clause; a new flight or impact is one row in a consumer table and no
    regeneration at all.
    """

    projectile_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    display_name: str
    silhouette: ProjectileSilhouette
    flight: ProjectileFlight
    impact: ProjectileImpact
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    #: How long the object is along its own travel axis, as a multiple of the player's height.
    #:
    #: Length rather than height, and the one family measured across rather than up. Every
    #: projectile is drawn pointing right, so its travel axis is its width; declaring a height for
    #: a dart drawn lengthwise would describe how thick it is, which is not the dimension anyone
    #: means. The published calibration names the axis it measured so the consumer cannot guess.
    length_units: float | None = None
    prompt: str

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalized_text(value, "projectile display_name")

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "projectile prompt", multiline=True)

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "projectile reference_id")
        return value

    @field_validator("length_units")
    @classmethod
    def validate_length_units(cls, value: float | None) -> float | None:
        return _validated_height_units(value, "projectile length_units")


class ProjectileContentCatalog(PersistedContractModel):
    schema_version: Literal[2]
    kind: Literal["projectile-content-v2"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    references: list[ContentReference] = Field(min_length=1, max_length=32)
    #: At least one. The FILE is what a game may omit; a declared catalog holding nothing would be
    #: a member whose references are all unused, which the closure check rejects anyway.
    projectiles: list[ProjectileContent] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_catalog(self) -> ProjectileContentCatalog:
        unique_values((entry.projectile_id for entry in self.projectiles), "projectile_id")
        _validate_reference_closure(self.references, self.projectiles)
        return self


def load_player_content_bytes(data: bytes) -> PlayerContentCatalog:
    return parse_toml_contract(data, model=PlayerContentCatalog, label="player content")


def load_mob_content_bytes(data: bytes) -> MobContentCatalog:
    return parse_toml_contract(data, model=MobContentCatalog, label="mob content")


def load_npc_content_bytes(data: bytes) -> NpcContentCatalog:
    return parse_toml_contract(data, model=NpcContentCatalog, label="NPC content")


def load_prop_content_bytes(data: bytes) -> PropContentCatalog:
    return parse_toml_contract(data, model=PropContentCatalog, label="prop content")


def load_item_content_bytes(data: bytes) -> ItemContentCatalog:
    return parse_toml_contract(data, model=ItemContentCatalog, label="item content")


def load_projectile_content_bytes(data: bytes) -> ProjectileContentCatalog:
    return parse_toml_contract(data, model=ProjectileContentCatalog, label="projectile content")


def canonical_game_content_json(contract: PersistedContractModel) -> bytes:
    return canonical_contract_json(contract)


__all__ = [
    "GAME_CONTENT_SCHEMA_VERSION",
    "NPC_CONTENT_SCHEMA_VERSION",
    "PLAYER_CONTENT_SCHEMA_VERSION",
    "WEAPON_CLASSES_BY_PLAYER_EQUIPMENT",
    "ContentReference",
    "DialogueArtDirection",
    "ItemContent",
    "ItemContentCatalog",
    "MobContent",
    "MobContentCatalog",
    "NpcContent",
    "NpcContentCatalog",
    "NpcWorldOrientation",
    "PlayerContent",
    "PlayerContentCatalog",
    "PlayerEquipment",
    "ProjectileContent",
    "ProjectileContentCatalog",
    "ProjectileFlight",
    "ProjectileImpact",
    "ProjectileSilhouette",
    "PropContent",
    "PropContentCatalog",
    "canonical_game_content_json",
    "load_item_content_bytes",
    "load_projectile_content_bytes",
    "load_mob_content_bytes",
    "load_npc_content_bytes",
    "load_player_content_bytes",
    "load_prop_content_bytes",
]
