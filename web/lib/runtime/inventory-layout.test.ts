import { describe, expect, test } from "bun:test";
import {
  INVENTORY_GRID_4X2_V1,
  parseInventoryPanelLayout,
} from "./inventory-layout";

describe("prepared inventory layout", () => {
  test("parses and freezes the exact manifest-published V1 geometry", () => {
    const parsed = parseInventoryPanelLayout(
      structuredClone(INVENTORY_GRID_4X2_V1),
    );

    expect(parsed.canvas).toEqual({ width: 1536, height: 1024 });
    expect(parsed.panel_bounds).toEqual({
      x: 128,
      y: 160,
      width: 1280,
      height: 704,
    });
    expect(parsed.slots).toHaveLength(8);
    expect(parsed.slots[0]).toEqual({
      slot_id: "slot_0",
      x: 208,
      y: 240,
      width: 256,
      height: 256,
    });
    expect(Object.isFrozen(parsed)).toBeTrue();
    expect(Object.isFrozen(parsed.slots)).toBeTrue();
  });

  test("rejects arbitrary geometry under the exact V1 identity", () => {
    const moved = structuredClone(INVENTORY_GRID_4X2_V1) as unknown as {
      slots: Array<{ x: number }>;
    };
    moved.slots[0]!.x = 209;

    expect(() => parseInventoryPanelLayout(moved)).toThrow(
      "ui.inventory_panel.slots[0].x must equal 208",
    );
  });
});
