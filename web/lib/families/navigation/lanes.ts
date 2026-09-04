// Where a body may walk without leaving the ground.
//
// One derivation, and there were two. The graph cut the heightfield into
// maximal runs of columns sharing one surface; the wandering creature expanded
// left and right from its spawn column while the *height* matched the spawn's.
// Those are the same rule read two ways — a run of adjacent columns whose
// surfaces agree — and the reason it mattered that they were separate is that
// only one of them was ever checked against the walk the controller actually
// performs. `resolveTerrainWalk` refuses any column standing above the foot, so
// a lane is exactly a run the walk cannot be stopped inside, and a second
// derivation that drew the boundary elsewhere would put a creature where its
// own physics will not let it stand.
//
// Adjacent-connectivity is the form that subsumes both. At tolerance zero it is
// equality between neighbours, which chains to equality with the spawn, so the
// creature's run is recovered exactly; at a nonzero tolerance it is the graph's
// own cut. Nothing here is in pixels or in rows — a surface is whatever the
// caller measures surfaces in.

/** One level standing run, in columns. `endColumn` is exclusive. */
export interface LaneSpan {
  readonly startColumn: number;
  readonly endColumn: number;
  readonly surface: number;
}

export interface LaneField {
  readonly columns: number;
  surfaceAt: (column: number) => number;
  /** How far two neighbouring surfaces may differ and still be one lane. */
  readonly tolerance: number;
}

function assertField(field: LaneField): void {
  if (!Number.isSafeInteger(field.columns) || field.columns < 0) {
    throw new Error("a lane field must have a nonnegative integer column count");
  }
  if (!Number.isFinite(field.tolerance) || field.tolerance < 0) {
    throw new Error("a lane tolerance must be finite and nonnegative");
  }
}

function connected(field: LaneField, left: number, right: number): boolean {
  const a = field.surfaceAt(left);
  const b = field.surfaceAt(right);
  if (!Number.isFinite(a) || !Number.isFinite(b)) {
    throw new Error("lane surfaces must be finite");
  }
  return Math.abs(b - a) <= field.tolerance;
}

/** Every lane in the field, left to right. */
export function terrainLanes(field: LaneField): readonly LaneSpan[] {
  assertField(field);
  const lanes: LaneSpan[] = [];
  let start = 0;
  for (let column = 1; column <= field.columns; column += 1) {
    if (column < field.columns && connected(field, column - 1, column)) continue;
    lanes.push(
      Object.freeze({
        startColumn: start,
        endColumn: column,
        surface: field.surfaceAt(start),
      }),
    );
    start = column;
  }
  return Object.freeze(lanes);
}

/**
 * The one lane containing `column`, without deriving the others.
 *
 * The creature's form of the question, and it is answered by walking outward
 * rather than by cutting the whole field: a map is thousands of columns wide
 * and a creature only ever needs the shelf it is standing on. The span it
 * returns is the same span `terrainLanes` would have put it in — asserted, not
 * asserted-by-construction, because the two walks really are two walks.
 */
export function laneAtColumn(field: LaneField, column: number): LaneSpan {
  assertField(field);
  if (!Number.isSafeInteger(column) || column < 0 || column >= field.columns) {
    throw new Error("a lane column must lie inside the field");
  }
  let start = column;
  while (start > 0 && connected(field, start - 1, start)) start -= 1;
  let end = column;
  while (end + 1 < field.columns && connected(field, end, end + 1)) end += 1;
  return Object.freeze({
    startColumn: start,
    endColumn: end + 1,
    surface: field.surfaceAt(start),
  });
}
