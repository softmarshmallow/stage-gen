import { describe, expect, test } from "bun:test";
import { rebasedSheetScales } from "@/lib/sideview/sprite-scale";
import { preparedPlayerStateRebase } from "./prepared-player";
import type { MotionCalibration } from "@/lib/manifest/prepared-manifest";

// The multipliers the judge actually returned for the canonical actor, and the defect they
// describe: the climb strips are generated on a 1115x2850 canvas against the master states'
// 457x799, so they are drawn roughly three times too large.
const JUDGED: MotionCalibration = {
  baselineState: "idle",
  stateRebase: {
    idle: 1,
    walk: 1,
    run: 1,
    jump: 1,
    crouch: 1,
    climb_ladder: 0.33,
    climb_rope: 0.33,
    basic_attack: 1.25,
    skill_cast: 1.25,
    hurt: 1,
    death: 1,
  },
  plateSha256: "a".repeat(64),
};

describe("player motion rebase reaches the drawn sprite", () => {
  test("every published state resolves a scale composed with the baseline anchor", () => {
    const master = 0.2;
    const scales = rebasedSheetScales(master, preparedPlayerStateRebase(JUDGED));

    expect(scales.get("character_idle")).toBeCloseTo(0.2, 10);
    expect(scales.get("character_climb_ladder")).toBeCloseTo(0.2 * 0.33, 10);
    expect(scales.get("character_attack")).toBeCloseTo(0.2 * 1.25, 10);
  });

  test("the baseline is its own reference, so idle draws at the anchor exactly", () => {
    const scales = rebasedSheetScales(0.37, preparedPlayerStateRebase(JUDGED));
    expect(scales.get("character_idle")).toBe(0.37);
  });

  test("hurt and death carry real multipliers instead of inheriting the baseline blindly", () => {
    // The shipped defect: both fell back to the master sheet scale because no measurement
    // existed for them. They must now resolve from the published record like any other state.
    const scales = rebasedSheetScales(0.2, preparedPlayerStateRebase(JUDGED));
    expect(scales.has("character_hurt")).toBe(true);
    expect(scales.has("character_death")).toBe(true);
  });

  test("a climb strip drawn three times too large is corrected on screen", () => {
    const master = 0.2;
    const scales = rebasedSheetScales(master, preparedPlayerStateRebase(JUDGED));
    // Same source cell height, drawn through each state's scale.
    const climbSourceH = 2850;
    const idleSourceH = 799;
    const idleDrawn = idleSourceH * scales.get("character_idle")!;
    const climbDrawn = climbSourceH * scales.get("character_climb_ladder")!;
    // Without the rebase the climb strip would draw 2850*0.2 = 570px against idle's 160px.
    expect(climbSourceH * master).toBeGreaterThan(idleDrawn * 3);
    // With it, the two land within a pose-sized margin of each other.
    expect(climbDrawn / idleDrawn).toBeLessThan(1.5);
  });

  test("both attack poses carry their own multiplier", () => {
    // `skill_cast` was measured and published from the first run that drew it, and went unused
    // for as long as nothing played it. A throwing class plays it, and it must be corrected on
    // screen exactly as the swing is rather than inheriting the master sheet scale.
    const scales = rebasedSheetScales(0.2, preparedPlayerStateRebase(JUDGED));
    expect(scales.get("character_attack")).toBeCloseTo(0.2 * 1.25, 10);
    expect(scales.get("character_skill_cast")).toBeCloseTo(0.2 * 1.25, 10);
  });

  test("a state the controller does not draw is skipped, not rejected", () => {
    // Every state the current contract can emit is bound, so this is asserted against a name no
    // package produces. The property is still worth holding: the adapter table is the runtime's
    // view of the contract, not a claim that the contract may not grow past it, and a package
    // from a later contract must load rather than fail on a pose this build cannot play.
    const keyed = preparedPlayerStateRebase({
      ...JUDGED,
      stateRebase: { ...JUDGED.stateRebase, celebration: 1.1 },
    });
    expect(keyed.has("character_attack")).toBe(true);
    expect([...keyed.keys()].some((key) => key.includes("celebration"))).toBe(false);
  });

  test("a non-positive anchor or multiplier is refused rather than drawn", () => {
    expect(() => rebasedSheetScales(0, preparedPlayerStateRebase(JUDGED))).toThrow("positive");
    expect(() =>
      rebasedSheetScales(0.2, new Map([["character_idle", 0]])),
    ).toThrow("positive");
    expect(() => rebasedSheetScales(0.2, new Map())).toThrow("at least the baseline");
  });
});
