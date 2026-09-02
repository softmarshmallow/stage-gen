import { describe, expect, test } from "bun:test";
import {
  MobDeckLaneNode,
  MobNavigationPolicy,
  MobTerrainLaneNode,
} from "./mob-navigation";

function node(heights: readonly number[], spawnColumn: number) {
  const tilePixels = 64;
  return new MobTerrainLaneNode({
    spawnColumn,
    spawnX: spawnColumn * tilePixels + tilePixels / 2,
    tilePixels,
    worldWidthPx: heights.length * tilePixels,
    baselineY: 720,
    renderedHalfWidth: 24,
    heightAtColumn: (column) => heights[column] ?? 0,
    policy: new MobNavigationPolicy(tilePixels),
  });
}

describe("mob terrain-lane navigation node", () => {
  test("keeps patrol, pursuit territory, and connected terrain as separate boundaries", () => {
    const navigation = node([2, 2, 2, 2, 2, 2, 2, 2, 2, 2], 2);
    expect(navigation.patrolMinX).toBe(64);
    expect(navigation.patrolMaxX).toBe(256);
    expect(navigation.laneMinX).toBe(24);
    expect(navigation.laneMaxX).toBe(616);
    expect(navigation.pursuitMinX).toBe(24);
    expect(navigation.pursuitMaxX).toBe(544);
    expect(navigation.walk(160, 560, "pursuit").x).toBe(544);
  });

  test("a pit or step terminates the connected lane", () => {
    const navigation = node([2, 2, 2, 0, 2, 3, 3], 1);
    expect(navigation.laneMinX).toBe(24);
    expect(navigation.laneMaxX).toBe(191);
    expect(navigation.containsWorldX(190)).toBeTrue();
    expect(navigation.containsWorldX(192)).toBeFalse();
    expect(navigation.walk(96, 224, "pursuit").blocked).toBeTrue();
  });

  test("ladder metadata cannot affect a terrain-only node", () => {
    const uninterrupted = node([2, 2, 2, 2, 2], 2);
    expect(uninterrupted.containsWorldX(32)).toBeTrue();
    expect(uninterrupted.containsWorldX(288)).toBeTrue();
    expect(uninterrupted.walk(96, 224, "pursuit").blocked).toBeFalse();
  });

  test("adopts a disconnected knockback landing shelf and can restore authored home", () => {
    const navigation = node([2, 2, 0, 0, 0], 1);
    expect(navigation.homeX).toBe(96);
    expect(navigation.rehomeAfterForcedDisplacement(100)).toBeFalse();

    expect(navigation.rehomeAfterForcedDisplacement(224)).toBeTrue();
    expect(navigation.homeX).toBe(224);
    expect(navigation.laneMinX).toBe(128);
    expect(navigation.laneMaxX).toBe(296);
    expect(navigation.containsPursuitX(224)).toBeTrue();
    expect(navigation.walk(224, 160, "patrol").blocked).toBeFalse();

    navigation.restoreHome(1, 96);
    expect(navigation.homeX).toBe(96);
    expect(navigation.laneMaxX).toBe(127);
  });

  test("walks an externally displaced actor inward without snapping it to home bounds", () => {
    const navigation = node(Array.from({ length: 20 }, () => 2), 2);
    expect(navigation.patrolMaxX).toBe(256);

    const inward = navigation.walk(400, 395, "patrol");
    expect(inward).toEqual({ x: 395, blocked: false, blockedColumn: null });

    const outward = navigation.walk(400, 405, "patrol");
    expect(outward).toEqual({ x: 400, blocked: true, blockedColumn: null });
  });
});

describe("mob deck-lane navigation node", () => {
  const tilePixels = 64;

  // A six-tile deck starting at column four, two tiles over a baseline of 720.
  function deck(overrides: Partial<{ spawnX: number }> = {}) {
    return new MobDeckLaneNode({
      deckId: "deck-lower",
      spawnX: overrides.spawnX ?? 288,
      deckLeftX: 256,
      deckRightX: 640,
      deckSurfaceY: 592,
      renderedHalfWidth: 24,
      policy: new MobNavigationPolicy(tilePixels),
    });
  }

  test("the deck's edges are the lane, and its top is the whole height field", () => {
    const navigation = deck();
    expect(navigation.laneMinX).toBe(280);
    expect(navigation.laneMaxX).toBe(616);
    // The patrol radius is 96, so it reaches past the left edge and is held there.
    expect(navigation.patrolMinX).toBe(280);
    expect(navigation.patrolMaxX).toBe(384);
    expect(navigation.surfaceYAt(280)).toBe(592);
    expect(navigation.surfaceYAt(616)).toBe(592);
  });

  test("a spawn asked for beyond the deck is placed on it instead", () => {
    const navigation = deck({ spawnX: 4_096 });
    expect(navigation.homeX).toBe(616);
    expect(navigation.containsPatrolX(616)).toBeTrue();
  });

  test("knockback stops at the edge rather than carrying the body off the deck", () => {
    // The one rule that differs from terrain. A terrain mob shoved over a drop lands on the
    // shelf below and adopts it; a deck mob shoved off the end would land on nothing, so the
    // edge holds against the blow and re-homing never happens.
    const navigation = deck();
    expect(navigation.walk(600, 900, "world")).toEqual({
      x: 616,
      blocked: true,
      blockedColumn: null,
    });
    expect(navigation.rehomeAfterForcedDisplacement(900)).toBeFalse();
    expect(navigation.homeX).toBe(288);
  });

  test("patrol turns at the deck edge when home sits against it", () => {
    const navigation = deck({ spawnX: 600 });
    expect(navigation.patrolMaxX).toBe(616);
    expect(navigation.walk(610, 700, "patrol").blocked).toBeTrue();
    expect(navigation.walk(610, 560, "patrol").blocked).toBeFalse();
  });

  test("a deck narrower than the body still has its middle to stand on", () => {
    const narrow = new MobDeckLaneNode({
      deckId: "deck-perch",
      spawnX: 300,
      deckLeftX: 288,
      deckRightX: 320,
      deckSurfaceY: 592,
      renderedHalfWidth: 24,
      policy: new MobNavigationPolicy(tilePixels),
    });
    expect(narrow.laneMinX).toBe(304);
    expect(narrow.laneMaxX).toBe(304);
    expect(narrow.homeX).toBe(304);
    expect(narrow.walk(304, 400, "patrol")).toEqual({
      x: 304,
      blocked: true,
      blockedColumn: null,
    });
  });

  test("a deck with no width is refused", () => {
    expect(
      () =>
        new MobDeckLaneNode({
          deckId: "deck-none",
          spawnX: 300,
          deckLeftX: 320,
          deckRightX: 320,
          deckSurfaceY: 592,
          renderedHalfWidth: 24,
          policy: new MobNavigationPolicy(tilePixels),
        }),
    ).toThrow("positive width");
  });
});
