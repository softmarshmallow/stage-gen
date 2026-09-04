import { describe, expect, test } from "bun:test";
import {
  atlasGroundTileKey,
  bandTilePositionX,
  layerBandDepth,
  parseRunnerParallaxBlock,
  RUNNER_DEPTHS,
  RUNNER_DEPTH_LADDER,
  runnerLayerFrameHeight,
  runnerLayerPlacement,
  structuralGroundPlacement,
  structuralGroundSourceSize,
} from "./parallax";
import { RUNNER_BLOCKS } from "./contract";
import { bandDepth, layerLayout } from "@/lib/families/sideview/parallax";

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

  test("a trimmed band keeps the shared cover-frame scale instead of filling the screen", () => {
    const cover = {
      width: 1536,
      height: 1024,
      alphaMode: "opaque" as const,
      verticalAnchor: "canvas_cover" as const,
    };
    const foreground = {
      width: 1536,
      height: 240,
      alphaMode: "transparent" as const,
      verticalAnchor: "screen_bottom" as const,
      verticalOffset: null,
    };
    const frameHeight = runnerLayerFrameHeight(foreground, [cover, foreground]);
    expect(frameHeight).toBe(1024);
    const placement = runnerLayerPlacement(foreground, VIEW_H, GROUND_LINE, frameHeight);
    expect(placement.renderedHeight).toBeCloseTo((240 * VIEW_H) / 1024, 10);
    expect(placement.topY + placement.renderedHeight).toBeCloseTo(VIEW_H, 10);
  });

  test("keeps cover-frame scale when generated repeat bridges have different widths", () => {
    const layer = {
      width: 1200,
      height: 300,
      alphaMode: "transparent" as const,
      verticalAnchor: "screen_bottom" as const,
    };
    const cover = {
      width: 1536,
      height: 1024,
      alphaMode: "opaque" as const,
      verticalAnchor: "canvas_cover" as const,
    };
    expect(runnerLayerFrameHeight(layer, [cover, layer])).toBe(1024);
  });

  test("falls back to a transparent layer's own height without an opaque cover", () => {
    const layer = {
      width: 1200,
      height: 300,
      alphaMode: "transparent" as const,
      verticalAnchor: "screen_bottom" as const,
    };
    expect(runnerLayerFrameHeight(layer, [layer])).toBe(300);
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

describe("structural ground placement", () => {
  test("projects a full segment raster through the occupancy grid", () => {
    expect(structuralGroundSourceSize(12, 8, 64)).toEqual({ width: 768, height: 512 });
    expect(structuralGroundPlacement(24, 12, 8, 48)).toEqual({
      leftX: 1152,
      topY: 336,
      width: 576,
      height: 384,
    });
  });

  test("refuses degenerate raster grids", () => {
    expect(() => structuralGroundSourceSize(0, 8, 64)).toThrow("valid grid");
    expect(() => structuralGroundPlacement(0, 12, 8, 0)).toThrow("valid grid");
  });
});

describe("atlas ground tile identity", () => {
  test("replaces a coordinate when its boundary frame changes", () => {
    const before = atlasGroundTileKey(12, 5, "mask_001");
    const after = atlasGroundTileKey(12, 5, "mask_101");

    expect(after).not.toBe(before);
    expect(atlasGroundTileKey(12, 5, "mask_101")).toBe(after);
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

describe("the runner's bands are the parallax family's, at this genre's numbers", () => {
  test("every anchor resolves to the family's own resolution", () => {
    const layer = {
      height: 540,
      verticalAnchor: "screen_bottom" as const,
      verticalOffset: 0.25,
    };
    for (const verticalAnchor of [
      "canvas_cover",
      "screen_top",
      "screen_bottom",
      "walk_surface",
    ] as const) {
      const genre = runnerLayerPlacement({ ...layer, verticalAnchor }, 720, 700, 1080);
      const family = layerLayout(
        {
          verticalAnchor,
          verticalOffset: layer.verticalOffset,
          sourceHeight: 1080,
          trimmedHeight: 540,
        },
        { viewportHeight: 720, walkSurfaceY: 700, parallax: 0 },
      );
      expect(genre).toEqual({
        topY: family.topY,
        renderedHeight: family.renderedHeight,
        scale: family.scale,
      });
    }
    // A null offset is this genre's own fact — its contract makes the field
    // nullable where the platformer's producer always resolves one — and it
    // means zero.
    expect(
      runnerLayerPlacement({ ...layer, verticalOffset: null }, 720, 700, 1080).topY,
    ).toBe(runnerLayerPlacement({ ...layer, verticalOffset: 0 }, 720, 700, 1080).topY);
  });

  test("the depth ladder is this genre's rungs in the family's order", () => {
    expect(RUNNER_DEPTH_LADDER).toEqual({
      background: RUNNER_DEPTHS.background,
      world: RUNNER_DEPTHS.ground,
      actors: RUNNER_DEPTHS.avatar,
      foreground: RUNNER_DEPTHS.foreground,
      hud: RUNNER_DEPTHS.hud,
      overlay: RUNNER_DEPTHS.fx,
    });
    expect(layerBandDepth({ plane: "foreground", order: 2 })).toBe(
      bandDepth(RUNNER_DEPTH_LADDER, "foreground", 2),
    );
  });

  test("the parallax block is gated by the family, by name", () => {
    expect(parseRunnerParallaxBlock(RUNNER_BLOCKS).published).toBe(true);
    expect(() =>
      parseRunnerParallaxBlock({ ...RUNNER_BLOCKS, layers: "runner-layers-block-v2" }),
    ).toThrow('manifest block "layers" is published as runner-layers-block-v2');
  });
});
