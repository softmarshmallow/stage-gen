import { describe, expect, test } from "bun:test";
import {
  bandTilePositionX,
  layerBandDepth,
  RUNNER_DEPTHS,
  runnerLayerPlacement,
} from "./parallax";

const VIEW_H = 720;
const GROUND_LINE = 528;

describe("runnerLayerPlacement", () => {
  test("a cover plate fills the canvas from the top", () => {
    const placement = runnerLayerPlacement(
      { height: 1024, verticalAnchor: "canvas_cover", verticalOffset: null },
      VIEW_H,
      GROUND_LINE,
    );
    expect(placement.topY).toBe(0);
    expect(placement.renderedHeight).toBe(VIEW_H);
    expect(placement.scale).toBeCloseTo(VIEW_H / 1024, 10);
  });

  test("screen_top hangs from the ceiling and slides by its offset", () => {
    const placement = runnerLayerPlacement(
      { height: 1024, verticalAnchor: "screen_top", verticalOffset: 0.1 },
      VIEW_H,
      GROUND_LINE,
    );
    expect(placement.topY).toBeCloseTo(0.1 * VIEW_H, 10);
  });

  test("screen_bottom registers its base on the canvas bottom", () => {
    const placement = runnerLayerPlacement(
      { height: 1024, verticalAnchor: "screen_bottom", verticalOffset: null },
      VIEW_H,
      GROUND_LINE,
    );
    expect(placement.topY + placement.renderedHeight).toBeCloseTo(VIEW_H, 10);
  });

  test("walk_surface registers its base on the ground line", () => {
    const placement = runnerLayerPlacement(
      { height: 1024, verticalAnchor: "walk_surface", verticalOffset: null },
      VIEW_H,
      GROUND_LINE,
    );
    expect(placement.topY + placement.renderedHeight).toBeCloseTo(GROUND_LINE, 10);
    const nudged = runnerLayerPlacement(
      { height: 1024, verticalAnchor: "walk_surface", verticalOffset: 0.05 },
      VIEW_H,
      GROUND_LINE,
    );
    expect(nudged.topY).toBeGreaterThan(placement.topY);
  });

  test("refuses degenerate heights", () => {
    expect(() =>
      runnerLayerPlacement(
        { height: 0, verticalAnchor: "canvas_cover", verticalOffset: null },
        VIEW_H,
        GROUND_LINE,
      ),
    ).toThrow("positive heights");
  });
});

describe("layerBandDepth", () => {
  test("keeps background bands under the world and foreground bands over it", () => {
    expect(layerBandDepth({ plane: "background", order: 3 })).toBeLessThan(
      RUNNER_DEPTHS.ground,
    );
    expect(layerBandDepth({ plane: "foreground", order: 0 })).toBeGreaterThan(
      RUNNER_DEPTHS.avatar,
    );
    expect(layerBandDepth({ plane: "background", order: 2 })).toBeGreaterThan(
      layerBandDepth({ plane: "background", order: 1 }),
    );
  });
});

describe("bandTilePositionX", () => {
  test("scrolls texture space by parallax over scale", () => {
    expect(bandTilePositionX(1000, 0.5, 2)).toBe(250);
    expect(bandTilePositionX(1000, 0, 2)).toBe(0);
  });
});
