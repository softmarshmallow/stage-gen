import { describe, expect, test } from "bun:test";
import { cameraWorldBounds } from "./camera-follow";

describe("declared camera axes", () => {
  // Bellweather's two shipped maps, at the prepared adapter's 64px tiles and 720px viewport:
  // a 12-row village whose camera holds the floor, and a 16-row road whose camera may climb.
  const village = { worldWidth: 4096, terrainTopY: 720 - 12 * 64, groundBaselineY: 720, viewportHeight: 720 };
  const road = { worldWidth: 6144, terrainTopY: 720 - 16 * 64, groundBaselineY: 720, viewportHeight: 720 };

  test("without a vertical axis the box is exactly one viewport, so the camera cannot leave the floor", () => {
    expect(cameraWorldBounds({ ...village, followAxes: ["x"] })).toEqual({
      x: 0,
      y: 0,
      width: 4096,
      height: 720,
    });
  });

  test("with a vertical axis the box is the authored grid, so every buildable row is reachable", () => {
    // 16 rows of 64px is 1024 tall against a 720 viewport: 304px the camera could never reach
    // before, which is where the road's highest deck sits.
    expect(cameraWorldBounds({ ...road, followAxes: ["x", "y"] })).toEqual({
      x: 0,
      y: -304,
      width: 6144,
      height: 1024,
    });
  });

  test("the axis list drives the box, not the map's dimensions", () => {
    const pinned = cameraWorldBounds({ ...road, followAxes: ["x"] });
    expect(pinned.y).toBe(0);
    expect(pinned.height).toBe(720);
  });

  test("a vertical-only camera still gets its full world width, because width is not an axis", () => {
    // Width is the world; only the follow is gated. A climbing tower that declares ["y"] must
    // still render its whole map rather than a 720-wide slice of it.
    expect(cameraWorldBounds({ ...road, followAxes: ["y"] })).toEqual({
      x: 0,
      y: -304,
      width: 6144,
      height: 1024,
    });
  });

  test("degenerate geometry is rejected rather than clamped", () => {
    expect(() => cameraWorldBounds({ ...road, followAxes: [], worldWidth: 0 })).toThrow(
      /must be positive/,
    );
    expect(() =>
      cameraWorldBounds({ ...road, followAxes: [], groundBaselineY: road.terrainTopY }),
    ).toThrow(/floor below the top of the terrain/);
  });
});
