import { describe, expect, test } from "bun:test";
import { GAMEPLAY_AUTOMATION_FRAME_MS } from "./automation";
import {
  MOB_DEATH_FADE_MS,
  MOB_KNOCKBACK_MS,
  sampleFixedMobHit,
  type FixedMobHitMotion,
} from "./fixed-motion";

describe("fixed-clock mob hit motion", () => {
  test("has a stable killed-mob position at transcript frame 40", () => {
    // The gameplay timeline starts its attack on frame 31; the fixed attack
    // window hits on frame 34. Frame 40 is six controlled ticks later.
    const hitFrame = 34;
    const motion: FixedMobHitMotion = {
      startedMs: hitFrame * GAMEPLAY_AUTOMATION_FRAME_MS,
      startX: 128.1,
      targetX: 160.1,
      died: true,
    };
    const frame40Ms = 40 * GAMEPLAY_AUTOMATION_FRAME_MS;
    const first = sampleFixedMobHit(motion, frame40Ms);
    const second = sampleFixedMobHit(motion, frame40Ms);

    expect(second).toEqual(first);
    expect(first.x).toBeCloseTo(160.07595792637113, 12);
    expect(first.alpha).toBeCloseTo(2 / 7, 12);
    expect(first.hidden).toBeFalse();
  });

  test("completes knockback and death only from supplied simulation time", () => {
    const motion: FixedMobHitMotion = {
      startedMs: 1_000,
      startX: 10,
      targetX: 90,
      died: true,
    };
    expect(sampleFixedMobHit(motion, 1_000)).toEqual({
      x: 10,
      alpha: 1,
      hidden: false,
      complete: false,
    });
    expect(sampleFixedMobHit(motion, 1_000 + MOB_KNOCKBACK_MS).x).toBe(90);
    expect(sampleFixedMobHit(motion, 1_000 + MOB_DEATH_FADE_MS)).toEqual({
      x: 90,
      alpha: 0,
      hidden: true,
      complete: true,
    });
  });

});
