"""Authored game-map identities, engine-neutral level profiles, and their ordered book.

The current game-map-v2 document embeds the descriptive view, camera, traversal, and
gameplay-mechanism capabilities that make a level portable across recipes and optional runtimes
without assigning engine implementation details to the map contract. The authored book, book
binding, and nested level profile keep their own independently current v1 identities.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import Field, field_validator, model_validator

from gnode import PersistedContractModel

GAME_MAP_SCHEMA_VERSION = 2
GAME_MAP_BOOK_SCHEMA_VERSION = 1
_JS_SAFE_INTEGER_MAX = 9_007_199_254_740_991

_GAME_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_MAP_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_TRACK_ID = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")

LevelRole = Literal["social_hub", "combat_field"]
LevelScrollAxis = Literal["horizontal", "vertical"]
#: `climb` is role-neutral on purpose. A level that admits climbing admits it for every climbable
#: role the map places; which pose the player draws is decided by the climbable, not the level.
LevelTraversalAffordance = Literal[
    "ground_move",
    "jump",
    "air_jump",
    "drop_through",
    "climb",
]

_SCROLL_AXIS_ORDER = {"horizontal": 0, "vertical": 1}
_AFFORDANCE_ORDER = {
    "ground_move": 0,
    "jump": 1,
    "air_jump": 2,
    "drop_through": 3,
    "climb": 4,
}


def _normalized_text(value: str, label: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if not normalized or normalized != normalized.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")
    return normalized


class LevelView(PersistedContractModel):
    """Engine-neutral projection and viewpoint of a playable level."""

    projection: Literal["orthographic_2d"]
    viewpoint: Literal["side_on"]


class LevelCamera(PersistedContractModel):
    """Observable camera behavior without engine component settings."""

    tracking_mode: Literal["player_follow"]
    framing_mode: Literal["dead_zone"]
    scroll_axes: list[LevelScrollAxis] = Field(min_length=1, max_length=2)

    @field_validator("scroll_axes")
    @classmethod
    def validate_scroll_axes(cls, value: list[LevelScrollAxis]) -> list[LevelScrollAxis]:
        if len(set(value)) != len(value):
            raise ValueError("camera.scroll_axes must be unique")
        if value != sorted(value, key=_SCROLL_AXIS_ORDER.__getitem__):
            raise ValueError("camera.scroll_axes must use canonical horizontal, vertical order")
        return value


class LevelTraversal(PersistedContractModel):
    """Terrain model and player traversal capabilities exposed by the level."""

    ground_model: Literal["heightfield"]
    platform_model: Literal["none", "one_way"]
    affordances: list[LevelTraversalAffordance] = Field(min_length=1, max_length=5)

    @field_validator("affordances")
    @classmethod
    def validate_affordance_order(
        cls, value: list[LevelTraversalAffordance]
    ) -> list[LevelTraversalAffordance]:
        if len(set(value)) != len(value):
            raise ValueError("traversal.affordances must be unique")
        if value != sorted(value, key=_AFFORDANCE_ORDER.__getitem__):
            raise ValueError("traversal.affordances must use canonical capability order")
        return value

    @model_validator(mode="after")
    def validate_affordance_dependencies(self) -> LevelTraversal:
        affordances = set(self.affordances)
        if "air_jump" in affordances and "jump" not in affordances:
            raise ValueError("air_jump requires jump")
        platform_affordances = {"drop_through", "climb"}
        if affordances & platform_affordances and self.platform_model != "one_way":
            raise ValueError("drop_through and climb require platform_model='one_way'")
        return self


class LevelMechanisms(PersistedContractModel):
    """Gameplay mechanisms a level declares, independently of its descriptive role."""

    encounter_model: Literal["none", "continuous_population"]
    combat_model: Literal["none", "real_time_action"]
    loot_model: Literal["none", "defeat_drops"]
    transition_model: Literal["bidirectional_portals"]
    interaction_model: Literal["none", "proximity_dialogue"]

    @model_validator(mode="after")
    def validate_loot_requires_combat(self) -> LevelMechanisms:
        if self.loot_model == "defeat_drops" and self.combat_model != "real_time_action":
            raise ValueError("loot_model='defeat_drops' requires combat_model='real_time_action'")
        return self


class LevelProfile(PersistedContractModel):
    """Complete engine-neutral classification and capability profile for one level."""

    schema_version: Literal[1] = 1
    kind: Literal["level-profile-v1"] = "level-profile-v1"
    role: LevelRole
    view: LevelView
    camera: LevelCamera
    traversal: LevelTraversal
    mechanisms: LevelMechanisms


class GameMap(PersistedContractModel):
    """One current authored map's stable metadata, track pool, and level profile."""

    schema_version: Literal[2]
    kind: Literal["game-map-v2"]
    game_id: str = Field(pattern=_GAME_ID.pattern, max_length=96)
    map_id: str = Field(pattern=_MAP_ID.pattern, max_length=96)
    revision: int = Field(ge=1, le=_JS_SAFE_INTEGER_MAX)
    display_name: str = Field(max_length=160)
    soundtrack_track_ids: list[str] = Field(min_length=2, max_length=64)
    level_profile: LevelProfile

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return _normalized_text(value, "display_name")

    @field_validator("soundtrack_track_ids")
    @classmethod
    def validate_track_ids(cls, value: list[str]) -> list[str]:
        for track_id in value:
            if len(track_id) > 64 or not _TRACK_ID.fullmatch(track_id):
                raise ValueError(f"invalid soundtrack track_id: {track_id!r}")
        if len(set(value)) != len(value):
            raise ValueError("soundtrack_track_ids must be unique")
        # Track selection is shuffle-based, so authored list order is not semantic.
        return sorted(value)


class GameMapReference(PersistedContractModel):
    """Digest lock for ``maps/<map_id>.toml`` inside one map book."""

    map_id: str = Field(pattern=_MAP_ID.pattern, max_length=96)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class GameMapBook(PersistedContractModel):
    """The ordered maps a game exposes through this v1 book."""

    schema_version: Literal[1]
    kind: Literal["game-map-book-v1"]
    game_id: str = Field(pattern=_GAME_ID.pattern, max_length=96)
    revision: int = Field(ge=1, le=_JS_SAFE_INTEGER_MAX)
    entry_map_id: str = Field(pattern=_MAP_ID.pattern, max_length=96)
    maps: list[GameMapReference] = Field(min_length=2, max_length=64)

    @model_validator(mode="after")
    def validate_order_and_identity(self) -> GameMapBook:
        map_ids = [entry.map_id for entry in self.maps]
        if len(set(map_ids)) != len(map_ids):
            raise ValueError("map book map_id values must be unique")
        if self.entry_map_id != map_ids[0]:
            raise ValueError("entry_map_id must equal the first ordered map_id in v1")
        return self

    @property
    def map_ids(self) -> tuple[str, ...]:
        return tuple(entry.map_id for entry in self.maps)


class GameMapBookBinding(PersistedContractModel):
    """Digest-bound reference to ``library/games/<game_id>/maps/index.toml``."""

    schema_version: Literal[1]
    kind: Literal["game-map-book-binding-v1"]
    ref: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("ref")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        normalized = _normalized_text(value, "game map book ref")
        if "\\" in normalized or ":" in normalized or normalized.startswith("/"):
            raise ValueError("game map book ref must be a portable relative path")
        parts = normalized.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("game map book ref must not contain empty, dot, or parent segments")
        return normalized


class ResolvedGameMapBookDocument(PersistedContractModel):
    """Canonical run-local projection of an index and all of its locked maps."""

    schema_version: Literal[2]
    kind: Literal["resolved-game-map-book-v2"]
    game_id: str = Field(pattern=_GAME_ID.pattern, max_length=96)
    revision: int = Field(ge=1, le=_JS_SAFE_INTEGER_MAX)
    entry_map_id: str = Field(pattern=_MAP_ID.pattern, max_length=96)
    maps: list[GameMap] = Field(min_length=2, max_length=64)

    @model_validator(mode="after")
    def validate_map_book(self) -> ResolvedGameMapBookDocument:
        map_ids = [game_map.map_id for game_map in self.maps]
        if len(set(map_ids)) != len(map_ids):
            raise ValueError("resolved map book map_id values must be unique")
        if self.entry_map_id != map_ids[0]:
            raise ValueError("resolved entry_map_id must equal the first map_id")
        if any(game_map.game_id != self.game_id for game_map in self.maps):
            raise ValueError("resolved map book maps must belong to its game_id")
        return self

    @property
    def map_ids(self) -> tuple[str, ...]:
        return tuple(game_map.map_id for game_map in self.maps)

    @property
    def referenced_track_ids(self) -> frozenset[str]:
        return frozenset(
            track_id for game_map in self.maps for track_id in game_map.soundtrack_track_ids
        )


__all__ = [
    "GAME_MAP_BOOK_SCHEMA_VERSION",
    "GAME_MAP_SCHEMA_VERSION",
    "GameMap",
    "GameMapBook",
    "GameMapBookBinding",
    "GameMapReference",
    "LevelCamera",
    "LevelMechanisms",
    "LevelProfile",
    "LevelRole",
    "LevelScrollAxis",
    "LevelTraversal",
    "LevelTraversalAffordance",
    "LevelView",
    "ResolvedGameMapBookDocument",
]
