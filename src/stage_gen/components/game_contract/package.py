"""Exact-current prepared-package root contract (``game-contract-v5``)."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator

from stage_gen.components._game_input import (
    GAME_ID_PATTERN,
    KEBAB_ID_PATTERN,
    SHA256_PATTERN,
    SNAKE_ID_PATTERN,
    canonical_contract_json,
    normalized_text,
    parse_toml_contract,
    portable_relative_path,
    sha256_bytes,
    unique_values,
)
from stage_gen.contracts.artifacts import PersistedContractModel

PREPARED_GAME_CONTRACT_SCHEMA_VERSION = 5


class PackageSource(PersistedContractModel):
    source: str
    source_sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        return portable_relative_path(value, "package source")


class UniverseSource(PackageSource):
    pass


class MapSource(PackageSource):
    map_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)

    @model_validator(mode="after")
    def validate_filename(self) -> MapSource:
        if self.source != f"maps/{self.map_id}.toml":
            raise ValueError("map source must equal maps/<map_id>.toml")
        return self


class SequenceCatalogSource(PersistedContractModel):
    index_source: str
    index_sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("index_source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        return portable_relative_path(value, "sequence index source")


class PreparedPresentation(PersistedContractModel):
    view_profile: Literal["side_view_2d"]
    gameplay_space: Literal["side_plane"]


class PreparedStyle(PersistedContractModel):
    label: str
    keywords: list[str] = Field(min_length=1, max_length=32)
    avoid: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        return normalized_text(value, "style.label")

    @field_validator("keywords", "avoid")
    @classmethod
    def validate_entries(cls, value: list[str], info: ValidationInfo) -> list[str]:
        normalized = [
            normalized_text(entry, f"style.{info.field_name or 'entry'}") for entry in value
        ]
        unique_values(normalized, f"style.{info.field_name or 'entry'}")
        return normalized


class PreparedProportion(PersistedContractModel):
    heads_tall: float = Field(ge=1.5, le=12.0)
    by_body_kind: dict[str, float] = Field(default_factory=dict)

    @field_validator("by_body_kind")
    @classmethod
    def validate_body_kinds(cls, value: dict[str, float]) -> dict[str, float]:
        for body_kind, heads_tall in value.items():
            if not body_kind or body_kind != body_kind.strip():
                raise ValueError("proportion body kinds must be non-empty trimmed strings")
            if heads_tall < 1.5 or heads_tall > 12.0:
                raise ValueError("proportion body-kind values must be between 1.5 and 12.0")
        return value

    def heads_for(self, body_kind: str) -> float:
        return self.by_body_kind.get(body_kind, self.heads_tall)


class PreparedCast(PersistedContractModel):
    player_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    mob_ids: list[str] = Field(min_length=1, max_length=64)
    npc_ids: list[str] = Field(min_length=1, max_length=64)

    @field_validator("mob_ids", "npc_ids")
    @classmethod
    def validate_ids(cls, value: list[str], info: ValidationInfo) -> list[str]:
        for identifier in value:
            if not identifier or identifier != identifier.strip():
                raise ValueError(f"cast.{info.field_name} must contain trimmed IDs")
            if re.fullmatch(SNAKE_ID_PATTERN, identifier) is None:
                raise ValueError(f"cast.{info.field_name} contains an invalid ID")
        unique_values(value, f"cast.{info.field_name}")
        return value


class PreparedContentSources(PersistedContractModel):
    player: PackageSource
    mobs: PackageSource
    npcs: PackageSource
    props: PackageSource
    items: PackageSource


class PreparedEvidence(PersistedContractModel):
    artifact_source: str
    artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    provenance_source: str
    provenance_sha256: str = Field(pattern=SHA256_PATTERN)
    review_source: str
    review_sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("artifact_source", "provenance_source", "review_source")
    @classmethod
    def validate_source(cls, value: str, info: ValidationInfo) -> str:
        source = portable_relative_path(value, f"evidence.{info.field_name}")
        if not source.startswith("references/"):
            raise ValueError("evidence sources must live under references/")
        return source

    @model_validator(mode="after")
    def validate_extensions(self) -> PreparedEvidence:
        if not self.provenance_source.endswith(".provenance.json"):
            raise ValueError("evidence provenance_source must end in .provenance.json")
        if not self.review_source.endswith(".visual-review.md"):
            raise ValueError("evidence review_source must end in .visual-review.md")
        return self


class PreparedRights(PersistedContractModel):
    status: Literal["unreviewed", "restricted", "redistribution-approved"]
    basis: list[str] = Field(min_length=1, max_length=32)

    @field_validator("basis")
    @classmethod
    def validate_basis(cls, value: list[str]) -> list[str]:
        normalized = [normalized_text(entry, "rights basis") for entry in value]
        unique_values(normalized, "rights basis")
        return normalized


class PreparedGameContract(PersistedContractModel):
    """One prepared game's complete, digest-bound membership root."""

    schema_version: Literal[5]
    kind: Literal["game-contract-v5"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    display_name: str
    universe: UniverseSource
    presentation: PreparedPresentation
    style: PreparedStyle
    proportion: PreparedProportion
    cast: PreparedCast
    gameplay: PackageSource
    ui: PackageSource
    soundtrack: PackageSource
    maps: list[MapSource] = Field(min_length=1, max_length=64)
    content: PreparedContentSources
    sequences: SequenceCatalogSource
    evidence: dict[str, PreparedEvidence] = Field(min_length=1, max_length=64)
    rights: PreparedRights

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalized_text(value, "display_name")

    @field_validator("maps")
    @classmethod
    def validate_maps(cls, value: list[MapSource]) -> list[MapSource]:
        unique_values((entry.map_id for entry in value), "map_id")
        unique_values((entry.source for entry in value), "map source")
        return value

    @field_validator("evidence")
    @classmethod
    def validate_evidence(cls, value: dict[str, PreparedEvidence]) -> dict[str, PreparedEvidence]:
        for evidence_id in value:
            if re.fullmatch(SNAKE_ID_PATTERN, evidence_id) is None:
                raise ValueError("evidence keys must be lower_snake_case IDs")
        paths = [
            path
            for entry in value.values()
            for path in (entry.artifact_source, entry.provenance_source, entry.review_source)
        ]
        unique_values(paths, "evidence source")
        return value

    @model_validator(mode="after")
    def validate_member_sources(self) -> PreparedGameContract:
        exact_sources = {
            "universe": (self.universe.source, "universe.md"),
            "gameplay": (self.gameplay.source, "gameplay.toml"),
            "ui": (self.ui.source, "ui.toml"),
            "soundtrack": (self.soundtrack.source, "soundtrack.toml"),
            "content.player": (self.content.player.source, "content/player.toml"),
            "content.mobs": (self.content.mobs.source, "content/mobs.toml"),
            "content.npcs": (self.content.npcs.source, "content/npcs.toml"),
            "content.props": (self.content.props.source, "content/props.toml"),
            "content.items": (self.content.items.source, "content/items.toml"),
            "sequences": (self.sequences.index_source, "sequences/index.toml"),
        }
        for label, (actual, expected) in exact_sources.items():
            if actual != expected:
                raise ValueError(f"{label} source must equal {expected}")
        member_sources = [
            self.universe.source,
            self.gameplay.source,
            self.ui.source,
            self.soundtrack.source,
            *(entry.source for entry in self.maps),
            self.content.player.source,
            self.content.mobs.source,
            self.content.npcs.source,
            self.content.props.source,
            self.content.items.source,
            self.sequences.index_source,
        ]
        unique_values(member_sources, "package member source")
        return self


def load_prepared_game_contract_bytes(data: bytes) -> PreparedGameContract:
    return parse_toml_contract(data, model=PreparedGameContract, label="prepared game contract")


def canonical_prepared_game_contract_json(contract: PreparedGameContract) -> bytes:
    return canonical_contract_json(contract)


def prepared_game_contract_sha256(contract: PreparedGameContract) -> str:
    return sha256_bytes(canonical_prepared_game_contract_json(contract))


__all__ = [
    "PREPARED_GAME_CONTRACT_SCHEMA_VERSION",
    "MapSource",
    "PackageSource",
    "PreparedCast",
    "PreparedContentSources",
    "PreparedEvidence",
    "PreparedGameContract",
    "PreparedPresentation",
    "PreparedProportion",
    "PreparedRights",
    "PreparedStyle",
    "SequenceCatalogSource",
    "UniverseSource",
    "canonical_prepared_game_contract_json",
    "load_prepared_game_contract_bytes",
    "prepared_game_contract_sha256",
]
