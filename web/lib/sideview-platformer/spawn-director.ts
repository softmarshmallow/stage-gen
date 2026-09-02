export type SpawnVisibility =
  | "offscreen_required"
  | "offscreen_preferred"
  | "allow_onscreen";

export type ReplacementPolicy = "reroll_spawn_table" | "same_archetype";

/**
 * How a zone places a fresh spawn among its eligible columns.
 *
 * `uniform` is the established behaviour: every eligible column is equally likely, which spreads
 * a population evenly along the zone and is what the separation rule was written for.
 * `clustered` is the hunting-ground read: a fresh spawn usually joins a creature already standing
 * in the zone, landing within `cluster_radius_px` of it, and only sometimes starts a new group of
 * its own. Eligibility - player distance, separation, occupancy, camera - is unchanged; clustering
 * only chooses *among* the columns that rule already admitted.
 */
export type SpawnPlacement = "uniform" | "clustered";

/**
 * What a zone's creatures may stand on.
 *
 * `terrain` is the floor alone. `terrain_and_decks` also admits the floating decks stacked over
 * that floor, which is what a hunting ground looks like once a map has storeys: bodies on every
 * ledge the player can reach, not only on the lane beneath them. The word is a permission, and
 * the candidate set decides what it actually amounts to on a given map -- a zone naming decks on
 * a map that has none simply populates its floor.
 */
export const SPAWN_SURFACES = ["terrain", "terrain_and_decks"] as const;
export type SpawnSurface = (typeof SPAWN_SURFACES)[number];

/**
 * What one body is standing on, as opposed to what its zone allowed.
 *
 * A reservation reports this rather than repeating the zone's permission, because the consumer
 * has to bind the creature to the surface it actually landed on: a deck body walks the deck's
 * span and stands at the deck's height, and nothing about the zone says which deck that was.
 */
export type SpawnFooting = "terrain" | "deck";

/** How often a clustered spawn joins an existing group rather than founding a new one. */
export const CLUSTER_JOIN_CHANCE = 0.7;

export interface MobSpawnTableEntry {
  readonly mob_slot: number;
  readonly weight: number;
  readonly min_alive: number;
  readonly max_alive: number;
}

export interface MobSpawnZoneManifest {
  readonly zone_id: string;
  readonly surface: SpawnSurface;
  readonly left_column: number;
  readonly right_column_exclusive: number;
  readonly initial_population: number;
  readonly target_population: number;
  readonly population_cap: number;
  readonly respawn_delay_ms: number;
  readonly respawn_variance_ms: number;
  readonly spawn_interval_ms: number;
  readonly spawn_batch_size: number;
  readonly retry_delay_ms: number;
  readonly spawn_visibility: SpawnVisibility;
  readonly camera_margin_px: number;
  readonly min_player_distance_px: number;
  readonly minimum_spawn_separation_px: number;
  readonly wander_radius_px: number;
  readonly replacement_policy: ReplacementPolicy;
  /** Absent means `uniform`, so every manifest written before the field reads as it did. */
  readonly placement?: SpawnPlacement;
  /** How far from a nucleus a clustered spawn may land; ignored for uniform placement. */
  readonly cluster_radius_px?: number;
  readonly spawn_table: readonly MobSpawnTableEntry[];
}

export interface MobPopulationMapManifest {
  readonly map_id: string;
  readonly seed_salt: number;
  readonly zones: readonly MobSpawnZoneManifest[];
}

export interface MobPopulationManifest {
  readonly schema_version: 2;
  readonly kind: "mob-population-v2";
  readonly update_interval_ms: number;
  readonly max_spawn_batch_per_update: number;
  readonly maps: readonly MobPopulationMapManifest[];
}

export interface SpawnCandidateColumn {
  column: number;
  x_px: number;
  y_px: number;
  /** The deck this footing stands on; absent means the column's own ground. */
  deck_id?: string;
}

export interface ZoneCandidateColumns {
  map_id: string;
  zone_id: string;
  candidate_columns: readonly SpawnCandidateColumn[];
}

export interface WorldPoint {
  x_px: number;
  y_px: number;
}

export interface CameraBounds {
  left_px: number;
  right_px_exclusive: number;
  top_px: number;
  bottom_px_exclusive: number;
}

export interface SpawnUpdateContext {
  players: readonly WorldPoint[];
  cameras: readonly CameraBounds[];
  occupied_points?: readonly WorldPoint[];
}

export type SpawnTicketReason =
  | "initial_fill"
  | "population_replenishment"
  | "death_replacement";

export interface SpawnReservation {
  reservation_id: string;
  map_id: string;
  zone_id: string;
  mob_slot: number;
  surface: SpawnFooting;
  candidate_column: number;
  /** Set when `surface` is `deck`: which deck the body was placed on. */
  deck_id?: string;
  x_px: number;
  y_px: number;
  issued_at_ms: number;
  ticket_reason: SpawnTicketReason;
}

export interface DeathTicketReceipt {
  ticket_id: string;
  map_id: string;
  zone_id: string;
  due_at_ms: number;
  locked_mob_slot?: number;
}

export interface MobSlotPopulationSnapshot {
  mob_slot: number;
  alive: number;
  reserved: number;
  scheduled_locked: number;
}

export interface ZonePopulationSnapshot {
  zone_id: string;
  initialized: boolean;
  alive_count: number;
  reserved_count: number;
  scheduled_count: number;
  effective_population: number;
  target_population: number;
  population_cap: number;
  counts_by_mob_slot: readonly MobSlotPopulationSnapshot[];
  alive: readonly {
    instance_id: string;
    mob_slot: number;
    x_px: number;
    y_px: number;
  }[];
  reservations: readonly SpawnReservation[];
  tickets: readonly {
    ticket_id: string;
    due_at_ms: number;
    reason: SpawnTicketReason;
    locked_mob_slot?: number;
    attempt_count: number;
  }[];
}

export interface PopulationSnapshot {
  disposed: boolean;
  maps: readonly {
    map_id: string;
    zones: readonly ZonePopulationSnapshot[];
  }[];
}

export interface DisposeResult {
  instance_ids: readonly string[];
  reservation_ids: readonly string[];
  cancelled_ticket_count: number;
}

export interface MobPopulationDirectorOptions {
  /** A deterministic session/world seed. It is mixed with map and zone salts. */
  seed?: number;
}

export class ManifestValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ManifestValidationError";
  }
}

function freezeManifest(manifest: MobPopulationManifest): MobPopulationManifest {
  for (const map of manifest.maps) {
    for (const zone of map.zones) {
      for (const entry of zone.spawn_table) Object.freeze(entry);
      Object.freeze(zone.spawn_table);
      Object.freeze(zone);
    }
    Object.freeze(map.zones);
    Object.freeze(map);
  }
  Object.freeze(manifest.maps);
  return Object.freeze(manifest);
}

type UnknownRecord = Record<string, unknown>;

const TOP_LEVEL_KEYS = [
  "schema_version",
  "kind",
  "update_interval_ms",
  "max_spawn_batch_per_update",
  "maps",
] as const;

const MAP_KEYS = ["map_id", "seed_salt", "zones"] as const;

const ZONE_KEYS = [
  "zone_id",
  "surface",
  "left_column",
  "right_column_exclusive",
  "initial_population",
  "target_population",
  "population_cap",
  "respawn_delay_ms",
  "respawn_variance_ms",
  "spawn_interval_ms",
  "spawn_batch_size",
  "retry_delay_ms",
  "spawn_visibility",
  "camera_margin_px",
  "min_player_distance_px",
  "minimum_spawn_separation_px",
  "wander_radius_px",
  "replacement_policy",
  "spawn_table",
] as const;

/** Keys a zone may carry but need not: each reads as its established default when absent. */
const ZONE_OPTIONAL_KEYS = ["placement", "cluster_radius_px"] as const;

const SPAWN_TABLE_KEYS = ["mob_slot", "weight", "min_alive", "max_alive"] as const;
const KEBAB_CASE_ID = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const UINT32_MAX = 0xffff_ffff;

function expectObject(value: unknown, path: string): UnknownRecord {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new ManifestValidationError(`${path} must be a table/object`);
  }
  return value as UnknownRecord;
}

function expectExactKeys(
  value: UnknownRecord,
  allowed: readonly string[],
  path: string,
  optional: readonly string[] = [],
): void {
  const allowedSet = new Set([...allowed, ...optional]);
  for (const key of Object.keys(value)) {
    if (!allowedSet.has(key)) {
      throw new ManifestValidationError(`${path}.${key} is not a supported key`);
    }
  }
  for (const key of allowed) {
    if (!Object.prototype.hasOwnProperty.call(value, key)) {
      throw new ManifestValidationError(`${path}.${key} is required`);
    }
  }
}

function expectArray(value: unknown, path: string, allowEmpty = false): readonly unknown[] {
  if (!Array.isArray(value) || (!allowEmpty && value.length === 0)) {
    const suffix = allowEmpty ? "an array" : "a non-empty array";
    throw new ManifestValidationError(`${path} must be ${suffix}`);
  }
  return value;
}

function expectString(value: unknown, path: string): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new ManifestValidationError(`${path} must be a non-empty string`);
  }
  return value;
}

function expectKebabCaseId(value: unknown, path: string): string {
  const identifier = expectString(value, path);
  if (!KEBAB_CASE_ID.test(identifier)) {
    throw new ManifestValidationError(`${path} must be a kebab-case identifier`);
  }
  return identifier;
}

function expectLiteral<T extends string | number>(
  value: unknown,
  expected: T,
  path: string,
): T {
  if (value !== expected) {
    throw new ManifestValidationError(`${path} must be ${JSON.stringify(expected)}`);
  }
  return expected;
}

function expectEnum<T extends string>(
  value: unknown,
  allowed: readonly T[],
  path: string,
): T {
  if (typeof value !== "string" || !allowed.includes(value as T)) {
    throw new ManifestValidationError(`${path} must be one of: ${allowed.join(", ")}`);
  }
  return value as T;
}

function expectFiniteNumber(value: unknown, path: string, minimum = 0): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < minimum) {
    throw new ManifestValidationError(`${path} must be a finite number >= ${minimum}`);
  }
  return value;
}

function expectInteger(value: unknown, path: string, minimum = 0): number {
  if (!Number.isSafeInteger(value) || (value as number) < minimum) {
    throw new ManifestValidationError(`${path} must be a safe integer >= ${minimum}`);
  }
  return value as number;
}

export function parseMobPopulationManifest(input: unknown): MobPopulationManifest {
  const root = expectObject(input, "mob_population");
  expectExactKeys(root, TOP_LEVEL_KEYS, "mob_population");

  const schemaVersion = expectLiteral(root.schema_version, 2, "mob_population.schema_version");
  const kind = expectLiteral(root.kind, "mob-population-v2", "mob_population.kind");
  const updateIntervalMs = expectInteger(
    root.update_interval_ms,
    "mob_population.update_interval_ms",
    1,
  );
  const maxSpawnBatchPerUpdate = expectInteger(
    root.max_spawn_batch_per_update,
    "mob_population.max_spawn_batch_per_update",
    1,
  );

  const mapIds = new Set<string>();
  const maps = expectArray(root.maps, "mob_population.maps").map((mapValue, mapIndex) => {
    const mapPath = `mob_population.maps[${mapIndex}]`;
    const map = expectObject(mapValue, mapPath);
    expectExactKeys(map, MAP_KEYS, mapPath);
    const mapId = expectKebabCaseId(map.map_id, `${mapPath}.map_id`);
    if (mapIds.has(mapId)) {
      throw new ManifestValidationError(`${mapPath}.map_id duplicates ${JSON.stringify(mapId)}`);
    }
    mapIds.add(mapId);
    const seedSalt = expectInteger(map.seed_salt, `${mapPath}.seed_salt`);
    if (seedSalt > UINT32_MAX) {
      throw new ManifestValidationError(`${mapPath}.seed_salt must be <= ${UINT32_MAX}`);
    }
    const zoneIds = new Set<string>();

    const zones = expectArray(map.zones, `${mapPath}.zones`).map((zoneValue, zoneIndex) => {
      const zonePath = `${mapPath}.zones[${zoneIndex}]`;
      const zone = expectObject(zoneValue, zonePath);
      expectExactKeys(zone, ZONE_KEYS, zonePath, ZONE_OPTIONAL_KEYS);

      const zoneId = expectKebabCaseId(zone.zone_id, `${zonePath}.zone_id`);
      if (zoneIds.has(zoneId)) {
        throw new ManifestValidationError(
          `${zonePath}.zone_id duplicates ${JSON.stringify(zoneId)} in map ${JSON.stringify(mapId)}`,
        );
      }
      zoneIds.add(zoneId);

      const surface = expectEnum(zone.surface, SPAWN_SURFACES, `${zonePath}.surface`);
      const leftColumn = expectInteger(zone.left_column, `${zonePath}.left_column`);
      const rightColumnExclusive = expectInteger(
        zone.right_column_exclusive,
        `${zonePath}.right_column_exclusive`,
      );
      if (rightColumnExclusive <= leftColumn) {
        throw new ManifestValidationError(
          `${zonePath}.right_column_exclusive must be greater than left_column`,
        );
      }

      const initialPopulation = expectInteger(
        zone.initial_population,
        `${zonePath}.initial_population`,
      );
      const targetPopulation = expectInteger(
        zone.target_population,
        `${zonePath}.target_population`,
        1,
      );
      const populationCap = expectInteger(zone.population_cap, `${zonePath}.population_cap`, 1);
      if (initialPopulation > targetPopulation || targetPopulation > populationCap) {
        throw new ManifestValidationError(
          `${zonePath} must satisfy initial_population <= target_population <= population_cap`,
        );
      }

      const respawnDelayMs = expectInteger(zone.respawn_delay_ms, `${zonePath}.respawn_delay_ms`);
      const respawnVarianceMs = expectInteger(
        zone.respawn_variance_ms,
        `${zonePath}.respawn_variance_ms`,
      );
      if (respawnVarianceMs > respawnDelayMs) {
        throw new ManifestValidationError(
          `${zonePath}.respawn_variance_ms must not exceed respawn_delay_ms`,
        );
      }

      const spawnIntervalMs = expectInteger(
        zone.spawn_interval_ms,
        `${zonePath}.spawn_interval_ms`,
        1,
      );
      const spawnBatchSize = expectInteger(zone.spawn_batch_size, `${zonePath}.spawn_batch_size`, 1);
      if (spawnBatchSize > populationCap) {
        throw new ManifestValidationError(
          `${zonePath}.spawn_batch_size must not exceed population_cap`,
        );
      }
      if (spawnBatchSize > maxSpawnBatchPerUpdate) {
        throw new ManifestValidationError(
          `${zonePath}.spawn_batch_size must not exceed max_spawn_batch_per_update`,
        );
      }
      const retryDelayMs = expectInteger(zone.retry_delay_ms, `${zonePath}.retry_delay_ms`, 1);
      const spawnVisibility = expectEnum(
        zone.spawn_visibility,
        ["offscreen_required", "offscreen_preferred", "allow_onscreen"] as const,
        `${zonePath}.spawn_visibility`,
      );
      const cameraMarginPx = expectInteger(
        zone.camera_margin_px,
        `${zonePath}.camera_margin_px`,
      );
      const minPlayerDistancePx = expectInteger(
        zone.min_player_distance_px,
        `${zonePath}.min_player_distance_px`,
      );
      const minimumSpawnSeparationPx = expectInteger(
        zone.minimum_spawn_separation_px,
        `${zonePath}.minimum_spawn_separation_px`,
      );
      const wanderRadiusPx = expectInteger(
        zone.wander_radius_px,
        `${zonePath}.wander_radius_px`,
      );
      const placement: SpawnPlacement =
        zone.placement === undefined
          ? "uniform"
          : expectEnum(zone.placement, ["uniform", "clustered"] as const, `${zonePath}.placement`);
      const clusterRadiusPx =
        zone.cluster_radius_px === undefined
          ? 0
          : expectInteger(zone.cluster_radius_px, `${zonePath}.cluster_radius_px`);
      if (placement === "clustered" && clusterRadiusPx <= 0) {
        throw new ManifestValidationError(
          `${zonePath}.cluster_radius_px must be positive for clustered placement`,
        );
      }
      const replacementPolicy = expectEnum(
        zone.replacement_policy,
        ["reroll_spawn_table", "same_archetype"] as const,
        `${zonePath}.replacement_policy`,
      );

      const mobSlots = new Set<number>();
      let totalMinimum = 0;
      let totalMaximum = 0;
      const spawnTable = expectArray(zone.spawn_table, `${zonePath}.spawn_table`).map(
        (entryValue, entryIndex) => {
          const entryPath = `${zonePath}.spawn_table[${entryIndex}]`;
          const entry = expectObject(entryValue, entryPath);
          expectExactKeys(entry, SPAWN_TABLE_KEYS, entryPath);
          const mobSlot = expectInteger(entry.mob_slot, `${entryPath}.mob_slot`);
          if (mobSlots.has(mobSlot)) {
            throw new ManifestValidationError(
              `${entryPath}.mob_slot duplicates ${JSON.stringify(mobSlot)}`,
            );
          }
          mobSlots.add(mobSlot);
          const weight = expectInteger(entry.weight, `${entryPath}.weight`, 1);
          const minAlive = expectInteger(entry.min_alive, `${entryPath}.min_alive`);
          const maxAlive = expectInteger(entry.max_alive, `${entryPath}.max_alive`, 1);
          if (minAlive > maxAlive) {
            throw new ManifestValidationError(`${entryPath} must satisfy min_alive <= max_alive`);
          }
          if (maxAlive > populationCap) {
            throw new ManifestValidationError(
              `${entryPath}.max_alive must not exceed the zone population_cap`,
            );
          }
          totalMinimum += minAlive;
          totalMaximum += maxAlive;
          return {
            mob_slot: mobSlot,
            weight,
            min_alive: minAlive,
            max_alive: maxAlive,
          } satisfies MobSpawnTableEntry;
        },
      );

      if (totalMinimum > targetPopulation) {
        throw new ManifestValidationError(
          `${zonePath} spawn_table min_alive total exceeds target_population`,
        );
      }
      if (totalMaximum < targetPopulation) {
        throw new ManifestValidationError(
          `${zonePath} spawn_table max_alive total is below target_population`,
        );
      }

      return {
        zone_id: zoneId,
        surface,
        left_column: leftColumn,
        right_column_exclusive: rightColumnExclusive,
        initial_population: initialPopulation,
        target_population: targetPopulation,
        population_cap: populationCap,
        respawn_delay_ms: respawnDelayMs,
        respawn_variance_ms: respawnVarianceMs,
        spawn_interval_ms: spawnIntervalMs,
        spawn_batch_size: spawnBatchSize,
        retry_delay_ms: retryDelayMs,
        spawn_visibility: spawnVisibility,
        camera_margin_px: cameraMarginPx,
        min_player_distance_px: minPlayerDistancePx,
        minimum_spawn_separation_px: minimumSpawnSeparationPx,
        wander_radius_px: wanderRadiusPx,
        replacement_policy: replacementPolicy,
        placement,
        cluster_radius_px: clusterRadiusPx,
        spawn_table: spawnTable,
      } satisfies MobSpawnZoneManifest;
    });

    const zonesByPosition = [...zones].sort(
      (left, right) => left.left_column - right.left_column || left.right_column_exclusive - right.right_column_exclusive,
    );
    for (let zoneIndex = 1; zoneIndex < zonesByPosition.length; zoneIndex += 1) {
      const previous = zonesByPosition[zoneIndex - 1]!;
      const current = zonesByPosition[zoneIndex]!;
      if (current.left_column < previous.right_column_exclusive) {
        throw new ManifestValidationError(
          `${mapPath}.zones ${JSON.stringify(previous.zone_id)} and ${JSON.stringify(current.zone_id)} ` +
            "must not overlap",
        );
      }
    }

    return { map_id: mapId, seed_salt: seedSalt, zones } satisfies MobPopulationMapManifest;
  });

  return freezeManifest({
    schema_version: schemaVersion,
    kind,
    update_interval_ms: updateIntervalMs,
    max_spawn_batch_per_update: maxSpawnBatchPerUpdate,
    maps,
  });
}

interface SpawnTicket {
  ticketId: string;
  sequence: number;
  dueAtMs: number;
  reason: SpawnTicketReason;
  lockedMobSlot?: number;
  attemptCount: number;
}

interface InternalReservation {
  publicValue: SpawnReservation;
  ticket: SpawnTicket;
  candidate: SpawnCandidateColumn;
}

interface AliveMob {
  instanceId: string;
  mobSlot: number;
  position: WorldPoint;
  candidateColumn?: number;
  candidateDeckId?: string;
  issuedAtMs: number;
}

interface ZoneState {
  mapId: string;
  definition: MobSpawnZoneManifest;
  candidates: readonly SpawnCandidateColumn[];
  rng: DeterministicRandom;
  initialized: boolean;
  lastSpawnBatchAtMs?: number;
  tickets: SpawnTicket[];
  reservations: Map<string, InternalReservation>;
  alive: Map<string, AliveMob>;
}

interface MapState {
  definition: MobPopulationMapManifest;
  zones: ZoneState[];
  timeWatermarkMs?: number;
  lastUpdateAtMs?: number;
  nextZoneIndex: number;
}

class DeterministicRandom {
  private state: number;

  constructor(seed: number) {
    this.state = seed >>> 0;
    if (this.state === 0) this.state = 0x6d2b79f5;
  }

  next(): number {
    this.state = (this.state + 0x6d2b79f5) >>> 0;
    let value = this.state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4_294_967_296;
  }
}

function hashString(value: string): number {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

function mixSeed(seed: number, mapId: string, zoneId: string, salt: number): number {
  let mixed = seed >>> 0;
  mixed ^= hashString(mapId);
  mixed = Math.imul(mixed ^ (mixed >>> 16), 0x45d9f3b);
  mixed ^= hashString(zoneId);
  mixed = Math.imul(mixed ^ (mixed >>> 16), 0x45d9f3b);
  mixed ^= salt >>> 0;
  mixed ^= mixed >>> 16;
  return mixed >>> 0;
}

function zoneKey(mapId: string, zoneId: string): string {
  return `${mapId}\u0000${zoneId}`;
}

function validateCandidateSets(
  candidateSets: readonly ZoneCandidateColumns[],
  manifest: MobPopulationManifest,
): Map<string, readonly SpawnCandidateColumn[]> {
  if (!Array.isArray(candidateSets)) {
    throw new ManifestValidationError("candidate_sets must be an array");
  }

  const definitions = new Map<string, MobSpawnZoneManifest>();
  for (const map of manifest.maps) {
    for (const zone of map.zones) definitions.set(zoneKey(map.map_id, zone.zone_id), zone);
  }

  const result = new Map<string, readonly SpawnCandidateColumn[]>();
  for (let setIndex = 0; setIndex < candidateSets.length; setIndex += 1) {
    const path = `candidate_sets[${setIndex}]`;
    const rawSet = expectObject(candidateSets[setIndex], path);
    expectExactKeys(rawSet, ["map_id", "zone_id", "candidate_columns"], path);
    const mapId = expectString(rawSet.map_id, `${path}.map_id`);
    const zoneId = expectString(rawSet.zone_id, `${path}.zone_id`);
    const key = zoneKey(mapId, zoneId);
    const definition = definitions.get(key);
    if (!definition) {
      throw new ManifestValidationError(`${path} references unknown zone ${mapId}/${zoneId}`);
    }
    if (result.has(key)) {
      throw new ManifestValidationError(`${path} duplicates candidate set ${mapId}/${zoneId}`);
    }

    // A footing is a column *and* the surface it stands on, which is why the uniqueness key is
    // the pair. A column under a stack of decks offers one place to stand per storey plus the
    // ground, and they are genuinely different places: they are tiles apart vertically, a body
    // on one cannot reach a body on another, and rejecting the second as a duplicate column
    // would silently discard every deck above the first.
    const usedFootings = new Set<string>();
    const columns = expectArray(rawSet.candidate_columns, `${path}.candidate_columns`, true)
      .map((candidateValue, candidateIndex) => {
        const candidatePath = `${path}.candidate_columns[${candidateIndex}]`;
        const candidate = expectObject(candidateValue, candidatePath);
        expectExactKeys(candidate, ["column", "x_px", "y_px"], candidatePath, ["deck_id"]);
        const column = expectInteger(candidate.column, `${candidatePath}.column`);
        if (column < definition.left_column || column >= definition.right_column_exclusive) {
          throw new ManifestValidationError(
            `${candidatePath}.column must be within the half-open zone range ` +
              `[${definition.left_column}, ${definition.right_column_exclusive})`,
          );
        }
        const deckId =
          candidate.deck_id === undefined
            ? undefined
            : expectString(candidate.deck_id, `${candidatePath}.deck_id`);
        if (deckId !== undefined && definition.surface !== "terrain_and_decks") {
          throw new ManifestValidationError(
            `${candidatePath}.deck_id is a deck footing, which zone ` +
              `${JSON.stringify(definition.zone_id)} does not allow with surface ` +
              `${JSON.stringify(definition.surface)}`,
          );
        }
        const footing = `${column}\u0000${deckId ?? ""}`;
        if (usedFootings.has(footing)) {
          throw new ManifestValidationError(
            deckId === undefined
              ? `${candidatePath}.column duplicates ${column}`
              : `${candidatePath} duplicates column ${column} on deck ${JSON.stringify(deckId)}`,
          );
        }
        usedFootings.add(footing);
        return {
          column,
          x_px: expectFiniteNumber(candidate.x_px, `${candidatePath}.x_px`, -Infinity),
          y_px: expectFiniteNumber(candidate.y_px, `${candidatePath}.y_px`, -Infinity),
          ...(deckId === undefined ? {} : { deck_id: deckId }),
        } satisfies SpawnCandidateColumn;
      })
      .sort((left, right) => left.column - right.column || left.y_px - right.y_px);
    result.set(key, columns);
  }

  for (const [key] of definitions) {
    if (!result.has(key)) {
      const [mapId, zoneId] = key.split("\u0000");
      throw new ManifestValidationError(`candidate set is required for ${mapId}/${zoneId}`);
    }
  }
  return result;
}

function validateRuntimeTime(nowMs: number, path = "now_ms"): void {
  if (!Number.isSafeInteger(nowMs) || nowMs < 0) {
    throw new RangeError(`${path} must be a safe integer >= 0`);
  }
}

function checkedDeadline(nowMs: number, delayMs: number, path: string): number {
  if (!Number.isSafeInteger(delayMs) || delayMs < 0 || nowMs > Number.MAX_SAFE_INTEGER - delayMs) {
    throw new RangeError(`${path} exceeds the safe simulation-time range`);
  }
  return nowMs + delayMs;
}

function validatePoint(point: WorldPoint, path: string): void {
  if (!Number.isFinite(point.x_px) || !Number.isFinite(point.y_px)) {
    throw new RangeError(`${path} must contain finite x_px and y_px`);
  }
}

function validateContext(context: SpawnUpdateContext): void {
  if (!context || !Array.isArray(context.players) || !Array.isArray(context.cameras)) {
    throw new TypeError("context.players and context.cameras must be arrays");
  }
  context.players.forEach((point, index) => validatePoint(point, `context.players[${index}]`));
  (context.occupied_points ?? []).forEach((point, index) =>
    validatePoint(point, `context.occupied_points[${index}]`),
  );
  context.cameras.forEach((camera, index) => {
    const values = [
      camera.left_px,
      camera.right_px_exclusive,
      camera.top_px,
      camera.bottom_px_exclusive,
    ];
    if (!values.every(Number.isFinite)) {
      throw new RangeError(`context.cameras[${index}] must contain finite bounds`);
    }
    if (
      camera.right_px_exclusive <= camera.left_px ||
      camera.bottom_px_exclusive <= camera.top_px
    ) {
      throw new RangeError(`context.cameras[${index}] must have positive half-open bounds`);
    }
  });
}

function squaredDistance(left: WorldPoint, right: WorldPoint): number {
  const dx = left.x_px - right.x_px;
  const dy = left.y_px - right.y_px;
  return dx * dx + dy * dy;
}

function isOnscreen(point: WorldPoint, cameras: readonly CameraBounds[], margin: number): boolean {
  return cameras.some(
    (camera) =>
      point.x_px >= camera.left_px - margin &&
      point.x_px < camera.right_px_exclusive + margin &&
      point.y_px >= camera.top_px - margin &&
      point.y_px < camera.bottom_px_exclusive + margin,
  );
}

export class MobPopulationDirector {
  readonly manifest: MobPopulationManifest;

  private readonly maps = new Map<string, MapState>();
  private readonly reservationIndex = new Map<string, ZoneState>();
  private readonly instanceIndex = new Map<string, ZoneState>();
  private readonly seenInstanceIds = new Set<string>();
  private nextTicketSequence = 1;
  private nextReservationSequence = 1;
  private isDisposed = false;

  constructor(
    manifestBlock: unknown,
    candidateSets: readonly ZoneCandidateColumns[],
    options: MobPopulationDirectorOptions = {},
  ) {
    this.manifest = parseMobPopulationManifest(manifestBlock);
    const seed = options.seed ?? 0;
    if (!Number.isSafeInteger(seed)) {
      throw new RangeError("options.seed must be a safe integer");
    }
    const candidates = validateCandidateSets(candidateSets, this.manifest);

    for (const mapDefinition of this.manifest.maps) {
      const zones = mapDefinition.zones.map((definition) => ({
        mapId: mapDefinition.map_id,
        definition,
        candidates: candidates.get(zoneKey(mapDefinition.map_id, definition.zone_id))!,
        rng: new DeterministicRandom(
          mixSeed(seed, mapDefinition.map_id, definition.zone_id, mapDefinition.seed_salt),
        ),
        initialized: false,
        tickets: [],
        reservations: new Map<string, InternalReservation>(),
        alive: new Map<string, AliveMob>(),
      } satisfies ZoneState));
      this.maps.set(mapDefinition.map_id, {
        definition: mapDefinition,
        zones,
        nextZoneIndex: 0,
      });
    }
  }

  update(mapId: string, nowMs: number, context: SpawnUpdateContext): readonly SpawnReservation[] {
    this.assertActive();
    validateRuntimeTime(nowMs);
    validateContext(context);
    const map = this.maps.get(mapId);
    if (!map) throw new RangeError(`Unknown map_id ${JSON.stringify(mapId)}`);
    this.advanceTimeWatermark(map, nowMs);
    if (map.lastUpdateAtMs !== undefined) {
      if (nowMs - map.lastUpdateAtMs < this.manifest.update_interval_ms) return [];
    }
    for (const zone of map.zones) {
      checkedDeadline(nowMs, zone.definition.retry_delay_ms, "retry deadline");
    }
    map.lastUpdateAtMs = nowMs;

    for (const zone of map.zones) {
      if (!zone.initialized) {
        zone.initialized = true;
        this.addTickets(zone, zone.definition.initial_population, "initial_fill", nowMs);
      } else {
        const missing = zone.definition.target_population - this.committedPopulation(zone);
        if (missing > 0) {
          this.addTickets(zone, missing, "population_replenishment", nowMs);
        }
      }
    }

    const issued: SpawnReservation[] = [];
    if (map.zones.length === 0) return issued;
    const startIndex = map.nextZoneIndex % map.zones.length;
    let globalCapacity = this.manifest.max_spawn_batch_per_update;

    for (let offset = 0; offset < map.zones.length && globalCapacity > 0; offset += 1) {
      const zone = map.zones[(startIndex + offset) % map.zones.length]!;
      const zoneReservations = this.issueForZone(
        map,
        zone,
        nowMs,
        context,
        Math.min(zone.definition.spawn_batch_size, globalCapacity),
      );
      issued.push(...zoneReservations);
      globalCapacity -= zoneReservations.length;
    }
    map.nextZoneIndex = (startIndex + 1) % map.zones.length;
    return issued;
  }

  confirm(reservationId: string, instanceId: string): SpawnReservation {
    this.assertActive();
    if (typeof instanceId !== "string" || instanceId.trim().length === 0) {
      throw new TypeError("instance_id must be a non-empty string");
    }
    if (this.seenInstanceIds.has(instanceId)) {
      throw new Error(`instance_id ${JSON.stringify(instanceId)} has already been used`);
    }
    const zone = this.reservationIndex.get(reservationId);
    if (!zone) throw new RangeError(`Unknown reservation_id ${JSON.stringify(reservationId)}`);
    const reservation = zone.reservations.get(reservationId)!;
    zone.reservations.delete(reservationId);
    this.reservationIndex.delete(reservationId);
    zone.alive.set(instanceId, {
      instanceId,
      mobSlot: reservation.publicValue.mob_slot,
      position: { x_px: reservation.candidate.x_px, y_px: reservation.candidate.y_px },
      candidateColumn: reservation.candidate.column,
      candidateDeckId: reservation.candidate.deck_id,
      issuedAtMs: reservation.publicValue.issued_at_ms,
    });
    this.instanceIndex.set(instanceId, zone);
    this.seenInstanceIds.add(instanceId);
    return reservation.publicValue;
  }

  reject(reservationId: string, nowMs: number): boolean {
    this.assertActive();
    validateRuntimeTime(nowMs);
    const zone = this.reservationIndex.get(reservationId);
    if (!zone) return false;
    const reservation = zone.reservations.get(reservationId)!;
    if (nowMs < reservation.publicValue.issued_at_ms) {
      throw new RangeError("rejection now_ms cannot precede reservation issuance");
    }
    const map = this.maps.get(zone.mapId)!;
    this.advanceTimeWatermark(map, nowMs);
    const retryAtMs = checkedDeadline(nowMs, zone.definition.retry_delay_ms, "retry deadline");
    zone.reservations.delete(reservationId);
    this.reservationIndex.delete(reservationId);
    reservation.ticket.dueAtMs = retryAtMs;
    reservation.ticket.attemptCount += 1;
    zone.tickets.push(reservation.ticket);
    return true;
  }

  recordDeath(instanceId: string, nowMs: number): DeathTicketReceipt | undefined {
    this.assertActive();
    validateRuntimeTime(nowMs);
    const zone = this.instanceIndex.get(instanceId);
    if (!zone) return undefined;
    const actor = zone.alive.get(instanceId)!;
    if (nowMs < actor.issuedAtMs) {
      throw new RangeError("death now_ms cannot precede spawn reservation issuance");
    }
    const map = this.maps.get(zone.mapId)!;
    this.advanceTimeWatermark(map, nowMs);

    const variance = zone.definition.respawn_variance_ms;
    const offset = variance === 0 ? 0 : Math.round((zone.rng.next() * 2 - 1) * variance);
    const delayMs = zone.definition.respawn_delay_ms + offset;
    const dueAtMs = checkedDeadline(nowMs, delayMs, "respawn deadline");
    const lockedMobSlot =
      zone.definition.replacement_policy === "same_archetype" ? actor.mobSlot : undefined;
    const ticket = this.createTicket(zone, "death_replacement", dueAtMs, lockedMobSlot);
    zone.alive.delete(instanceId);
    this.instanceIndex.delete(instanceId);
    zone.tickets.push(ticket);
    return {
      ticket_id: ticket.ticketId,
      map_id: zone.mapId,
      zone_id: zone.definition.zone_id,
      due_at_ms: ticket.dueAtMs,
      ...(lockedMobSlot === undefined ? {} : { locked_mob_slot: lockedMobSlot }),
    };
  }

  updateInstancePosition(instanceId: string, position: WorldPoint): boolean {
    this.assertActive();
    validatePoint(position, "position");
    const zone = this.instanceIndex.get(instanceId);
    if (!zone) return false;
    const actor = zone.alive.get(instanceId)!;
    actor.position = { x_px: position.x_px, y_px: position.y_px };
    actor.candidateColumn = undefined;
    actor.candidateDeckId = undefined;
    return true;
  }

  snapshot(): PopulationSnapshot {
    return {
      disposed: this.isDisposed,
      maps: [...this.maps.values()].map((map) => ({
        map_id: map.definition.map_id,
        zones: map.zones.map((zone) => this.snapshotZone(zone)),
      })),
    };
  }

  dispose(): DisposeResult {
    if (this.isDisposed) {
      return { instance_ids: [], reservation_ids: [], cancelled_ticket_count: 0 };
    }
    const instanceIds = [...this.instanceIndex.keys()].sort();
    const reservationIds = [...this.reservationIndex.keys()].sort();
    let cancelledTicketCount = 0;
    for (const map of this.maps.values()) {
      for (const zone of map.zones) {
        cancelledTicketCount += zone.tickets.length;
        zone.tickets.length = 0;
        zone.reservations.clear();
        zone.alive.clear();
      }
    }
    this.reservationIndex.clear();
    this.instanceIndex.clear();
    this.isDisposed = true;
    return {
      instance_ids: instanceIds,
      reservation_ids: reservationIds,
      cancelled_ticket_count: cancelledTicketCount,
    };
  }

  private assertActive(): void {
    if (this.isDisposed) throw new Error("MobPopulationDirector is disposed");
  }

  private advanceTimeWatermark(map: MapState, nowMs: number): void {
    if (map.timeWatermarkMs !== undefined && nowMs < map.timeWatermarkMs) {
      throw new RangeError("now_ms must be monotonic for each map");
    }
    map.timeWatermarkMs = nowMs;
  }

  private createTicket(
    zone: ZoneState,
    reason: SpawnTicketReason,
    dueAtMs: number,
    lockedMobSlot?: number,
  ): SpawnTicket {
    const sequence = this.nextTicketSequence++;
    return {
      ticketId: `${zone.mapId}/${zone.definition.zone_id}/ticket/${sequence}`,
      sequence,
      dueAtMs,
      reason,
      ...(lockedMobSlot === undefined ? {} : { lockedMobSlot }),
      attemptCount: 0,
    };
  }

  private addTickets(
    zone: ZoneState,
    count: number,
    reason: SpawnTicketReason,
    dueAtMs: number,
  ): void {
    for (let index = 0; index < count; index += 1) {
      zone.tickets.push(this.createTicket(zone, reason, dueAtMs));
    }
  }

  private committedPopulation(zone: ZoneState): number {
    return zone.alive.size + zone.reservations.size + zone.tickets.length;
  }

  private issueForZone(
    map: MapState,
    zone: ZoneState,
    nowMs: number,
    context: SpawnUpdateContext,
    capacity: number,
  ): SpawnReservation[] {
    if (
      zone.lastSpawnBatchAtMs !== undefined &&
      nowMs - zone.lastSpawnBatchAtMs < zone.definition.spawn_interval_ms
    ) {
      return [];
    }

    const due = zone.tickets
      .filter((ticket) => ticket.dueAtMs <= nowMs)
      .sort((left, right) => left.dueAtMs - right.dueAtMs || left.sequence - right.sequence);
    const issued: SpawnReservation[] = [];
    for (const ticket of due) {
      if (issued.length >= capacity) break;
      if (zone.alive.size + zone.reservations.size >= zone.definition.population_cap) break;
      const reservation = this.tryReserve(map, zone, ticket, nowMs, context);
      if (!reservation) {
        ticket.dueAtMs = checkedDeadline(
          nowMs,
          zone.definition.retry_delay_ms,
          "retry deadline",
        );
        ticket.attemptCount += 1;
        continue;
      }
      const ticketIndex = zone.tickets.indexOf(ticket);
      if (ticketIndex >= 0) zone.tickets.splice(ticketIndex, 1);
      zone.reservations.set(reservation.publicValue.reservation_id, reservation);
      this.reservationIndex.set(reservation.publicValue.reservation_id, zone);
      issued.push(reservation.publicValue);
    }
    if (issued.length > 0) zone.lastSpawnBatchAtMs = nowMs;
    return issued;
  }

  private tryReserve(
    map: MapState,
    zone: ZoneState,
    ticket: SpawnTicket,
    nowMs: number,
    context: SpawnUpdateContext,
  ): InternalReservation | undefined {
    const entry = this.selectMobEntry(zone, ticket);
    if (!entry) return undefined;
    const candidates = this.eligibleCandidates(map, zone, context);
    if (candidates.length === 0) return undefined;
    const candidate = this.chooseCandidate(zone, candidates);
    const sequence = this.nextReservationSequence++;
    const publicValue: SpawnReservation = Object.freeze({
      reservation_id: `${zone.mapId}/${zone.definition.zone_id}/reservation/${sequence}`,
      map_id: zone.mapId,
      zone_id: zone.definition.zone_id,
      mob_slot: entry.mob_slot,
      surface: candidate.deck_id === undefined ? "terrain" : "deck",
      candidate_column: candidate.column,
      ...(candidate.deck_id === undefined ? {} : { deck_id: candidate.deck_id }),
      x_px: candidate.x_px,
      y_px: candidate.y_px,
      issued_at_ms: nowMs,
      ticket_reason: ticket.reason,
    });
    return { publicValue, ticket, candidate };
  }

  /**
   * Pick one column from those eligibility admitted.
   *
   * Uniform placement draws once. Clustered placement draws a join roll first; on a join it picks
   * a nucleus among the zone's live creatures and pending reservations, then draws uniformly among
   * the eligible columns within the cluster radius of it. An empty zone, a losing roll, or a
   * nucleus with no room beside it all fall through to the uniform draw, so a clustered zone still
   * fills when nothing can be joined. Every draw is on the zone's own stream, so a replay clusters
   * the same way twice.
   */
  private chooseCandidate(
    zone: ZoneState,
    candidates: readonly SpawnCandidateColumn[],
  ): SpawnCandidateColumn {
    const definition = zone.definition;
    if (definition.placement === "clustered") {
      const nuclei: WorldPoint[] = [
        ...[...zone.alive.values()].map((actor) => actor.position),
        ...[...zone.reservations.values()].map((reservation) => ({
          x_px: reservation.candidate.x_px,
          y_px: reservation.candidate.y_px,
        })),
      ];
      if (nuclei.length > 0 && zone.rng.next() < CLUSTER_JOIN_CHANCE) {
        const nucleus = nuclei[Math.floor(zone.rng.next() * nuclei.length)]!;
        const radiusSquared = (definition.cluster_radius_px ?? 0) ** 2;
        const near = candidates.filter(
          (candidate) =>
            squaredDistance({ x_px: candidate.x_px, y_px: candidate.y_px }, nucleus) <=
            radiusSquared,
        );
        if (near.length > 0) return near[Math.floor(zone.rng.next() * near.length)]!;
      }
    }
    return candidates[Math.floor(zone.rng.next() * candidates.length)]!;
  }

  private selectMobEntry(
    zone: ZoneState,
    ticket: SpawnTicket,
  ): MobSpawnTableEntry | undefined {
    const counts = new Map<number, number>();
    for (const actor of zone.alive.values()) {
      counts.set(actor.mobSlot, (counts.get(actor.mobSlot) ?? 0) + 1);
    }
    for (const reservation of zone.reservations.values()) {
      const mobSlot = reservation.publicValue.mob_slot;
      counts.set(mobSlot, (counts.get(mobSlot) ?? 0) + 1);
    }

    // A same-archetype death ticket owns one future slot until it is fulfilled. Without this
    // reservation an unlocked warm-up/replenishment ticket can consume the archetype's final
    // max_alive slot while the death ticket is delayed. The locked ticket would then retry
    // forever while still counting toward effective_population. Exclude only the ticket being
    // selected so each locked ticket can claim its own reserved capacity when it becomes due.
    for (const scheduled of zone.tickets) {
      if (scheduled === ticket || scheduled.lockedMobSlot === undefined) continue;
      counts.set(
        scheduled.lockedMobSlot,
        (counts.get(scheduled.lockedMobSlot) ?? 0) + 1,
      );
    }

    const lockedMobSlot = ticket.lockedMobSlot;
    if (lockedMobSlot !== undefined) {
      const locked = zone.definition.spawn_table.find((entry) => entry.mob_slot === lockedMobSlot);
      if (!locked || (counts.get(lockedMobSlot) ?? 0) >= locked.max_alive) return undefined;
      return locked;
    }

    const belowMinimum = zone.definition.spawn_table.filter(
      (entry) => (counts.get(entry.mob_slot) ?? 0) < entry.min_alive,
    );
    const pool =
      belowMinimum.length > 0
        ? belowMinimum
        : zone.definition.spawn_table.filter(
            (entry) => (counts.get(entry.mob_slot) ?? 0) < entry.max_alive,
          );
    if (pool.length === 0) return undefined;
    const totalWeight = pool.reduce((sum, entry) => sum + entry.weight, 0);
    let selection = zone.rng.next() * totalWeight;
    for (const entry of pool) {
      selection -= entry.weight;
      if (selection < 0) return entry;
    }
    return pool[pool.length - 1];
  }

  private eligibleCandidates(
    map: MapState,
    zone: ZoneState,
    context: SpawnUpdateContext,
  ): readonly SpawnCandidateColumn[] {
    const definition = zone.definition;
    const playerDistanceSquared = definition.min_player_distance_px ** 2;
    const separationSquared = definition.minimum_spawn_separation_px ** 2;
    const occupied: Array<
      WorldPoint & { zoneId?: string; candidateColumn?: number; candidateDeckId?: string }
    > = [
      ...(context.occupied_points ?? []),
    ];
    for (const otherZone of map.zones) {
      for (const actor of otherZone.alive.values()) {
        occupied.push({
          ...actor.position,
          zoneId: otherZone.definition.zone_id,
          candidateColumn: actor.candidateColumn,
          candidateDeckId: actor.candidateDeckId,
        });
      }
      for (const reservation of otherZone.reservations.values()) {
        occupied.push({
          x_px: reservation.candidate.x_px,
          y_px: reservation.candidate.y_px,
          zoneId: otherZone.definition.zone_id,
          candidateColumn: reservation.candidate.column,
          candidateDeckId: reservation.candidate.deck_id,
        });
      }
    }

    const spatiallyEligible = zone.candidates.filter((candidate) => {
      const point = { x_px: candidate.x_px, y_px: candidate.y_px };
      if (
        definition.min_player_distance_px > 0 &&
        context.players.some((player) => squaredDistance(point, player) < playerDistanceSquared)
      ) {
        return false;
      }
      return !occupied.some((other) => {
        if (
          other.zoneId === definition.zone_id &&
          other.candidateColumn !== undefined &&
          other.candidateColumn === candidate.column &&
          other.candidateDeckId === candidate.deck_id
        ) {
          return true;
        }
        const distance = squaredDistance(point, other);
        return definition.minimum_spawn_separation_px === 0
          ? distance === 0
          : distance < separationSquared;
      });
    });

    if (definition.spawn_visibility === "allow_onscreen") return spatiallyEligible;
    const offscreen = spatiallyEligible.filter(
      (candidate) =>
        !isOnscreen(
          { x_px: candidate.x_px, y_px: candidate.y_px },
          context.cameras,
          definition.camera_margin_px,
        ),
    );
    if (definition.spawn_visibility === "offscreen_required") return offscreen;
    return offscreen.length > 0 ? offscreen : spatiallyEligible;
  }

  private snapshotZone(zone: ZoneState): ZonePopulationSnapshot {
    const slots = zone.definition.spawn_table.map((entry) => {
      let alive = 0;
      let reserved = 0;
      let scheduledLocked = 0;
      for (const actor of zone.alive.values()) if (actor.mobSlot === entry.mob_slot) alive += 1;
      for (const reservation of zone.reservations.values()) {
        if (reservation.publicValue.mob_slot === entry.mob_slot) reserved += 1;
      }
      for (const ticket of zone.tickets) {
        if (ticket.lockedMobSlot === entry.mob_slot) scheduledLocked += 1;
      }
      return {
        mob_slot: entry.mob_slot,
        alive,
        reserved,
        scheduled_locked: scheduledLocked,
      };
    });
    return {
      zone_id: zone.definition.zone_id,
      initialized: zone.initialized,
      alive_count: zone.alive.size,
      reserved_count: zone.reservations.size,
      scheduled_count: zone.tickets.length,
      effective_population: this.committedPopulation(zone),
      target_population: zone.definition.target_population,
      population_cap: zone.definition.population_cap,
      counts_by_mob_slot: slots,
      alive: [...zone.alive.values()]
        .map((actor) => ({
          instance_id: actor.instanceId,
          mob_slot: actor.mobSlot,
          x_px: actor.position.x_px,
          y_px: actor.position.y_px,
        }))
        .sort((left, right) => left.instance_id.localeCompare(right.instance_id)),
      reservations: [...zone.reservations.values()]
        .map((reservation) => reservation.publicValue)
        .sort((left, right) => left.reservation_id.localeCompare(right.reservation_id)),
      tickets: [...zone.tickets]
        .sort((left, right) => left.dueAtMs - right.dueAtMs || left.sequence - right.sequence)
        .map((ticket) => ({
          ticket_id: ticket.ticketId,
          due_at_ms: ticket.dueAtMs,
          reason: ticket.reason,
          ...(ticket.lockedMobSlot === undefined
            ? {}
            : { locked_mob_slot: ticket.lockedMobSlot }),
          attempt_count: ticket.attemptCount,
        })),
    };
  }
}
