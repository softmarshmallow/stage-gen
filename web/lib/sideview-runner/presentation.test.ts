import { describe, expect, test } from "bun:test";
import {
  collectiblePresentation,
  hazardCueAlpha,
  hazardVisualScale,
  presentationPhase,
} from "./presentation";

describe("collectible presentation", () => {
  test("a single-image pickup visibly flips, bobs, and glints over time", () => {
    const phase = presentationPhase("6:2:sunleaf_token");
    const first = collectiblePresentation(0, phase);
    const later = collectiblePresentation(173, phase);
    expect(later).not.toEqual(first);
    for (const sample of [first, later]) {
      expect(sample.scaleXMultiplier).toBeGreaterThanOrEqual(0.16);
      expect(sample.scaleXMultiplier).toBeLessThanOrEqual(1);
      expect(Math.abs(sample.bobRows)).toBeLessThanOrEqual(0.1);
      expect(sample.haloAlpha).toBeGreaterThan(0);
    }
  });

  test("different instances do not animate in lockstep", () => {
    expect(presentationPhase("6:2:coin")).not.toBe(presentationPhase("7:2:coin"));
    expect(
      collectiblePresentation(400, presentationPhase("6:2:coin")),
    ).not.toEqual(collectiblePresentation(400, presentationPhase("7:2:coin")));
  });
});

describe("hazard readability", () => {
  test("keeps vertical calibration and constrains misleading horizontal spill", () => {
    expect(hazardVisualScale(0.5, 200, 48)).toEqual({ scaleX: 0.24, scaleY: 0.5 });
    expect(hazardVisualScale(0.2, 200, 48)).toEqual({ scaleX: 0.2, scaleY: 0.2 });
  });

  test("telegraphs only threats still ahead and grows with proximity", () => {
    expect(hazardCueAlpha(-0.1, 0)).toBe(0);
    expect(hazardCueAlpha(8.1, 0)).toBe(0);
    expect(hazardCueAlpha(2, 0)).toBeGreaterThan(hazardCueAlpha(7, 0));
  });
});
