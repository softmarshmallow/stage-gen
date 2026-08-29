import { describe, expect, test } from "bun:test";
import { DEATH_STRIP_DURATION_MS } from "./death-presentation";
import {
  DEFEAT_RECOVERY_DELAY_MS,
  defeatRecoveryDue,
  resolveHomeSpawn,
} from "./respawn";

const VILLAGE_SPAWN = {
  spawn_id: "village_west_gate",
  map_id: "sunpetal-crossing",
  normalized_x: 0.08,
};
const VILLAGE_EAST_SPAWN = {
  spawn_id: "village_east_gate",
  map_id: "sunpetal-crossing",
  normalized_x: 0.92,
};
const ROAD_SPAWN = {
  spawn_id: "road_west_gate",
  map_id: "crowncrag-road",
  normalized_x: 0.05,
};
const MAP_USES = [
  { map_id: "sunpetal-crossing", role: "safe_village_hub" },
  { map_id: "crowncrag-road", role: "scrolling_hunting_route" },
];

describe("home spawn resolution", () => {
  test("keeps the authored entry spawn when the game opens in the village", () => {
    expect(
      resolveHomeSpawn({
        entry_map_id: "sunpetal-crossing",
        entry_spawn_id: "village_west_gate",
        map_uses: MAP_USES,
        spawns: [VILLAGE_SPAWN, VILLAGE_EAST_SPAWN, ROAD_SPAWN],
      }),
    ).toEqual(VILLAGE_SPAWN);
  });

  test("prefers the village over an entry spawn that stands on a hostile route", () => {
    // Respawning into the population that just killed the player is a death loop, not a recovery.
    expect(
      resolveHomeSpawn({
        entry_map_id: "crowncrag-road",
        entry_spawn_id: "road_west_gate",
        map_uses: MAP_USES,
        spawns: [ROAD_SPAWN, VILLAGE_SPAWN, VILLAGE_EAST_SPAWN],
      }),
    ).toEqual(VILLAGE_SPAWN);
  });

  test("falls back to the entry spawn when a package declares no safe hub", () => {
    expect(
      resolveHomeSpawn({
        entry_map_id: "crowncrag-road",
        entry_spawn_id: "road_west_gate",
        map_uses: [{ map_id: "crowncrag-road", role: "scrolling_hunting_route" }],
        spawns: [ROAD_SPAWN],
      }),
    ).toEqual(ROAD_SPAWN);
  });

  test("rejects a package whose entry spawn does not resolve", () => {
    expect(() =>
      resolveHomeSpawn({
        entry_map_id: "sunpetal-crossing",
        entry_spawn_id: "missing_gate",
        map_uses: MAP_USES,
        spawns: [VILLAGE_SPAWN],
      }),
    ).toThrow(/does not resolve/);
  });

  test("returns a frozen spawn the scene cannot edit in place", () => {
    const home = resolveHomeSpawn({
      entry_map_id: "sunpetal-crossing",
      entry_spawn_id: "village_west_gate",
      map_uses: MAP_USES,
      spawns: [VILLAGE_SPAWN],
    });
    expect(Object.isFrozen(home)).toBe(true);
  });
});

describe("defeat recovery timing", () => {
  test("outlasts the authored terminal strip so defeat reads as an ending", () => {
    expect(DEFEAT_RECOVERY_DELAY_MS).toBeGreaterThan(DEATH_STRIP_DURATION_MS);
  });

  test("holds the corpse until the delay elapses, then releases it", () => {
    const defeatedAtMs = 5_000;
    expect(defeatRecoveryDue({ defeatedAtMs, nowMs: defeatedAtMs })).toBe(false);
    expect(
      defeatRecoveryDue({
        defeatedAtMs,
        nowMs: defeatedAtMs + DEFEAT_RECOVERY_DELAY_MS - 1,
      }),
    ).toBe(false);
    expect(
      defeatRecoveryDue({
        defeatedAtMs,
        nowMs: defeatedAtMs + DEFEAT_RECOVERY_DELAY_MS,
      }),
    ).toBe(true);
  });

  test("accepts an explicit delay and rejects nonsense timing", () => {
    expect(defeatRecoveryDue({ defeatedAtMs: 0, nowMs: 10, delayMs: 10 })).toBe(true);
    expect(() =>
      defeatRecoveryDue({ defeatedAtMs: Number.NaN, nowMs: 10 }),
    ).toThrow(/finite/);
    expect(() =>
      defeatRecoveryDue({ defeatedAtMs: 0, nowMs: 10, delayMs: -1 }),
    ).toThrow(/finite/);
  });
});
