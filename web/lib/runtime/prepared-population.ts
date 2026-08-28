import type { PreparedGameplayContract } from "./prepared-gameplay";
import {
  parseMobPopulationManifest,
  type MobPopulationManifest,
  type SpawnVisibility,
  type ZoneCandidateColumns,
} from "./spawn-director";
import { terrainSurfaceY } from "./terrain";

type PreparedMobPopulation = PreparedGameplayContract["mob_population"];

export type PreparedPopulationGeometry = Readonly<{
  /** Number of whole terrain columns in the runtime world. */
  world_columns: number;
  /** Width and height of one terrain column, in world pixels. */
  tile_pixels: number;
  /** World-space Y coordinate below height-zero terrain. */
  baseline_y: number;
  /** Authored terrain height, in tiles, for one column. */
  height_at_column: (column: number) => number;
  /** Optional runtime exclusion gate for climbables, portals, or other reservations. */
  is_spawnable_column?: (column: number) => boolean;
}>;

export type PreparedPopulationProjectionPolicy = Readonly<{
  respawn_variance_ms: number;
  spawn_interval_ms: number;
  retry_delay_ms: number;
  spawn_visibility: SpawnVisibility;
  camera_margin_px: number;
  min_player_distance_px: number;
  minimum_spawn_separation_px: number;
  wander_radius_px: number;
}>;

export type PreparedPopulationProjection = Readonly<{
  manifest: MobPopulationManifest;
  candidates: readonly ZoneCandidateColumns[];
  /** Dense, deterministic lookup used directly by SpawnReservation.mob_slot. */
  mob_id_by_slot: readonly string[];
  /** Source gameplay zone ID to the spawn-director's required kebab-case ID. */
  zone_id_by_source_id: Readonly<Record<string, string>>;
}>;

export class PreparedPopulationProjectionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PreparedPopulationProjectionError";
  }
}

const UINT32_MAX = 0xffff_ffff;
const KEBAB_CASE_ID = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;

function positiveSafeInteger(value: number, path: string): number {
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new PreparedPopulationProjectionError(`${path} must be a positive safe integer`);
  }
  return value;
}

function nonnegativeSafeInteger(value: number, path: string): number {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new PreparedPopulationProjectionError(`${path} must be a nonnegative safe integer`);
  }
  return value;
}

function normalizeZoneId(sourceId: string): string {
  const normalized = sourceId.replaceAll("_", "-");
  if (!KEBAB_CASE_ID.test(normalized)) {
    throw new PreparedPopulationProjectionError(
      `mob population zone ${JSON.stringify(sourceId)} cannot be normalized to kebab-case`,
    );
  }
  return normalized;
}

function defaultPolicy(
  population: PreparedMobPopulation,
  tilePixels: number,
): PreparedPopulationProjectionPolicy {
  return Object.freeze({
    respawn_variance_ms: 0,
    spawn_interval_ms: population.update_interval_ms,
    retry_delay_ms: population.update_interval_ms,
    spawn_visibility: "offscreen_preferred",
    camera_margin_px: tilePixels,
    min_player_distance_px: Math.round(tilePixels * 2.5),
    minimum_spawn_separation_px: Math.round(tilePixels * 1.25),
    wander_radius_px: Math.round(tilePixels * 1.5),
  });
}

function resolvePolicy(
  population: PreparedMobPopulation,
  tilePixels: number,
  overrides: Partial<PreparedPopulationProjectionPolicy>,
): PreparedPopulationProjectionPolicy {
  const policy = { ...defaultPolicy(population, tilePixels), ...overrides };
  nonnegativeSafeInteger(policy.respawn_variance_ms, "policy.respawn_variance_ms");
  positiveSafeInteger(policy.spawn_interval_ms, "policy.spawn_interval_ms");
  positiveSafeInteger(policy.retry_delay_ms, "policy.retry_delay_ms");
  nonnegativeSafeInteger(policy.camera_margin_px, "policy.camera_margin_px");
  nonnegativeSafeInteger(policy.min_player_distance_px, "policy.min_player_distance_px");
  nonnegativeSafeInteger(
    policy.minimum_spawn_separation_px,
    "policy.minimum_spawn_separation_px",
  );
  nonnegativeSafeInteger(policy.wander_radius_px, "policy.wander_radius_px");
  return Object.freeze(policy);
}

/**
 * Convert a fractional, authored gameplay population for one map into the
 * established integer-column spawn-director contract.
 *
 * A column belongs to an authored interval when its center lies inside the
 * half-open [left_fraction, right_fraction) range. This gives adjacent authored
 * zones deterministic, non-overlapping integer ranges.
 */
export function projectPreparedMobPopulation(
  population: PreparedMobPopulation,
  mapId: string,
  geometry: PreparedPopulationGeometry,
  policyOverrides: Partial<PreparedPopulationProjectionPolicy> = {},
): PreparedPopulationProjection | null {
  const sourceMap = population.maps.find((candidate) => candidate.map_id === mapId);
  if (sourceMap === undefined) return null;

  const worldColumns = positiveSafeInteger(geometry.world_columns, "geometry.world_columns");
  const tilePixels = positiveSafeInteger(geometry.tile_pixels, "geometry.tile_pixels");
  if (!Number.isSafeInteger(geometry.baseline_y)) {
    throw new PreparedPopulationProjectionError("geometry.baseline_y must be a safe integer");
  }
  if (sourceMap.seed_salt > UINT32_MAX) {
    throw new PreparedPopulationProjectionError(
      `mob population map ${JSON.stringify(mapId)} seed_salt must be <= ${UINT32_MAX}`,
    );
  }

  const policy = resolvePolicy(population, tilePixels, policyOverrides);
  const mobIdBySlot = Object.freeze(
    [...new Set(sourceMap.zones.flatMap((zone) => zone.spawn_table.map((entry) => entry.mob_id)))]
      .sort((left, right) => (left < right ? -1 : left > right ? 1 : 0)),
  );
  const slotByMobId = new Map(mobIdBySlot.map((mobId, slot) => [mobId, slot] as const));
  const zoneIdBySourceId: Record<string, string> = {};
  const usedZoneIds = new Set<string>();

  const zones = sourceMap.zones.map((sourceZone) => {
    const zoneId = normalizeZoneId(sourceZone.zone_id);
    if (usedZoneIds.has(zoneId)) {
      throw new PreparedPopulationProjectionError(
        `mob population map ${JSON.stringify(mapId)} has colliding normalized zone ID ${JSON.stringify(zoneId)}`,
      );
    }
    usedZoneIds.add(zoneId);
    zoneIdBySourceId[sourceZone.zone_id] = zoneId;

    const leftColumn = Math.max(
      0,
      Math.min(worldColumns, Math.ceil(sourceZone.left_fraction * worldColumns - 0.5)),
    );
    const rightColumnExclusive = Math.max(
      0,
      Math.min(worldColumns, Math.ceil(sourceZone.right_fraction * worldColumns - 0.5)),
    );
    if (rightColumnExclusive <= leftColumn) {
      throw new PreparedPopulationProjectionError(
        `mob population zone ${JSON.stringify(mapId + "/" + sourceZone.zone_id)} ` +
          `does not contain a column center at world resolution ${worldColumns}`,
      );
    }

    return {
      zone_id: zoneId,
      surface: sourceZone.surface,
      left_column: leftColumn,
      right_column_exclusive: rightColumnExclusive,
      initial_population: sourceZone.initial_population,
      target_population: sourceZone.target_population,
      population_cap: sourceZone.population_cap,
      respawn_delay_ms: sourceZone.respawn_delay_ms,
      respawn_variance_ms: Math.min(policy.respawn_variance_ms, sourceZone.respawn_delay_ms),
      spawn_interval_ms: policy.spawn_interval_ms,
      spawn_batch_size: Math.min(
        population.max_spawn_batch_per_update,
        sourceZone.population_cap,
      ),
      retry_delay_ms: policy.retry_delay_ms,
      spawn_visibility: policy.spawn_visibility,
      camera_margin_px: policy.camera_margin_px,
      min_player_distance_px: policy.min_player_distance_px,
      minimum_spawn_separation_px: policy.minimum_spawn_separation_px,
      wander_radius_px: policy.wander_radius_px,
      replacement_policy: "reroll_spawn_table" as const,
      spawn_table: sourceZone.spawn_table.map((entry) => ({
        mob_slot: slotByMobId.get(entry.mob_id)!,
        weight: entry.weight,
        min_alive: 0,
        max_alive: sourceZone.population_cap,
      })),
    };
  });

  const manifest = parseMobPopulationManifest({
    schema_version: 2,
    kind: "mob-population-v2",
    update_interval_ms: population.update_interval_ms,
    max_spawn_batch_per_update: population.max_spawn_batch_per_update,
    maps: [{ map_id: sourceMap.map_id, seed_salt: sourceMap.seed_salt, zones }],
  });

  const candidates = Object.freeze(
    manifest.maps[0]!.zones.map((zone) => {
      const zoneLeftPx = zone.left_column * tilePixels;
      const zoneRightPx = zone.right_column_exclusive * tilePixels;
      const candidateColumns = [];
      for (let column = zone.left_column; column < zone.right_column_exclusive; column += 1) {
        if (geometry.is_spawnable_column?.(column) === false) continue;
        const xPx = column * tilePixels + tilePixels / 2;
        if (
          xPx - zone.wander_radius_px < zoneLeftPx ||
          xPx + zone.wander_radius_px >= zoneRightPx
        ) {
          continue;
        }
        const height = geometry.height_at_column(column);
        nonnegativeSafeInteger(height, `geometry.height_at_column(${column})`);
        candidateColumns.push(
          Object.freeze({
            column,
            x_px: xPx,
            y_px: terrainSurfaceY(height, tilePixels, geometry.baseline_y),
          }),
        );
      }
      if (candidateColumns.length === 0) {
        throw new PreparedPopulationProjectionError(
          `mob population zone ${JSON.stringify(mapId + "/" + zone.zone_id)} ` +
            "has no spawnable terrain columns",
        );
      }
      return Object.freeze({
        map_id: sourceMap.map_id,
        zone_id: zone.zone_id,
        candidate_columns: Object.freeze(candidateColumns),
      });
    }),
  );

  return Object.freeze({
    manifest,
    candidates,
    mob_id_by_slot: mobIdBySlot,
    zone_id_by_source_id: Object.freeze(zoneIdBySourceId),
  });
}
