import { describe, expect, test } from "bun:test";
import { parseUiAtlasRoleLayout, uiAtlasCellFor } from "./ui-atlas-layout";

const INSETS = { left: 72, top: 50, right: 80, bottom: 56 };

function cell(state: string, x: number, y: number, width: number, height: number) {
  const content_rect = {
    x: x + INSETS.left,
    y: y + INSETS.top,
    width: width - INSETS.left - INSETS.right,
    height: height - INSETS.top - INSETS.bottom,
  };
  return { state, cell: { x, y, width, height }, content_rect, safe_rect: { ...content_rect } };
}

/** A button sheet as the producer publishes it after detecting four drifted bodies. */
function buttonSheet() {
  return {
    role: "button_rect",
    layout: "nine_slice_button_sheet_4x1024_v1",
    scale_mode: "nine_slice",
    alpha_policy: "transparent_exterior_opaque_body_v1",
    band_fill: "tile",
    draw_scale: 2,
    canvas: { width: 1024, height: 1024 },
    insets: { ...INSETS },
    cells: [
      cell("normal", 152, 132, 721, 156),
      cell("hover", 152, 326, 721, 154),
      cell("pressed", 152, 517, 720, 154),
      cell("disabled", 151, 708, 722, 155),
    ],
  };
}

describe("ui atlas role layout", () => {
  test("parses a detected button sheet and keeps its states in order", () => {
    const parsed = parseUiAtlasRoleLayout(buttonSheet(), "button_rect");

    expect(parsed.band_fill).toBe("tile");
    expect(parsed.insets).toEqual(INSETS);
    expect(parsed.cells.map((entry) => entry.state)).toEqual([
      "normal",
      "hover",
      "pressed",
      "disabled",
    ]);
    expect(uiAtlasCellFor(parsed, "pressed").cell).toEqual({
      x: 152,
      y: 517,
      width: 720,
      height: 154,
    });
    expect(uiAtlasCellFor(parsed, "missing")).toBe(parsed.cells[0]);
    expect(Object.isFrozen(parsed.cells)).toBe(true);
  });

  test("a panel publishes one default cell", () => {
    const parsed = parseUiAtlasRoleLayout(
      {
        role: "panel_frame",
        layout: "nine_slice_panel_1024_v1",
        scale_mode: "nine_slice",
        alpha_policy: "transparent_exterior_opaque_body_v1",
        band_fill: "stretch",
        draw_scale: 2,
        canvas: { width: 1024, height: 1024 },
        insets: { left: 96, top: 96, right: 96, bottom: 96 },
        cells: [
          {
            state: "default",
            cell: { x: 141, y: 233, width: 742, height: 537 },
            content_rect: { x: 237, y: 329, width: 550, height: 345 },
            safe_rect: { x: 249, y: 341, width: 526, height: 321 },
          },
        ],
      },
      "panel_frame",
    );

    expect(parsed.cells).toHaveLength(1);
    expect(parsed.cells[0].content_rect.width).toBe(550);
  });

  test("refuses a content rect that disagrees with the cell and insets", () => {
    const sheet = buttonSheet();
    sheet.cells[1].content_rect.width += 1;
    expect(() => parseUiAtlasRoleLayout(sheet, "button_rect")).toThrow(
      /content_rect disagrees/,
    );
  });

  test("refuses states out of order, cells off the canvas, and unknown fills", () => {
    const reordered = buttonSheet();
    [reordered.cells[0], reordered.cells[1]] = [reordered.cells[1], reordered.cells[0]];
    expect(() => parseUiAtlasRoleLayout(reordered, "button_rect")).toThrow(/state must be/);

    const escaped = buttonSheet();
    escaped.cells[3] = cell("disabled", 400, 900, 721, 156);
    expect(() => parseUiAtlasRoleLayout(escaped, "button_rect")).toThrow(/leaves the canvas/);

    const fill = { ...buttonSheet(), band_fill: "mirror" };
    expect(() => parseUiAtlasRoleLayout(fill, "button_rect")).toThrow(/band_fill/);

    const wrongRole = buttonSheet();
    expect(() => parseUiAtlasRoleLayout(wrongRole, "panel_frame")).toThrow(/role must be/);
  });
});

test("a safe rect that leaves its content rect is refused", () => {
  const sheet = buttonSheet();
  sheet.cells[0].safe_rect.x -= 1;
  expect(() => parseUiAtlasRoleLayout(sheet, "button_rect")).toThrow(/safe_rect leaves/);
});
