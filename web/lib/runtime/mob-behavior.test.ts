import { describe, expect, test } from "bun:test";
import {
  constrainMobStrikeToAttackLevel,
  mobLocomotionAnimationNeedsRestart,
} from "./mob-behavior";

describe("mob vertical combat intent", () => {
  test("starts a strike only inside the one-level band", () => {
    const base = {
      requestedIntent: "strike" as const,
      mobFootY: 600,
      tilePixels: 64,
    };
    expect(constrainMobStrikeToAttackLevel({ ...base, playerFootY: 536 })).toBe("strike");
    expect(constrainMobStrikeToAttackLevel({ ...base, playerFootY: 535 })).toBe("chase");
    expect(constrainMobStrikeToAttackLevel({ ...base, playerFootY: null })).toBe("chase");
    expect(
      constrainMobStrikeToAttackLevel({
        ...base,
        requestedIntent: "flee",
        playerFootY: 0,
      }),
    ).toBe("flee");
  });
});

describe("mob locomotion presentation", () => {
  test("recovers after attack completion without interrupting active finite states", () => {
    const base = {
      idleAnimationKey: "petal_puff_idle",
      currentAnimationKey: "petal_puff_attack_anim",
      isPlaying: false,
    } as const;
    expect(mobLocomotionAnimationNeedsRestart({ ...base, state: "chase" })).toBeTrue();
    expect(mobLocomotionAnimationNeedsRestart({ ...base, state: "wander" })).toBeTrue();
    expect(mobLocomotionAnimationNeedsRestart({ ...base, state: "windup" })).toBeFalse();
    expect(
      mobLocomotionAnimationNeedsRestart({
        ...base,
        state: "wander",
        currentAnimationKey: "petal_puff_idle",
        isPlaying: true,
      }),
    ).toBeFalse();
    expect(
      mobLocomotionAnimationNeedsRestart({
        ...base,
        state: "wander",
        currentAnimationKey: "petal_puff_idle",
      }),
    ).toBeTrue();
  });
});
