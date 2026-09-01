import { describe, expect, test } from "bun:test";
import {
  isNeutralLayerPresentation,
  presentPreparedLayerPixels,
} from "./prepared-layer-presentation";
import type { PreparedLayerPresentation } from "@/lib/manifest/prepared-manifest";

const NEUTRAL: PreparedLayerPresentation = Object.freeze({
  contrast: 1,
  saturation: 1,
  atmosphere_color: "#ffffff",
  atmosphere_strength: 0,
  detail_blur_screen_pixels: 0,
});

describe("prepared layer runtime presentation", () => {
  test("leaves neutral pixels byte-identical", () => {
    const source = new Uint8ClampedArray([10, 20, 30, 255, 40, 50, 60, 0]);
    const result = presentPreparedLayerPixels(source, 2, 1, NEUTRAL, 1);
    expect(isNeutralLayerPresentation(NEUTRAL)).toBeTrue();
    expect([...result]).toEqual([...source]);
    expect(result).not.toBe(source);
  });

  test("grades RGB while retaining the admitted alpha silhouette", () => {
    const source = new Uint8ClampedArray([
      220, 80, 30, 255,
      20, 200, 60, 128,
      17, 19, 23, 0,
    ]);
    const result = presentPreparedLayerPixels(
      source,
      3,
      1,
      {
        contrast: 0.84,
        saturation: 0.9,
        atmosphere_color: "#b8e8f4",
        atmosphere_strength: 0.06,
        detail_blur_screen_pixels: 0.65,
      },
      1,
    );
    expect([result[3], result[7], result[11]]).toEqual([255, 128, 0]);
    expect([...result.slice(0, 3)]).not.toEqual([...source.slice(0, 3)]);
  });

  test("wraps horizontal blur across the admitted repeat boundary", () => {
    const source = new Uint8ClampedArray([
      255, 0, 0, 255,
      0, 0, 0, 255,
      0, 0, 255, 255,
    ]);
    const result = presentPreparedLayerPixels(
      source,
      3,
      1,
      { ...NEUTRAL, detail_blur_screen_pixels: 1 },
      1,
    );
    expect(result[2]).toBeGreaterThan(0);
    expect(result[8]).toBeGreaterThan(0);
    expect(result[11]).toBe(255);
  });
});
