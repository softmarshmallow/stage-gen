"""Exact-current prepared player, mob, NPC, prop, and item catalogs."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Literal, Protocol

from pydantic import Field, ValidationInfo, field_validator, model_validator

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
from stage_gen.contracts.artifacts import PersistedContractModel

GAME_CONTENT_SCHEMA_VERSION = 1


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


class PlayerContent(PersistedContractModel):
    player_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    display_name: str
    body_kind: str
    age: int = Field(ge=18, le=130)
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    prompt: str
    motion_states: list[
        Literal[
            "idle",
            "walk",
            "run",
            "jump",
            "climb",
            "basic_attack",
            "skill_cast",
            "hurt",
            "death",
        ]
    ] = Field(min_length=1)
    required_facings: list[Literal["left", "right"]] = Field(min_length=2, max_length=2)
    dialogue_art: DialogueArtDirection

    @field_validator("display_name", "body_kind")
    @classmethod
    def validate_scalar_text(cls, value: str, info: ValidationInfo) -> str:
        return normalized_text(value, f"player {info.field_name}")

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "player prompt", multiline=True)

    @field_validator("reference_ids", "motion_states", "required_facings")
    @classmethod
    def validate_lists(cls, value: list[str], info: ValidationInfo) -> list[str]:
        unique_values(value, f"player {info.field_name}")
        return value

    @model_validator(mode="after")
    def validate_facings(self) -> PlayerContent:
        if set(self.required_facings) != {"left", "right"}:
            raise ValueError("player required_facings must contain left and right")
        return self


class PlayerContentCatalog(PersistedContractModel):
    schema_version: Literal[1]
    kind: Literal["player-content-v1"]
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
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    prompt: str
    motion_states: list[Literal["idle", "move", "attack", "hurt", "death"]] = Field(min_length=1)

    @field_validator("display_name", "body_kind")
    @classmethod
    def validate_scalar_text(cls, value: str, info: ValidationInfo) -> str:
        return normalized_text(value, f"mob {info.field_name}")

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "mob prompt", multiline=True)

    @field_validator("reference_ids", "motion_states")
    @classmethod
    def validate_lists(cls, value: list[str], info: ValidationInfo) -> list[str]:
        unique_values(value, f"mob {info.field_name}")
        return value


class MobContentCatalog(PersistedContractModel):
    schema_version: Literal[1]
    kind: Literal["mob-content-v1"]
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
    display_name: str
    role: str
    body_kind: str
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    prompt: str
    world_motion_states: list[Literal["idle"]] = Field(min_length=1, max_length=1)
    dialogue_expressions: list[str] = Field(min_length=1, max_length=16)

    @field_validator("display_name", "role", "body_kind")
    @classmethod
    def validate_scalar_text(cls, value: str, info: ValidationInfo) -> str:
        return normalized_text(value, f"npc {info.field_name}")

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "npc prompt", multiline=True)

    @field_validator("reference_ids", "world_motion_states", "dialogue_expressions")
    @classmethod
    def validate_lists(cls, value: list[str], info: ValidationInfo) -> list[str]:
        unique_values(value, f"npc {info.field_name}")
        return value


class NpcContentCatalog(PersistedContractModel):
    schema_version: Literal[1]
    kind: Literal["npc-content-v1"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
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


class PropContentCatalog(PersistedContractModel):
    schema_version: Literal[1]
    kind: Literal["prop-content-v1"]
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
        "currency", "healing_consumable", "traversal_tool", "key_item", "quest_collectible"
    ]
    reference_ids: list[str] = Field(min_length=1, max_length=16)
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


class ItemContentCatalog(PersistedContractModel):
    schema_version: Literal[1]
    kind: Literal["item-content-v1"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    references: list[ContentReference] = Field(min_length=1, max_length=32)
    items: list[ItemContent] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_catalog(self) -> ItemContentCatalog:
        unique_values((entry.item_id for entry in self.items), "item_id")
        _validate_reference_closure(self.references, self.items)
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


def canonical_game_content_json(contract: PersistedContractModel) -> bytes:
    return canonical_contract_json(contract)


__all__ = [
    "GAME_CONTENT_SCHEMA_VERSION",
    "ContentReference",
    "DialogueArtDirection",
    "ItemContent",
    "ItemContentCatalog",
    "MobContent",
    "MobContentCatalog",
    "NpcContent",
    "NpcContentCatalog",
    "PlayerContent",
    "PlayerContentCatalog",
    "PropContent",
    "PropContentCatalog",
    "canonical_game_content_json",
    "load_item_content_bytes",
    "load_mob_content_bytes",
    "load_npc_content_bytes",
    "load_player_content_bytes",
    "load_prop_content_bytes",
]
