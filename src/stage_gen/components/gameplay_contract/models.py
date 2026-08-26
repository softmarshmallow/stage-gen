"""Exact-current root gameplay contract for a prepared game package."""

from __future__ import annotations

from itertools import pairwise
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from stage_gen.components._game_input import (
    GAME_ID_PATTERN,
    KEBAB_ID_PATTERN,
    SNAKE_ID_PATTERN,
    canonical_contract_json,
    normalized_text,
    parse_toml_contract,
    unique_values,
)
from stage_gen.contracts.artifacts import PersistedContractModel

GAMEPLAY_CONTRACT_SCHEMA_VERSION = 1


class NavigationPolicy(PersistedContractModel):
    allowed_movements: list[Literal["move_left", "move_right", "jump", "climb"]] = Field(
        min_length=1
    )
    logical_world_wrap: Literal[False]
    fall_recovery: Literal["last_safe_ground"]

    @field_validator("allowed_movements")
    @classmethod
    def validate_movements(cls, value: list[str]) -> list[str]:
        unique_values(value, "allowed movement")
        return value


class PlayerPolicy(PersistedContractModel):
    player_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    starting_level: int = Field(ge=1, le=999)
    starting_health: int = Field(ge=1, le=1_000_000)
    starting_item_ids: list[str] = Field(default_factory=list, max_length=64)

    @field_validator("starting_item_ids")
    @classmethod
    def validate_item_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "starting item_id")
        return value


class ProgressionPolicy(PersistedContractModel):
    maximum_level: int = Field(ge=1, le=999)
    experience_curve: Literal["gentle_rpg_v1"]
    stat_growth: Literal["balanced_novice_v1"]


class InventoryPolicy(PersistedContractModel):
    currency_item_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    starting_capacity: int = Field(ge=1, le=999)


class CombatPolicy(PersistedContractModel):
    enabled: bool
    basic_action: Literal["basic_attack"]
    secondary_action: Literal["skill_cast"]
    contact_damage: bool
    lethal_presentation: Literal[False]
    defeat_presentation: Literal["story_beast_disperses_into_page_light"]


class CombatTextPolicy(PersistedContractModel):
    enabled: bool


class MapUse(PersistedContractModel):
    map_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    role: Literal["safe_village_hub", "scrolling_hunting_route"]
    hostile_population_enabled: bool
    track_ids: list[str] = Field(min_length=1, max_length=16)

    @field_validator("track_ids")
    @classmethod
    def validate_track_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "map track_id")
        return value

    @model_validator(mode="after")
    def validate_role(self) -> MapUse:
        expected_hostility = self.role == "scrolling_hunting_route"
        if self.hostile_population_enabled is not expected_hostility:
            raise ValueError("map role contradicts hostile_population_enabled")
        return self


class SpawnPoint(PersistedContractModel):
    spawn_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    map_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    anchor: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    normalized_x: float = Field(ge=0.0, le=1.0)


class MapTransition(PersistedContractModel):
    transition_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    from_map_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    from_anchor: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    to_map_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    to_spawn_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)


class SpawnTableEntry(PersistedContractModel):
    mob_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    weight: int = Field(ge=1, le=1_000_000)


class SpawnZone(PersistedContractModel):
    zone_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    surface: Literal["terrain"]
    left_fraction: float = Field(ge=0.0, lt=1.0)
    right_fraction: float = Field(gt=0.0, le=1.0)
    initial_population: int = Field(ge=0, le=10_000)
    target_population: int = Field(ge=0, le=10_000)
    population_cap: int = Field(ge=1, le=10_000)
    respawn_delay_ms: int = Field(ge=1, le=86_400_000)
    spawn_table: list[SpawnTableEntry] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_zone(self) -> SpawnZone:
        if self.left_fraction >= self.right_fraction:
            raise ValueError("spawn zone left_fraction must be less than right_fraction")
        if not self.initial_population <= self.target_population <= self.population_cap:
            raise ValueError("spawn population must satisfy initial <= target <= population_cap")
        unique_values((entry.mob_id for entry in self.spawn_table), "spawn-table mob_id")
        return self


class MobPopulationMap(PersistedContractModel):
    map_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    seed_salt: int = Field(ge=0, le=9_007_199_254_740_991)
    zones: list[SpawnZone] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_zones(self) -> MobPopulationMap:
        unique_values((zone.zone_id for zone in self.zones), "spawn zone_id")
        ordered = sorted(self.zones, key=lambda zone: zone.left_fraction)
        for previous, current in pairwise(ordered):
            if previous.right_fraction > current.left_fraction:
                raise ValueError("spawn zones must not overlap")
        return self


class MobPopulationPolicy(PersistedContractModel):
    update_interval_ms: int = Field(ge=1, le=60_000)
    max_spawn_batch_per_update: int = Field(ge=1, le=1_000)
    maps: list[MobPopulationMap] = Field(min_length=1, max_length=64)

    @field_validator("maps")
    @classmethod
    def validate_maps(cls, value: list[MobPopulationMap]) -> list[MobPopulationMap]:
        unique_values((entry.map_id for entry in value), "mob-population map_id")
        return value


class BossEncounter(PersistedContractModel):
    encounter_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    map_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    anchor: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    mob_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    track_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    respawn_policy: Literal["quest_reset_only"]


class LootRule(PersistedContractModel):
    mob_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    item_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    chance: float = Field(gt=0.0, le=1.0)
    quantity_min: int = Field(ge=1, le=999)
    quantity_max: int = Field(ge=1, le=999)

    @model_validator(mode="after")
    def validate_quantity(self) -> LootRule:
        if self.quantity_min > self.quantity_max:
            raise ValueError("loot quantity_min must not exceed quantity_max")
        return self


class NpcPlacement(PersistedContractModel):
    map_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    npc_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    anchor: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    normalized_x: float = Field(ge=0.0, le=1.0)


class PropPlacement(PersistedContractModel):
    map_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    prop_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    anchor: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    normalized_x: float = Field(ge=0.0, le=1.0)


class Interaction(PersistedContractModel):
    interaction_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    map_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    actor_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    sequence_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)


class Quest(PersistedContractModel):
    quest_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    display_name: str
    start_effect_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    completion_item_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    completion_count: int = Field(ge=1, le=1_000_000)
    completion_effect_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalized_text(value, "quest display_name")


class SetQuestStateEffect(PersistedContractModel):
    effect_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    operation: Literal["set_quest_state"]
    quest_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    state: Literal["active", "completed"]


class GrantItemEffect(PersistedContractModel):
    effect_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    operation: Literal["grant_item"]
    item_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    quantity: int = Field(ge=1, le=999)


GameplayEffect = Annotated[
    SetQuestStateEffect | GrantItemEffect,
    Field(discriminator="operation"),
]


class GameplayContract(PersistedContractModel):
    schema_version: Literal[1]
    kind: Literal["gameplay-contract-v1"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    entry_map_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    entry_spawn_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    navigation: NavigationPolicy
    player: PlayerPolicy
    progression: ProgressionPolicy
    inventory: InventoryPolicy
    combat: CombatPolicy
    combat_text: CombatTextPolicy
    map_uses: list[MapUse] = Field(min_length=1, max_length=64)
    spawns: list[SpawnPoint] = Field(min_length=1, max_length=256)
    transitions: list[MapTransition] = Field(min_length=1, max_length=256)
    mob_population: MobPopulationPolicy
    boss_encounters: list[BossEncounter] = Field(default_factory=list, max_length=64)
    loot_rules: list[LootRule] = Field(default_factory=list, max_length=512)
    npc_placements: list[NpcPlacement] = Field(default_factory=list, max_length=512)
    prop_placements: list[PropPlacement] = Field(default_factory=list, max_length=1024)
    interactions: list[Interaction] = Field(default_factory=list, max_length=512)
    quests: list[Quest] = Field(default_factory=list, max_length=256)
    effects: list[GameplayEffect] = Field(default_factory=list, max_length=512)

    @model_validator(mode="after")
    def validate_internal_graph(self) -> GameplayContract:
        unique_values((entry.map_id for entry in self.map_uses), "map-use map_id")
        unique_values((entry.spawn_id for entry in self.spawns), "spawn_id")
        unique_values((entry.transition_id for entry in self.transitions), "transition_id")
        unique_values((entry.encounter_id for entry in self.boss_encounters), "encounter_id")
        unique_values(
            (f"{entry.mob_id}:{entry.item_id}" for entry in self.loot_rules),
            "loot mob/item pair",
        )
        unique_values((entry.npc_id for entry in self.npc_placements), "placed npc_id")
        unique_values((entry.prop_id for entry in self.prop_placements), "placed prop_id")
        unique_values((entry.interaction_id for entry in self.interactions), "interaction_id")
        unique_values((entry.quest_id for entry in self.quests), "quest_id")
        unique_values((entry.effect_id for entry in self.effects), "effect_id")

        spawn_by_id = {entry.spawn_id: entry for entry in self.spawns}
        entry_spawn = spawn_by_id.get(self.entry_spawn_id)
        if entry_spawn is None:
            raise ValueError("entry_spawn_id does not resolve")
        if entry_spawn.map_id != self.entry_map_id:
            raise ValueError("entry spawn belongs to a different map")
        for transition in self.transitions:
            target = spawn_by_id.get(transition.to_spawn_id)
            if target is None:
                raise ValueError(f"transition {transition.transition_id} has unknown to_spawn_id")
            if target.map_id != transition.to_map_id:
                raise ValueError(
                    f"transition {transition.transition_id} target spawn belongs to another map"
                )

        effect_ids = {entry.effect_id for entry in self.effects}
        for quest in self.quests:
            missing = {quest.start_effect_id, quest.completion_effect_id} - effect_ids
            if missing:
                raise ValueError(
                    f"quest {quest.quest_id} references unknown effects: {sorted(missing)}"
                )
        return self


def load_gameplay_contract_bytes(data: bytes) -> GameplayContract:
    return parse_toml_contract(data, model=GameplayContract, label="gameplay contract")


def canonical_gameplay_contract_json(contract: GameplayContract) -> bytes:
    return canonical_contract_json(contract)


__all__ = [
    "GAMEPLAY_CONTRACT_SCHEMA_VERSION",
    "BossEncounter",
    "CombatPolicy",
    "CombatTextPolicy",
    "GameplayContract",
    "GameplayEffect",
    "GrantItemEffect",
    "Interaction",
    "InventoryPolicy",
    "LootRule",
    "MapTransition",
    "MapUse",
    "MobPopulationMap",
    "MobPopulationPolicy",
    "NavigationPolicy",
    "NpcPlacement",
    "PlayerPolicy",
    "ProgressionPolicy",
    "PropPlacement",
    "Quest",
    "SetQuestStateEffect",
    "SpawnPoint",
    "SpawnTableEntry",
    "SpawnZone",
    "canonical_gameplay_contract_json",
    "load_gameplay_contract_bytes",
]
