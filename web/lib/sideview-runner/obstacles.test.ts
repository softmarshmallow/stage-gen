import { describe, expect, test } from "bun:test";
import {
  avatarBox,
  boxesOverlap,
  createObstaclesSystem,
  hazardBox,
  pickupBox,
  pickupKey,
} from "./obstacles";
import { parseRunnerRuntimeManifest } from "./contract";
import { runnerManifestFixture } from "./fixture";
import { createRunnerWorld, type RunnerWorld } from "./world";

const STEP = { dt: 1 / 60, now: 1 / 60, frame: 1 } as const;
const manifest = parseRunnerRuntimeManifest(runnerManifestFixture());

// The fixture's single chunk places a hazard on column 6 and a pickup at
// (column 6, row 2) of every streamed repeat; the walk surface is row 5.
function worldAt(distanceColumns: number): RunnerWorld {
  const world = createRunnerWorld(manifest, 1);
  world.avatar.distanceColumns = distanceColumns;
  return world;
}

describe("boxesOverlap", () => {
  test("overlaps interiors and not edges", () => {
    const box = { left: 0, top: 0, right: 1, bottom: 1 };
    expect(boxesOverlap(box, { left: 0.5, top: 0.5, right: 1.5, bottom: 1.5 })).toBe(true);
    expect(boxesOverlap(box, { left: 1, top: 0, right: 2, bottom: 1 })).toBe(false);
    expect(boxesOverlap(box, { left: 0, top: 1, right: 1, bottom: 2 })).toBe(false);
  });
});

describe("box shapes", () => {
  test("the avatar box hangs its height above the feet", () => {
    const box = avatarBox(
      { distanceColumns: 10, y: 5, vy: 0, grounded: true, motion: "run", deathCause: null },
      2.4,
    );
    expect(box.bottom).toBe(5);
    expect(box.top).toBeCloseTo(2.6, 10);
    expect(box.right - box.left).toBeCloseTo(0.6, 10);
  });

  test("a hazard stands on its surface, inset inside its column", () => {
    const box = hazardBox(6, 5, 2.4);
    expect(box.bottom).toBe(5);
    expect(box.top).toBeCloseTo(2.6, 10);
    expect(box.left).toBeGreaterThan(6);
    expect(box.right).toBeLessThan(7);
  });

  test("a pickup occupies the middle of its cell", () => {
    const box = pickupBox(6, 2);
    expect(box.left).toBeCloseTo(6.2, 10);
    expect(box.bottom).toBeCloseTo(2.8, 10);
  });
});

describe("createObstaclesSystem", () => {
  const system = createObstaclesSystem();

  test("reports hazard contact when the avatar runs into the placement", () => {
    const world = worldAt(6.5);
    system.update(world, STEP);
    expect(world.obstacles.hazardContact).toBe(true);
  });

  test("reports no contact a column away", () => {
    const world = worldAt(4.5);
    system.update(world, STEP);
    expect(world.obstacles.hazardContact).toBe(false);
  });

  test("collects a pickup once and never again", () => {
    // The fixture's token floats at head height (row 2 over walk row 5), so
    // the grounded avatar's 2.4-tile body brushes its cell in passing.
    const world = worldAt(6.5);
    system.update(world, STEP);
    expect(world.obstacles.collectedThisFrame).toHaveLength(1);
    const key = pickupKey(world.obstacles.collectedThisFrame[0]);
    expect(world.obstacles.collected.has(key)).toBe(true);
    system.update(world, STEP);
    expect(world.obstacles.collectedThisFrame).toHaveLength(0);
    expect(world.obstacles.collected.has(key)).toBe(true);
  });

  test("an out-of-reach pickup stays uncollected", () => {
    const world = worldAt(6.5);
    // Ducked under a floor two rows lower, the token would sit above the body;
    // emulate by dropping the avatar's feet below the walk row.
    world.avatar.y = 7.5;
    system.update(world, STEP);
    expect(world.obstacles.collectedThisFrame).toHaveLength(0);
    expect(world.obstacles.collected.size).toBe(0);
  });

  test("a dead run collides with nothing", () => {
    const world = worldAt(6.5);
    world.run.phase = "dead";
    system.update(world, STEP);
    expect(world.obstacles.hazardContact).toBe(false);
  });
});
