import { describe, expect, test } from "bun:test";
import { drawnHeightPx, spriteScale, type ScaleVocabulary, type SubjectCalibration } from "./asset-unit";

const TILE_PX = 64;

const scale: ScaleVocabulary = {
  unit: "player_height",
  playerHeightTiles: 2.4,
  minimum: 0.25,
  steps: [0.25, 0.5, 0.75, 1, 1.5, 2, 3],
  ranks: { common: 0.5, uncommon: 0.65, elite: 0.85, boss: 1.5 },
};

function calibration(heightUnits: number, extentPx: number): SubjectCalibration {
  return {
    heightUnits,
    heightUnitsSource: "authored",
    sourcePxPerUnit: extentPx / heightUnits,
    measuredSha256: "a".repeat(64),
    subjectExtentPx: extentPx,
  };
}

describe("asset unit projection", () => {
  test("a subject draws at its declared magnitude, projected exactly once", () => {
    // 2.4 units x 2.4 tiles per player height x 64 px per tile.
    const well = calibration(2.4, 900);
    expect(drawnHeightPx(well, scale, TILE_PX)).toBeCloseTo(2.4 * 2.4 * TILE_PX, 6);
  });

  test("artwork resolution does not change the drawn size", () => {
    const coarse = calibration(3, 240);
    const fine = calibration(3, 1920);
    expect(drawnHeightPx(coarse, scale, TILE_PX)).toBeCloseTo(
      drawnHeightPx(fine, scale, TILE_PX),
      6,
    );
  });

  test("the player is the unit, so it draws exactly player_height_tiles tall", () => {
    const player = calibration(1, 600);
    expect(drawnHeightPx(player, scale, TILE_PX)).toBeCloseTo(2.4 * TILE_PX, 6);
  });

  test("a boss is large because it is authored large, not by a rank fudge factor", () => {
    const boss = calibration(scale.ranks.boss, 800);
    const common = calibration(scale.ranks.common, 800);
    expect(drawnHeightPx(boss, scale, TILE_PX) / drawnHeightPx(common, scale, TILE_PX)).toBeCloseTo(
      scale.ranks.boss / scale.ranks.common,
      6,
    );
  });

  test("scale is uniform, so it does not depend on the subject's aspect", () => {
    const wide = calibration(2, 400);
    expect(spriteScale(wide, scale, TILE_PX)).toBeCloseTo((2.4 * TILE_PX) / (400 / 2), 6);
  });

  test("a non-positive tile size is refused", () => {
    expect(() => spriteScale(calibration(1, 100), scale, 0)).toThrow("positive finite");
  });
});
