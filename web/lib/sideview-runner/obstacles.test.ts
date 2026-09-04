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

const BOX_CONFIG = {
  playerHeightTiles: 2.4,
  arithmetic: {
    baseSpeedColumnsPerSecond: 6,
    maxSpeedMultiplier: 1.5,
    jumpPeakMarginTiles: 0.75,
    airtimeHeadroom: 1.15,
    avatarHalfWidthColumns: 0.3,
    hazardColumnInset: 0.15,
  },
  duckedHeightFraction: 0.5,
} as const;

describe("box shapes", () => {
  test("the avatar box hangs its height above the feet", () => {
    const box = avatarBox({ distanceColumns: 10, y: 5, sliding: false }, BOX_CONFIG);
    expect(box.bottom).toBe(5);
    expect(box.top).toBeCloseTo(2.6, 10);
    expect(box.right - box.left).toBeCloseTo(0.6, 10);
  });

  test("the ducked box stands the published fraction of full height", () => {
    const box = avatarBox({ distanceColumns: 10, y: 5, sliding: true }, BOX_CONFIG);
    expect(box.bottom).toBe(5);
    expect(box.top).toBeCloseTo(5 - 2.4 * 0.5, 10);
  });

  test("a hazard stands on its surface, inset inside its column", () => {
    const box = hazardBox({ anchor: "surface", clearanceRows: null }, 6, 5, 2.4, 0.15);
    expect(box.bottom).toBe(5);
    expect(box.top).toBeCloseTo(2.6, 10);
    expect(box.left).toBeGreaterThan(6);
    expect(box.right).toBeLessThan(7);
  });

  test("an overhead hazard hangs above its declared clearance", () => {
    const box = hazardBox({ anchor: "overhead", clearanceRows: 1.6 }, 6, 5, 1.2, 0.15);
    expect(box.bottom).toBeCloseTo(3.4, 10);
    expect(box.top).toBeCloseTo(2.2, 10);
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

describe("missed pickups", () => {
  test("a passed pickup is missed exactly once", () => {
    const world = worldAt(9.0);
    const system = createObstaclesSystem();
    // The chunk's token sits at column 6; at distance 9 it is fully behind.
    system.update(world, STEP);
    expect(world.obstacles.missedThisFrame).toBe(1);
    system.update(world, STEP);
    expect(world.obstacles.missedThisFrame).toBe(0);
    expect(world.obstacles.missed.size).toBe(1);
  });

  test("a collected pickup is never counted missed", () => {
    const world = worldAt(6.5);
    const system = createObstaclesSystem();
    system.update(world, STEP);
    expect(world.obstacles.collectedThisFrame).toHaveLength(1);
    world.avatar.distanceColumns = 9.0;
    system.update(world, STEP);
    expect(world.obstacles.missedThisFrame).toBe(0);
  });

  test("a slide under an overhead hazard survives where a run dies", () => {
    const document = runnerManifestFixture();
    const segments = document.segments as { chunks: Record<string, unknown>[] };
    segments.chunks[0].hazards = [
      { prop_id: "toppled_cart", column: 6, anchor: "overhead", clearance_rows: 1.6 },
    ];
    const overhead = parseRunnerRuntimeManifest(document);
    const system = createObstaclesSystem();

    const standing = createRunnerWorld(overhead, 1);
    standing.avatar.distanceColumns = 6.5;
    system.update(standing, STEP);
    expect(standing.obstacles.hazardContact).toBe(true);

    const sliding = createRunnerWorld(overhead, 1);
    sliding.avatar.distanceColumns = 6.5;
    sliding.avatar.sliding = true;
    system.update(sliding, STEP);
    expect(sliding.obstacles.hazardContact).toBe(false);
  });
});

// --- What the obstacle field says happened -----------------------------------------------------

describe("the obstacle field reports its own occurrences", () => {
  const system = createObstaclesSystem();

  test("a pickup taken is an occurrence, once, keyed like the instance it is", () => {
    const world = worldAt(6.5);
    system.update(world, STEP);
    const collected = world.events.ofType("collected");
    expect(collected).toHaveLength(1);
    expect(collected[0].key).toBe(pickupKey(world.obstacles.collectedThisFrame[0]));
    world.events.beginFrame();
    system.update(world, STEP);
    expect(world.events.ofType("collected")).toHaveLength(0);
  });

  test("a hazard crossed is cleared once, and edge-triggered by its own set", () => {
    // The cue system used to work this out by keeping last frame's distance and
    // re-scanning every streamed hazard against it — a shadow copy of a slice
    // it does not own. It is the same per-instance set `struck` and `missed`
    // already were.
    const before = worldAt(6.5);
    system.update(before, STEP);
    expect(before.events.ofType("hazard-cleared")).toHaveLength(0);

    const world = worldAt(7.5);
    system.update(world, STEP);
    expect(world.events.ofType("hazard-cleared")).toHaveLength(1);
    expect(world.obstacles.cleared.size).toBe(1);
    world.events.beginFrame();
    world.avatar.distanceColumns = 8.5;
    system.update(world, STEP);
    expect(world.events.ofType("hazard-cleared")).toHaveLength(0);
  });

  test("a dead run clears nothing", () => {
    const world = worldAt(7.5);
    world.run.phase = "dead";
    system.update(world, STEP);
    expect(world.events.frame).toHaveLength(0);
  });
});
