// Exact browser boundary for the gameplay-contract-v1 object embedded in a
// prepared-game-runtime-v9 manifest. Keep this projection in lockstep with
// src/stage_gen/components/gameplay_contract/models.py.

import type { PreparedRuntimeManifest } from "./prepared-manifest";

export const PREPARED_GAMEPLAY_MOVEMENTS = [
  "move_left",
  "move_right",
  "jump",
  "crouch",
  "climb",
] as const;

export type PreparedGameplayMovement =
  (typeof PREPARED_GAMEPLAY_MOVEMENTS)[number];

export type PreparedGameplayMapRole =
  | "safe_village_hub"
  | "scrolling_hunting_route";

export type PreparedGameplayEffect =
  | Readonly<{
      effect_id: string;
      operation: "set_quest_state";
      quest_id: string;
      state: "active" | "completed";
    }>
  | Readonly<{
      effect_id: string;
      operation: "grant_item";
      item_id: string;
      quantity: number;
    }>;

export type PreparedGameplayContract = Readonly<{
  schema_version: 1;
  kind: "gameplay-contract-v1";
  game_id: string;
  revision: number;
  entry_map_id: string;
  entry_spawn_id: string;
  navigation: Readonly<{
    allowed_movements: readonly PreparedGameplayMovement[];
    logical_world_wrap: false;
    fall_recovery: "last_safe_ground";
  }>;
  player: Readonly<{
    player_id: string;
    starting_level: number;
    starting_health: number;
    starting_item_ids: readonly string[];
  }>;
  progression: Readonly<{
    maximum_level: number;
    experience_curve: "gentle_rpg_v1";
    stat_growth: "balanced_novice_v1";
  }>;
  inventory: Readonly<{
    currency_item_id: string;
    starting_capacity: number;
  }>;
  combat: Readonly<{
    enabled: boolean;
    basic_action: "basic_attack";
    secondary_action: "skill_cast";
    contact_damage: boolean;
    lethal_presentation: false;
    defeat_presentation: "story_beast_disperses_into_page_light";
  }>;
  combat_text: Readonly<{ enabled: boolean }>;
  map_uses: readonly Readonly<{
    map_id: string;
    role: PreparedGameplayMapRole;
    hostile_population_enabled: boolean;
    track_ids: readonly string[];
  }>[];
  spawns: readonly Readonly<{
    spawn_id: string;
    map_id: string;
    anchor: string;
    normalized_x: number;
  }>[];
  transitions: readonly Readonly<{
    transition_id: string;
    from_map_id: string;
    from_anchor: string;
    to_map_id: string;
    to_spawn_id: string;
  }>[];
  mob_population: Readonly<{
    update_interval_ms: number;
    max_spawn_batch_per_update: number;
    maps: readonly Readonly<{
      map_id: string;
      seed_salt: number;
      zones: readonly Readonly<{
        zone_id: string;
        surface: "terrain";
        left_fraction: number;
        right_fraction: number;
        initial_population: number;
        target_population: number;
        population_cap: number;
        respawn_delay_ms: number;
        spawn_table: readonly Readonly<{
          mob_id: string;
          weight: number;
        }>[];
      }>[];
    }>[];
  }>;
  boss_encounters: readonly Readonly<{
    encounter_id: string;
    map_id: string;
    anchor: string;
    mob_id: string;
    track_id: string;
    respawn_policy: "quest_reset_only";
  }>[];
  loot_rules: readonly Readonly<{
    mob_id: string;
    item_id: string;
    chance: number;
    quantity_min: number;
    quantity_max: number;
  }>[];
  npc_placements: readonly Readonly<{
    map_id: string;
    npc_id: string;
    anchor: string;
    normalized_x: number;
  }>[];
  prop_placements: readonly Readonly<{
    map_id: string;
    prop_id: string;
    anchor: string;
    normalized_x: number;
  }>[];
  interactions: readonly Readonly<{
    interaction_id: string;
    map_id: string;
    actor_id: string;
    sequence_id: string;
  }>[];
  quests: readonly Readonly<{
    quest_id: string;
    display_name: string;
    start_effect_id: string;
    completion_item_id: string;
    completion_count: number;
    completion_effect_id: string;
  }>[];
  effects: readonly PreparedGameplayEffect[];
}>;

const KEBAB_ID = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const SNAKE_ID = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$/;

const ROOT_KEYS = [
  "schema_version",
  "kind",
  "game_id",
  "revision",
  "entry_map_id",
  "entry_spawn_id",
  "navigation",
  "player",
  "progression",
  "inventory",
  "combat",
  "combat_text",
  "map_uses",
  "spawns",
  "transitions",
  "mob_population",
  "boss_encounters",
  "loot_rules",
  "npc_placements",
  "prop_placements",
  "interactions",
  "quests",
  "effects",
] as const;

function fail(path: string, message: string): never {
  throw new Error(`${path} ${message}`);
}

function record(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return fail(path, "must be an object");
  }
  return value as Record<string, unknown>;
}

function exactKeys(
  value: Record<string, unknown>,
  keys: readonly string[],
  path: string,
): void {
  const expected = new Set(keys);
  for (const key of Object.keys(value)) {
    if (!expected.has(key)) fail(`${path}.${key}`, "is not a supported key");
  }
  for (const key of keys) {
    if (!Object.prototype.hasOwnProperty.call(value, key)) {
      fail(`${path}.${key}`, "is required");
    }
  }
}

function list(
  value: unknown,
  path: string,
  minimum = 0,
  maximum = Number.MAX_SAFE_INTEGER,
): unknown[] {
  if (!Array.isArray(value) || value.length < minimum || value.length > maximum) {
    return fail(path, `must be an array with ${minimum}..${maximum} entries`);
  }
  return value;
}

function literal<const Value extends string | number | boolean>(
  value: unknown,
  expected: Value,
  path: string,
): Value {
  if (value !== expected) fail(path, `must equal ${JSON.stringify(expected)}`);
  return expected;
}

function member<const Values extends readonly string[]>(
  value: unknown,
  values: Values,
  path: string,
): Values[number] {
  if (typeof value !== "string" || !(values as readonly string[]).includes(value)) {
    return fail(path, `must be one of ${values.join(", ")}`);
  }
  return value as Values[number];
}

function boolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") return fail(path, "must be boolean");
  return value;
}

function integer(
  value: unknown,
  path: string,
  minimum: number,
  maximum = Number.MAX_SAFE_INTEGER,
): number {
  if (!Number.isSafeInteger(value) || (value as number) < minimum || (value as number) > maximum) {
    return fail(path, `must be a safe integer in ${minimum}..${maximum}`);
  }
  return value as number;
}

function numberIn(
  value: unknown,
  path: string,
  minimum: number,
  maximum: number,
  minimumExclusive = false,
  maximumExclusive = false,
): number {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    (minimumExclusive ? value <= minimum : value < minimum) ||
    (maximumExclusive ? value >= maximum : value > maximum)
  ) {
    return fail(path, `must be a finite number in the supported range`);
  }
  return value;
}

function normalizedText(value: unknown, path: string): string {
  if (typeof value !== "string") return fail(path, "must be a string");
  const normalized = value.normalize("NFC");
  if (normalized.length === 0 || normalized.trim() !== normalized) {
    return fail(path, "must be a non-empty trimmed string");
  }
  return normalized;
}

function identifier(
  value: unknown,
  pattern: RegExp,
  path: string,
): string {
  const parsed = normalizedText(value, path);
  if (parsed.length > 96 || !pattern.test(parsed)) return fail(path, "is invalid");
  return parsed;
}

function kebabId(value: unknown, path: string): string {
  return identifier(value, KEBAB_ID, path);
}

function snakeId(value: unknown, path: string): string {
  return identifier(value, SNAKE_ID, path);
}

function unique(values: readonly string[], path: string): void {
  if (new Set(values).size !== values.length) fail(path, "values must be unique");
}

function parseObjects<T>(
  value: unknown,
  path: string,
  minimum: number,
  maximum: number,
  parse: (value: unknown, path: string) => T,
): readonly T[] {
  return Object.freeze(
    list(value, path, minimum, maximum).map((entry, index) =>
      parse(entry, `${path}[${index}]`),
    ),
  );
}

function assertMap(
  mapIds: ReadonlySet<string>,
  mapId: string,
  path: string,
): void {
  if (!mapIds.has(mapId)) fail(path, `does not resolve to map_uses`);
}

/** Parse, cross-check, and deeply freeze one complete gameplay-contract-v1. */
export function parsePreparedGameplayContract(
  value: unknown,
  path = "gameplay",
): PreparedGameplayContract {
  const root = record(value, path);
  exactKeys(root, ROOT_KEYS, path);

  const rawNavigation = record(root.navigation, `${path}.navigation`);
  exactKeys(
    rawNavigation,
    ["allowed_movements", "logical_world_wrap", "fall_recovery"],
    `${path}.navigation`,
  );
  const allowedMovements = Object.freeze(
    list(rawNavigation.allowed_movements, `${path}.navigation.allowed_movements`, 1, 5).map(
      (entry, index) =>
        member(
          entry,
          PREPARED_GAMEPLAY_MOVEMENTS,
          `${path}.navigation.allowed_movements[${index}]`,
        ),
    ),
  );
  unique(allowedMovements, `${path}.navigation.allowed_movements`);
  const navigation = Object.freeze({
    allowed_movements: allowedMovements,
    logical_world_wrap: literal(
      rawNavigation.logical_world_wrap,
      false,
      `${path}.navigation.logical_world_wrap`,
    ),
    fall_recovery: literal(
      rawNavigation.fall_recovery,
      "last_safe_ground",
      `${path}.navigation.fall_recovery`,
    ),
  });

  const rawPlayer = record(root.player, `${path}.player`);
  exactKeys(
    rawPlayer,
    ["player_id", "starting_level", "starting_health", "starting_item_ids"],
    `${path}.player`,
  );
  const startingItemIds = Object.freeze(
    list(rawPlayer.starting_item_ids, `${path}.player.starting_item_ids`, 0, 64).map(
      (entry, index) => snakeId(entry, `${path}.player.starting_item_ids[${index}]`),
    ),
  );
  unique(startingItemIds, `${path}.player.starting_item_ids`);
  const player = Object.freeze({
    player_id: snakeId(rawPlayer.player_id, `${path}.player.player_id`),
    starting_level: integer(rawPlayer.starting_level, `${path}.player.starting_level`, 1, 999),
    starting_health: integer(
      rawPlayer.starting_health,
      `${path}.player.starting_health`,
      1,
      1_000_000,
    ),
    starting_item_ids: startingItemIds,
  });

  const rawProgression = record(root.progression, `${path}.progression`);
  exactKeys(
    rawProgression,
    ["maximum_level", "experience_curve", "stat_growth"],
    `${path}.progression`,
  );
  const progression = Object.freeze({
    maximum_level: integer(
      rawProgression.maximum_level,
      `${path}.progression.maximum_level`,
      1,
      999,
    ),
    experience_curve: literal(
      rawProgression.experience_curve,
      "gentle_rpg_v1",
      `${path}.progression.experience_curve`,
    ),
    stat_growth: literal(
      rawProgression.stat_growth,
      "balanced_novice_v1",
      `${path}.progression.stat_growth`,
    ),
  });

  const rawInventory = record(root.inventory, `${path}.inventory`);
  exactKeys(rawInventory, ["currency_item_id", "starting_capacity"], `${path}.inventory`);
  const inventory = Object.freeze({
    currency_item_id: snakeId(
      rawInventory.currency_item_id,
      `${path}.inventory.currency_item_id`,
    ),
    starting_capacity: integer(
      rawInventory.starting_capacity,
      `${path}.inventory.starting_capacity`,
      1,
      999,
    ),
  });

  const rawCombat = record(root.combat, `${path}.combat`);
  exactKeys(
    rawCombat,
    [
      "enabled",
      "basic_action",
      "secondary_action",
      "contact_damage",
      "lethal_presentation",
      "defeat_presentation",
    ],
    `${path}.combat`,
  );
  const combat = Object.freeze({
    enabled: boolean(rawCombat.enabled, `${path}.combat.enabled`),
    basic_action: literal(rawCombat.basic_action, "basic_attack", `${path}.combat.basic_action`),
    secondary_action: literal(
      rawCombat.secondary_action,
      "skill_cast",
      `${path}.combat.secondary_action`,
    ),
    contact_damage: boolean(rawCombat.contact_damage, `${path}.combat.contact_damage`),
    lethal_presentation: literal(
      rawCombat.lethal_presentation,
      false,
      `${path}.combat.lethal_presentation`,
    ),
    defeat_presentation: literal(
      rawCombat.defeat_presentation,
      "story_beast_disperses_into_page_light",
      `${path}.combat.defeat_presentation`,
    ),
  });

  const rawCombatText = record(root.combat_text, `${path}.combat_text`);
  exactKeys(rawCombatText, ["enabled"], `${path}.combat_text`);
  const combatText = Object.freeze({
    enabled: boolean(rawCombatText.enabled, `${path}.combat_text.enabled`),
  });

  const mapUses = parseObjects(root.map_uses, `${path}.map_uses`, 1, 64, (value, itemPath) => {
    const item = record(value, itemPath);
    exactKeys(item, ["map_id", "role", "hostile_population_enabled", "track_ids"], itemPath);
    const role = member(
      item.role,
      ["safe_village_hub", "scrolling_hunting_route"] as const,
      `${itemPath}.role`,
    );
    const hostile = boolean(item.hostile_population_enabled, `${itemPath}.hostile_population_enabled`);
    if (hostile !== (role === "scrolling_hunting_route")) {
      fail(itemPath, "role contradicts hostile_population_enabled");
    }
    const trackIds = Object.freeze(
      list(item.track_ids, `${itemPath}.track_ids`, 1, 16).map((entry, index) =>
        snakeId(entry, `${itemPath}.track_ids[${index}]`),
      ),
    );
    unique(trackIds, `${itemPath}.track_ids`);
    return Object.freeze({
      map_id: kebabId(item.map_id, `${itemPath}.map_id`),
      role,
      hostile_population_enabled: hostile,
      track_ids: trackIds,
    });
  });
  unique(mapUses.map((entry) => entry.map_id), `${path}.map_uses.map_id`);
  const mapIds = new Set(mapUses.map((entry) => entry.map_id));

  const spawns = parseObjects(root.spawns, `${path}.spawns`, 1, 256, (value, itemPath) => {
    const item = record(value, itemPath);
    exactKeys(item, ["spawn_id", "map_id", "anchor", "normalized_x"], itemPath);
    const mapId = kebabId(item.map_id, `${itemPath}.map_id`);
    assertMap(mapIds, mapId, `${itemPath}.map_id`);
    return Object.freeze({
      spawn_id: snakeId(item.spawn_id, `${itemPath}.spawn_id`),
      map_id: mapId,
      anchor: snakeId(item.anchor, `${itemPath}.anchor`),
      normalized_x: numberIn(item.normalized_x, `${itemPath}.normalized_x`, 0, 1),
    });
  });
  unique(spawns.map((entry) => entry.spawn_id), `${path}.spawns.spawn_id`);
  const spawnById = new Map(spawns.map((entry) => [entry.spawn_id, entry]));

  const transitions = parseObjects(
    root.transitions,
    `${path}.transitions`,
    1,
    256,
    (value, itemPath) => {
      const item = record(value, itemPath);
      exactKeys(
        item,
        ["transition_id", "from_map_id", "from_anchor", "to_map_id", "to_spawn_id"],
        itemPath,
      );
      const fromMapId = kebabId(item.from_map_id, `${itemPath}.from_map_id`);
      const toMapId = kebabId(item.to_map_id, `${itemPath}.to_map_id`);
      assertMap(mapIds, fromMapId, `${itemPath}.from_map_id`);
      assertMap(mapIds, toMapId, `${itemPath}.to_map_id`);
      return Object.freeze({
        transition_id: snakeId(item.transition_id, `${itemPath}.transition_id`),
        from_map_id: fromMapId,
        from_anchor: snakeId(item.from_anchor, `${itemPath}.from_anchor`),
        to_map_id: toMapId,
        to_spawn_id: snakeId(item.to_spawn_id, `${itemPath}.to_spawn_id`),
      });
    },
  );
  unique(transitions.map((entry) => entry.transition_id), `${path}.transitions.transition_id`);
  for (const [index, transition] of transitions.entries()) {
    const target = spawnById.get(transition.to_spawn_id);
    if (target === undefined) {
      fail(`${path}.transitions[${index}].to_spawn_id`, "does not resolve");
    }
    if (target.map_id !== transition.to_map_id) {
      fail(`${path}.transitions[${index}].to_spawn_id`, "belongs to another map");
    }
  }

  const rawPopulation = record(root.mob_population, `${path}.mob_population`);
  exactKeys(
    rawPopulation,
    ["update_interval_ms", "max_spawn_batch_per_update", "maps"],
    `${path}.mob_population`,
  );
  const populationMaps = parseObjects(
    rawPopulation.maps,
    `${path}.mob_population.maps`,
    1,
    64,
    (value, itemPath) => {
      const item = record(value, itemPath);
      exactKeys(item, ["map_id", "seed_salt", "zones"], itemPath);
      const mapId = kebabId(item.map_id, `${itemPath}.map_id`);
      assertMap(mapIds, mapId, `${itemPath}.map_id`);
      const zones = parseObjects(item.zones, `${itemPath}.zones`, 1, 64, (zoneValue, zonePath) => {
        const zone = record(zoneValue, zonePath);
        exactKeys(
          zone,
          [
            "zone_id",
            "surface",
            "left_fraction",
            "right_fraction",
            "initial_population",
            "target_population",
            "population_cap",
            "respawn_delay_ms",
            "spawn_table",
          ],
          zonePath,
        );
        const left = numberIn(zone.left_fraction, `${zonePath}.left_fraction`, 0, 1, false, true);
        const right = numberIn(zone.right_fraction, `${zonePath}.right_fraction`, 0, 1, true);
        if (left >= right) fail(zonePath, "left_fraction must be less than right_fraction");
        const initial = integer(zone.initial_population, `${zonePath}.initial_population`, 0, 10_000);
        const target = integer(zone.target_population, `${zonePath}.target_population`, 0, 10_000);
        const cap = integer(zone.population_cap, `${zonePath}.population_cap`, 1, 10_000);
        if (!(initial <= target && target <= cap)) {
          fail(zonePath, "population must satisfy initial <= target <= population_cap");
        }
        const spawnTable = parseObjects(
          zone.spawn_table,
          `${zonePath}.spawn_table`,
          1,
          64,
          (spawnValue, spawnPath) => {
            const spawn = record(spawnValue, spawnPath);
            exactKeys(spawn, ["mob_id", "weight"], spawnPath);
            return Object.freeze({
              mob_id: snakeId(spawn.mob_id, `${spawnPath}.mob_id`),
              weight: integer(spawn.weight, `${spawnPath}.weight`, 1, 1_000_000),
            });
          },
        );
        unique(spawnTable.map((entry) => entry.mob_id), `${zonePath}.spawn_table.mob_id`);
        return Object.freeze({
          zone_id: snakeId(zone.zone_id, `${zonePath}.zone_id`),
          surface: literal(zone.surface, "terrain", `${zonePath}.surface`),
          left_fraction: left,
          right_fraction: right,
          initial_population: initial,
          target_population: target,
          population_cap: cap,
          respawn_delay_ms: integer(
            zone.respawn_delay_ms,
            `${zonePath}.respawn_delay_ms`,
            1,
            86_400_000,
          ),
          spawn_table: spawnTable,
        });
      });
      unique(zones.map((entry) => entry.zone_id), `${itemPath}.zones.zone_id`);
      const ordered = [...zones].sort((left, right) => left.left_fraction - right.left_fraction);
      for (let index = 1; index < ordered.length; index += 1) {
        if (ordered[index - 1]!.right_fraction > ordered[index]!.left_fraction) {
          fail(`${itemPath}.zones`, "must not overlap");
        }
      }
      return Object.freeze({
        map_id: mapId,
        seed_salt: integer(item.seed_salt, `${itemPath}.seed_salt`, 0),
        zones,
      });
    },
  );
  unique(populationMaps.map((entry) => entry.map_id), `${path}.mob_population.maps.map_id`);
  const mobPopulation = Object.freeze({
    update_interval_ms: integer(
      rawPopulation.update_interval_ms,
      `${path}.mob_population.update_interval_ms`,
      1,
      60_000,
    ),
    max_spawn_batch_per_update: integer(
      rawPopulation.max_spawn_batch_per_update,
      `${path}.mob_population.max_spawn_batch_per_update`,
      1,
      1_000,
    ),
    maps: populationMaps,
  });

  const bossEncounters = parseObjects(
    root.boss_encounters,
    `${path}.boss_encounters`,
    0,
    64,
    (value, itemPath) => {
      const item = record(value, itemPath);
      exactKeys(
        item,
        ["encounter_id", "map_id", "anchor", "mob_id", "track_id", "respawn_policy"],
        itemPath,
      );
      const mapId = kebabId(item.map_id, `${itemPath}.map_id`);
      assertMap(mapIds, mapId, `${itemPath}.map_id`);
      return Object.freeze({
        encounter_id: snakeId(item.encounter_id, `${itemPath}.encounter_id`),
        map_id: mapId,
        anchor: snakeId(item.anchor, `${itemPath}.anchor`),
        mob_id: snakeId(item.mob_id, `${itemPath}.mob_id`),
        track_id: snakeId(item.track_id, `${itemPath}.track_id`),
        respawn_policy: literal(
          item.respawn_policy,
          "quest_reset_only",
          `${itemPath}.respawn_policy`,
        ),
      });
    },
  );
  unique(bossEncounters.map((entry) => entry.encounter_id), `${path}.boss_encounters.encounter_id`);

  const lootRules = parseObjects(root.loot_rules, `${path}.loot_rules`, 0, 512, (value, itemPath) => {
    const item = record(value, itemPath);
    exactKeys(item, ["mob_id", "item_id", "chance", "quantity_min", "quantity_max"], itemPath);
    const minimum = integer(item.quantity_min, `${itemPath}.quantity_min`, 1, 999);
    const maximum = integer(item.quantity_max, `${itemPath}.quantity_max`, 1, 999);
    if (minimum > maximum) fail(itemPath, "quantity_min must not exceed quantity_max");
    return Object.freeze({
      mob_id: snakeId(item.mob_id, `${itemPath}.mob_id`),
      item_id: snakeId(item.item_id, `${itemPath}.item_id`),
      chance: numberIn(item.chance, `${itemPath}.chance`, 0, 1, true),
      quantity_min: minimum,
      quantity_max: maximum,
    });
  });
  unique(
    lootRules.map((entry) => `${entry.mob_id}:${entry.item_id}`),
    `${path}.loot_rules.mob_item_pair`,
  );

  const npcPlacements = parseObjects(
    root.npc_placements,
    `${path}.npc_placements`,
    0,
    512,
    (value, itemPath) => {
      const item = record(value, itemPath);
      exactKeys(item, ["map_id", "npc_id", "anchor", "normalized_x"], itemPath);
      const mapId = kebabId(item.map_id, `${itemPath}.map_id`);
      assertMap(mapIds, mapId, `${itemPath}.map_id`);
      return Object.freeze({
        map_id: mapId,
        npc_id: snakeId(item.npc_id, `${itemPath}.npc_id`),
        anchor: snakeId(item.anchor, `${itemPath}.anchor`),
        normalized_x: numberIn(item.normalized_x, `${itemPath}.normalized_x`, 0, 1),
      });
    },
  );
  unique(npcPlacements.map((entry) => entry.npc_id), `${path}.npc_placements.npc_id`);
  const propPlacements = parseObjects(
    root.prop_placements,
    `${path}.prop_placements`,
    0,
    1024,
    (value, itemPath) => {
      const item = record(value, itemPath);
      exactKeys(item, ["map_id", "prop_id", "anchor", "normalized_x"], itemPath);
      const mapId = kebabId(item.map_id, `${itemPath}.map_id`);
      assertMap(mapIds, mapId, `${itemPath}.map_id`);
      return Object.freeze({
        map_id: mapId,
        prop_id: snakeId(item.prop_id, `${itemPath}.prop_id`),
        anchor: snakeId(item.anchor, `${itemPath}.anchor`),
        normalized_x: numberIn(item.normalized_x, `${itemPath}.normalized_x`, 0, 1),
      });
    },
  );
  unique(propPlacements.map((entry) => entry.prop_id), `${path}.prop_placements.prop_id`);

  const interactions = parseObjects(
    root.interactions,
    `${path}.interactions`,
    0,
    512,
    (value, itemPath) => {
      const item = record(value, itemPath);
      exactKeys(item, ["interaction_id", "map_id", "actor_id", "sequence_id"], itemPath);
      const mapId = kebabId(item.map_id, `${itemPath}.map_id`);
      assertMap(mapIds, mapId, `${itemPath}.map_id`);
      return Object.freeze({
        interaction_id: snakeId(item.interaction_id, `${itemPath}.interaction_id`),
        map_id: mapId,
        actor_id: snakeId(item.actor_id, `${itemPath}.actor_id`),
        sequence_id: kebabId(item.sequence_id, `${itemPath}.sequence_id`),
      });
    },
  );
  unique(interactions.map((entry) => entry.interaction_id), `${path}.interactions.interaction_id`);

  const quests = parseObjects(root.quests, `${path}.quests`, 0, 256, (value, itemPath) => {
    const item = record(value, itemPath);
    exactKeys(
      item,
      [
        "quest_id",
        "display_name",
        "start_effect_id",
        "completion_item_id",
        "completion_count",
        "completion_effect_id",
      ],
      itemPath,
    );
    return Object.freeze({
      quest_id: snakeId(item.quest_id, `${itemPath}.quest_id`),
      display_name: normalizedText(item.display_name, `${itemPath}.display_name`),
      start_effect_id: snakeId(item.start_effect_id, `${itemPath}.start_effect_id`),
      completion_item_id: snakeId(item.completion_item_id, `${itemPath}.completion_item_id`),
      completion_count: integer(item.completion_count, `${itemPath}.completion_count`, 1, 1_000_000),
      completion_effect_id: snakeId(
        item.completion_effect_id,
        `${itemPath}.completion_effect_id`,
      ),
    });
  });
  unique(quests.map((entry) => entry.quest_id), `${path}.quests.quest_id`);
  const questIds = new Set(quests.map((entry) => entry.quest_id));

  const effects = parseObjects(root.effects, `${path}.effects`, 0, 512, (value, itemPath) => {
    const item = record(value, itemPath);
    const operation = member(
      item.operation,
      ["set_quest_state", "grant_item"] as const,
      `${itemPath}.operation`,
    );
    if (operation === "set_quest_state") {
      exactKeys(item, ["effect_id", "operation", "quest_id", "state"], itemPath);
      const questId = snakeId(item.quest_id, `${itemPath}.quest_id`);
      if (!questIds.has(questId)) fail(`${itemPath}.quest_id`, "does not resolve");
      return Object.freeze({
        effect_id: snakeId(item.effect_id, `${itemPath}.effect_id`),
        operation,
        quest_id: questId,
        state: member(item.state, ["active", "completed"] as const, `${itemPath}.state`),
      });
    }
    exactKeys(item, ["effect_id", "operation", "item_id", "quantity"], itemPath);
    return Object.freeze({
      effect_id: snakeId(item.effect_id, `${itemPath}.effect_id`),
      operation,
      item_id: snakeId(item.item_id, `${itemPath}.item_id`),
      quantity: integer(item.quantity, `${itemPath}.quantity`, 1, 999),
    });
  });
  unique(effects.map((entry) => entry.effect_id), `${path}.effects.effect_id`);
  const effectIds = new Set(effects.map((entry) => entry.effect_id));
  for (const [index, quest] of quests.entries()) {
    for (const field of ["start_effect_id", "completion_effect_id"] as const) {
      if (!effectIds.has(quest[field])) {
        fail(`${path}.quests[${index}].${field}`, "does not resolve");
      }
    }
  }

  const gameId = kebabId(root.game_id, `${path}.game_id`);
  const entryMapId = kebabId(root.entry_map_id, `${path}.entry_map_id`);
  assertMap(mapIds, entryMapId, `${path}.entry_map_id`);
  const entrySpawnId = snakeId(root.entry_spawn_id, `${path}.entry_spawn_id`);
  const entrySpawn = spawnById.get(entrySpawnId);
  if (entrySpawn === undefined) fail(`${path}.entry_spawn_id`, "does not resolve");
  if (entrySpawn.map_id !== entryMapId) {
    fail(`${path}.entry_spawn_id`, "belongs to a different map");
  }

  return Object.freeze({
    schema_version: literal(root.schema_version, 1, `${path}.schema_version`),
    kind: literal(root.kind, "gameplay-contract-v1", `${path}.kind`),
    game_id: gameId,
    revision: integer(root.revision, `${path}.revision`, 1),
    entry_map_id: entryMapId,
    entry_spawn_id: entrySpawnId,
    navigation,
    player,
    progression,
    inventory,
    combat,
    combat_text: combatText,
    map_uses: mapUses,
    spawns,
    transitions,
    mob_population: mobPopulation,
    boss_encounters: bossEncounters,
    loot_rules: lootRules,
    npc_placements: npcPlacements,
    prop_placements: propPlacements,
    interactions,
    quests,
    effects,
  });
}

type PreparedReference = readonly [path: string, id: string];

function manifestIds<T>(
  entries: readonly T[],
  idOf: (entry: T) => string,
  path: string,
): ReadonlySet<string> {
  const ids = entries.map(idOf);
  unique(ids, path);
  return new Set(ids);
}

function assertManifestReferences(
  references: readonly PreparedReference[],
  allowed: ReadonlySet<string>,
  catalog: string,
): void {
  for (const [path, id] of references) {
    if (!allowed.has(id)) fail(path, `does not resolve to manifest ${catalog}`);
  }
}

function assertSameOrderedValues(
  actual: readonly string[],
  expected: readonly string[],
  path: string,
): void {
  if (
    actual.length !== expected.length ||
    actual.some((value, index) => value !== expected[index])
  ) {
    fail(path, "does not match the prepared manifest");
  }
}

/** Fail closed when gameplay references do not resolve in its prepared manifest. */
export function assertPreparedGameplayManifestClosure(
  manifest: PreparedRuntimeManifest,
  gameplay: PreparedGameplayContract,
): void {
  const mapIds = manifestIds(manifest.maps, (entry) => entry.map_id, "manifest.maps.map_id");
  const mobIds = manifestIds(manifest.mobs, (entry) => entry.mob_id, "manifest.mobs.mob_id");
  const npcIds = manifestIds(manifest.npcs, (entry) => entry.npc_id, "manifest.npcs.npc_id");
  const propIds = manifestIds(manifest.props, (entry) => entry.prop_id, "manifest.props.prop_id");
  const itemIds = manifestIds(manifest.items, (entry) => entry.item_id, "manifest.items.item_id");
  const trackIds = manifestIds(
    manifest.soundtrack.tracks,
    (entry) => entry.track_id,
    "manifest.soundtrack.tracks.track_id",
  );
  const sequenceIdValues = manifest.sequences.map((entry, index) =>
    kebabId(entry.sequence_id, `manifest.sequences[${index}].sequence_id`),
  );
  unique(sequenceIdValues, "manifest.sequences.sequence_id");
  const sequenceIds = new Set(sequenceIdValues);

  if (manifest.game_id !== gameplay.game_id) {
    fail("gameplay.game_id", "does not match manifest.game_id");
  }
  if (manifest.entry_map_id !== gameplay.entry_map_id) {
    fail("gameplay.entry_map_id", "does not match manifest.entry_map_id");
  }
  if (manifest.entry_spawn_id !== gameplay.entry_spawn_id) {
    fail("gameplay.entry_spawn_id", "does not match manifest.entry_spawn_id");
  }
  if (manifest.player.player_id !== gameplay.player.player_id) {
    fail("gameplay.player.player_id", "does not match manifest.player.player_id");
  }

  const gameplayMapIds = new Set(gameplay.map_uses.map((entry) => entry.map_id));
  if (
    mapIds.size !== gameplayMapIds.size ||
    [...mapIds].some((mapId) => !gameplayMapIds.has(mapId))
  ) {
    fail("gameplay.map_uses", "must cover manifest.maps exactly");
  }
  const manifestMapById = new Map(manifest.maps.map((entry) => [entry.map_id, entry]));
  for (const [index, mapUse] of gameplay.map_uses.entries()) {
    const manifestMap = manifestMapById.get(mapUse.map_id);
    if (manifestMap === undefined) {
      fail(`gameplay.map_uses[${index}].map_id`, "does not resolve to manifest maps");
    }
    if (manifestMap.role !== mapUse.role) {
      fail(`gameplay.map_uses[${index}].role`, "does not match the prepared manifest");
    }
    if (manifestMap.hostile_population_enabled !== mapUse.hostile_population_enabled) {
      fail(
        `gameplay.map_uses[${index}].hostile_population_enabled`,
        "does not match the prepared manifest",
      );
    }
    assertSameOrderedValues(
      mapUse.track_ids,
      manifestMap.track_ids,
      `gameplay.map_uses[${index}].track_ids`,
    );
  }

  const portalEndpoint = (mapId: string, anchor: string) =>
    manifestMapById
      .get(mapId)
      ?.portal?.endpoints.find((endpoint) => endpoint.anchor === anchor);
  for (const [index, spawn] of gameplay.spawns.entries()) {
    const endpoint = portalEndpoint(spawn.map_id, spawn.anchor);
    if (!endpoint) {
      fail(
        `gameplay.spawns[${index}].anchor`,
        "does not resolve to a map portal endpoint",
      );
    }
    if (endpoint.normalized_x !== spawn.normalized_x) {
      fail(
        `gameplay.spawns[${index}].normalized_x`,
        "does not match its map portal endpoint",
      );
    }
  }
  for (const [index, transition] of gameplay.transitions.entries()) {
    if (!portalEndpoint(transition.from_map_id, transition.from_anchor)) {
      fail(
        `gameplay.transitions[${index}].from_anchor`,
        "does not resolve to a map portal endpoint",
      );
    }
  }

  const mobReferences: PreparedReference[] = [];
  for (const [mapIndex, populationMap] of gameplay.mob_population.maps.entries()) {
    for (const [zoneIndex, zone] of populationMap.zones.entries()) {
      for (const [spawnIndex, spawn] of zone.spawn_table.entries()) {
        mobReferences.push([
          `gameplay.mob_population.maps[${mapIndex}].zones[${zoneIndex}].spawn_table[${spawnIndex}].mob_id`,
          spawn.mob_id,
        ]);
      }
    }
  }
  gameplay.boss_encounters.forEach((entry, index) =>
    mobReferences.push([`gameplay.boss_encounters[${index}].mob_id`, entry.mob_id]),
  );
  gameplay.loot_rules.forEach((entry, index) =>
    mobReferences.push([`gameplay.loot_rules[${index}].mob_id`, entry.mob_id]),
  );
  assertManifestReferences(mobReferences, mobIds, "mobs");

  assertManifestReferences(
    [
      ...gameplay.npc_placements.map(
        (entry, index): PreparedReference => [
          `gameplay.npc_placements[${index}].npc_id`,
          entry.npc_id,
        ],
      ),
      ...gameplay.interactions.map(
        (entry, index): PreparedReference => [
          `gameplay.interactions[${index}].actor_id`,
          entry.actor_id,
        ],
      ),
    ],
    npcIds,
    "npcs",
  );
  assertManifestReferences(
    gameplay.prop_placements.map(
      (entry, index): PreparedReference => [
        `gameplay.prop_placements[${index}].prop_id`,
        entry.prop_id,
      ],
    ),
    propIds,
    "props",
  );

  const itemReferences: PreparedReference[] = [
    ["gameplay.inventory.currency_item_id", gameplay.inventory.currency_item_id],
    ...gameplay.player.starting_item_ids.map(
      (itemId, index): PreparedReference => [
        `gameplay.player.starting_item_ids[${index}]`,
        itemId,
      ],
    ),
    ...gameplay.loot_rules.map(
      (entry, index): PreparedReference => [
        `gameplay.loot_rules[${index}].item_id`,
        entry.item_id,
      ],
    ),
    ...gameplay.quests.map(
      (entry, index): PreparedReference => [
        `gameplay.quests[${index}].completion_item_id`,
        entry.completion_item_id,
      ],
    ),
  ];
  gameplay.effects.forEach((effect, index) => {
    if (effect.operation === "grant_item") {
      itemReferences.push([`gameplay.effects[${index}].item_id`, effect.item_id]);
    }
  });
  assertManifestReferences(itemReferences, itemIds, "items");

  assertManifestReferences(
    [
      ...gameplay.map_uses.flatMap((mapUse, mapIndex) =>
        mapUse.track_ids.map(
          (trackId, trackIndex): PreparedReference => [
            `gameplay.map_uses[${mapIndex}].track_ids[${trackIndex}]`,
            trackId,
          ],
        ),
      ),
      ...gameplay.boss_encounters.map(
        (entry, index): PreparedReference => [
          `gameplay.boss_encounters[${index}].track_id`,
          entry.track_id,
        ],
      ),
    ],
    trackIds,
    "soundtrack tracks",
  );
  assertManifestReferences(
    gameplay.interactions.map(
      (entry, index): PreparedReference => [
        `gameplay.interactions[${index}].sequence_id`,
        entry.sequence_id,
      ],
    ),
    sequenceIds,
    "sequences",
  );
}
