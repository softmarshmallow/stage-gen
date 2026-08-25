"""Authored mob-population contracts for a side-scrolling game's hunting maps.

The game contract owns the desired population and the consumer owns placement against its terrain.
Authors select the generated roster by one-based ascending mob tier. The runtime-facing projection
validates those tiers and emits zero-based mob slots as plain lower_snake_case manifest JSON.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection
from itertools import pairwise
from typing import Literal

from pydantic import Field, field_validator, model_validator

from stage_gen.contracts.artifacts import PersistedContractModel

_SLUG = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_UINT32_MAX = (1 << 32) - 1

SpawnVisibility = Literal["offscreen_required", "offscreen_preferred", "allow_onscreen"]
ReplacementPolicy = Literal["reroll_spawn_table", "same_archetype"]


def _slug(value: str, label: str) -> str:
    """Return a normalized portable identifier or reject it by name."""

    normalized = unicodedata.normalize("NFC", value)
    if not _SLUG.fullmatch(normalized):
        raise ValueError(f"{label} must be a lowercase kebab-case slug")
    return normalized


class MobSpawnEntry(PersistedContractModel):
    """One weighted mob-archetype entry in a zone's spawn table."""

    # Authored tiers are one-based and follow the generated world's stable ascending roster.
    # The scrolling runtime addresses the same roster with a zero-based slot; that adapter-only
    # representation is produced by ``manifest_projection`` below rather than leaked into TOML.
    mob_tier: int = Field(ge=1)
    weight: int = Field(ge=1)
    min_alive: int = Field(default=0, ge=0)
    max_alive: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_population_range(self) -> MobSpawnEntry:
        if self.min_alive > self.max_alive:
            raise ValueError("min_alive must be less than or equal to max_alive")
        return self


class MobSpawnZone(PersistedContractModel):
    """A bounded terrain territory maintained by one population controller."""

    zone_id: str
    surface: Literal["terrain"] = "terrain"
    left_column: int = Field(ge=0)
    right_column_exclusive: int = Field(ge=1)

    initial_population: int = Field(ge=0)
    target_population: int = Field(ge=1)
    population_cap: int = Field(ge=1)

    respawn_delay_ms: int = Field(ge=0)
    respawn_variance_ms: int = Field(ge=0)
    spawn_interval_ms: int = Field(ge=1)
    spawn_batch_size: int = Field(ge=1)
    retry_delay_ms: int = Field(ge=1)

    spawn_visibility: SpawnVisibility
    camera_margin_px: int = Field(ge=0)
    min_player_distance_px: int = Field(ge=0)
    minimum_spawn_separation_px: int = Field(ge=0)
    wander_radius_px: int = Field(ge=0)
    pursuit_leash_px: int = Field(ge=0)
    replacement_policy: ReplacementPolicy
    spawn_table: list[MobSpawnEntry] = Field(min_length=1)

    @field_validator("zone_id")
    @classmethod
    def validate_zone_id(cls, value: str) -> str:
        return _slug(value, "zone_id")

    @model_validator(mode="after")
    def validate_zone_contract(self) -> MobSpawnZone:
        if self.left_column >= self.right_column_exclusive:
            raise ValueError("left_column must be less than right_column_exclusive")
        if not (self.initial_population <= self.target_population <= self.population_cap):
            raise ValueError(
                "population must satisfy initial_population <= target_population <= population_cap"
            )
        if self.respawn_variance_ms > self.respawn_delay_ms:
            raise ValueError(
                "respawn_variance_ms must not exceed respawn_delay_ms; "
                "the minimum respawn delay cannot be negative"
            )
        if self.spawn_batch_size > self.population_cap:
            raise ValueError("spawn_batch_size must not exceed population_cap")
        if self.pursuit_leash_px < self.wander_radius_px:
            raise ValueError("pursuit_leash_px must be greater than or equal to wander_radius_px")

        tiers = [entry.mob_tier for entry in self.spawn_table]
        if len(set(tiers)) != len(tiers):
            raise ValueError("spawn_table mob_tier values must be unique within a zone")

        for entry in self.spawn_table:
            if entry.max_alive > self.population_cap:
                raise ValueError(
                    f"mob_tier {entry.mob_tier} max_alive must not exceed population_cap"
                )

        minimum_required = sum(entry.min_alive for entry in self.spawn_table)
        maximum_available = sum(entry.max_alive for entry in self.spawn_table)
        if minimum_required > self.target_population:
            raise ValueError("sum of spawn_table min_alive values exceeds target_population")
        if maximum_available < self.target_population:
            raise ValueError("sum of spawn_table max_alive values cannot reach target_population")
        return self


class MobPopulationMap(PersistedContractModel):
    """Population authoring for one map instance; zone identifiers are map-scoped."""

    map_id: str
    seed_salt: int = Field(ge=0, le=_UINT32_MAX)
    zones: list[MobSpawnZone] = Field(min_length=1)

    @field_validator("map_id")
    @classmethod
    def validate_map_id(cls, value: str) -> str:
        return _slug(value, "map_id")

    @model_validator(mode="after")
    def validate_unique_zone_ids(self) -> MobPopulationMap:
        zone_ids = [zone.zone_id for zone in self.zones]
        if len(set(zone_ids)) != len(zone_ids):
            raise ValueError(f"map {self.map_id!r} must have unique zone_id values")
        ordered = sorted(
            self.zones,
            key=lambda zone: (zone.left_column, zone.right_column_exclusive),
        )
        for previous, current in pairwise(ordered):
            if current.left_column < previous.right_column_exclusive:
                raise ValueError(
                    f"map {self.map_id!r} spawn zones {previous.zone_id!r} and "
                    f"{current.zone_id!r} overlap"
                )
        return self


class MobPopulationDirection(PersistedContractModel):
    """Versioned authoring contract for continuous hunting-map repopulation."""

    schema_version: Literal[1] = 1
    kind: Literal["mob-population-v1"] = "mob-population-v1"
    update_interval_ms: int = Field(ge=1)
    max_spawn_batch_per_update: int = Field(ge=1)
    maps: list[MobPopulationMap] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_direction_contract(self) -> MobPopulationDirection:
        map_ids = [population_map.map_id for population_map in self.maps]
        if len(set(map_ids)) != len(map_ids):
            raise ValueError("mob population maps must have unique map_id values")

        for population_map in self.maps:
            for zone in population_map.zones:
                if zone.spawn_batch_size > self.max_spawn_batch_per_update:
                    raise ValueError(
                        f"map {population_map.map_id!r} zone {zone.zone_id!r} "
                        "spawn_batch_size must not exceed max_spawn_batch_per_update"
                    )
        return self

    def manifest_projection(
        self,
        *,
        mob_count: int,
        allowed_map_ids: Collection[str] | None = None,
        stage_column_count: int | None = None,
    ) -> dict[str, object]:
        """Return runtime JSON after resolving tiers and adapter geometry.

        ``mob_count`` comes from the generated world roster, so it cannot be validated while
        loading ``game.toml``.  Keeping that check at this projection boundary prevents the web
        runtime from receiving a spawn table that names artwork the run did not publish.

        ``allowed_map_ids`` is optional because the game contract remains reusable by consumers
        that do not publish a map catalog.  A map-aware adapter passes its hunting-map identities
        explicitly. ``stage_column_count`` likewise lets the adapter reject authored half-open
        zone bounds that cannot exist in its terrain grid.
        """

        if isinstance(mob_count, bool) or not isinstance(mob_count, int) or mob_count < 1:
            raise ValueError("mob_count must be a positive integer")

        allowed: frozenset[str] | None = None
        if allowed_map_ids is not None:
            if isinstance(allowed_map_ids, (str, bytes)) or any(
                not isinstance(map_id, str) for map_id in allowed_map_ids
            ):
                raise ValueError("allowed_map_ids must be a collection of strings")
            allowed = frozenset(allowed_map_ids)
            if not allowed:
                raise ValueError("allowed_map_ids must contain at least one hunting map")

        if stage_column_count is not None and (
            isinstance(stage_column_count, bool)
            or not isinstance(stage_column_count, int)
            or stage_column_count < 1
        ):
            raise ValueError("stage_column_count must be a positive integer")

        for map_index, population_map in enumerate(self.maps):
            if allowed is not None and population_map.map_id not in allowed:
                raise ValueError(
                    f"maps[{map_index}].map_id {population_map.map_id!r} "
                    "is not an allowed hunting map"
                )
            for zone_index, zone in enumerate(population_map.zones):
                if (
                    stage_column_count is not None
                    and zone.right_column_exclusive > stage_column_count
                ):
                    raise ValueError(
                        f"maps[{map_index}].zones[{zone_index}].right_column_exclusive "
                        f"{zone.right_column_exclusive} exceeds stage_column_count "
                        f"{stage_column_count}"
                    )
                for entry_index, entry in enumerate(zone.spawn_table):
                    if entry.mob_tier > mob_count:
                        raise ValueError(
                            f"maps[{map_index}].zones[{zone_index}].spawn_table[{entry_index}]"
                            f".mob_tier {entry.mob_tier} exceeds mob_count {mob_count}"
                        )

        # No aliases are defined anywhere in this subsystem.  Spelling out by_alias=False makes
        # the manifest boundary explicit and keeps every emitted key lower_snake_case. The
        # runtime's zero-based ``mob_slot`` is intentionally assembled here rather than made an
        # alias: authored canonical game JSON must continue to say one-based ``mob_tier``.
        projection = self.model_dump(mode="json", by_alias=False)
        projected_maps = projection["maps"]
        assert isinstance(projected_maps, list)
        for population_map, projected_map in zip(self.maps, projected_maps, strict=True):
            assert isinstance(projected_map, dict)
            projected_zones = projected_map["zones"]
            assert isinstance(projected_zones, list)
            for zone, projected_zone in zip(population_map.zones, projected_zones, strict=True):
                assert isinstance(projected_zone, dict)
                projected_zone["spawn_table"] = [
                    {
                        "mob_slot": entry.mob_tier - 1,
                        "weight": entry.weight,
                        "min_alive": entry.min_alive,
                        "max_alive": entry.max_alive,
                    }
                    for entry in zone.spawn_table
                ]
        return projection


__all__ = [
    "MobPopulationDirection",
    "MobPopulationMap",
    "MobSpawnEntry",
    "MobSpawnZone",
    "ReplacementPolicy",
    "SpawnVisibility",
]
