import { describe, expect, test } from "bun:test";
import {
  frameScaleForHeight,
  headMatchedScale,
  masterSheetScale,
  parseScaleReference,
  runtimeRoleOwnsScaleReference,
  type ScaleReference,
} from "./sprite-scale";

describe("frameScaleForHeight", () => {
  test("preserves non-square settlement and dialogue frame proportions", () => {
    const settlement = frameScaleForHeight(150, 364, 838);
    expect(settlement.displayHeight).toBe(150);
    expect(settlement.displayWidth / settlement.displayHeight).toBeCloseTo(
      364 / 838,
      12,
    );

    const dialogue = frameScaleForHeight(190, 466, 523);
    expect(dialogue.displayHeight).toBe(190);
    expect(dialogue.displayWidth / dialogue.displayHeight).toBeCloseTo(
      466 / 523,
      12,
    );
  });

  test("rejects invalid dimensions instead of inventing an aspect ratio", () => {
    expect(() => frameScaleForHeight(0, 364, 838)).toThrow(
      "target display height",
    );
    expect(() => frameScaleForHeight(150, 0, 838)).toThrow(
      "source frame width",
    );
    expect(() => frameScaleForHeight(150, 364, Number.NaN)).toThrow(
      "source frame height",
    );
  });
});

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
  Object.freeze({
    part: "head",
    topFraction: 0.1,
    bottomFraction: 0.3,
    leftFraction: 0.2,
    rightFraction: 0.4,
    extentPixels,
    confident,
    evidence: "Visible head bounds.",
    frameIndex: 0,
    cellWidth: 600,
    cellHeight: 688,
  });

const publishedReference = (overrides: Record<string, unknown> = {}) => ({
  part: "head",
  top_fraction: 0.1,
  bottom_fraction: 0.3,
  left_fraction: 0.2,
  right_fraction: 0.4,
  extent_pixels: 137.6,
  confident: true,
  evidence: "Visible head bounds.",
  frame_index: 0,
  cell_width: 600,
  cell_height: 688,
  ...overrides,
});

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

  test("rejects bad inputs rather than inventing a fallback scale", () => {
    const ref = reference();
    expect(() => headMatchedScale(ref, sheet(0))).toThrow("sheet extent");
    expect(() => headMatchedScale(ref, sheet(Number.NaN))).toThrow("sheet extent");
    expect(() =>
      headMatchedScale({ extentPixels: 0, scale: 1 }, sheet(50)),
    ).toThrow("reference extent");
    expect(() =>
      headMatchedScale({ extentPixels: 100, scale: 0 }, sheet(50)),
    ).toThrow("reference scale");
    expect(() => masterSheetScale(TARGET_SPRITE_HEIGHT, 0)).toThrow(
      "standing frame height",
    );
  });
});

describe("parseScaleReference", () => {
  test("reads a published reference", () => {
    const parsed = parseScaleReference(publishedReference());
    expect(parsed).toEqual({
      part: "head",
      topFraction: 0.1,
      bottomFraction: 0.3,
      leftFraction: 0.2,
      rightFraction: 0.4,
      extentPixels: 137.6,
      confident: true,
      evidence: "Visible head bounds.",
      frameIndex: 0,
      cellWidth: 600,
      cellHeight: 688,
    });
  });

  test("accepts a body reference for an undivided creature", () => {
    // A slime is one dome; its head is its body, and that is the same reference applied.
    expect(
      parseScaleReference(
        publishedReference({
          part: "body",
          top_fraction: 0,
          bottom_fraction: 1,
          left_fraction: 0.1,
          right_fraction: 0.9,
          extent_pixels: 688,
        }),
      ).part,
    ).toBe("body");
  });

  test("rejects absent, partial, aliased, and inconsistent payloads", () => {
    for (const value of [
      undefined,
      null,
      {},
      { part: "head" },
      publishedReference({ part: "elbow" }),
      publishedReference({ extent_pixels: 0 }),
      publishedReference({ top_fraction: 0.3, bottom_fraction: 0.1 }),
      publishedReference({ extent_pixels: 100 }),
      publishedReference({ frameIndex: 0 }),
    ]) {
      expect(() => parseScaleReference(value)).toThrow();
    }
  });
});

describe("runtimeRoleOwnsScaleReference", () => {
  test("recognizes the exact current measured actor roles", () => {
    for (const role of [
      "character-idle",
      "character-walk",
      "character-run",
      "character-jump",
      "character-crawl",
      "character-climb",
      "character-attack",
      "mob-0-idle",
      "mob-12-hurt",
      "mob-2-attack",
      "village-npc-0-idle",
      "village-npc-3-still",
    ]) {
      expect(runtimeRoleOwnsScaleReference(role)).toBeTrue();
    }
  });

  test("does not classify concepts, fixtures, or optional hurt as measured roles", () => {
    for (const role of [
      "character-concept",
      "character-hurt",
      "mob-concept-0",
      "mob-0-concept",
      "village-npc-concept-0",
      "village-fixtures",
    ]) {
      expect(runtimeRoleOwnsScaleReference(role)).toBeFalse();
    }
  });
});
