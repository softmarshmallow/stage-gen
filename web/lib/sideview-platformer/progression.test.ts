import { describe, expect, test } from "bun:test";
import {
  experienceCurveRule,
  experienceForNextLevel,
  experienceForRank,
  grantExperience,
  initialProgression,
  maximumHealthForLevel,
  type ProgressionPolicy,
} from "./progression";

const POLICY: ProgressionPolicy = Object.freeze({
  enabled: true,
  maximumLevel: 20,
  curve: "gentle_rpg_v1",
  growth: "balanced_novice_v1",
  baseHealth: 10,
});

describe("experience curve", () => {
  test("every level costs more than the one before it", () => {
    // A flat cost makes the twentieth level as cheap as the second, which empties the whole ladder
    // of meaning by the end of a run.
    for (const curve of ["gentle_rpg_v1", "steady_rpg_v1", "brisk_rpg_v1"] as const) {
      for (let level = 1; level < 20; level += 1) {
        expect(experienceForNextLevel(level + 1, curve)).toBeGreaterThan(
          experienceForNextLevel(level, curve),
        );
      }
    }
  });

  test("cost is geometric, which makes level logarithmic in total experience", () => {
    const rule = experienceCurveRule("gentle_rpg_v1");
    expect(rule.growth).toBeGreaterThan(1);
    const first = experienceForNextLevel(1, "gentle_rpg_v1");
    const fifth = experienceForNextLevel(5, "gentle_rpg_v1");
    expect(fifth).toBe(Math.round(first * rule.growth ** 4));
  });

  test("brisk levels faster than gentle, and steady slower", () => {
    expect(experienceForNextLevel(6, "brisk_rpg_v1")).toBeLessThan(
      experienceForNextLevel(6, "gentle_rpg_v1"),
    );
    expect(experienceForNextLevel(6, "steady_rpg_v1")).toBeGreaterThan(
      experienceForNextLevel(6, "gentle_rpg_v1"),
    );
  });

  test("rejects a level below one and an unknown curve", () => {
    expect(() => experienceForNextLevel(0, "gentle_rpg_v1")).toThrow(RangeError);
    expect(() =>
      experienceCurveRule("nonexistent_v1" as "gentle_rpg_v1"),
    ).toThrow(/unknown experience curve/);
  });
});

describe("kill awards", () => {
  test("rises with the rank the package already publishes", () => {
    expect(experienceForRank("boss")).toBeGreaterThan(experienceForRank("elite"));
    expect(experienceForRank("elite")).toBeGreaterThan(experienceForRank("uncommon"));
    expect(experienceForRank("uncommon")).toBeGreaterThan(experienceForRank("common"));
  });

  test("an unrecognised rank is worth the common award, not nothing", () => {
    // An unknown rank is a catalog the runtime has not caught up with, not a worthless creature.
    expect(experienceForRank("swarm_tier_9")).toBe(experienceForRank("common"));
  });
});

describe("stat growth", () => {
  test("a level always buys at least one point, scaled to the authored pool", () => {
    expect(maximumHealthForLevel(10, 1)).toBe(10);
    expect(maximumHealthForLevel(10, 2)).toBe(12);
    expect(maximumHealthForLevel(10, 5)).toBe(18);
    // A tiny authored pool still grows rather than rounding to a standstill.
    expect(maximumHealthForLevel(2, 3)).toBe(4);
  });

  test("rejects invalid pools, levels, and growth names", () => {
    expect(() => maximumHealthForLevel(0, 1)).toThrow(RangeError);
    expect(() => maximumHealthForLevel(10, 0)).toThrow(RangeError);
    expect(() =>
      maximumHealthForLevel(10, 1, "unknown_v1" as "balanced_novice_v1"),
    ).toThrow(/unknown stat growth/);
  });
});

describe("granting experience", () => {
  test("starts at level one with the authored pool and a real next-level cost", () => {
    const state = initialProgression(POLICY);
    expect(state).toEqual({
      level: 1,
      experienceIntoLevel: 0,
      experienceForNext: experienceForNextLevel(1, "gentle_rpg_v1"),
      totalExperience: 0,
      maximumHealth: 10,
    });
  });

  test("banks points below the threshold without levelling", () => {
    const award = grantExperience(initialProgression(POLICY), 6, POLICY);
    expect(award).toMatchObject({ awarded: 6, levelsGained: 0 });
    expect(award.state.level).toBe(1);
    expect(award.state.experienceIntoLevel).toBe(6);
    expect(award.state.totalExperience).toBe(6);
  });

  test("settles several levels from one award and keeps the remainder", () => {
    // A boss worth three levels should read as three levels, not one plus a remainder the next
    // kill quietly collects.
    const cost = (level: number) => experienceForNextLevel(level, POLICY.curve);
    const award = grantExperience(
      initialProgression(POLICY),
      cost(1) + cost(2) + 5,
      POLICY,
    );
    expect(award.levelsGained).toBe(2);
    expect(award.state.level).toBe(3);
    expect(award.state.experienceIntoLevel).toBe(5);
    expect(award.state.maximumHealth).toBe(maximumHealthForLevel(10, 3));
  });

  test("stops levelling at the authored maximum but keeps counting the total", () => {
    const capped: ProgressionPolicy = { ...POLICY, maximumLevel: 2 };
    const first = grantExperience(
      initialProgression(capped),
      experienceForNextLevel(1, capped.curve) * 40,
      capped,
    );
    expect(first.state.level).toBe(2);
    expect(first.state.experienceForNext).toBeNull();
    const second = grantExperience(first.state, 25, capped);
    expect(second.awarded).toBe(25);
    expect(second.state.level).toBe(2);
    // The display must never lie about what was earned, even with nothing left to buy.
    expect(second.state.totalExperience).toBe(first.state.totalExperience + 25);
  });

  test("a disabled policy awards nothing and leaves the state identical", () => {
    const off: ProgressionPolicy = { ...POLICY, enabled: false };
    const state = initialProgression(off);
    const award = grantExperience(state, 500, off);
    expect(award.awarded).toBe(0);
    expect(award.levelsGained).toBe(0);
    expect(award.state).toBe(state);
  });

  test("ignores invalid and non-positive awards", () => {
    const state = initialProgression(POLICY);
    for (const amount of [0, -10, Number.NaN, Number.POSITIVE_INFINITY, 0.4]) {
      expect(grantExperience(state, amount, POLICY).awarded).toBe(0);
    }
  });
});
