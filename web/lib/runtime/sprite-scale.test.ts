import { describe, expect, test } from "bun:test";
import {
  headMatchedScale,
  masterSheetScale,
  parseScaleReference,
  type ScaleReference,
} from "./sprite-scale";

// Head extents measured by the recipe on a real run's character sheets, in each sheet's own
// source pixels. Every sheet is a separate provider call, and the artwork really is drawn at
// these different sizes - crawl and attack have visibly smaller heads than idle at 1:1.
const HEAD = {
  idle: 222.981,
  walk: 220.16,
  crawl: 160.992,
  attack: 152.0,
  climb: 47.36,
} as const;

/** Painted height of each sheet's first frame, for the baseline scale. */
const IDLE_FRAME_HEIGHT = 460;
/** Player target height in the scene: TILE_PX * 2.2. */
const TARGET_SPRITE_HEIGHT = 64 * 2.2;

const reference = () => ({
  extentPixels: HEAD.idle,
  scale: masterSheetScale(TARGET_SPRITE_HEIGHT, IDLE_FRAME_HEIGHT),
});

const sheet = (extentPixels: number, confident = true): ScaleReference =>
  Object.freeze({ part: "head", extentPixels, confident });

describe("headMatchedScale", () => {
  test("renders every sheet's head at the same size on screen", () => {
    const ref = reference();
    const onScreen = (extent: number) => {
      const scale = headMatchedScale(ref, sheet(extent))!;
      return extent * scale;
    };
    const target = HEAD.idle * ref.scale;
    for (const extent of Object.values(HEAD)) {
      expect(onScreen(extent)).toBeCloseTo(target, 6);
    }
  });

  test("rescues the climb sheet, which is the whole reason this exists", () => {
    const ref = reference();
    // Inheriting the master scale drew a 47px head at 14px while idle's rendered at 68px.
    expect(HEAD.climb * ref.scale).toBeLessThan(20);
    const scale = headMatchedScale(ref, sheet(HEAD.climb))!;
    expect(HEAD.climb * scale).toBeCloseTo(HEAD.idle * ref.scale, 6);
    // A 64x128 sheet has to be scaled up, not down.
    expect(scale).toBeGreaterThan(1);
  });

  test("corrects crawl and attack, which were quietly wrong too", () => {
    const ref = reference();
    for (const extent of [HEAD.crawl, HEAD.attack]) {
      expect(extent * ref.scale).toBeLessThan(HEAD.idle * ref.scale * 0.75);
      const scale = headMatchedScale(ref, sheet(extent))!;
      expect(extent * scale).toBeCloseTo(HEAD.idle * ref.scale, 6);
    }
  });

  test("leaves a sheet drawn at the reference scale alone", () => {
    const ref = reference();
    expect(headMatchedScale(ref, sheet(HEAD.idle))).toBeCloseTo(ref.scale, 6);
  });

  test("uses an unconfident reading rather than falling back", () => {
    // The climb sheet is a small rear view and is read unconfidently most often. It is also the
    // sheet the fallback serves worst, so an approximate number beats the master scale.
    const ref = reference();
    const scale = headMatchedScale(ref, sheet(HEAD.climb, false));
    expect(scale).not.toBeNull();
    expect(HEAD.climb * scale!).toBeCloseTo(HEAD.idle * ref.scale, 6);
  });

  test("falls back rather than resizing a character off a bad number", () => {
    const ref = reference();
    expect(headMatchedScale(ref, null)).toBeNull();
    expect(headMatchedScale(ref, sheet(0))).toBeNull();
    expect(headMatchedScale(ref, sheet(Number.NaN))).toBeNull();
    expect(headMatchedScale({ extentPixels: 0, scale: 1 }, sheet(50))).toBeNull();
    expect(headMatchedScale({ extentPixels: 100, scale: 0 }, sheet(50))).toBeNull();
  });
});

describe("parseScaleReference", () => {
  test("reads a published reference", () => {
    const parsed = parseScaleReference({
      part: "head",
      extent_pixels: 222.981,
      confident: true,
    });
    expect(parsed).toEqual({ part: "head", extentPixels: 222.981, confident: true });
  });

  test("accepts a body reference for an undivided creature", () => {
    // A slime is one dome; its head is its body, and that is the same reference applied.
    expect(parseScaleReference({ part: "body", extent_pixels: 90, confident: true })?.part).toBe(
      "body",
    );
  });

  test("returns null for a run generated before the measurement existed", () => {
    // Absence means "scale this the way you always did", not a broken manifest.
    expect(parseScaleReference(undefined)).toBeNull();
    expect(parseScaleReference(null)).toBeNull();
    expect(parseScaleReference({})).toBeNull();
    expect(parseScaleReference({ part: "head" })).toBeNull();
    expect(parseScaleReference({ part: "elbow", extent_pixels: 10 })).toBeNull();
    expect(parseScaleReference({ part: "head", extent_pixels: 0 })).toBeNull();
    expect(parseScaleReference({ part: "head", extent_pixels: -4 })).toBeNull();
  });
});
