import { describe, expect, test } from "bun:test";
import { createRunLoopSystem, nextRunSeed, PICKUP_SCORE } from "./run-loop";
import { parseRunnerRuntimeManifest } from "./contract";
import { runnerManifestFixture } from "./fixture";
import { runnerIntent } from "./intent";
import { createRunnerWorld, mulberry32 } from "./world";

const STEP = { dt: 1 / 60, now: 1 / 60, frame: 1 } as const;
const manifest = parseRunnerRuntimeManifest(runnerManifestFixture());
const system = createRunLoopSystem();

describe("createRunLoopSystem", () => {
  test("scores this frame's collected pickups", () => {
    const world = createRunnerWorld(manifest, 1);
    world.obstacles.collectedThisFrame = [{ itemId: "sunleaf_token", worldColumn: 6, row: 2 }];
    system.update(world, STEP);
    expect(world.run.score).toBe(PICKUP_SCORE);
    expect(world.run.phase).toBe("running");
  });

  test("a run-ended verdict ends the run and carries its source as the cause", () => {
    const world = createRunnerWorld(manifest, 1);
    world.events.emit({ type: "run-ended", source: "crush" });
    system.update(world, STEP);
    expect(world.run.phase).toBe("dead");
    expect(world.run.cause).toBe("crush");
    expect(world.avatar.motion).toBe("death");
  });

  test("hazard contact alone does not end the run: the consequence decides", () => {
    const world = createRunnerWorld(manifest, 1);
    world.obstacles.hazardContact = true;
    world.events.emit({ type: "hazard-contact", key: "6:filter_stack" });
    system.update(world, STEP);
    // No verdict was emitted, so nothing here ends anything. Under this
    // fixture a hazard drains instead, which is runner/vitals' answer to give.
    expect(world.run.phase).toBe("running");
  });

  test("a drained point that did not empty the gauge leaves the run alive", () => {
    const world = createRunnerWorld(manifest, 1);
    world.events.emit({ type: "drained", source: "hazard", remaining: 2 });
    system.update(world, STEP);
    expect(world.run.phase).toBe("running");
    expect(world.run.cause).toBe(null);
  });

  test("dead runs ignore scoring and wait for the restart request", () => {
    const world = createRunnerWorld(manifest, 1);
    world.run.phase = "dead";
    world.run.score = 30;
    world.obstacles.collectedThisFrame = [{ itemId: "sunleaf_token", worldColumn: 6, row: 2 }];
    system.update(world, STEP);
    expect(world.run.score).toBe(30);
    expect(world.run.phase).toBe("dead");
  });

  test("a jump or action request restarts a dead run under a fresh seed", () => {
    const world = createRunnerWorld(manifest, 1);
    const firstSeed = world.run.seed;
    world.run.phase = "dead";
    world.run.score = 90;
    world.avatar.distanceColumns = 300;
    world.intent = runnerIntent({ jump: true });
    system.update(world, STEP);
    // Widened read: TS control-flow narrowing cannot see the in-place reset.
    expect(world.run.phase as string).toBe("running");
    expect(world.run.seed).not.toBe(firstSeed);
    expect(world.run.score).toBe(0);
    expect(world.avatar.distanceColumns).toBe(2);
    expect(world.segments.chunks.length).toBeGreaterThan(0);
  });

  test("the fresh seed is deterministic from the dying run's RNG", () => {
    const runA = createRunnerWorld(manifest, 5);
    const runB = createRunnerWorld(manifest, 5);
    for (const world of [runA, runB]) {
      world.run.phase = "dead";
      world.intent = runnerIntent({ action: true });
      system.update(world, STEP);
    }
    expect(runA.run.seed).toBe(runB.run.seed);
  });
});

describe("nextRunSeed", () => {
  test("draws a 32-bit seed from the stream", () => {
    const seed = nextRunSeed(mulberry32(9));
    expect(Number.isSafeInteger(seed)).toBe(true);
    expect(seed).toBeGreaterThanOrEqual(0);
    expect(seed).toBeLessThan(0x100000000);
  });
});

describe("the pickup chain", () => {
  test("the multiplier steps at 5, 15, and 30 and caps at x4", async () => {
    const { chainMultiplier } = await import("./run-loop");
    expect(chainMultiplier(0)).toBe(1);
    expect(chainMultiplier(4)).toBe(1);
    expect(chainMultiplier(5)).toBe(2);
    expect(chainMultiplier(15)).toBe(3);
    expect(chainMultiplier(30)).toBe(4);
    expect(chainMultiplier(500)).toBe(4);
  });

  test("collections extend the chain and score by the earned multiplier", async () => {
    const { createRunLoopSystem, PICKUP_SCORE } = await import("./run-loop");
    const { parseRunnerRuntimeManifest } = await import("./contract");
    const { runnerManifestFixture } = await import("./fixture");
    const { createRunnerWorld } = await import("./world");
    const world = createRunnerWorld(parseRunnerRuntimeManifest(runnerManifestFixture()), 1);
    const system = createRunLoopSystem();
    const step = { dt: 1 / 60, now: 1 / 60, frame: 1 } as const;
    const token = { itemId: "sunleaf_token", worldColumn: 6, row: 2 } as const;
    world.run.chain = 4;
    world.obstacles.collectedThisFrame = [token];
    system.update(world, step);
    // Chain reaches 5 this frame, so the frame scores at the x2 it earned.
    expect(world.run.chain).toBe(5);
    expect(world.run.multiplier).toBe(2);
    expect(world.run.score).toBe(PICKUP_SCORE * 2);
  });

  test("a miss breaks the chain before the frame's collections extend it", async () => {
    const { createRunLoopSystem, PICKUP_SCORE } = await import("./run-loop");
    const { parseRunnerRuntimeManifest } = await import("./contract");
    const { runnerManifestFixture } = await import("./fixture");
    const { createRunnerWorld } = await import("./world");
    const world = createRunnerWorld(parseRunnerRuntimeManifest(runnerManifestFixture()), 1);
    const system = createRunLoopSystem();
    const step = { dt: 1 / 60, now: 1 / 60, frame: 1 } as const;
    world.run.chain = 40;
    world.run.multiplier = 4;
    world.obstacles.missedThisFrame = 1;
    world.obstacles.collectedThisFrame = [
      { itemId: "sunleaf_token", worldColumn: 6, row: 2 } as const,
    ];
    system.update(world, step);
    expect(world.run.chain).toBe(1);
    expect(world.run.multiplier).toBe(1);
    expect(world.run.score).toBe(PICKUP_SCORE);
  });

  test("formatCombo is silent without a chain and loud about the multiplier", async () => {
    const { formatCombo } = await import("./hud");
    expect(formatCombo(0, 1)).toBe("");
    expect(formatCombo(3, 1)).toBe("3 chain");
    expect(formatCombo(17, 3)).toBe("\u00d73 \u00b7 17 chain");
  });
});

describe("the intro phase", () => {
  test("holds the run until the fx moment releases it, then never replays on restart", async () => {
    const { fxBlockFixture } = await import("@/lib/manifest/fx");
    const document = runnerManifestFixture();
    document.fx = fxBlockFixture();
    const world = createRunnerWorld(parseRunnerRuntimeManifest(document), 1);
    expect(world.run.phase).toBe("intro");
    expect(world.fx?.moment).toBe("stage_start");
    system.update(world, STEP);
    expect(world.run.phase).toBe("intro");
    world.events.emit({ type: "fx-released", moment: "stage_start" });
    system.update(world, STEP);
    expect(world.run.phase).toBe("running");

    world.events.beginFrame();
    world.events.emit({ type: "run-ended", source: "pit" });
    system.update(world, STEP);
    expect(world.run.phase).toBe("dead");
    world.events.beginFrame();
    world.intent = runnerIntent({ jump: true });
    system.update(world, STEP);
    expect(world.run.phase).toBe("running");
    expect(world.fx).toBeNull();
  });

  test("a package with no fx block is born running", () => {
    const world = createRunnerWorld(manifest, 1);
    expect(world.run.phase).toBe("running");
    expect(world.fx).toBeNull();
  });
});
