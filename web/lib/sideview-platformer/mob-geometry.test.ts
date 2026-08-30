import { describe, expect, test } from "bun:test";
import {
  mobFullAlphaBounds,
  mobHitFacing,
  mobRenderEnvelope,
  mobWorldLane,
} from "./mob-geometry";

describe("mob rendered geometry", () => {
  test("uses every idle and hurt alpha crop instead of frame zero", () => {
    const envelope = mobRenderEnvelope({
      idleFrames: [
        { w: 40, h: 80 },
        { w: 92, h: 76 },
      ],
      hurtFrames: [{ w: 120, h: 100 }],
      targetFrameZeroHeight: 160,
    });
    expect(envelope).toEqual({ scale: 2, halfWidth: 120, height: 200 });
    expect(mobFullAlphaBounds(120, 300, envelope)).toEqual({
      left: 0,
      right: 240,
      top: 100,
      bottom: 300,
    });
  });

  test("clamps spawn, wander, and knockback-safe centres by rendered half-width", () => {
    expect(
      mobWorldLane({
        candidateSpawnX: 32,
        wanderExtent: 100,
        worldWidth: 1280,
        renderedHalfWidth: 96,
      }),
    ).toEqual({ spawnX: 96, wanderMin: 96, wanderMax: 196 });
    expect(
      mobWorldLane({
        candidateSpawnX: 1260,
        wanderExtent: 100,
        worldWidth: 1280,
        renderedHalfWidth: 96,
      }),
    ).toEqual({ spawnX: 1184, wanderMin: 1084, wanderMax: 1184 });
  });

  test("rejects an envelope that cannot fit in the world", () => {
    expect(() =>
      mobWorldLane({
        candidateSpawnX: 100,
        wanderExtent: 0,
        worldWidth: 100,
        renderedHalfWidth: 51,
      }),
    ).toThrow("wider than the world");
  });

  test("turns a struck mob toward the swing rather than away from it", () => {
    // Knockback points away from the attacker, so the two are opposites: a mob
    // shoved right was hit from its left. The sprite's unflipped art faces
    // right, which is why -1 is the flipped, left-looking pose.
    expect(mobHitFacing(1)).toBe(-1);
    expect(mobHitFacing(-1)).toBe(1);
    expect(mobHitFacing(mobHitFacing(1) as 1 | -1)).toBe(1);
  });
});
