// Tileset role mapping for the 12×4 grid.
//
// The pipeline produces tileset_<tag>.png at 2400×800 with cells in a 12×4
// grid (200×200 each). Per docs/spec/tileset.md the "compact 4×4 essentials"
// roles map onto the *first 4 columns* of each row; the remaining 8 columns
// in our 12-wide sheet are alternate styles / variants of the same role.
// We pick column 0 from each row for the canonical role.
//
// Row 1 — top surface       (cols: TL, top-mid, TR, top-single)
// Row 2 — slopes + inner    (cols: slope_up, slope_down, inner_TL, inner_TR)
// Row 3 — sides + bottom    (cols: side_L, side_R, bot_L, bot_R)
// Row 4 — fill + platform   (cols: interior_fill, plat_L, plat_M, plat_R)

export type TileRole =
  | "top_left"
  | "top_mid"
  | "top_right"
  | "top_single"
  | "slope_up"
  | "slope_down"
  | "inner_tl"
  | "inner_tr"
  | "side_left"
  | "side_right"
  | "bot_left"
  | "bot_right"
  | "fill"
  | "plat_left"
  | "plat_mid"
  | "plat_right";

// Each cell in the 12×4 sheet is identified by (row, col).
// We map to the first 4 cols of each row for the canonical roles, but we
// give each role 3 alternate cells (cols 4..7 and 8..11) by index modulo 4
// for visual variety.
const ROLE_TO_CELL: Record<TileRole, { row: number; col: number }> = {
  top_left:    { row: 0, col: 0 },
  top_mid:     { row: 0, col: 1 },
  top_right:   { row: 0, col: 2 },
  top_single:  { row: 0, col: 3 },
  slope_up:    { row: 1, col: 0 },
  slope_down:  { row: 1, col: 1 },
  inner_tl:    { row: 1, col: 2 },
  inner_tr:    { row: 1, col: 3 },
  side_left:   { row: 2, col: 0 },
  side_right:  { row: 2, col: 1 },
  bot_left:    { row: 2, col: 2 },
  bot_right:   { row: 2, col: 3 },
  fill:        { row: 3, col: 0 },
  plat_left:   { row: 3, col: 1 },
  plat_mid:    { row: 3, col: 2 },
  plat_right:  { row: 3, col: 3 },
};

export const TILESET_ROWS = 4;
export const TILESET_COLS = 12;

export function cellRectFor(
  role: TileRole,
  sheetW: number,
  sheetH: number,
  variant: number = 0,
): { x: number; y: number; w: number; h: number } {
  const cellW = Math.floor(sheetW / TILESET_COLS);
  const cellH = Math.floor(sheetH / TILESET_ROWS);
  const base = ROLE_TO_CELL[role];
  // Pick a variant column that lives in same row; mod 3 across cols 0/4/8.
  const colVariant = base.col + (variant % 3) * 4;
  const col = Math.min(TILESET_COLS - 1, colVariant);
  return {
    x: col * cellW,
    y: base.row * cellH,
    w: cellW,
    h: cellH,
  };
}

import type { SlopeKind } from "./heightmap";

/**
 * Pick a tile role for a given (column, row-from-surface) of the rendered
 * ground band, based on the column's slope kind and how deep below the
 * surface this row is.
 *
 * - depth=0    → surface row (top_left / top_mid / top_right / slope_*)
 * - depth=1+   → interior fill (or side edges when adjacent column is air)
 */
export function pickRole(
  slope: SlopeKind,
  depth: number,
  isLeftEdge: boolean,
  isRightEdge: boolean,
): TileRole {
  if (depth === 0) {
    if (slope === "rise_r") return "slope_up";
    if (slope === "fall_r") return "slope_down";
    if (slope === "fall_l") return "slope_down";
    if (slope === "rise_l") return "slope_up";
    if (isLeftEdge && isRightEdge) return "top_single";
    if (isLeftEdge) return "top_left";
    if (isRightEdge) return "top_right";
    return "top_mid";
  }
  if (isLeftEdge) return "side_left";
  if (isRightEdge) return "side_right";
  return "fill";
}
