"""Exact-current compound map-generation contract (``game-map-v3``)."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, field_validator, model_validator

from stage_gen.components._game_input import (
    GAME_ID_PATTERN,
    KEBAB_ID_PATTERN,
    SHA256_PATTERN,
    SNAKE_ID_PATTERN,
    canonical_contract_json,
    normalized_text,
    parse_toml_contract,
    portable_relative_path,
    unique_values,
)
from stage_gen.contracts.artifacts import PersistedContractModel

PREPARED_GAME_MAP_SCHEMA_VERSION = 3


class PreparedMapView(PersistedContractModel):
    profile: Literal["side_view_2d"]
    gameplay_space: Literal["side_plane"]
    camera_behavior: Literal["scrolling"]
    scroll_axis: Literal["x"]


class PreparedMapContinuity(PersistedContractModel):
    seamless_axis: Literal["x"]


class PreparedMapReference(PersistedContractModel):
    reference_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    source: str
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    rights_status: Literal["unreviewed", "restricted", "redistribution-approved"]
    rights_basis: list[str] = Field(min_length=1, max_length=16)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        source = portable_relative_path(value, "map reference source")
        if not source.startswith("references/"):
            raise ValueError("map references must live under references/")
        if PurePosixPath(source).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("map references must use PNG, JPEG, or WebP")
        return source

    @field_validator("rights_basis")
    @classmethod
    def validate_rights_basis(cls, value: list[str]) -> list[str]:
        normalized = [normalized_text(entry, "map reference rights basis") for entry in value]
        unique_values(normalized, "map reference rights basis")
        return normalized


class PreparedMapLayer(PersistedContractModel):
    layer_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    plane: Literal["background", "foreground"]
    order: int = Field(ge=0, le=7)
    parallax: float = Field(ge=0.0, le=8.0)
    alpha_mode: Literal["opaque", "transparent"]
    prompt: str

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "map layer reference_id")
        return value

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "map layer prompt", multiline=True)


class PreparedMapGround(PersistedContractModel):
    mode: Literal["tileset-12x4-v1"]
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    prompt: str

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "map ground reference_id")
        return value

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "map ground prompt", multiline=True)


class PreparedGameMap(PersistedContractModel):
    schema_version: Literal[3]
    kind: Literal["game-map-v3"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    map_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    display_name: str
    view: PreparedMapView
    continuity: PreparedMapContinuity
    references: list[PreparedMapReference] = Field(min_length=1, max_length=32)
    layers: list[PreparedMapLayer] = Field(min_length=1, max_length=8)
    ground: PreparedMapGround

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalized_text(value, "map display_name")

    @field_validator("references")
    @classmethod
    def validate_references(cls, value: list[PreparedMapReference]) -> list[PreparedMapReference]:
        unique_values((entry.reference_id for entry in value), "map reference_id")
        unique_values((entry.source for entry in value), "map reference source")
        return value

    @field_validator("layers")
    @classmethod
    def validate_layers(cls, value: list[PreparedMapLayer]) -> list[PreparedMapLayer]:
        unique_values((entry.layer_id for entry in value), "map layer_id")
        for plane in ("background", "foreground"):
            orders = sorted(entry.order for entry in value if entry.plane == plane)
            if orders and orders != list(range(len(orders))):
                raise ValueError(f"{plane} layer order must be contiguous from zero")
        return value

    @model_validator(mode="after")
    def validate_composition(self) -> PreparedGameMap:
        reference_ids = {entry.reference_id for entry in self.references}
        selected_ids = {
            reference_id for layer in self.layers for reference_id in layer.reference_ids
        } | set(self.ground.reference_ids)
        unknown = sorted(selected_ids - reference_ids)
        if unknown:
            raise ValueError("map generation references unknown IDs: " + ", ".join(unknown))
        unused = sorted(reference_ids - selected_ids)
        if unused:
            raise ValueError("map declares unused reference IDs: " + ", ".join(unused))
        opaque_layers = [layer for layer in self.layers if layer.alpha_mode == "opaque"]
        if len(opaque_layers) != 1:
            raise ValueError("map must declare exactly one opaque layer")
        base = opaque_layers[0]
        if base.plane != "background" or base.order != 0 or base.parallax != 0.0:
            raise ValueError("the opaque map base must be background order zero with parallax zero")
        if any(layer.alpha_mode != "transparent" for layer in self.layers if layer is not base):
            raise ValueError("every non-base map layer must use transparent alpha")
        return self


def load_prepared_game_map_bytes(data: bytes) -> PreparedGameMap:
    return parse_toml_contract(data, model=PreparedGameMap, label="prepared game map")


def canonical_prepared_game_map_json(game_map: PreparedGameMap) -> bytes:
    return canonical_contract_json(game_map)


__all__ = [
    "PREPARED_GAME_MAP_SCHEMA_VERSION",
    "PreparedGameMap",
    "PreparedMapContinuity",
    "PreparedMapGround",
    "PreparedMapLayer",
    "PreparedMapReference",
    "PreparedMapView",
    "canonical_prepared_game_map_json",
    "load_prepared_game_map_bytes",
]
