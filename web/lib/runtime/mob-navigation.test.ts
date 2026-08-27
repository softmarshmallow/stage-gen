import { describe, expect, test } from "bun:test";
import { MobNavigationPolicy, MobTerrainLaneNode } from "./mob-navigation";

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
