import { describe, expect, test } from "bun:test";
import { DEATH_STRIP_DURATION_MS } from "./death-presentation";
import {
  DEFEAT_AUTOMATED_CONFIRM_DELAY_MS,
  DEFEAT_PROMPT_DELAY_MS,
  DEFEAT_PROMPT_FADE_MS,
  automatedDefeatConfirmDue,
  defeatPromptState,
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

describe("defeat prompt timing", () => {
  test("waits out the authored terminal strip, so it never talks over the death", () => {
    expect(DEFEAT_PROMPT_DELAY_MS).toBeGreaterThan(DEATH_STRIP_DURATION_MS);
  });

  test("stays hidden until its delay, then fades in and settles", () => {
    const defeatedAtMs = 5_000;
    expect(defeatPromptState({ defeatedAtMs, nowMs: defeatedAtMs })).toMatchObject({
      visible: false,
      alpha: 0,
    });
    expect(
      defeatPromptState({
        defeatedAtMs,
        nowMs: defeatedAtMs + DEFEAT_PROMPT_DELAY_MS - 1,
      }).visible,
    ).toBe(false);
    const arriving = defeatPromptState({
      defeatedAtMs,
      nowMs: defeatedAtMs + DEFEAT_PROMPT_DELAY_MS + DEFEAT_PROMPT_FADE_MS / 2,
    });
    expect(arriving.visible).toBe(true);
    expect(arriving.alpha).toBeGreaterThan(0);
    expect(arriving.alpha).toBeLessThan(1);
    expect(
      defeatPromptState({
        defeatedAtMs,
        nowMs: defeatedAtMs + DEFEAT_PROMPT_DELAY_MS + DEFEAT_PROMPT_FADE_MS,
      }).alpha,
    ).toBe(1);
  });

  test("a clock left running does not drive the fade past full", () => {
    expect(defeatPromptState({ defeatedAtMs: 0, nowMs: 900_000 }).alpha).toBe(1);
  });

  test("nonsense timing is refused rather than rendered", () => {
    expect(() => defeatPromptState({ defeatedAtMs: Number.NaN, nowMs: 10 })).toThrow(
      /finite/,
    );
    expect(() => defeatPromptState({ defeatedAtMs: 0, nowMs: 10, delayMs: -1 })).toThrow(
      /finite/,
    );
  });
});

describe("answering the prompt without a player", () => {
  test("an unattended run waits for the prompt to stand before accepting it", () => {
    expect(DEFEAT_AUTOMATED_CONFIRM_DELAY_MS).toBeGreaterThan(DEFEAT_PROMPT_DELAY_MS);
  });

  test("it holds until the delay elapses, then answers", () => {
    const defeatedAtMs = 5_000;
    expect(automatedDefeatConfirmDue({ defeatedAtMs, nowMs: defeatedAtMs })).toBe(false);
    expect(
      automatedDefeatConfirmDue({
        defeatedAtMs,
        nowMs: defeatedAtMs + DEFEAT_AUTOMATED_CONFIRM_DELAY_MS - 1,
      }),
    ).toBe(false);
    expect(
      automatedDefeatConfirmDue({
        defeatedAtMs,
        nowMs: defeatedAtMs + DEFEAT_AUTOMATED_CONFIRM_DELAY_MS,
      }),
    ).toBe(true);
  });

  test("accepts an explicit delay and rejects nonsense timing", () => {
    expect(automatedDefeatConfirmDue({ defeatedAtMs: 0, nowMs: 10, delayMs: 10 })).toBe(
      true,
    );
    expect(() =>
      automatedDefeatConfirmDue({ defeatedAtMs: Number.NaN, nowMs: 10 }),
    ).toThrow(/finite/);
  });
});
