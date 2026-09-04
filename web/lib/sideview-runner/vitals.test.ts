import { describe, expect, test } from "bun:test";
import { parseRunnerRuntimeManifest, type RunnerConsequences } from "./contract";
import { runnerManifestFixture } from "./fixture";
import { createRunnerWorld, type RunnerWorld } from "./world";
import { stepAvatar } from "./avatar";
import {
  applyPendingRecovery,
  avatarBlinkAlpha,
  avatarIsImmune,
  createVitalsSystem,
  recoverySurface,
  RUNNER_BLINK_ALPHA,
  RUNNER_REFRACTORY_MS,
} from "./vitals";

const system = createVitalsSystem();

/** `now` is in seconds, the way the fixed-step accumulator counts. */
function step(nowSeconds: number) {
  return { dt: 1 / 60, now: nowSeconds, frame: Math.round(nowSeconds * 60) } as const;
}

/**
 * Advance the simulation clock and resolve vitals.
 *
 * The system stamps its window from `clock.simulationNow` rather than from
 * `step.now` since the `clock` family landed, so a unit test has to say what
 * the simulation clock reads. Under a hold the two numbers differ, which is
 * the whole reason the integral exists.
 */
function tick(world: RunnerWorld, nowSeconds: number): void {
  world.clock.simulationDt = 1 / 60;
  world.clock.simulationNow = nowSeconds;
  system.update(world, step(nowSeconds));
}

function worldWith(consequences: Partial<RunnerConsequences> = {}): RunnerWorld {
  const document = runnerManifestFixture();
  const gameplay = document.gameplay as Record<string, unknown>;
  gameplay.consequences = { ...(gameplay.consequences as object), ...consequences };
  return createRunnerWorld(parseRunnerRuntimeManifest(document), 1);
}

describe("createVitalsSystem", () => {
  test("a hazard contact spends one point and leaves the run alive", () => {
    const world = worldWith();
    world.events.emit({ type: "hazard-contact", key: "6:filter_stack" });
    tick(world, 1);
    expect(world.vitals.gauge?.value).toBe(2);
    expect(world.vitals.hurtThisFrame).toBe(true);
    expect(world.events.ofType("run-ended")).toHaveLength(0);
    expect(world.events.ofType("drained")[0]?.remaining).toBe(2);
  });

  test("a second contact inside the immunity window is absorbed, not charged", () => {
    const world = worldWith();
    world.events.emit({ type: "hazard-contact", key: "6:a" });
    tick(world, 1);
    world.events.beginFrame();
    world.events.emit({ type: "hazard-contact", key: "9:b" });
    tick(world, 1.4);
    expect(world.vitals.gauge?.value).toBe(2);
    expect(world.events.ofType("absorbed")).toHaveLength(1);
  });

  test("a contact after the window connects again", () => {
    const world = worldWith();
    world.events.emit({ type: "hazard-contact", key: "6:a" });
    tick(world, 1);
    world.events.beginFrame();
    world.events.emit({ type: "hazard-contact", key: "9:b" });
    tick(world, 1 + RUNNER_REFRACTORY_MS / 1000);
    expect(world.vitals.gauge?.value).toBe(1);
  });

  test("the run ends only when the last point is spent", () => {
    const world = worldWith();
    let now = 1;
    for (let hit = 0; hit < 2; hit += 1) {
      world.events.beginFrame();
      world.events.emit({ type: "hazard-contact", key: `${hit}:a` });
      tick(world, now);
      expect(world.events.ofType("run-ended")).toHaveLength(0);
      now += RUNNER_REFRACTORY_MS / 1000;
    }
    world.events.beginFrame();
    world.events.emit({ type: "hazard-contact", key: "final:a" });
    tick(world, now);
    expect(world.vitals.gauge?.value).toBe(0);
    expect(world.vitals.depletedThisFrame).toBe(true);
    expect(world.events.ofType("run-ended")[0]?.source).toBe("hazard");
  });

  test("a terminal consequence ends the run without touching the gauge", () => {
    const world = worldWith({ crush: "end_run_v1" });
    world.events.emit({ type: "crush" });
    tick(world, 1);
    expect(world.events.ofType("run-ended")[0]?.source).toBe("crush");
    expect(world.vitals.gauge?.value).toBe(3);
  });

  test("a compound accident in one frame costs one point, not three", () => {
    // Clipping a prop on the way into a pit is ordinary play: the window
    // opened by the first source absorbs the rest of the same frame.
    const world = worldWith({ crush: "drain_v1" });
    world.events.emit({ type: "hazard-contact", key: "6:a" });
    world.events.emit({ type: "crush" });
    tick(world, 1);
    expect(world.vitals.gauge?.value).toBe(2);
    expect(world.events.ofType("absorbed")).toHaveLength(1);
  });

  test("a forgiven pit schedules a recovery rather than writing the avatar", () => {
    const world = worldWith();
    world.avatar.y = world.config.rows + 4;
    world.events.emit({ type: "pit" });
    tick(world, 1);
    // The sealer proved a same-frame write impossible: the avatar emits the
    // occurrence, so the answer has to arrive as next frame's feedback.
    expect(world.avatar.y).toBe(world.config.rows + 4);
    expect(world.vitals.pendingRecovery).not.toBe(null);
  });

  test("a dead run resolves nothing further", () => {
    const world = worldWith();
    world.run.phase = "dead";
    world.events.emit({ type: "hazard-contact", key: "6:a" });
    tick(world, 1);
    expect(world.vitals.gauge?.value).toBe(3);
    expect(world.events.ofType("run-ended")).toHaveLength(0);
  });

  test("the clock is converted once: fixed steps count seconds, the gauge milliseconds", () => {
    const world = worldWith();
    tick(world, 2);
    expect(world.vitals.clockMs).toBe(2000);
  });
});

describe("applyPendingRecovery", () => {
  test("stands the avatar on the scheduled surface and clears the request", () => {
    const world = worldWith();
    world.vitals.pendingRecovery = { column: 40, row: 8 };
    world.avatar.y = 99;
    world.avatar.vy = 12;
    world.avatar.grounded = false;
    applyPendingRecovery(world);
    expect(world.avatar.y).toBe(8);
    expect(world.avatar.vy).toBe(0);
    expect(world.avatar.grounded).toBe(true);
    expect(world.avatar.motion).toBe("run");
    expect(world.vitals.pendingRecovery).toBeNull();
  });

  test("never rewinds distance the player already earned", () => {
    const world = worldWith();
    world.avatar.distanceColumns = 120;
    world.vitals.pendingRecovery = { column: 40, row: 8 };
    applyPendingRecovery(world);
    expect(world.avatar.distanceColumns).toBe(120);
  });

  test("is a no-op with nothing scheduled", () => {
    const world = worldWith();
    const before = world.avatar.y;
    applyPendingRecovery(world);
    expect(world.avatar.y).toBe(before);
  });

  test("the avatar applies it at the top of its own step", () => {
    const world = worldWith();
    world.vitals.pendingRecovery = { column: 30, row: world.config.walkSurfaceRow };
    stepAvatar(world, 1 / 60);
    expect(world.avatar.grounded).toBe(true);
    expect(world.vitals.pendingRecovery).toBeNull();
  });
});

describe("recoverySurface", () => {
  test("finds the first solid column at or after the fall", () => {
    const world = worldWith();
    const found = recoverySurface(world, world.avatar.distanceColumns);
    expect(found).not.toBe(null);
    expect(found?.row).toBe(world.config.walkSurfaceRow);
  });
});

describe("the immunity read", () => {
  test("blinks only inside the window, and never once depleted", () => {
    const world = worldWith();
    expect(avatarIsImmune(world)).toBe(false);
    expect(avatarBlinkAlpha(world)).toBe(1);

    world.events.emit({ type: "hazard-contact", key: "6:a" });
    tick(world, 1);
    expect(avatarIsImmune(world)).toBe(true);
    expect(avatarBlinkAlpha(world)).toBe(RUNNER_BLINK_ALPHA);

    world.vitals.clockMs = 1000 + RUNNER_REFRACTORY_MS;
    expect(avatarIsImmune(world)).toBe(false);
    expect(avatarBlinkAlpha(world)).toBe(1);
  });

  test("a package with no gauge never blinks", () => {
    const document = runnerManifestFixture();
    const gameplay = document.gameplay as Record<string, unknown>;
    gameplay.consequences = { hazard: "end_run_v1", pit: "end_run_v1", crush: "end_run_v1" };
    gameplay.vitals = null;
    const world = createRunnerWorld(parseRunnerRuntimeManifest(document), 1);
    expect(world.vitals.gauge).toBeNull();
    expect(avatarBlinkAlpha(world)).toBe(1);
    expect(avatarIsImmune(world)).toBe(false);
  });
});
