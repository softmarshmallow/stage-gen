// The resolved geometry the producer publishes for each nine-slice atlas role.
//
// Unlike the inventory panel, whose V1 geometry is fixed and checked number for number, an atlas
// role's cells are *detected* by the producer's gate (the model keeps a sheet's count and order
// but re-spaces its bodies), and its insets may be widened past the template guide to the end of
// the drawn corner ornament. So this parser checks shape and consistency — states in the declared
// order, every cell inside the canvas, every content rect equal to its cell minus the sheet
// insets — rather than a fixed table of coordinates.

import type { Rect } from "../shell/hud-geometry";

/** How a sheet's edge bands were admitted: rebuilt from one strip, or repeated end to end. */
export type BandFill = "stretch" | "tile";

/** Per-side corner widths, in sheet pixels. */
export type Insets = Readonly<{ left: number; top: number; right: number; bottom: number }>;

export type UiAtlasRoleName = "panel_frame" | "button_rect";

export type UiAtlasCell = Readonly<{
  state: string;
  cell: Rect;
  /** The geometric interior: the cell minus the sheet insets. */
  content_rect: Rect;
  /** The measured ornament-free interior, where text is safe. Inside `content_rect`. */
  safe_rect: Rect;
}>;

export type UiAtlasRoleLayout = Readonly<{
  role: UiAtlasRoleName;
  layout: string;
  scale_mode: "nine_slice";
  alpha_policy: "transparent_exterior_opaque_body_v1";
  band_fill: BandFill;
  /** Sheet pixels per screen pixel: lay slices out at this multiple, then scale down. */
  draw_scale: number;
  canvas: Readonly<{ width: number; height: number }>;
  insets: Insets;
  cells: readonly UiAtlasCell[];
}>;

export const UI_ATLAS_ALPHA_POLICY = "transparent_exterior_opaque_body_v1";

/** What each role promises: its layout identity and the states it publishes, in order. */
export const UI_ATLAS_ROLES: Readonly<
  Record<UiAtlasRoleName, Readonly<{ layout: string; states: readonly string[] }>>
> = Object.freeze({
  panel_frame: Object.freeze({
    layout: "nine_slice_panel_1024_v1",
    states: Object.freeze(["default"]),
  }),
  button_rect: Object.freeze({
    layout: "nine_slice_button_sheet_4x1024_v1",
    states: Object.freeze(["normal", "hover", "pressed", "disabled"]),
  }),
});

function record(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function integer(value: unknown, label: string, minimum = 0): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < minimum) {
    throw new Error(`${label} must be an integer of at least ${minimum}`);
  }
  return value;
}

function rect(value: unknown, label: string): Rect {
  const source = record(value, label);
  return Object.freeze({
    x: integer(source.x, `${label}.x`),
    y: integer(source.y, `${label}.y`),
    width: integer(source.width, `${label}.width`, 1),
    height: integer(source.height, `${label}.height`, 1),
  });
}

function inside(inner: Rect, outer: Rect): boolean {
  return (
    inner.x >= outer.x &&
    inner.y >= outer.y &&
    inner.x + inner.width <= outer.x + outer.width &&
    inner.y + inner.height <= outer.y + outer.height
  );
}

/** Parse one published atlas role, refusing geometry that does not agree with itself. */
export function parseUiAtlasRoleLayout(
  value: unknown,
  role: UiAtlasRoleName,
  label = `ui.${role}`,
): UiAtlasRoleLayout {
  const expected = UI_ATLAS_ROLES[role];
  const source = record(value, label);
  if (source.role !== role) throw new Error(`${label}.role must be ${role}`);
  if (source.layout !== expected.layout) throw new Error(`${label}.layout is invalid`);
  if (source.scale_mode !== "nine_slice") throw new Error(`${label}.scale_mode is invalid`);
  if (source.alpha_policy !== UI_ATLAS_ALPHA_POLICY) {
    throw new Error(`${label}.alpha_policy is invalid`);
  }
  if (source.band_fill !== "stretch" && source.band_fill !== "tile") {
    throw new Error(`${label}.band_fill is invalid`);
  }
  const drawScale = integer(source.draw_scale, `${label}.draw_scale`, 1);
  const canvasRecord = record(source.canvas, `${label}.canvas`);
  const canvas = Object.freeze({
    width: integer(canvasRecord.width, `${label}.canvas.width`, 1),
    height: integer(canvasRecord.height, `${label}.canvas.height`, 1),
  });
  const insetsRecord = record(source.insets, `${label}.insets`);
  const insets: Insets = Object.freeze({
    left: integer(insetsRecord.left, `${label}.insets.left`, 1),
    top: integer(insetsRecord.top, `${label}.insets.top`, 1),
    right: integer(insetsRecord.right, `${label}.insets.right`, 1),
    bottom: integer(insetsRecord.bottom, `${label}.insets.bottom`, 1),
  });
  if (!Array.isArray(source.cells) || source.cells.length !== expected.states.length) {
    throw new Error(`${label}.cells must publish exactly ${expected.states.length} cells`);
  }
  const canvasRect: Rect = { x: 0, y: 0, width: canvas.width, height: canvas.height };
  const cells = source.cells.map((entry, index): UiAtlasCell => {
    const cellLabel = `${label}.cells[${index}]`;
    const cellRecord = record(entry, cellLabel);
    if (cellRecord.state !== expected.states[index]) {
      throw new Error(`${cellLabel}.state must be ${expected.states[index]}`);
    }
    const cell = rect(cellRecord.cell, `${cellLabel}.cell`);
    const content = rect(cellRecord.content_rect, `${cellLabel}.content_rect`);
    if (!inside(cell, canvasRect)) throw new Error(`${cellLabel}.cell leaves the canvas`);
    const derived: Rect = {
      x: cell.x + insets.left,
      y: cell.y + insets.top,
      width: cell.width - insets.left - insets.right,
      height: cell.height - insets.top - insets.bottom,
    };
    if (derived.width < 1 || derived.height < 1) {
      throw new Error(`${cellLabel}.cell is smaller than the sheet insets`);
    }
    if (
      content.x !== derived.x ||
      content.y !== derived.y ||
      content.width !== derived.width ||
      content.height !== derived.height
    ) {
      throw new Error(`${cellLabel}.content_rect disagrees with the cell and insets`);
    }
    const safe = rect(cellRecord.safe_rect, `${cellLabel}.safe_rect`);
    if (!inside(safe, content)) throw new Error(`${cellLabel}.safe_rect leaves the content rect`);
    return Object.freeze({
      state: expected.states[index],
      cell,
      content_rect: content,
      safe_rect: safe,
    });
  });
  return Object.freeze({
    role,
    layout: expected.layout,
    scale_mode: "nine_slice",
    alpha_policy: UI_ATLAS_ALPHA_POLICY,
    band_fill: source.band_fill,
    draw_scale: drawScale,
    canvas,
    insets,
    cells: Object.freeze(cells),
  });
}

/** The cell published for `state`, or the first cell when the role has no such state. */
export function uiAtlasCellFor(layout: UiAtlasRoleLayout, state: string): UiAtlasCell {
  return layout.cells.find((cell) => cell.state === state) ?? layout.cells[0];
}
