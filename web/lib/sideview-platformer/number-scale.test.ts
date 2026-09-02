import { describe, expect, test } from "bun:test";
import {
  DEFAULT_NUMBER_SCALE,
  NUMBER_SCALES,
  numberScaleProfile,
  parseNumberScale,
  scaleMobHealth,
  scaleOutgoingDamage,
} from "./number-scale";

describe("the unit scale is the identity every earlier package played at", () => {
  test("damage and health pass through exactly", () => {
    const unit = numberScaleProfile("unit_v1");
    for (const seed of [0, 1, 7, 0xffff_ffff]) {
      expect(scaleOutgoingDamage(1, unit, seed)).toBe(1);
      expect(scaleOutgoingDamage(2, unit, seed)).toBe(2);
    }
    expect(scaleMobHealth(2, unit)).toBe(2);
    expect(scaleMobHealth(12, unit)).toBe(12);
  });

  test("it is the default for a package that names nothing", () => {
    expect(numberScaleProfile(null)).toBe(numberScaleProfile(DEFAULT_NUMBER_SCALE));
    expect(numberScaleProfile(undefined).numberScale).toBe("unit_v1");
  });
});

describe("the arcade scale is the same fight in hundreds", () => {
  const arcade = numberScaleProfile("arcade_v1");

  test("health scales exactly, so the ladder between ranks is preserved", () => {
    expect(scaleMobHealth(2, arcade)).toBe(200);
    expect(scaleMobHealth(3, arcade)).toBe(300);
    expect(scaleMobHealth(12, arcade)).toBe(1200);
  });

  test("damage lands inside the variance band around the scaled amount", () => {
    let low = Number.POSITIVE_INFINITY;
    let high = 0;
    for (let seed = 0; seed < 500; seed += 1) {
      const amount = scaleOutgoingDamage(1, arcade, seed);
      expect(amount).toBeGreaterThanOrEqual(Math.round(100 * (1 - arcade.varianceRatio)));
      expect(amount).toBeLessThanOrEqual(Math.round(100 * (1 + arcade.varianceRatio)));
      low = Math.min(low, amount);
      high = Math.max(high, amount);
    }
    expect(high - low).toBeGreaterThan(10);
  });

  test("the same blow seed rolls the same variance", () => {
    expect(scaleOutgoingDamage(1, arcade, 12_345)).toBe(scaleOutgoingDamage(1, arcade, 12_345));
  });

  test("a scaled blow never rounds away to nothing", () => {
    const tiny = { ...arcade, factor: 0.001 };
    expect(scaleOutgoingDamage(1, tiny, 3)).toBe(1);
  });

  test("the expected damage per blow is a whole creature per few blows, as at unit scale", () => {
    // Two hit points at unit scale die to two blows; two hundred at arcade scale die to two
    // blows of about a hundred. The scale changes the digits, not the number of swings.
    let total = 0;
    for (let seed = 0; seed < 200; seed += 1) total += scaleOutgoingDamage(1, arcade, seed);
    expect(total / 200).toBeGreaterThan(90);
    expect(total / 200).toBeLessThan(110);
  });
});

describe("the vocabulary", () => {
  test("parsing accepts exactly the published names", () => {
    for (const scale of NUMBER_SCALES) expect(parseNumberScale(scale)).toBe(scale);
    expect(parseNumberScale("huge_v1")).toBeNull();
    expect(parseNumberScale(100)).toBeNull();
  });

  test("invalid inputs are refused or passed through as the caller's problem", () => {
    const arcade = numberScaleProfile("arcade_v1");
    expect(scaleOutgoingDamage(0, arcade, 1)).toBe(0);
    expect(scaleOutgoingDamage(Number.NaN, arcade, 1)).toBeNaN();
    expect(() => scaleMobHealth(0, arcade)).toThrow("positive integer");
    expect(() => scaleMobHealth(1.5, arcade)).toThrow("positive integer");
  });

  test("every profile is frozen", () => {
    for (const scale of NUMBER_SCALES) expect(Object.isFrozen(numberScaleProfile(scale))).toBe(true);
  });
});
