import { describe, expect, test } from "bun:test";
import {
  createDifficultySystem,
  difficultyCeiling,
  rampProfile,
  speedMultiplier,
} from "./difficulty";
import { parseRunnerRuntimeManifest } from "./contract";
import { runnerManifestFixture } from "./fixture";
import { createRunnerWorld } from "./world";

const gentle = rampProfile("gentle_ramp_v1");
const brisk = rampProfile("brisk_ramp_v1");

function manifestWithDifficultyBand(): ReturnType<typeof parseRunnerRuntimeManifest> {
  const document = runnerManifestFixture();
  const segments = document.segments as { chunks: Array<Record<string, unknown>> };
  const base = segments.chunks[0];
  segments.chunks = [
    base,
    ...[5, 6, 7, 8].map((difficulty) => ({
      ...base,
      segment_id: `difficulty_${difficulty}`,
      difficulty,
    })),
  ];
  return parseRunnerRuntimeManifest(document);
}

describe("difficultyCeiling", () => {
  test("starts at 1 and climbs one step per configured span", () => {
    expect(difficultyCeiling(gentle, 0)).toBe(1);
    expect(difficultyCeiling(gentle, gentle.columnsPerCeilingStep - 1)).toBe(1);
    expect(difficultyCeiling(gentle, gentle.columnsPerCeilingStep)).toBe(2);
    expect(difficultyCeiling(gentle, gentle.columnsPerCeilingStep * 3)).toBe(4);
  });

  test("never leaves the authored 1..10 vocabulary", () => {
    expect(difficultyCeiling(gentle, 1e9)).toBe(10);
    expect(difficultyCeiling(gentle, -50)).toBe(1);
  });
});

describe("speedMultiplier", () => {
  test("ramps gently from 1 to the profile's cap and holds there", () => {
    expect(speedMultiplier(gentle, 0)).toBe(1);
    const half = speedMultiplier(gentle, gentle.speedRampColumns / 2);
    expect(half).toBeCloseTo(1 + gentle.maxSpeedBonus / 2, 10);
    expect(speedMultiplier(gentle, gentle.speedRampColumns)).toBeCloseTo(
      1 + gentle.maxSpeedBonus,
      10,
    );
    expect(speedMultiplier(gentle, 1e9)).toBeCloseTo(1 + gentle.maxSpeedBonus, 10);
  });

  test("is monotonic, so ramped speed never drops", () => {
    let previous = 0;
    for (let distance = 0; distance <= gentle.speedRampColumns * 2; distance += 25) {
      const value = speedMultiplier(gentle, distance);
      expect(value).toBeGreaterThanOrEqual(previous);
      previous = value;
    }
  });

  test("the brisk profile earns the same proved cap during an opening run", () => {
    expect(brisk.maxSpeedBonus).toBe(gentle.maxSpeedBonus);
    expect(brisk.speedRampColumns).toBe(720);
    expect(brisk.speedRampColumns).toBeLessThan(gentle.speedRampColumns);
    expect(speedMultiplier(brisk, 360)).toBeCloseTo(1.25, 10);
    expect(speedMultiplier(brisk, 720)).toBeCloseTo(1.5, 10);
  });
});

describe("createDifficultySystem", () => {
  test("publishes the ramp for the distance the avatar last wrote", () => {
    const world = createRunnerWorld(manifestWithDifficultyBand(), 1);
    const system = createDifficultySystem();
    world.avatar.distanceColumns = gentle.columnsPerCeilingStep * 2;
    system.update(world, { dt: 1 / 60, now: 1 / 60, frame: 1 });
    expect(world.difficulty.ceiling).toBe(3);
    expect(world.difficulty.speedMultiplier).toBeGreaterThan(1);
  });

  test("clamps the long-run selection band to the package's authored maximum", () => {
    const world = createRunnerWorld(manifestWithDifficultyBand(), 1);
    const system = createDifficultySystem();
    world.avatar.distanceColumns = 1e9;
    system.update(world, { dt: 1 / 60, now: 1 / 60, frame: 1 });

    expect(world.config.maxAuthoredDifficulty).toBe(8);
    expect(world.difficulty.ceiling).toBe(8);
    expect(world.difficulty.floor).toBe(5);
  });

  test("keeps ramping speed to the published cap after selection difficulty is spent", () => {
    const world = createRunnerWorld(manifestWithDifficultyBand(), 1);
    const system = createDifficultySystem();
    world.avatar.distanceColumns = 1e9;
    system.update(world, { dt: 1 / 60, now: 1 / 60, frame: 1 });

    expect(world.difficulty.speedMultiplier).toBe(
      world.config.arithmetic.maxSpeedMultiplier,
    );
    expect(world.difficulty.speedColumnsPerSecond).toBe(
      world.config.arithmetic.baseSpeedColumnsPerSecond *
        world.config.arithmetic.maxSpeedMultiplier,
    );
  });
});
