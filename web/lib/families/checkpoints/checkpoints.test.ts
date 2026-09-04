import { describe, expect, test } from "bun:test";
import { CheckpointLedger, resolveRespawnTarget, type RespawnSpawn } from "./home";
import { automatedConfirmDue, DefeatState, defeatPromptState } from "./defeat";
import { parseCheckpointsBlock } from "./manifest";

const VILLAGE: RespawnSpawn = { spawn_id: "village_gate", map_id: "village", normalized_x: 0.08 };
const ROUTE: RespawnSpawn = { spawn_id: "route_west", map_id: "route", normalized_x: 0.1 };
const BRAZIER: RespawnSpawn = { spawn_id: "brazier_3", map_id: "route", normalized_x: 0.62 };

// --- E4: one resolver, two genres that call their safe place different things ------------------

describe("E4: the respawn target under two vocabularies", () => {
  test("a platformer-shaped package: a safe village hub, and the entry spawn standing in it", () => {
    expect(
      resolveRespawnTarget({
        entry_spawn_id: "village_gate",
        map_uses: [
          { map_id: "village", role: "safe_village_hub" },
          { map_id: "route", role: "scrolling_hunting_route" },
        ],
        spawns: [VILLAGE, ROUTE],
        safeRole: "safe_village_hub",
      }),
    ).toEqual(VILLAGE);
  });

  test("a metroidvania-shaped package: the same rule, under the word `save_room`", () => {
    // The role was a literal inside the resolver, which is what made the whole
    // rule platformer-only. It is a parameter, and nothing else changed.
    expect(
      resolveRespawnTarget({
        entry_spawn_id: "route_west",
        map_uses: [
          { map_id: "route", role: "hostile_corridor" },
          { map_id: "village", role: "save_room" },
        ],
        spawns: [ROUTE, VILLAGE],
        safeRole: "save_room",
      }),
    ).toEqual(VILLAGE);
  });

  test("a game that opens on a hostile route wakes in the first safe place it declares", () => {
    // Respawning into the population that just killed the player is a death
    // loop rather than a recovery.
    expect(
      resolveRespawnTarget({
        entry_spawn_id: "route_west",
        map_uses: [
          { map_id: "route", role: "scrolling_hunting_route" },
          { map_id: "village", role: "safe_village_hub" },
        ],
        spawns: [ROUTE, VILLAGE],
        safeRole: "safe_village_hub",
      }),
    ).toEqual(VILLAGE);
  });

  test("a game with no safe place at all uses its entry spawn as-is", () => {
    expect(
      resolveRespawnTarget({
        entry_spawn_id: "route_west",
        map_uses: [{ map_id: "route", role: "scrolling_hunting_route" }],
        spawns: [ROUTE],
        safeRole: "safe_village_hub",
      }),
    ).toEqual(ROUTE);
  });

  test("an entry spawn that does not resolve is refused rather than guessed at", () => {
    expect(() =>
      resolveRespawnTarget({
        entry_spawn_id: "nowhere",
        map_uses: [],
        spawns: [ROUTE],
        safeRole: "safe_village_hub",
      }),
    ).toThrow("gameplay entry spawn nowhere does not resolve to a spawn point");
  });
});

// --- the last safe datum ------------------------------------------------------------------------

describe("the checkpoint ledger", () => {
  test("a genre that authors none falls through to the home spawn, which is the whole cost", () => {
    // This is the platformer, on every frame of both goldens.
    expect(new CheckpointLedger().placement(VILLAGE)).toEqual(VILLAGE);
  });

  test("and one that authors some wakes at the last one reached", () => {
    const ledger = new CheckpointLedger();
    expect(ledger.reach(ROUTE)).toBe(true);
    // Standing on the one already held is not reaching it again.
    expect(ledger.reach(ROUTE)).toBe(false);
    expect(ledger.reach(BRAZIER)).toBe(true);
    expect(ledger.placement(VILLAGE)).toEqual(BRAZIER);
    expect(ledger.reached()).toBe(2);
    ledger.clear();
    expect(ledger.placement(VILLAGE)).toEqual(VILLAGE);
  });
});

// --- being down, and being asked about it ------------------------------------------------------

const TIMING = { delayMs: 1000, fadeMs: 200 } as const;

describe("the defeat store", () => {
  test("a defeat is one edge however long the body lies there", () => {
    const defeat = new DefeatState();
    expect(defeat.record(500)).toBe(true);
    expect(defeat.record(533)).toBe(false);
    expect(defeat.since()).toBe(500);
    expect(defeat.defeated()).toBe(true);
    expect(defeat.deaths()).toBe(1);
  });

  test("the count survives the rebuild the recovery performs; the stamp does not", () => {
    const defeat = new DefeatState();
    defeat.record(500);
    defeat.clear();
    expect(defeat.since()).toBe(null);
    expect(defeat.deaths()).toBe(1);
    defeat.record(9000);
    expect(defeat.deaths()).toBe(2);
  });

  test("the prompt arrives after the delay and fades in over its own window", () => {
    expect(defeatPromptState({ defeatedAtMs: 0, nowMs: 999 }, TIMING)).toEqual({
      visible: false,
      alpha: 0,
    });
    expect(defeatPromptState({ defeatedAtMs: 0, nowMs: 1100 }, TIMING)).toEqual({
      visible: true,
      alpha: 0.5,
    });
    expect(defeatPromptState({ defeatedAtMs: 0, nowMs: 5000 }, TIMING)).toEqual({
      visible: true,
      alpha: 1,
    });
    // A zero fade is a cut, and is allowed rather than divided by.
    expect(
      defeatPromptState({ defeatedAtMs: 0, nowMs: 1000 }, { delayMs: 1000, fadeMs: 0 }),
    ).toEqual({ visible: true, alpha: 1 });
    expect(() =>
      defeatPromptState({ defeatedAtMs: Number.NaN, nowMs: 0 }, TIMING),
    ).toThrow("finite milliseconds");
  });

  test("an unattended run answers its own prompt, and only after the screen has been seen", () => {
    expect(automatedConfirmDue({ defeatedAtMs: 0, nowMs: 2399 }, 2400)).toBe(false);
    expect(automatedConfirmDue({ defeatedAtMs: 0, nowMs: 2400 }, 2400)).toBe(true);
  });
});

describe("the block the family gates for itself", () => {
  test("a moved safe-place table is refused by name", () => {
    expect(() =>
      parseCheckpointsBlock(
        { gameplay: "platformer-gameplay-block-v2" },
        { block: "gameplay", version: "platformer-gameplay-block-v1" },
      ),
    ).toThrow('manifest block "gameplay" is published as platformer-gameplay-block-v2');
  });
});
