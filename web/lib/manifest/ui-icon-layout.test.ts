import { describe, expect, test } from "bun:test";
import { UI_ATLAS_FIXTURE_ROLES } from "@/lib/shell/prepared-runtime.fixture";
import {
  UI_PREVIEW_ICON_GLYPHS,
  parseUiIconSetLayout,
  uiIconCellFor,
  uiIconNativeSize,
} from "./ui-icon-layout";

function grid(): Record<string, unknown> {
  return JSON.parse(JSON.stringify(UI_ATLAS_FIXTURE_ROLES.preview_icons)) as Record<
    string,
    unknown
  >;
}

describe("ui icon set layout", () => {
  test("parses the published grid and keeps the vocabulary in order", () => {
    const parsed = parseUiIconSetLayout(grid());
    expect(parsed.cells.map((cell) => cell.glyph)).toEqual([...UI_PREVIEW_ICON_GLYPHS]);
    expect(parsed.cell_size).toBe(232);
    expect(uiIconNativeSize(parsed)).toBe(116);
    expect(uiIconCellFor(parsed, "home").cell).toEqual({ x: 272, y: 272, width: 232, height: 232 });
  });

  test("refuses a grid whose vocabulary, cells or glyph bounds disagree with the contract", () => {
    const renamed = grid();
    (renamed.cells as Record<string, unknown>[])[0]!.glyph = "start";
    expect(() => parseUiIconSetLayout(renamed)).toThrow(/glyph must be play/);

    const short = grid();
    (short.cells as unknown[]).pop();
    expect(() => parseUiIconSetLayout(short)).toThrow(/exactly 16 cells/);

    const uneven = grid();
    (uneven.cells as Record<string, unknown>[])[3]!.cell = { x: 0, y: 0, width: 200, height: 232 };
    expect(() => parseUiIconSetLayout(uneven)).toThrow(/not one 232px square/);

    const escaped = grid();
    (escaped.cells as Record<string, unknown>[])[15]!.cell = { x: 900, y: 900, width: 232, height: 232 };
    expect(() => parseUiIconSetLayout(escaped)).toThrow(/leaves the canvas/);

    const loose = grid();
    (loose.cells as Record<string, unknown>[])[5]!.glyph_rect = { x: 0, y: 0, width: 50, height: 50 };
    expect(() => parseUiIconSetLayout(loose)).toThrow(/glyph_rect leaves the cell/);

    const sliced = { ...grid(), scale_mode: "nine_slice" };
    expect(() => parseUiIconSetLayout(sliced)).toThrow(/scale_mode/);
  });

  test("a glyph the grid does not hold is refused rather than drawn as something else", () => {
    const parsed = parseUiIconSetLayout(grid());
    expect(() => uiIconCellFor(parsed, "trophy" as never)).toThrow(/no trophy cell/);
  });
});
