// Where the ground is, from the one rule that decides it.
//
// A column carries a body only when its ground stack grows up from the bottom
// row; the surface is the top cell of that stack, and a floating cell above a
// gap is scenery. That sentence was written three times in this tree, in three
// directions — the runner read an occupancy grid and answered a *row*, the
// platformer read the same grid and answered a *height*, and the terrain atlas
// went the other way and rebuilt a grid from heights — plus a fourth time as an
// inline `row >= rows - heights[column]` predicate inside the platformer's
// floating-platform scan. They are one rule seen from four sides, and this is
// the one implementation of it.
//
// Everything here is **generic over the length unit**, which is the whole
// reason the two genres can share it. A grid cell is a cell; whether the body
// standing on it measures in rows (the runner's avatar lives in the occupancy
// grid itself) or in pixels (the platformer projects the grid onto a pixel
// datum) is a projection, and `surfaceDatum` is that projection. Nothing in
// this file knows which unit it is being asked about.

/**
 * A rectangular occupancy grid, however the genre stores its cells.
 *
 * Row 0 is the top and rows grow downward, which is the orientation both
 * genres' authored occupancy already uses and the orientation the physics
 * integrates in.
 */
export interface OccupancyGrid {
  readonly rows: number;
  readonly columns: number;
  filled(row: number, column: number): boolean;
}

/** Read an authored grid of `"0"`/`"1"` row strings. */
export function stringOccupancy(rows: readonly string[]): OccupancyGrid {
  return {
    rows: rows.length,
    columns: rows[0]?.length ?? 0,
    filled: (row, column) => rows[row]?.[column] === "1",
  };
}

/** Read a parsed grid of boolean rows. */
export function booleanOccupancy(rows: readonly (readonly boolean[])[]): OccupancyGrid {
  return {
    rows: rows.length,
    columns: rows[0]?.length ?? 0,
    filled: (row, column) => rows[row]?.[column] === true,
  };
}

/**
 * The top cell of `column`'s bottom-contiguous stack, or null over a pit.
 *
 * The answer is a row index, which is the runner's own length unit; a genre
 * whose bodies measure in something else takes `bottomContiguousHeight` and
 * `surfaceDatum` instead.
 */
export function bottomContiguousSurfaceRow(
  grid: OccupancyGrid,
  column: number,
): number | null {
  const rows = grid.rows;
  if (!grid.filled(rows - 1, column)) return null;
  let surface = rows - 1;
  while (surface > 0 && grid.filled(surface - 1, column)) surface -= 1;
  return surface;
}

/**
 * How many cells `column`'s bottom-contiguous stack is tall; zero over a pit.
 *
 * The same walk as `bottomContiguousSurfaceRow` read from the other end, which
 * is why it is derived from it rather than written a second time.
 */
export function bottomContiguousHeight(grid: OccupancyGrid, column: number): number {
  const surface = bottomContiguousSurfaceRow(grid, column);
  return surface === null ? 0 : grid.rows - surface;
}

/** Every column's stack height, left to right. */
export function bottomContiguousHeights(grid: OccupancyGrid): readonly number[] {
  return Object.freeze(
    Array.from({ length: grid.columns }, (_, column) => bottomContiguousHeight(grid, column)),
  );
}

/**
 * Whether `row` belongs to `column`'s bottom stack, given that stack's height.
 *
 * The membership predicate on its own, because two callers need it without
 * needing the walk: the atlas projects heights back into a grid, and the
 * platformer's floating-platform scan asks the question per cell while it is
 * already holding the heights.
 */
export function belongsToBottomStack(row: number, rows: number, height: number): boolean {
  return row >= rows - height;
}

/**
 * Rebuild an occupancy grid from column heights.
 *
 * The inverse projection, and the third of the three writings: a heightfield
 * has no overhangs by construction, so the grid it implies is exactly the
 * membership predicate evaluated over every cell.
 */
export function bottomContiguousGrid(
  heights: readonly number[],
): readonly (readonly boolean[])[] {
  const rows = Math.max(0, ...heights);
  return Object.freeze(
    Array.from({ length: rows }, (_, row) =>
      Object.freeze(heights.map((height) => belongsToBottomStack(row, rows, height))),
    ),
  );
}

/**
 * Project a stack height onto the length unit a body integrates in.
 *
 * `baseline` is where a zero-height column's surface sits and `tile` is how far
 * one cell reaches from it, both in the caller's unit. A genre whose bodies
 * live in the grid itself does not call this at all — for the runner the
 * surface row *is* the surface — which is the point of the unit being a
 * parameter rather than a fact of the family.
 */
export function surfaceDatum(height: number, tile: number, baseline: number): number {
  return baseline - height * tile;
}
