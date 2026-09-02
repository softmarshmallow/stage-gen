import { describe, expect, test } from "bun:test";

import {
  CLUSTER_JOIN_CHANCE,
  ManifestValidationError,
  MobPopulationDirector,
  parseMobPopulationManifest,
  type MobPopulationManifest,
  type MobSpawnZoneManifest,
  type SpawnUpdateContext,
  type ZoneCandidateColumns,
} from "./spawn-director";

const EMPTY_CONTEXT: SpawnUpdateContext = { players: [], cameras: [] };
const HUNTING_MAP = "hunting-ground";

function makeZone(
  overrides: Partial<MobSpawnZoneManifest> = {},
): MobSpawnZoneManifest {
  const populationCap = overrides.population_cap ?? 3;
  return {
    zone_id: "lower-terrace",
    surface: "terrain",
    left_column: 0,
    right_column_exclusive: 8,
    initial_population: 3,
    target_population: 3,
    population_cap: 3,
    respawn_delay_ms: 100,
    respawn_variance_ms: 0,
    spawn_interval_ms: 1,
    spawn_batch_size: overrides.spawn_batch_size ?? Math.min(3, populationCap),
    retry_delay_ms: 20,
    spawn_visibility: "allow_onscreen",
    camera_margin_px: 0,
    min_player_distance_px: 0,
    minimum_spawn_separation_px: 1,
    wander_radius_px: 32,
    replacement_policy: "same_archetype",
    spawn_table: [
      { mob_slot: 0, weight: 1, min_alive: 1, max_alive: 1 },
      { mob_slot: 1, weight: 100, min_alive: 0, max_alive: 2 },
    ],
    ...overrides,
  };
}

function makeManifest(
  zoneOverrides: Partial<MobSpawnZoneManifest> = {},
  rootOverrides: Partial<Pick<MobPopulationManifest, "update_interval_ms" | "max_spawn_batch_per_update">> = {},
): MobPopulationManifest {
  return {
    schema_version: 2,
    kind: "mob-population-v2",
    update_interval_ms: 1,
    max_spawn_batch_per_update: 8,
    maps: [
      {
        map_id: HUNTING_MAP,
        seed_salt: 117,
        zones: [makeZone(zoneOverrides)],
      },
    ],
    ...rootOverrides,
  };
}

function makeCandidates(
  columns: readonly { column: number; x_px: number; y_px: number }[] = [
    { column: 0, x_px: 0, y_px: 100 },
    { column: 1, x_px: 100, y_px: 100 },
    { column: 2, x_px: 200, y_px: 100 },
    { column: 3, x_px: 300, y_px: 100 },
    { column: 4, x_px: 400, y_px: 100 },
    { column: 5, x_px: 500, y_px: 100 },
    { column: 6, x_px: 600, y_px: 100 },
    { column: 7, x_px: 700, y_px: 100 },
  ],
): readonly ZoneCandidateColumns[] {
  return [
    {
      map_id: HUNTING_MAP,
      zone_id: "lower-terrace",
      candidate_columns: columns,
    },
  ];
}

describe("strict manifest and candidate validation", () => {
  test("parses the exact lower_snake_case mob-population-v2 wire shape", () => {
    const parsed = parseMobPopulationManifest(makeManifest());
    expect(parsed.kind).toBe("mob-population-v2");
    expect(parsed.maps[0]?.zones[0]?.right_column_exclusive).toBe(8);
    expect(Object.isFrozen(parsed.maps[0]?.zones[0]?.spawn_table)).toBe(true);
    const zone = parsed.maps[0]!.zones[0]!;
    expect(() => {
      (zone as { population_cap: number }).population_cap = 99;
    }).toThrow(TypeError);
    expect(zone.population_cap).toBe(3);
  });

  test("rejects aliases, unknown keys, and infeasible population bounds", () => {
    const aliased = {
      ...makeManifest(),
      updateIntervalMs: 10,
    };
    expect(() => parseMobPopulationManifest(aliased)).toThrow(ManifestValidationError);
    expect(() => parseMobPopulationManifest(aliased)).toThrow(
      "mob_population.updateIntervalMs is not a supported key",
    );

    expect(() =>
      parseMobPopulationManifest(
        makeManifest({ initial_population: 4, target_population: 3, population_cap: 3 }),
      ),
    ).toThrow("initial_population <= target_population <= population_cap");

    expect(() =>
      parseMobPopulationManifest(
        makeManifest({
          target_population: 3,
          spawn_table: [{ mob_slot: 0, weight: 1, min_alive: 0, max_alive: 2 }],
        }),
      ),
    ).toThrow("max_alive total is below target_population");
  });

  test("enforces half-open candidate column bounds", () => {
    expect(
      () =>
        new MobPopulationDirector(
          makeManifest(),
          makeCandidates([{ column: 8, x_px: 800, y_px: 100 }]),
        ),
    ).toThrow("[0, 8)");

    expect(
      () =>
        new MobPopulationDirector(
          makeManifest({
            initial_population: 1,
            target_population: 1,
            population_cap: 1,
            spawn_table: [{ mob_slot: 0, weight: 1, min_alive: 0, max_alive: 1 }],
          }),
          makeCandidates([{ column: 0, x_px: 0, y_px: 100 }]),
        ),
    ).not.toThrow();
  });

  test("enforces authoritative identifier, budget, salt, and non-overlap constraints", () => {
    expect(() => parseMobPopulationManifest(makeManifest({ target_population: 0 }))).toThrow(
      "target_population must be a safe integer >= 1",
    );
    expect(() =>
      parseMobPopulationManifest(
        makeManifest(
          { spawn_batch_size: 9, population_cap: 9 },
          { max_spawn_batch_per_update: 8 },
        ),
      ),
    ).toThrow("spawn_batch_size must not exceed max_spawn_batch_per_update");
    expect(() =>
      parseMobPopulationManifest(
        makeManifest({ spawn_batch_size: 4, population_cap: 3 }),
      ),
    ).toThrow("spawn_batch_size must not exceed population_cap");
    expect(() =>
      parseMobPopulationManifest(
        makeManifest({
          spawn_table: [
            { mob_slot: 0, weight: 0.5, min_alive: 1, max_alive: 1 },
            { mob_slot: 1, weight: 1, min_alive: 0, max_alive: 2 },
          ],
        }),
      ),
    ).toThrow("weight must be a safe integer >= 1");

    const validForSalt = makeManifest();
    const badSalt = {
      ...validForSalt,
      maps: [{ ...validForSalt.maps[0]!, seed_salt: 0x1_0000_0000 }],
    };
    expect(() => parseMobPopulationManifest(badSalt)).toThrow("seed_salt must be <= 4294967295");

    const overlapping = makeManifest();
    const map = overlapping.maps[0]!;
    const withOverlap = {
      ...overlapping,
      maps: [
        {
          ...map,
          zones: [
            makeZone({ zone_id: "left-zone", left_column: 0, right_column_exclusive: 5 }),
            makeZone({ zone_id: "right-zone", left_column: 4, right_column_exclusive: 8 }),
          ],
        },
      ],
    };
    expect(() => parseMobPopulationManifest(withOverlap)).toThrow("must not overlap");

    const snakeCaseId = {
      ...makeManifest(),
      maps: [{ ...map, map_id: "hunting_ground" }],
    };
    expect(() => parseMobPopulationManifest(snakeCaseId)).toThrow("kebab-case identifier");
  });
});

describe("population lifecycle", () => {
  test("initial fill honors per-archetype min/max and hard population cap", () => {
    const director = new MobPopulationDirector(makeManifest(), makeCandidates(), { seed: 9 });
    const reservations = director.update(HUNTING_MAP, 0, EMPTY_CONTEXT);

    expect(reservations).toHaveLength(3);
    expect(reservations.filter((reservation) => reservation.mob_slot === 0)).toHaveLength(1);
    expect(reservations.filter((reservation) => reservation.mob_slot === 1)).toHaveLength(2);
    expect(new Set(reservations.map((reservation) => reservation.candidate_column)).size).toBe(3);

    let zone = director.snapshot().maps[0]!.zones[0]!;
    expect(zone).toMatchObject({
      alive_count: 0,
      reserved_count: 3,
      scheduled_count: 0,
      effective_population: 3,
      population_cap: 3,
    });

    reservations.forEach((reservation, index) =>
      director.confirm(reservation.reservation_id, `mob-${index}`),
    );
    expect(director.update(HUNTING_MAP, 1, EMPTY_CONTEXT)).toEqual([]);
    zone = director.snapshot().maps[0]!.zones[0]!;
    expect(zone.alive_count).toBe(3);
    expect(zone.reserved_count).toBe(0);
  });

  test("paces initial fill by zone cadence and batch size", () => {
    const director = new MobPopulationDirector(
      makeManifest({ spawn_batch_size: 2, spawn_interval_ms: 100 }),
      makeCandidates(),
      { seed: 10 },
    );

    expect(director.update(HUNTING_MAP, 0, EMPTY_CONTEXT)).toHaveLength(2);
    expect(director.update(HUNTING_MAP, 99, EMPTY_CONTEXT)).toEqual([]);
    expect(director.update(HUNTING_MAP, 100, EMPTY_CONTEXT)).toHaveLength(1);
    expect(director.snapshot().maps[0]!.zones[0]!.effective_population).toBe(3);
  });

  test("warms to initial population, then continuously replenishes toward target", () => {
    const director = new MobPopulationDirector(
      makeManifest({
        initial_population: 1,
        target_population: 3,
        population_cap: 3,
      }),
      makeCandidates(),
      { seed: 101 },
    );

    const initial = director.update(HUNTING_MAP, 0, EMPTY_CONTEXT);
    expect(initial).toHaveLength(1);
    director.confirm(initial[0]!.reservation_id, "initial-mob");
    const replenishment = director.update(HUNTING_MAP, 1, EMPTY_CONTEXT);
    expect(replenishment).toHaveLength(2);
    expect(replenishment.every((reservation) => reservation.ticket_reason === "population_replenishment")).toBe(
      true,
    );
    expect(director.snapshot().maps[0]!.zones[0]!.effective_population).toBe(3);
  });

  test("enforces the director-wide spawn batch budget", () => {
    const lower = makeZone({
      zone_id: "lower-terrace",
      right_column_exclusive: 4,
      initial_population: 2,
      target_population: 2,
      population_cap: 2,
      spawn_batch_size: 1,
      spawn_table: [{ mob_slot: 0, weight: 1, min_alive: 0, max_alive: 2 }],
    });
    const upper = makeZone({
      zone_id: "upper-terrace",
      left_column: 4,
      right_column_exclusive: 8,
      initial_population: 2,
      target_population: 2,
      population_cap: 2,
      spawn_batch_size: 1,
      spawn_table: [{ mob_slot: 1, weight: 1, min_alive: 0, max_alive: 2 }],
    });
    const base = makeManifest({}, { max_spawn_batch_per_update: 1 });
    const manifest = {
      ...base,
      maps: [{ ...base.maps[0]!, zones: [lower, upper] }],
    };
    const candidateSets: readonly ZoneCandidateColumns[] = [
      {
        map_id: HUNTING_MAP,
        zone_id: "lower-terrace",
        candidate_columns: [
          { column: 0, x_px: 0, y_px: 100 },
          { column: 1, x_px: 100, y_px: 100 },
        ],
      },
      {
        map_id: HUNTING_MAP,
        zone_id: "upper-terrace",
        candidate_columns: [
          { column: 4, x_px: 400, y_px: 100 },
          { column: 5, x_px: 500, y_px: 100 },
        ],
      },
    ];
    const director = new MobPopulationDirector(
      manifest,
      candidateSets,
      { seed: 102 },
    );
    expect(director.update(HUNTING_MAP, 0, EMPTY_CONTEXT)[0]!.zone_id).toBe("lower-terrace");
    expect(director.update(HUNTING_MAP, 1, EMPTY_CONTEXT)[0]!.zone_id).toBe("upper-terrace");
    expect(director.update(HUNTING_MAP, 2, EMPTY_CONTEXT)[0]!.zone_id).toBe("lower-terrace");
    expect(director.update(HUNTING_MAP, 3, EMPTY_CONTEXT)[0]!.zone_id).toBe("upper-terrace");
    expect(director.update(HUNTING_MAP, 4, EMPTY_CONTEXT)).toEqual([]);
  });

  test("rejected reservations return to the same population ticket after retry delay", () => {
    const manifest = makeManifest({
      initial_population: 1,
      target_population: 1,
      population_cap: 1,
      retry_delay_ms: 50,
      spawn_table: [{ mob_slot: 0, weight: 1, min_alive: 0, max_alive: 1 }],
    });
    const director = new MobPopulationDirector(manifest, makeCandidates(), { seed: 11 });
    const first = director.update(HUNTING_MAP, 0, EMPTY_CONTEXT)[0]!;

    expect(director.reject(first.reservation_id, 5)).toBe(true);
    let zone = director.snapshot().maps[0]!.zones[0]!;
    expect(zone.reserved_count).toBe(0);
    expect(zone.tickets).toEqual([
      expect.objectContaining({ due_at_ms: 55, attempt_count: 1, reason: "initial_fill" }),
    ]);
    expect(director.update(HUNTING_MAP, 54, EMPTY_CONTEXT)).toEqual([]);
    const retried = director.update(HUNTING_MAP, 55, EMPTY_CONTEXT);
    expect(retried).toHaveLength(1);
    expect(retried[0]!.reservation_id).not.toBe(first.reservation_id);
    zone = director.snapshot().maps[0]!.zones[0]!;
    expect(zone.effective_population).toBe(1);
  });

  test("reject and death callbacks share the map simulation-time watermark", () => {
    const singleMobManifest = makeManifest({
      initial_population: 1,
      target_population: 1,
      population_cap: 1,
      spawn_table: [{ mob_slot: 0, weight: 1, min_alive: 0, max_alive: 1 }],
    });

    const deathDirector = new MobPopulationDirector(singleMobManifest, makeCandidates(), {
      seed: 201,
    });
    const deathReservation = deathDirector.update(HUNTING_MAP, 0, EMPTY_CONTEXT)[0]!;
    deathDirector.confirm(deathReservation.reservation_id, "watermark-mob");
    deathDirector.update(HUNTING_MAP, 1_000, EMPTY_CONTEXT);
    expect(() => deathDirector.recordDeath("watermark-mob", 999)).toThrow(
      "now_ms must be monotonic for each map",
    );
    expect(deathDirector.snapshot().maps[0]!.zones[0]!.alive_count).toBe(1);

    const rejectDirector = new MobPopulationDirector(singleMobManifest, makeCandidates(), {
      seed: 202,
    });
    const pending = rejectDirector.update(HUNTING_MAP, 0, EMPTY_CONTEXT)[0]!;
    rejectDirector.update(HUNTING_MAP, 1_000, EMPTY_CONTEXT);
    expect(() => rejectDirector.reject(pending.reservation_id, 999)).toThrow(
      "now_ms must be monotonic for each map",
    );
    expect(rejectDirector.snapshot().maps[0]!.zones[0]!.reserved_count).toBe(1);
  });

  test("deadline overflow fails without losing the actor or reservation", () => {
    const manifest = makeManifest({
      initial_population: 1,
      target_population: 1,
      population_cap: 1,
      respawn_delay_ms: 100,
      respawn_variance_ms: 0,
      retry_delay_ms: 100,
      spawn_table: [{ mob_slot: 0, weight: 1, min_alive: 0, max_alive: 1 }],
    });
    const nearLimit = Number.MAX_SAFE_INTEGER - 50;

    const deathDirector = new MobPopulationDirector(manifest, makeCandidates(), { seed: 203 });
    const liveReservation = deathDirector.update(HUNTING_MAP, 0, EMPTY_CONTEXT)[0]!;
    deathDirector.confirm(liveReservation.reservation_id, "overflow-mob");
    expect(() => deathDirector.recordDeath("overflow-mob", nearLimit)).toThrow(
      "respawn deadline exceeds the safe simulation-time range",
    );
    expect(deathDirector.snapshot().maps[0]!.zones[0]).toMatchObject({
      alive_count: 1,
      scheduled_count: 0,
    });

    const rejectDirector = new MobPopulationDirector(manifest, makeCandidates(), { seed: 204 });
    const pending = rejectDirector.update(HUNTING_MAP, 0, EMPTY_CONTEXT)[0]!;
    expect(() => rejectDirector.reject(pending.reservation_id, nearLimit)).toThrow(
      "retry deadline exceeds the safe simulation-time range",
    );
    expect(rejectDirector.snapshot().maps[0]!.zones[0]).toMatchObject({
      reserved_count: 1,
      scheduled_count: 0,
    });

    const batchManifest = makeManifest({
      initial_population: 2,
      target_population: 2,
      population_cap: 2,
      spawn_batch_size: 2,
      retry_delay_ms: 100,
      spawn_table: [{ mob_slot: 0, weight: 1, min_alive: 0, max_alive: 2 }],
    });
    const batchDirector = new MobPopulationDirector(
      batchManifest,
      makeCandidates([{ column: 0, x_px: 0, y_px: 100 }]),
      { seed: 205 },
    );
    expect(() => batchDirector.update(HUNTING_MAP, nearLimit, EMPTY_CONTEXT)).toThrow(
      "retry deadline exceeds the safe simulation-time range",
    );
    expect(batchDirector.snapshot().maps[0]!.zones[0]).toMatchObject({
      initialized: false,
      reserved_count: 0,
      scheduled_count: 0,
    });
  });

  test("death schedules one delayed same-archetype replacement and is idempotent", () => {
    const manifest = makeManifest({
      initial_population: 1,
      target_population: 1,
      population_cap: 1,
      respawn_delay_ms: 100,
      respawn_variance_ms: 0,
      replacement_policy: "same_archetype",
      spawn_table: [{ mob_slot: 2, weight: 1, min_alive: 0, max_alive: 1 }],
    });
    const director = new MobPopulationDirector(manifest, makeCandidates(), { seed: 12 });
    const first = director.update(HUNTING_MAP, 0, EMPTY_CONTEXT)[0]!;
    director.confirm(first.reservation_id, "mob-a");

    expect(director.recordDeath("mob-a", 100)).toEqual(
      expect.objectContaining({ due_at_ms: 200, locked_mob_slot: 2 }),
    );
    expect(director.recordDeath("mob-a", 100)).toBeUndefined();
    expect(director.update(HUNTING_MAP, 199, EMPTY_CONTEXT)).toEqual([]);
    const replacement = director.update(HUNTING_MAP, 200, EMPTY_CONTEXT);
    expect(replacement).toHaveLength(1);
    expect(replacement[0]!.mob_slot).toBe(2);
    expect(replacement[0]!.ticket_reason).toBe("death_replacement");
  });

  test("locked death tickets reserve archetype capacity from unlocked warm-up tickets", () => {
    const manifest = makeManifest({
      initial_population: 3,
      target_population: 3,
      population_cap: 3,
      spawn_batch_size: 2,
      respawn_delay_ms: 100,
      respawn_variance_ms: 0,
      replacement_policy: "same_archetype",
      spawn_table: [
        { mob_slot: 0, weight: 1, min_alive: 1, max_alive: 1 },
        { mob_slot: 1, weight: 1, min_alive: 1, max_alive: 2 },
      ],
    });
    const director = new MobPopulationDirector(manifest, makeCandidates(), { seed: 206 });
    const firstBatch = director.update(HUNTING_MAP, 0, EMPTY_CONTEXT);
    expect(firstBatch).toHaveLength(2);
    expect(new Set(firstBatch.map((reservation) => reservation.mob_slot))).toEqual(
      new Set([0, 1]),
    );
    for (const reservation of firstBatch) {
      director.confirm(reservation.reservation_id, `first-${reservation.mob_slot}`);
    }

    expect(director.recordDeath("first-0", 0)).toEqual(
      expect.objectContaining({ due_at_ms: 100, locked_mob_slot: 0 }),
    );
    const remainingWarmUp = director.update(HUNTING_MAP, 1, EMPTY_CONTEXT);
    expect(remainingWarmUp).toHaveLength(1);
    expect(remainingWarmUp[0]!.mob_slot).toBe(1);
    director.confirm(remainingWarmUp[0]!.reservation_id, "second-1");

    const replacement = director.update(HUNTING_MAP, 100, EMPTY_CONTEXT);
    expect(replacement).toHaveLength(1);
    expect(replacement[0]).toMatchObject({
      mob_slot: 0,
      ticket_reason: "death_replacement",
    });
    director.confirm(replacement[0]!.reservation_id, "replacement-0");
    expect(director.snapshot().maps[0]!.zones[0]).toMatchObject({
      alive_count: 3,
      scheduled_count: 0,
      effective_population: 3,
    });
  });

  test("respawn variance is deterministic, bounded, and reroll tickets stay unlocked", () => {
    const manifest = makeManifest({
      initial_population: 1,
      target_population: 1,
      population_cap: 1,
      respawn_delay_ms: 100,
      respawn_variance_ms: 40,
      replacement_policy: "reroll_spawn_table",
      spawn_table: [
        { mob_slot: 0, weight: 1, min_alive: 0, max_alive: 1 },
        { mob_slot: 1, weight: 1, min_alive: 0, max_alive: 1 },
      ],
    });
    const first = new MobPopulationDirector(manifest, makeCandidates(), { seed: 103 });
    const second = new MobPopulationDirector(manifest, makeCandidates(), { seed: 103 });
    const firstReservation = first.update(HUNTING_MAP, 0, EMPTY_CONTEXT)[0]!;
    const secondReservation = second.update(HUNTING_MAP, 0, EMPTY_CONTEXT)[0]!;
    first.confirm(firstReservation.reservation_id, "first-mob");
    second.confirm(secondReservation.reservation_id, "second-mob");

    const firstTicket = first.recordDeath("first-mob", 1_000)!;
    const secondTicket = second.recordDeath("second-mob", 1_000)!;
    expect(firstTicket.due_at_ms).toBe(secondTicket.due_at_ms);
    expect(firstTicket.due_at_ms).toBeGreaterThanOrEqual(1_060);
    expect(firstTicket.due_at_ms).toBeLessThanOrEqual(1_140);
    expect(firstTicket).not.toHaveProperty("locked_mob_slot");
  });

  test("seed and salt make weighted selection and candidate sampling replayable", () => {
    const manifest = makeManifest({
      initial_population: 6,
      target_population: 6,
      population_cap: 6,
      spawn_batch_size: 6,
      spawn_table: [
        { mob_slot: 0, weight: 1, min_alive: 0, max_alive: 6 },
        { mob_slot: 1, weight: 4, min_alive: 0, max_alive: 6 },
      ],
    });
    const first = new MobPopulationDirector(manifest, makeCandidates(), { seed: 42 });
    const second = new MobPopulationDirector(manifest, makeCandidates(), { seed: 42 });

    const firstResult = first
      .update(HUNTING_MAP, 0, EMPTY_CONTEXT)
      .map(({ mob_slot, candidate_column }) => ({ mob_slot, candidate_column }));
    const secondResult = second
      .update(HUNTING_MAP, 0, EMPTY_CONTEXT)
      .map(({ mob_slot, candidate_column }) => ({ mob_slot, candidate_column }));
    expect(firstResult).toEqual(secondResult);
    expect(firstResult).toHaveLength(6);
  });
});

describe("placement policy", () => {
  test("offscreen-required combines camera margin, player exclusion, and occupancy", () => {
    const manifest = makeManifest({
      initial_population: 1,
      target_population: 1,
      population_cap: 1,
      retry_delay_ms: 20,
      spawn_visibility: "offscreen_required",
      camera_margin_px: 0,
      min_player_distance_px: 30,
      minimum_spawn_separation_px: 20,
      spawn_table: [{ mob_slot: 1, weight: 1, min_alive: 0, max_alive: 1 }],
    });
    const candidates = makeCandidates([
      { column: 0, x_px: 10, y_px: 50 },
      { column: 1, x_px: 200, y_px: 50 },
      { column: 2, x_px: 300, y_px: 50 },
    ]);
    const director = new MobPopulationDirector(manifest, candidates, { seed: 13 });
    const blockedContext: SpawnUpdateContext = {
      cameras: [
        { left_px: 0, right_px_exclusive: 100, top_px: 0, bottom_px_exclusive: 100 },
      ],
      players: [{ x_px: 200, y_px: 50 }],
      occupied_points: [{ x_px: 300, y_px: 50 }],
    };

    expect(director.update(HUNTING_MAP, 0, blockedContext)).toEqual([]);
    expect(director.snapshot().maps[0]!.zones[0]!.tickets[0]).toMatchObject({
      due_at_ms: 20,
      attempt_count: 1,
    });

    const available = director.update(HUNTING_MAP, 20, {
      cameras: blockedContext.cameras,
      players: [],
      occupied_points: [],
    });
    expect(available).toHaveLength(1);
    expect(available[0]!.x_px).toBeGreaterThanOrEqual(200);
  });

  test("offscreen-preferred falls back onscreen, while reservations occupy candidates", () => {
    const manifest = makeManifest({
      initial_population: 2,
      target_population: 2,
      population_cap: 2,
      spawn_visibility: "offscreen_preferred",
      minimum_spawn_separation_px: 0,
      spawn_table: [{ mob_slot: 1, weight: 1, min_alive: 0, max_alive: 2 }],
    });
    const director = new MobPopulationDirector(
      manifest,
      makeCandidates([
        { column: 0, x_px: 10, y_px: 50 },
        { column: 1, x_px: 20, y_px: 50 },
      ]),
      { seed: 14 },
    );
    const reservations = director.update(HUNTING_MAP, 0, {
      players: [],
      cameras: [
        { left_px: 0, right_px_exclusive: 100, top_px: 0, bottom_px_exclusive: 100 },
      ],
    });

    expect(reservations).toHaveLength(2);
    expect(new Set(reservations.map((reservation) => reservation.candidate_column)).size).toBe(2);
  });
});

describe("clustered placement", () => {
  const WIDE_COLUMNS = Array.from({ length: 40 }, (_, column) => ({
    column,
    x_px: column * 64 + 32,
    y_px: 100,
  }));

  function clusteredManifest(overrides: Partial<MobSpawnZoneManifest> = {}) {
    return makeManifest(
      {
        right_column_exclusive: 40,
        initial_population: 9,
        target_population: 9,
        population_cap: 9,
        spawn_batch_size: 9,
        minimum_spawn_separation_px: 1,
        placement: "clustered",
        cluster_radius_px: 160,
        spawn_table: [{ mob_slot: 1, weight: 1, min_alive: 0, max_alive: 9 }],
        ...overrides,
      },
      { max_spawn_batch_per_update: 9 },
    );
  }

  function spread(reservations: readonly { x_px: number }[]): number {
    // The mean distance from each body to its nearest neighbour: small for clumps, large for an
    // even spread. Nine bodies over forty columns spread evenly stand about four columns apart.
    const xs = reservations.map((reservation) => reservation.x_px);
    let total = 0;
    for (const x of xs) {
      let nearest = Number.POSITIVE_INFINITY;
      for (const other of xs) if (other !== x) nearest = Math.min(nearest, Math.abs(other - x));
      total += nearest;
    }
    return total / xs.length;
  }

  test("absent placement reads as uniform and the zone shape is unchanged", () => {
    const parsed = parseMobPopulationManifest(makeManifest());
    const zone = parsed.maps[0]!.zones[0]!;
    expect(zone.placement).toBe("uniform");
    expect(zone.cluster_radius_px).toBe(0);
    expect(() =>
      parseMobPopulationManifest(makeManifest({ placement: "clustered", cluster_radius_px: 0 })),
    ).toThrow("cluster_radius_px must be positive");
    expect(() =>
      parseMobPopulationManifest(makeManifest({ placement: "huddled" as "uniform" })),
    ).toThrow("placement");
  });

  test("clustered bodies stand closer to their nearest neighbour than uniform ones", () => {
    const clustered = new MobPopulationDirector(
      clusteredManifest(),
      makeCandidates(WIDE_COLUMNS),
      { seed: 7 },
    ).update(HUNTING_MAP, 0, EMPTY_CONTEXT);
    const uniform = new MobPopulationDirector(
      clusteredManifest({ placement: "uniform", cluster_radius_px: 0 }),
      makeCandidates(WIDE_COLUMNS),
      { seed: 7 },
    ).update(HUNTING_MAP, 0, EMPTY_CONTEXT);
    expect(clustered).toHaveLength(9);
    expect(uniform).toHaveLength(9);
    expect(spread(clustered)).toBeLessThan(spread(uniform));
    // Every joined body is within the radius of at least one other body.
    let joined = 0;
    for (const body of clustered) {
      if (clustered.some((other) => other !== body && Math.abs(other.x_px - body.x_px) <= 160)) {
        joined += 1;
      }
    }
    expect(joined).toBeGreaterThanOrEqual(Math.floor(9 * CLUSTER_JOIN_CHANCE));
  });

  test("clustering never places two bodies on one column and replays with the seed", () => {
    const first = new MobPopulationDirector(clusteredManifest(), makeCandidates(WIDE_COLUMNS), {
      seed: 21,
    }).update(HUNTING_MAP, 0, EMPTY_CONTEXT);
    const second = new MobPopulationDirector(clusteredManifest(), makeCandidates(WIDE_COLUMNS), {
      seed: 21,
    }).update(HUNTING_MAP, 0, EMPTY_CONTEXT);
    expect(first.map((r) => r.candidate_column)).toEqual(second.map((r) => r.candidate_column));
    expect(new Set(first.map((r) => r.candidate_column)).size).toBe(first.length);
  });

  test("a clump with no free column beside it falls back to a uniform draw", () => {
    // Two columns only, far apart: the second body cannot join the first, so it must still land.
    const manifest = clusteredManifest({
      right_column_exclusive: 8,
      initial_population: 2,
      target_population: 2,
      population_cap: 2,
      spawn_batch_size: 2,
      spawn_table: [{ mob_slot: 1, weight: 1, min_alive: 0, max_alive: 2 }],
    });
    const reservations = new MobPopulationDirector(
      manifest,
      makeCandidates([
        { column: 0, x_px: 0, y_px: 100 },
        { column: 7, x_px: 700, y_px: 100 },
      ]),
      { seed: 3 },
    ).update(HUNTING_MAP, 0, EMPTY_CONTEXT);
    expect(reservations).toHaveLength(2);
  });
});

describe("snapshot and disposal", () => {
  test("snapshot exposes live ownership and dispose returns cleanup handles", () => {
    const director = new MobPopulationDirector(makeManifest(), makeCandidates(), { seed: 15 });
    const reservations = director.update(HUNTING_MAP, 0, EMPTY_CONTEXT);
    director.confirm(reservations[0]!.reservation_id, "mob-live");

    const before = director.snapshot().maps[0]!.zones[0]!;
    expect(before.alive[0]).toMatchObject({ instance_id: "mob-live" });
    expect(before.reserved_count).toBe(2);

    const disposed = director.dispose();
    expect(disposed.instance_ids).toEqual(["mob-live"]);
    expect(disposed.reservation_ids).toHaveLength(2);
    expect(director.snapshot()).toMatchObject({ disposed: true });
    expect(director.snapshot().maps[0]!.zones[0]).toMatchObject({
      alive_count: 0,
      reserved_count: 0,
      scheduled_count: 0,
    });
    expect(director.dispose()).toEqual({
      instance_ids: [],
      reservation_ids: [],
      cancelled_ticket_count: 0,
    });
    expect(() => director.update(HUNTING_MAP, 1, EMPTY_CONTEXT)).toThrow("is disposed");
  });
});
