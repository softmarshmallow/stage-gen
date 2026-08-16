import { describe, expect, test } from "bun:test";
import {
  GAMEPLAY_AUTOMATION_ENCOUNTER,
  GAMEPLAY_AUTOMATION_FRAME_MS,
  GAMEPLAY_AUTOMATION_MODE,
  GAMEPLAY_AUTOMATION_VIEWPORT,
  GameplayAutomationClock,
  GameplayAutomationRequestError,
  gameplayAutomationPresentation,
  heightmapSha256,
  readonlyGameplaySnapshot,
  resolveGameplayAutomationMode,
  sleepGameplayAutomationLoopAfterBoot,
  type GameplayAutomationSnapshot,
} from "./automation";

describe("gameplay automation server gate", () => {
  test("leaves normal previews unchanged when the query is absent", () => {
    expect(resolveGameplayAutomationMode(undefined, undefined)).toBeNull();
    expect(resolveGameplayAutomationMode(undefined, "1")).toBeNull();
  });

  test("accepts the exact mode only behind the exact server flag", () => {
    expect(resolveGameplayAutomationMode(GAMEPLAY_AUTOMATION_MODE, "1")).toBe(
      GAMEPLAY_AUTOMATION_MODE,
    );
    for (const [query, flag] of [
      [GAMEPLAY_AUTOMATION_MODE, undefined],
      [GAMEPLAY_AUTOMATION_MODE, "0"],
      ["gameplay-v2", "1"],
      [[GAMEPLAY_AUTOMATION_MODE], "1"],
    ] as const) {
      expect(() => resolveGameplayAutomationMode(query, flag)).toThrow(
        GameplayAutomationRequestError,
      );
    }
  });
});

describe("fixed gameplay clock", () => {
  test("sleeps only after Phaser has started its post-boot loop", async () => {
    const calls: string[] = [];
    const loop = {
      running: false,
      sleep: () => calls.push("sleep"),
    };
    sleepGameplayAutomationLoopAfterBoot(loop);
    expect(calls).toEqual([]);
    loop.running = true;
    await Promise.resolve();
    expect(calls).toEqual(["sleep"]);
  });

  test("starts at frame zero and advances by exactly one 30 Hz tick", () => {
    const clock = new GameplayAutomationClock();
    expect(clock.frame).toBe(0);
    expect(clock.simulationMs).toBe(0);
    expect(() => clock.advance()).toThrow("not ready");
    clock.markReady();

    expect(clock.advance()).toEqual({
      frame: 1,
      simulationMs: GAMEPLAY_AUTOMATION_FRAME_MS,
      deltaMs: GAMEPLAY_AUTOMATION_FRAME_MS,
    });
    expect(clock.advance().simulationMs).toBe(2 * GAMEPLAY_AUTOMATION_FRAME_MS);
    expect(GAMEPLAY_AUTOMATION_VIEWPORT).toEqual({ width: 1280, height: 720 });
  });

  test("a failed clock cannot advance or become ready", () => {
    const clock = new GameplayAutomationClock();
    clock.markFailed();
    expect(clock.state).toBe("error");
    expect(() => clock.advance()).toThrow("not ready");
    expect(() => clock.markReady()).toThrow("already settled");
  });
});

describe("deterministic gameplay presentation", () => {
  test("opens an unobscured encounter window and restores normal presentation", () => {
    const before = gameplayAutomationPresentation(0);
    const focused = gameplayAutomationPresentation(35);
    const restored = gameplayAutomationPresentation(81);
    expect(before.encounterFocus).toBeFalse();
    expect(focused).toMatchObject({
      encounterFocus: true,
      foregroundVisible: false,
      inventorySuppressed: true,
      cameraZoom: GAMEPLAY_AUTOMATION_ENCOUNTER.cameraZoom,
    });
    expect(restored).toMatchObject({
      encounterFocus: false,
      foregroundVisible: true,
      inventorySuppressed: false,
      cameraZoom: 1,
    });
  });

  test("keeps a deterministic portal pulse and marks every final active frame", () => {
    const start = gameplayAutomationPresentation(846);
    const penultimate = gameplayAutomationPresentation(899);
    const final = gameplayAutomationPresentation(900);
    expect(start.finalActiveWindow).toBeTrue();
    expect(penultimate.finalActiveWindow).toBeTrue();
    expect(final.finalActiveWindow).toBeTrue();
    expect(penultimate.portalScale).not.toBe(final.portalScale);
    expect(penultimate.portalAlpha).not.toBe(final.portalAlpha);
    expect(() => gameplayAutomationPresentation(-1)).toThrow(
      "nonnegative integer",
    );
  });
});

describe("public gameplay probe", () => {
  test("sorts asset keys and cannot mutate scene state", () => {
    const source: GameplayAutomationSnapshot = {
      version: GAMEPLAY_AUTOMATION_MODE,
      state: "ready",
      ready: true,
      errors: [],
      assetKeys: ["z", "a", "z"],
      frame: 0,
      simulationMs: 0,
      player: null,
      camera: { scrollX: 0, scrollY: 0, zoom: 1 },
      mobs: [],
      inventory: { visible: true, slots: [] },
      worldItems: [],
      encounter: {
        safeMarginPixels: GAMEPLAY_AUTOMATION_ENCOUNTER.safeMarginPixels,
        focusX: null,
        focusY: null,
        player: null,
        mob: null,
        attack: null,
        drop: null,
        pickup: null,
      },
      portals: [],
      presentation: gameplayAutomationPresentation(0),
      events: [
        { kind: "mob-hit", frame: 34, simulationMs: 34_000 / 30, data: null },
        { kind: "mob-drop", frame: 34, simulationMs: 34_000 / 30, data: null },
        {
          kind: "item-pickup",
          frame: 34,
          simulationMs: 34_000 / 30,
          data: null,
        },
      ],
      heightmapDigest: null,
    };
    const probe = readonlyGameplaySnapshot(source);
    expect(probe.assetKeys).toEqual(["a", "z"]);
    expect(JSON.parse(JSON.stringify(probe))).toEqual({
      ...source,
      assetKeys: ["a", "z"],
    });
    expect(Object.isFrozen(probe)).toBeTrue();
    expect(Object.isFrozen(probe.camera)).toBeTrue();
    expect(probe.events.map((event) => event.kind)).toEqual([
      "mob-hit",
      "mob-drop",
      "item-pickup",
    ]);
    expect(() => {
      (probe.camera as { scrollX: number }).scrollX = 12;
    }).toThrow();
    expect(source.camera.scrollX).toBe(0);
    expect(source.assetKeys).toEqual(["z", "a", "z"]);
  });

  test("uses a stable lowercase SHA-256 heightmap digest", async () => {
    const first = await heightmapSha256([1, 2, 4, 2]);
    expect(first).toMatch(/^[0-9a-f]{64}$/);
    expect(await heightmapSha256([1, 2, 4, 2])).toBe(first);
    expect(await heightmapSha256([1, 2, 4, 3])).not.toBe(first);
  });
});
