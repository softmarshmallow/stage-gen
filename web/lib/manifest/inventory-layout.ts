export type InventorySlotLayout = Readonly<{
  slot_id: string;
  x: number;
  y: number;
  width: number;
  height: number;
}>;

export type InventoryPanelLayout = Readonly<{
  layout: "inventory_grid_4x2_v1";
  alpha_policy: "transparent_exterior_opaque_panel_v1";
  canvas: Readonly<{ width: number; height: number }>;
  panel_bounds: Readonly<{ x: number; y: number; width: number; height: number }>;
  slots: readonly InventorySlotLayout[];
}>;

const slots = Array.from({ length: 8 }, (_, index): InventorySlotLayout => {
  const row = Math.floor(index / 4);
  const column = index % 4;
  return Object.freeze({
    slot_id: `slot_${index}`,
    x: 208 + column * 288,
    y: 240 + row * 288,
    width: 256,
    height: 256,
  });
});

export const INVENTORY_GRID_4X2_V1: InventoryPanelLayout = Object.freeze({
  layout: "inventory_grid_4x2_v1",
  alpha_policy: "transparent_exterior_opaque_panel_v1",
  canvas: Object.freeze({ width: 1536, height: 1024 }),
  panel_bounds: Object.freeze({ x: 128, y: 160, width: 1280, height: 704 }),
  slots: Object.freeze(slots),
});

function record(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function exactInteger(value: unknown, expected: number, label: string): number {
  if (value !== expected) throw new Error(`${label} must equal ${expected}`);
  return expected;
}

/** Parse the exact V1 geometry instead of trusting arbitrary manifest coordinates. */
export function parseInventoryPanelLayout(
  value: unknown,
  label = "ui.inventory_panel",
): InventoryPanelLayout {
  const source = record(value, label);
  if (source.layout !== INVENTORY_GRID_4X2_V1.layout) {
    throw new Error(`${label}.layout is invalid`);
  }
  if (source.alpha_policy !== INVENTORY_GRID_4X2_V1.alpha_policy) {
    throw new Error(`${label}.alpha_policy is invalid`);
  }
  const canvas = record(source.canvas, `${label}.canvas`);
  const panelBounds = record(source.panel_bounds, `${label}.panel_bounds`);
  if (!Array.isArray(source.slots) || source.slots.length !== 8) {
    throw new Error(`${label}.slots must contain the exact eight-slot layout`);
  }
  const parsedSlots = source.slots.map((value, index): InventorySlotLayout => {
    const slot = record(value, `${label}.slots[${index}]`);
    const expected = INVENTORY_GRID_4X2_V1.slots[index];
    if (slot.slot_id !== expected.slot_id) {
      throw new Error(`${label}.slots[${index}].slot_id is invalid`);
    }
    return Object.freeze({
      slot_id: expected.slot_id,
      x: exactInteger(slot.x, expected.x, `${label}.slots[${index}].x`),
      y: exactInteger(slot.y, expected.y, `${label}.slots[${index}].y`),
      width: exactInteger(slot.width, expected.width, `${label}.slots[${index}].width`),
      height: exactInteger(slot.height, expected.height, `${label}.slots[${index}].height`),
    });
  });
  return Object.freeze({
    layout: INVENTORY_GRID_4X2_V1.layout,
    alpha_policy: INVENTORY_GRID_4X2_V1.alpha_policy,
    canvas: Object.freeze({
      width: exactInteger(canvas.width, 1536, `${label}.canvas.width`),
      height: exactInteger(canvas.height, 1024, `${label}.canvas.height`),
    }),
    panel_bounds: Object.freeze({
      x: exactInteger(panelBounds.x, 128, `${label}.panel_bounds.x`),
      y: exactInteger(panelBounds.y, 160, `${label}.panel_bounds.y`),
      width: exactInteger(panelBounds.width, 1280, `${label}.panel_bounds.width`),
      height: exactInteger(panelBounds.height, 704, `${label}.panel_bounds.height`),
    }),
    slots: Object.freeze(parsedSlots),
  });
}
