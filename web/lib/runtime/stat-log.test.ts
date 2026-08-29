import { describe, expect, test } from "bun:test";
import {
  STAT_LOG_FADE_START_MS,
  STAT_LOG_LIFETIME_MS,
  STAT_LOG_LINE_HEIGHT_PX,
  formatExperienceLine,
  formatLevelUpLine,
  sampleStatLogEntry,
  statLogVisualStyle,
} from "./stat-log";

const MOTION = Object.freeze({
  entryId: 1,
  startedAtMs: 1_000,
  lineIndex: 0,
});

describe("stat log lines", () => {
  test("reads as a gain, with no room for a zero or a fraction", () => {
    expect(formatExperienceLine(12)).toBe("+12 XP");
    expect(formatExperienceLine(12.7)).toBe("+12 XP");
    expect(formatExperienceLine(0)).toBe("");
    expect(formatExperienceLine(-4)).toBe("");
    expect(formatExperienceLine(Number.NaN)).toBe("");
  });

  test("names the level reached rather than the levels gained", () => {
    expect(formatLevelUpLine(3)).toBe("LEVEL 3");
    expect(formatLevelUpLine(0)).toBe("");
    expect(formatLevelUpLine(1.5)).toBe("");
  });

  test("a level is louder than the experience that bought it", () => {
    const experience = statLogVisualStyle("experience");
    const levelUp = statLogVisualStyle("level_up");
    expect(levelUp.fontSizePx).toBeGreaterThan(experience.fontSizePx);
    expect(levelUp.color).not.toBe(experience.color);
  });
});

describe("stat log motion", () => {
  test("holds full opacity, then fades to nothing by its lifetime", () => {
    expect(sampleStatLogEntry(MOTION, 1_000).alpha).toBe(1);
    expect(sampleStatLogEntry(MOTION, 1_000 + STAT_LOG_FADE_START_MS).alpha).toBe(1);
    const midFade = sampleStatLogEntry(
      MOTION,
      1_000 + (STAT_LOG_FADE_START_MS + STAT_LOG_LIFETIME_MS) / 2,
    );
    expect(midFade.alpha).toBeGreaterThan(0);
    expect(midFade.alpha).toBeLessThan(1);
    expect(midFade.complete).toBe(false);
  });

  test("completes exactly at its lifetime, so nothing lingers", () => {
    const done = sampleStatLogEntry(MOTION, 1_000 + STAT_LOG_LIFETIME_MS);
    expect(done.complete).toBe(true);
    expect(done.alpha).toBe(0);
  });

  test("stacks upward by whole lines, newest nearest the anchor", () => {
    const newest = sampleStatLogEntry(MOTION, 1_000);
    const older = sampleStatLogEntry({ ...MOTION, lineIndex: 2 }, 1_000);
    expect(newest.offsetY).toBe(0);
    expect(older.offsetY).toBe(-2 * STAT_LOG_LINE_HEIGHT_PX);
  });

  test("drifts upward over its life without changing rows", () => {
    const early = sampleStatLogEntry(MOTION, 1_100);
    const late = sampleStatLogEntry(MOTION, 1_000 + STAT_LOG_FADE_START_MS);
    expect(late.offsetY).toBeLessThan(early.offsetY);
    expect(late.offsetY).toBeGreaterThan(-STAT_LOG_LINE_HEIGHT_PX);
  });

  test("a clock that ran backwards is clamped rather than trusted", () => {
    expect(sampleStatLogEntry(MOTION, 0).alpha).toBe(1);
    expect(() => sampleStatLogEntry(MOTION, Number.NaN)).toThrow(/finite/);
  });
});
