import { describe, expect, test } from "bun:test";
import {
  preparedGroundBaselineY,
  preparedLayerLayout,
  preparedWalkSurfaceY,
} from "./prepared-layers";
import { projectPreparedTerrainWorld } from "./prepared-terrain";
import type { PreparedLayerPlacement, PreparedMap } from "@/lib/manifest/prepared-manifest";

const VIEW_H = 720;
const TILE_PX = 64;

function placement(
  overrides: Partial<PreparedLayerPlacement> = {},
): PreparedLayerPlacement {
  return Object.freeze({
    vertical_anchor: "screen_bottom",
    vertical_offset: 0,
    vertical_offset_source: "measured",
    source_height: 1024,
    trimmed_height: 1024,
    trimmed_top: 0,
    ...overrides,
  }) as PreparedLayerPlacement;
}

function ground(
  rows: number,
  walkSurfaceRow: number,
): Pick<PreparedMap, "ground"> {
  return {
    ground: {
      mode: "terrain-atlas-3x3-minimal-v1",
      occupancy: Object.freeze(Array.from({ length: rows }, () => "1".repeat(8))),
      vertical_fit: "floor_to_screen_bottom",
      walk_surface_row: walkSurfaceRow,
      asset: {
        path: "maps/m/ground.png",
        sha256: "0".repeat(64),
        bytes: 1,
        media_type: "image/png",
      },
    },
  } as Pick<PreparedMap, "ground">;
}

describe("ground datum", () => {
  test("the world floor is the viewport edge, so no gap can open below it", () => {
    expect(preparedGroundBaselineY(ground(12, 9), VIEW_H)).toBe(VIEW_H);
  });

  test("the walk surface is the top edge of the authored row", () => {
    // Twelve rows with the main plane at row 9 leaves three rows below it.
    expect(preparedWalkSurfaceY(ground(12, 9), TILE_PX, VIEW_H)).toBe(720 - 3 * 64);
  });

  test("a walk_surface_row outside the authored grid is rejected", () => {
    expect(() => preparedWalkSurfaceY(ground(12, 12), TILE_PX, VIEW_H)).toThrow(
      /walk_surface_row/,
    );
  });
});

describe("layer layout", () => {
  const context = { viewportHeight: VIEW_H, walkSurfaceY: 528, parallax: 0 };

  test("an opaque base covers the viewport exactly", () => {
    const layout = preparedLayerLayout(
      placement({ vertical_anchor: "canvas_cover" }),
      context,
    );
    expect(layout.topY).toBe(0);
    expect(layout.renderedHeight).toBe(VIEW_H);
  });

  test("trimming never changes apparent size because the painted frame stays the datum", () => {
    // A strip trimmed to 186 of 1024 rows keeps the scale of the frame it was painted in.
    const layout = preparedLayerLayout(
      placement({ vertical_anchor: "screen_top", trimmed_height: 186 }),
      context,
    );
    expect(layout.scale).toBeCloseTo(720 / 1024, 10);
    expect(layout.renderedHeight).toBeCloseTo(186 * (720 / 1024), 10);
    expect(layout.sourceHeight).toBe(186);
  });

  test("a bottom anchor with no offset leaves the deepest tip on the datum", () => {
    const layout = preparedLayerLayout(
      placement({ trimmed_height: 186, vertical_offset: 0 }),
      context,
    );
    expect(layout.topY + layout.renderedHeight).toBeCloseTo(VIEW_H, 10);
  });

  test("the resolved offset puts the coverage line on the datum, not the deepest tip", () => {
    // near_garden_frame: 186 trimmed rows whose full-coverage line sits 28 rows above the bottom.
    const offset = 28 / 186;
    const layout = preparedLayerLayout(
      placement({ trimmed_height: 186, vertical_offset: offset }),
      context,
    );
    const coverageLineY =
      layout.topY + layout.renderedHeight - offset * layout.renderedHeight;
    expect(coverageLineY).toBeCloseTo(VIEW_H, 8);
    // The ragged tips are pushed past the frame edge rather than left showing sky behind them.
    expect(layout.topY + layout.renderedHeight).toBeGreaterThan(VIEW_H);
  });

  test("walk_surface registers against the visible terrain, not the buried floor", () => {
    const offset = 0.1;
    const layout = preparedLayerLayout(
      placement({
        vertical_anchor: "walk_surface",
        trimmed_height: 415,
        vertical_offset: offset,
      }),
      context,
    );
    const coverageLineY =
      layout.topY + layout.renderedHeight - offset * layout.renderedHeight;
    expect(coverageLineY).toBeCloseTo(context.walkSurfaceY, 8);
  });

  test.each([
    ["canvas_cover", "screen"],
    ["screen_top", "screen"],
    ["screen_bottom", "screen"],
    ["walk_surface", "world"],
  ] as const)("a %s anchor resolves in %s space", (anchor, space) => {
    expect(
      preparedLayerLayout(placement({ vertical_anchor: anchor }), context).space,
    ).toBe(space);
  });

  test("the walk surface datum is the same world coordinate the terrain is projected onto", () => {
    // The one anchor that is not viewport furniture. If these two ever disagreed, the painted
    // midground would sit off the terrain it is registered to - and because the camera rests at
    // the bottom of the world today, nothing on screen would reveal it.
    const map = ground(12, 9);
    const world = projectPreparedTerrainWorld(map, TILE_PX, preparedGroundBaselineY(map, VIEW_H));
    const walkSurfaceRowTopY = world.topY + map.ground.walk_surface_row * TILE_PX;
    expect(preparedWalkSurfaceY(map, TILE_PX, VIEW_H)).toBe(walkSurfaceRowTopY);
  });

  test("invalid raster heights are rejected", () => {
    expect(() =>
      preparedLayerLayout(placement({ trimmed_height: 0 }), context),
    ).toThrow(/positive raster heights/);
  });
});

describe("vertical parallax", () => {
  const placement = (
    anchor: PreparedLayerPlacement["vertical_anchor"],
  ): PreparedLayerPlacement =>
    Object.freeze({
      vertical_anchor: anchor,
      vertical_offset: 0,
      vertical_offset_source: "measured",
      source_height: 1024,
      trimmed_height: 512,
      trimmed_top: 0,
    });

  test("a layer takes as much of the camera's climb as its distance implies", () => {
    // Depth does not change with the axis you look along, so the number that already says
    // how far away a layer is says it on y as well. Horizontal parallax cannot use this,
    // because a layer repeats on x and slides inside itself instead of moving.
    const near = preparedLayerLayout(placement("screen_bottom"), {
      viewportHeight: VIEW_H,
      walkSurfaceY: 500,
      parallax: 1.42,
    });
    expect(near.verticalScrollFactor).toBe(1.42);
  });

  test("a sky plate holds still", () => {
    const sky = preparedLayerLayout(placement("canvas_cover"), {
      viewportHeight: VIEW_H,
      walkSurfaceY: 500,
      parallax: 0,
    });
    expect(sky.verticalScrollFactor).toBe(0);
  });

  test("the walk-surface layer travels with the terrain whatever its parallax", () => {
    // It is registered to the ground it was measured against. Letting it drift would take
    // its solid base off the row the producer resolved it to.
    const midground = preparedLayerLayout(placement("walk_surface"), {
      viewportHeight: VIEW_H,
      walkSurfaceY: 500,
      parallax: 0.62,
    });
    expect(midground.space).toBe("world");
    expect(midground.verticalScrollFactor).toBe(1);
  });

  test("a map that never scrolls vertically cannot notice any of this", () => {
    // Every factor multiplies the camera's vertical travel, and a map whose camera follows
    // x alone has none, which is why the village is untouched by this rule.
    for (const parallax of [0, 0.16, 0.58, 1.32]) {
      const layout = preparedLayerLayout(placement("screen_top"), {
        viewportHeight: VIEW_H,
        walkSurfaceY: 500,
        parallax,
      });
      expect(layout.topY - 0 * layout.verticalScrollFactor).toBe(layout.topY);
    }
  });

  test("a negative parallax is refused rather than inverting the world", () => {
    expect(() =>
      preparedLayerLayout(placement("screen_top"), {
        viewportHeight: VIEW_H,
        walkSurfaceY: 500,
        parallax: -1,
      }),
    ).toThrow(/non-negative parallax/);
  });
});
