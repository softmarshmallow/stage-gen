import { describe, expect, test } from "bun:test";
import {
  preparedGroundBaselineY,
  preparedLayerLayout,
  preparedWalkSurfaceY,
} from "./prepared-layers";
import type { PreparedLayerPlacement, PreparedMap } from "./prepared-manifest";

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
  const context = { viewportHeight: VIEW_H, walkSurfaceY: 528 };

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

  test("invalid raster heights are rejected", () => {
    expect(() =>
      preparedLayerLayout(placement({ trimmed_height: 0 }), context),
    ).toThrow(/positive raster heights/);
  });
});
