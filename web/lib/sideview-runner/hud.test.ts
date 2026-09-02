import { describe, expect, test } from "bun:test";
import {
  deathPanelRect,
  formatRunDistance,
  formatScore,
  hudReadoutRect,
  runDistanceMeters,
  vitalsBarRect,
} from "./hud";
import { RUNNER_VIEW_HEIGHT, RUNNER_VIEW_WIDTH } from "./world";

describe("run distance", () => {
  test("converts columns to whole meters through the tile size", () => {
    // 64px tiles: 100 screen pixels per meter makes one column 0.64m.
    expect(runDistanceMeters(0, 64)).toBe(0);
    expect(runDistanceMeters(10, 64)).toBe(6);
    expect(runDistanceMeters(156.25, 64)).toBe(100);
    expect(formatRunDistance(156.25, 64)).toBe("100 m");
  });

  test("never reports negative distance", () => {
    expect(runDistanceMeters(-5, 64)).toBe(0);
  });
});

describe("formatScore", () => {
  test("floors and clamps the score readout", () => {
    expect(formatScore(30)).toBe("✦ 30");
    expect(formatScore(30.9)).toBe("✦ 30");
    expect(formatScore(-2)).toBe("✦ 0");
  });
});

describe("hud layout", () => {
  test("the readout band stays inside the canvas", () => {
    const rect = hudReadoutRect();
    expect(rect.x).toBeGreaterThan(0);
    expect(rect.x + rect.width).toBeLessThanOrEqual(RUNNER_VIEW_WIDTH);
  });

  test("the death panel is centered", () => {
    const rect = deathPanelRect();
    expect(rect.x + rect.width / 2).toBeCloseTo(RUNNER_VIEW_WIDTH / 2, 6);
    expect(rect.y + rect.height / 2).toBeCloseTo(RUNNER_VIEW_HEIGHT / 2, 6);
  });

  test("the death panel shrinks with a small canvas instead of overflowing", () => {
    const rect = deathPanelRect(400, 300);
    expect(rect.width).toBeLessThanOrEqual(400 * 0.6);
    expect(rect.height).toBeLessThanOrEqual(300 * 0.4);
  });
});

describe("vitalsBarRect", () => {
  test("sits above the readout band, inside the same left margin", () => {
    const readout = hudReadoutRect();
    const bar = vitalsBarRect();
    expect(bar.x).toBe(readout.x);
    expect(bar.y).toBeLessThan(readout.y);
    expect(bar.width).toBeLessThanOrEqual(readout.width);
  });

  test("stays inside a narrow canvas", () => {
    const bar = vitalsBarRect(320);
    expect(bar.x + bar.width).toBeLessThanOrEqual(320);
  });
});
