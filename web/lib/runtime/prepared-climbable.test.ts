import { describe, expect, test } from "bun:test";

import {
  climbableAtlasFrames,
  climbableFrameKey,
  climbableVisualWidth,
} from "./prepared-climbable";
import type { PreparedMap } from "./prepared-manifest";

function mapWithClimbable(
  cells: readonly Readonly<{ x: number; y: number; width: number; height: number }>[],
): Pick<PreparedMap, "climbable"> {
  return {
    climbable: {
      mode: "climbable-atlas-v1",
      asset: {
        path: "maps/road/climbable.png",
        sha256: "a".repeat(64),
        bytes: 1,
        media_type: "image/png",
        role: "asset" as const,
      },
      index_order: "left_to_right",
      variants: cells.map((cell, index) => ({
        variant_id: `variant_${index}`,
        role: index === cells.length - 1 ? ("rope" as const) : ("ladder" as const),
        cell_index: index,
        cell,
      })),
      placements: cells.map((_, index) => ({
        climbable_id: `variant_${index}`,
        variant_id: `variant_${index}`,
        normalized_x: 0.1 * (index + 1),
        bottom_surface: "terrain" as const,
        rise_tiles: 4 as const,
      })),
    },
  };
}

describe("climbable atlas frames", () => {
  test("derives one frame per declared variant from its measured cell", () => {
    const map = mapWithClimbable([
      { x: 16, y: 21, width: 334, height: 1447 },
      { x: 860, y: 16, width: 109, height: 1452 },
    ]);

    expect(climbableAtlasFrames(map)).toEqual([
      {
        variantId: "variant_0",
        frameKey: "climbable:variant_0",
        x: 16,
        y: 21,
        width: 334,
        height: 1447,
      },
      {
        variantId: "variant_1",
        frameKey: "climbable:variant_1",
        x: 860,
        y: 16,
        width: 109,
        height: 1452,
      },
    ]);
  });

  test("a map without a climbable yields no frames", () => {
    expect(climbableAtlasFrames({ climbable: undefined })).toEqual([]);
  });

  test("frame keys are stable and distinct per variant", () => {
    expect(climbableFrameKey("bellrope_climb")).toBe("climbable:bellrope_climb");
    expect(climbableFrameKey("a")).not.toBe(climbableFrameKey("b"));
  });

  test("rejects an empty cell rather than registering a degenerate frame", () => {
    expect(() =>
      climbableAtlasFrames(mapWithClimbable([{ x: 0, y: 0, width: 0, height: 10 }])),
    ).toThrow("empty atlas cell");
  });
});

describe("climbable visual width", () => {
  test("preserves each variant's own artwork aspect at a shared visual height", () => {
    // The real Bellweather sheet: a ladder and a rope drawn at the same 320px zone height.
    expect(climbableVisualWidth({ width: 334, height: 1447 }, 320)).toBe(74);
    expect(climbableVisualWidth({ width: 260, height: 1442 }, 320)).toBe(58);
    expect(climbableVisualWidth({ width: 109, height: 1452 }, 320)).toBe(24);
  });

  test("a rope is materially narrower than a ladder at the same height", () => {
    const ladder = climbableVisualWidth({ width: 334, height: 1447 }, 320);
    const rope = climbableVisualWidth({ width: 109, height: 1452 }, 320);
    expect(rope).toBeLessThan(ladder / 2);
  });

  test("never collapses to zero and rejects degenerate input", () => {
    expect(climbableVisualWidth({ width: 1, height: 100000 }, 320)).toBe(1);
    expect(() => climbableVisualWidth({ width: 0, height: 10 }, 320)).toThrow();
    expect(() => climbableVisualWidth({ width: 10, height: 10 }, 0)).toThrow();
  });

  test("width is independent of the atlas the cell came from", () => {
    // The defect this guards: sizing derived from the full texture rather than the cell makes
    // the drawn width depend on how many variants happen to share the sheet.
    const cell = { width: 334, height: 1447 };
    expect(climbableVisualWidth(cell, 320)).toBe(74);
    // Same cell, hypothetically packed into a much wider sheet: the answer must not move.
    expect(climbableVisualWidth({ ...cell }, 320)).toBe(74);
  });
});
