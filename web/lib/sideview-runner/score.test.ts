import { describe, expect, test } from "bun:test";
import { chainMultiplier, createScoreSystem, PICKUP_SCORE } from "./score";
import { parseRunnerRuntimeManifest } from "./contract";
import { runnerManifestFixture } from "./fixture";
import { createRunnerWorld } from "./world";

const STEP = { dt: 1 / 60, now: 1 / 60, frame: 1 } as const;
const manifest = parseRunnerRuntimeManifest(runnerManifestFixture());
const system = createScoreSystem();
const TOKEN = { itemId: "sunleaf_token", worldColumn: 6, row: 2 } as const;

describe("createScoreSystem", () => {
  test("scores this frame's collected pickups", () => {
    const world = createRunnerWorld(manifest, 1);
    world.obstacles.collectedThisFrame = [TOKEN];
    system.update(world, STEP);
    expect(world.score.total).toBe(PICKUP_SCORE);
    // The scorer says nothing about the lifecycle; the session owns that.
    expect(world.run.phase).toBe("running");
  });

  test("a run that is over scores nothing", () => {
    const world = createRunnerWorld(manifest, 1);
    world.run.phase = "dead";
    world.score.total = 30;
    world.obstacles.collectedThisFrame = [TOKEN];
    system.update(world, STEP);
    expect(world.score.total).toBe(30);
  });

  test("a restart starts the score again, and the scorer is the one that clears it", () => {
    const world = createRunnerWorld(manifest, 1);
    world.score = { total: 90, chain: 12, multiplier: 2 };
    system.reset?.(world, "run");
    expect(world.score).toEqual({ total: 0, chain: 0, multiplier: 1 });
  });
});

describe("the pickup chain", () => {
  test("the multiplier steps at 5, 15, and 30 and caps at x4", () => {
    expect(chainMultiplier(0)).toBe(1);
    expect(chainMultiplier(4)).toBe(1);
    expect(chainMultiplier(5)).toBe(2);
    expect(chainMultiplier(15)).toBe(3);
    expect(chainMultiplier(30)).toBe(4);
    expect(chainMultiplier(500)).toBe(4);
  });

  test("collections extend the chain and score by the earned multiplier", () => {
    const world = createRunnerWorld(manifest, 1);
    world.score.chain = 4;
    world.obstacles.collectedThisFrame = [TOKEN];
    system.update(world, STEP);
    // Chain reaches 5 this frame, so the frame scores at the x2 it earned.
    expect(world.score.chain).toBe(5);
    expect(world.score.multiplier).toBe(2);
    expect(world.score.total).toBe(PICKUP_SCORE * 2);
  });

  test("a miss breaks the chain before the frame's collections extend it", () => {
    const world = createRunnerWorld(manifest, 1);
    world.score.chain = 40;
    world.score.multiplier = 4;
    world.obstacles.missedThisFrame = 1;
    world.obstacles.collectedThisFrame = [TOKEN];
    system.update(world, STEP);
    expect(world.score.chain).toBe(1);
    expect(world.score.multiplier).toBe(1);
    expect(world.score.total).toBe(PICKUP_SCORE);
  });

  test("formatCombo is silent without a chain and loud about the multiplier", async () => {
    const { formatCombo } = await import("./hud");
    expect(formatCombo(0, 1)).toBe("");
    expect(formatCombo(3, 1)).toBe("3 chain");
    expect(formatCombo(17, 3)).toBe("×3 · 17 chain");
  });
});
