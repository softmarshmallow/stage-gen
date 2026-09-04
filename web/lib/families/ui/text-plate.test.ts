import { describe, expect, test } from "bun:test";
import { textPlateLayout } from "./text-plate";
import { parseUiBlock } from "./manifest";

const SAFE = { x: 40, y: 500, width: 1200, height: 194 } as const;

// --- E4: one plate, two of the three layouts the table counted --------------------------------

describe("E4: the text plate instantiated into two layouts", () => {
  test("a conversation box: a portrait slot, a speaker row, and one padding", () => {
    const plate = textPlateLayout(SAFE, {
      portraitSlotWidth: 210,
      columnGap: 24,
      nameRowHeight: 34,
      rowGap: 10,
      paddingX: 8,
      paddingY: 8,
    });
    expect(plate.portrait).toEqual({ centerX: 40 + 8 + 105, bottomY: 500 + 8 + 178, height: 178 });
    expect(plate.name).toEqual({ x: 40 + 8 + 210 + 24, y: 508 });
    expect(plate.text).toEqual({ x: 282, y: 508 + 34 + 10, wrapWidth: 1184 - 210 - 24 });
  });

  test("a narration plate: no portrait, no speaker, and asymmetric padding", () => {
    // Which is the whole of the difference. A plate with no portrait is a
    // plate, and the arithmetic that puts the words where they go is the same.
    const plate = textPlateLayout(SAFE, {
      portraitSlotWidth: 0,
      columnGap: 0,
      nameRowHeight: 0,
      rowGap: 0,
      paddingX: 6,
      paddingY: 4,
    });
    expect(plate.text).toEqual({ x: 46, y: 504, wrapWidth: 1188 });
    // The portrait and the name come back and are ignored, rather than the port
    // growing two nullable halves every consumer would then have to test.
    expect(plate.name).toEqual({ x: 46, y: 504 });
  });
});

describe("the plate's own rule", () => {
  test("a safe rect too small for the slots it was asked for is refused", () => {
    expect(() =>
      textPlateLayout({ x: 0, y: 0, width: 200, height: 100 }, {
        portraitSlotWidth: 210,
        columnGap: 24,
        nameRowHeight: 34,
        rowGap: 10,
        paddingX: 8,
        paddingY: 8,
      }),
    ).toThrow("text plate safe rect is too small for its layout");
  });
});

describe("the block the family gates for itself", () => {
  test("`ui` is this family's own block, and a moved one is refused by name", () => {
    expect(parseUiBlock({ ui: "platformer-ui-block-v1" }, { block: "ui", version: "platformer-ui-block-v1" }).published).toBe(true);
    expect(() =>
      parseUiBlock({ ui: "platformer-ui-block-v2" }, { block: "ui", version: "platformer-ui-block-v1" }),
    ).toThrow('manifest block "ui" is published as platformer-ui-block-v2');
  });
});
