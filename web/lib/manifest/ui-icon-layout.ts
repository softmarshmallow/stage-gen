// The resolved geometry the producer publishes for the preview icon grid.
//
// The glyph vocabulary is the layout's, not the game's: a consumer indexes the sheet by these
// names, so the parser holds the published cells to exactly this list in exactly this order. The
// cells themselves are declared geometry (every cell is one square of `cell_size`), while each
// `glyph_rect` is what the producer's gate detected inside it; the parser checks that the two
// agree with each other and with the canvas rather than trusting either.

import type { Rect } from "../shell/hud-geometry";

/** The sixteen glyphs the preview grid holds, in reading order. */
export const UI_PREVIEW_ICON_GLYPHS = Object.freeze([
  "play",
  "pause",
  "close",
  "menu",
  "gear",
  "home",
  "retry",
  "check",
  "search",
  "hand",
  "heart",
  "star",
  "arrow_left",
  "arrow_right",
  "sound_on",
  "sound_off",
] as const);

export type UiIconGlyph = (typeof UI_PREVIEW_ICON_GLYPHS)[number];

export const UI_PREVIEW_ICONS_ROLE = "preview_icons";
export const UI_PREVIEW_ICONS_LAYOUT = "icon_grid_4x4_1024_preview_v1";
export const UI_ICON_ALPHA_POLICY = "transparent_exterior_opaque_glyph_v1";

export type UiIconCell = Readonly<{
  glyph: UiIconGlyph;
  /** The published cell: what a consumer cuts as one frame and scales as the glyph's box. */
  cell: Rect;
  /** The detected bounds of the drawn glyph, inside `cell`. */
  glyph_rect: Rect;
}>;

export type UiIconSetLayout = Readonly<{
  role: typeof UI_PREVIEW_ICONS_ROLE;
  layout: typeof UI_PREVIEW_ICONS_LAYOUT;
  scale_mode: "fixed";
  alpha_policy: typeof UI_ICON_ALPHA_POLICY;
  /** Sheet pixels per screen pixel: `cell_size / draw_scale` is the size the set was drawn for. */
  draw_scale: number;
  canvas: Readonly<{ width: number; height: number }>;
  cell_size: number;
  cells: readonly UiIconCell[];
}>;

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

/** Parse the published icon grid, refusing a vocabulary or geometry that disagrees with itself. */
export function parseUiIconSetLayout(value: unknown, label = "ui.preview_icons"): UiIconSetLayout {
  const source = record(value, label);
  if (source.role !== UI_PREVIEW_ICONS_ROLE) throw new Error(`${label}.role must be preview_icons`);
  if (source.layout !== UI_PREVIEW_ICONS_LAYOUT) throw new Error(`${label}.layout is invalid`);
  if (source.scale_mode !== "fixed") throw new Error(`${label}.scale_mode is invalid`);
  if (source.alpha_policy !== UI_ICON_ALPHA_POLICY) {
    throw new Error(`${label}.alpha_policy is invalid`);
  }
  const drawScale = integer(source.draw_scale, `${label}.draw_scale`, 1);
  const canvasRecord = record(source.canvas, `${label}.canvas`);
  const canvas = Object.freeze({
    width: integer(canvasRecord.width, `${label}.canvas.width`, 1),
    height: integer(canvasRecord.height, `${label}.canvas.height`, 1),
  });
  const cellSize = integer(source.cell_size, `${label}.cell_size`, 1);
  if (!Array.isArray(source.cells) || source.cells.length !== UI_PREVIEW_ICON_GLYPHS.length) {
    throw new Error(`${label}.cells must publish exactly ${UI_PREVIEW_ICON_GLYPHS.length} cells`);
  }
  const canvasRect: Rect = { x: 0, y: 0, width: canvas.width, height: canvas.height };
  const cells = source.cells.map((entry, index): UiIconCell => {
    const cellLabel = `${label}.cells[${index}]`;
    const cellRecord = record(entry, cellLabel);
    const glyph = UI_PREVIEW_ICON_GLYPHS[index];
    if (cellRecord.glyph !== glyph) throw new Error(`${cellLabel}.glyph must be ${glyph}`);
    const cell = rect(cellRecord.cell, `${cellLabel}.cell`);
    if (cell.width !== cellSize || cell.height !== cellSize) {
      throw new Error(`${cellLabel}.cell is not one ${cellSize}px square`);
    }
    if (!inside(cell, canvasRect)) throw new Error(`${cellLabel}.cell leaves the canvas`);
    const glyphRect = rect(cellRecord.glyph_rect, `${cellLabel}.glyph_rect`);
    if (!inside(glyphRect, cell)) throw new Error(`${cellLabel}.glyph_rect leaves the cell`);
    return Object.freeze({ glyph, cell, glyph_rect: glyphRect });
  });
  return Object.freeze({
    role: UI_PREVIEW_ICONS_ROLE,
    layout: UI_PREVIEW_ICONS_LAYOUT,
    scale_mode: "fixed",
    alpha_policy: UI_ICON_ALPHA_POLICY,
    draw_scale: drawScale,
    canvas,
    cell_size: cellSize,
    cells: Object.freeze(cells),
  });
}

/** The cell published for `glyph`. A glyph the grid does not hold is a contract violation. */
export function uiIconCellFor(layout: UiIconSetLayout, glyph: UiIconGlyph): UiIconCell {
  const cell = layout.cells.find((entry) => entry.glyph === glyph);
  if (!cell) throw new Error(`the icon grid publishes no ${glyph} cell`);
  return cell;
}

/** The on-screen size the set was drawn for: one cell at the published density. */
export function uiIconNativeSize(layout: UiIconSetLayout): number {
  return layout.cell_size / layout.draw_scale;
}
