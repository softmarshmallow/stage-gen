import { describe, expect, test } from "bun:test";
import {
  DEATH_STRIP_DURATION_MS,
  mobDeathPresentationPlan,
  playerDamagePresentationState,
} from "./death-presentation";

describe("death presentation", () => {
  test("selects the authored player death strip over the hurt fallback", () => {
    expect(
      playerDamagePresentationState({
        defeated: true,
        deathAvailable: true,
        hurtAvailable: true,
        hurtMotionActive: true,
        airborne: false,
      }),
    ).toBe("death");
  });

  test("keeps defeat playable when terminal artwork is unavailable", () => {
    expect(
      playerDamagePresentationState({
        defeated: true,
        deathAvailable: false,
        hurtAvailable: true,
        hurtMotionActive: false,
        airborne: false,
      }),
    ).toBe("hurt");
    expect(
      playerDamagePresentationState({
        defeated: true,
        deathAvailable: false,
        hurtAvailable: false,
        hurtMotionActive: false,
        airborne: true,
      }),
    ).toBe("jump");
  });

  test("delays the normal mob fade until the four-frame strip completes", () => {
    expect(
      mobDeathPresentationPlan({
        deathAnimationAvailable: true,
        fixedStepMotion: false,
      }),
    ).toEqual({
      playAnimation: true,
      fadeDelayMs: DEATH_STRIP_DURATION_MS,
    });
  });

  test("preserves immediate legacy and fixed-step death fading", () => {
    expect(
      mobDeathPresentationPlan({
        deathAnimationAvailable: false,
        fixedStepMotion: false,
      }),
    ).toEqual({ playAnimation: false, fadeDelayMs: 0 });
    expect(
      mobDeathPresentationPlan({
        deathAnimationAvailable: true,
        fixedStepMotion: true,
      }),
    ).toEqual({ playAnimation: false, fadeDelayMs: 0 });
  });
});
