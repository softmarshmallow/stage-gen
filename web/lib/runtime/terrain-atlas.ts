// Consumer-owned occupancy, selection, import, collision, and draw-plan adapter
// for the locked 47-mask terrain atlas. Generation and slicing remain in Python.

import lookupContract from "./terrain-atlas-lookup.json";

export const TERRAIN_ATLAS_COLUMNS = 12;
export const TERRAIN_ATLAS_ROWS = 4;
export const TERRAIN_ATLAS_CELL_PX = 120;
export const TERRAIN_ATLAS_WIDTH = 1440;
export const TERRAIN_ATLAS_HEIGHT = 480;
export const TERRAIN_ATLAS_PLACEHOLDER = Object.freeze({ column: 10, row: 1 });

export type TerrainAtlasCoordinate = Readonly<{
  column: number;
  row: number;
}>;

export type TerrainAtlasCellPlan = Readonly<{
  mapColumn: number;
  mapRow: number;
  mask: string;
  atlas: TerrainAtlasCoordinate;
  frame: string;
  collision: "solid-cell";
}>;

export const TERRAIN_ATLAS_IMPORT = Object.freeze({
  topology: "terrain-atlas-3x3-minimal-v1" as const,
  columns: TERRAIN_ATLAS_COLUMNS,
  rows: TERRAIN_ATLAS_ROWS,
  cellPixels: TERRAIN_ATLAS_CELL_PX,
  filtering: "nearest" as const,
  textureBleedPaddingPixels: 0,
  dynamicInternalSeamRepair: false,
  collisionSource: "binary-map-occupancy" as const,
  smoothSlopes: "separate-contract-required" as const,
});

const rawEntries = lookupContract.lookup as Record<string, readonly number[]>;
const TERRAIN_LOOKUP = new Map<string, TerrainAtlasCoordinate>();
const coordinates = new Set<string>();
if (
  lookupContract.kind !== "terrain-atlas-3x3-minimal-lookup-v1" ||
  lookupContract.terrain_mask_count !== 47 ||
  lookupContract.mask_order.join(",") !== "nw,n,ne,w,center,e,sw,s,se" ||
  lookupContract.placeholder_cell.join(",") !== "10,1"
) {
  throw new Error("terrain atlas lookup identity is invalid");
}
for (const [mask, coordinate] of Object.entries(rawEntries)) {
  if (!/^[01]{9}$/.test(mask) || mask[4] !== "1" || coordinate.length !== 2) {
    throw new Error("terrain atlas lookup entry is invalid");
  }
  const [column, row] = coordinate;
  if (
    !Number.isSafeInteger(column) ||
    !Number.isSafeInteger(row) ||
    column < 0 ||
    column >= TERRAIN_ATLAS_COLUMNS ||
    row < 0 ||
    row >= TERRAIN_ATLAS_ROWS ||
    (column === TERRAIN_ATLAS_PLACEHOLDER.column &&
      row === TERRAIN_ATLAS_PLACEHOLDER.row)
  ) {
    throw new Error("terrain atlas lookup coordinate is invalid");
  }
  const coordinateKey = `${column},${row}`;
  if (TERRAIN_LOOKUP.has(mask) || coordinates.has(coordinateKey)) {
    throw new Error("terrain atlas lookup must be one-to-one");
  }
  TERRAIN_LOOKUP.set(mask, Object.freeze({ column, row }));
  coordinates.add(coordinateKey);
}
if (TERRAIN_LOOKUP.size !== 47 || coordinates.size !== 47) {
  throw new Error("terrain atlas lookup must contain 47 unique reachable entries");
}

function assertOccupancy(occupied: readonly (readonly boolean[])[]): void {
  if (
    occupied.length === 0 ||
    occupied[0].length === 0 ||
    occupied.some((row) => row.length !== occupied[0].length)
  ) {
    throw new Error("terrain occupancy must be a nonempty rectangle");
  }
}

export function terrainAtlasFrameName(coordinate: TerrainAtlasCoordinate): string {
  return `terrain_${coordinate.column}_${coordinate.row}`;
}

export function terrainPeeringMask(
  occupied: readonly (readonly boolean[])[],
  x: number,
  y: number,
): string {
  assertOccupancy(occupied);
  if (!Number.isSafeInteger(x) || !Number.isSafeInteger(y) || !occupied[y]?.[x]) {
    throw new Error("terrain peering mask requires an occupied map cell");
  }
  const at = (px: number, py: number) =>
    py >= 0 && py < occupied.length && px >= 0 && px < occupied[0].length
      ? Number(occupied[py][px])
      : 0;
  const n = at(x, y - 1);
  const e = at(x + 1, y);
  const s = at(x, y + 1);
  const w = at(x - 1, y);
  return [
    n && w && at(x - 1, y - 1),
    n,
    n && e && at(x + 1, y - 1),
    w,
    1,
    e,
    s && w && at(x - 1, y + 1),
    s,
    s && e && at(x + 1, y + 1),
  ].join("");
}

export function terrainAtlasCoordinateForMask(mask: string): TerrainAtlasCoordinate {
  const coordinate = TERRAIN_LOOKUP.get(mask);
  if (!coordinate) throw new Error(`terrain atlas lookup has no entry for ${mask}`);
  return coordinate;
}

export function parseTerrainOccupancy(rows: readonly string[]): readonly (readonly boolean[])[] {
  if (
    rows.length === 0 ||
    rows[0].length === 0 ||
    rows.some((row) => row.length !== rows[0].length || /[^01]/.test(row))
  ) {
    throw new Error("binary terrain rows must be a nonempty zero-one rectangle");
  }
  return Object.freeze(
    rows.map((row) => Object.freeze([...row].map((value) => value === "1"))),
  );
}

export function terrainAtlasPlan(
  occupied: readonly (readonly boolean[])[],
): readonly TerrainAtlasCellPlan[] {
  assertOccupancy(occupied);
  const result: TerrainAtlasCellPlan[] = [];
  for (let y = 0; y < occupied.length; y += 1) {
    for (let x = 0; x < occupied[0].length; x += 1) {
      if (!occupied[y][x]) continue;
      const mask = terrainPeeringMask(occupied, x, y);
      const atlas = terrainAtlasCoordinateForMask(mask);
      result.push(
        Object.freeze({
          mapColumn: x,
          mapRow: y,
          mask,
          atlas,
          frame: terrainAtlasFrameName(atlas),
          collision: "solid-cell" as const,
        }),
      );
    }
  }
  return Object.freeze(result);
}

export function bottomContiguousOccupancy(
  heights: readonly number[],
): readonly (readonly boolean[])[] {
  if (
    heights.length === 0 ||
    heights.some((height) => !Number.isSafeInteger(height) || height < 0)
  ) {
    throw new Error("terrain heights must be nonnegative safe integers");
  }
  const rows = Math.max(0, ...heights);
  return Object.freeze(
    Array.from({ length: rows }, (_, row) =>
      Object.freeze(heights.map((height) => row >= rows - height)),
    ),
  );
}

export function terrainAtlasLookupEntries(): readonly Readonly<{
  mask: string;
  coordinate: TerrainAtlasCoordinate;
}>[] {
  return Object.freeze(
    [...TERRAIN_LOOKUP.entries()].map(([mask, coordinate]) =>
      Object.freeze({ mask, coordinate }),
    ),
  );
}
