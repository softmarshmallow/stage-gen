import { describe, expect, test } from "bun:test";

import {
  BOSS_BOB_PERIOD_SECONDS,
  BOSS_BOB_ROWS,
  bossBobRows,
  offsetScreenX,
} from "./encounter-arithmetic";
import { parseRunnerRuntimeManifest } from "./contract";
import { runnerManifestFixture } from "./fixture";
import { createRunnerWorld } from "./world";

const manifest = parseRunnerRuntimeManifest(runnerManifestFixture());

describe("the boss's own motion", () => {
  test("bobs within its published amplitude, whatever the clock", () => {
    for (let ms = 0; ms < 20_000; ms += 37) {
      expect(Math.abs(bossBobRows(ms))).toBeLessThanOrEqual(BOSS_BOB_ROWS + 1e-9);
    }
  });

  test("returns to where it started after one period", () => {
    const period = BOSS_BOB_PERIOD_SECONDS * 1000;

    expect(bossBobRows(period)).toBeCloseTo(bossBobRows(0), 9);
    expect(bossBobRows(period / 2)).toBeCloseTo(-bossBobRows(0), 9);
  });

  test("is a pure function of the simulation clock, so a replay draws the same frames", () => {
    expect(bossBobRows(1234)).toBe(bossBobRows(1234));
  });
});

describe("placing a thing measured in columns ahead of the avatar", () => {
  test("zero columns ahead is exactly the avatar's own screen anchor", () => {
    const { avatarScreenX, tilePx } = createRunnerWorld(manifest, 1).config;

    expect(offsetScreenX(0, avatarScreenX, tilePx)).toBe(avatarScreenX);
  });

  test("a column ahead is one tile to the right, and behind is to the left", () => {
    const { avatarScreenX, tilePx } = createRunnerWorld(manifest, 1).config;

    expect(offsetScreenX(1, avatarScreenX, tilePx)).toBe(avatarScreenX + tilePx);
    expect(offsetScreenX(-2, avatarScreenX, tilePx)).toBe(avatarScreenX - 2 * tilePx);
  });

  test("does not move with the run: the offset is already avatar-relative", () => {
    const world = createRunnerWorld(manifest, 1);
    const { avatarScreenX, tilePx } = world.config;
    const before = offsetScreenX(10, avatarScreenX, tilePx);
    world.avatar.distanceColumns += 500;

    expect(offsetScreenX(10, avatarScreenX, tilePx)).toBe(before);
  });
});
