import type { PreparedMap } from "./prepared-manifest";
import { climbableVisualWidth } from "./prepared-climbable";
import { parseTerrainOccupancy } from "./terrain-atlas";
import { terrainSurfaceY } from "./terrain";
import {
  createVerticalWorld,
  CLIMBABLE_VISUAL_OVERSHOOT,
  type UpperPlatform,
  type VerticalWorld,
} from "./vertical";

export type PreparedTerrainWorld = Readonly<{
  occupancy: readonly (readonly boolean[])[];
  columns: number;
  rows: number;
  worldWidth: number;
  topY: number;
  heights: readonly number[];
  verticalWorld: VerticalWorld;
}>;

function bottomContiguousHeights(
  occupancy: readonly (readonly boolean[])[],
): readonly number[] {
  const rows = occupancy.length;
  const columns = occupancy[0]!.length;
  return Object.freeze(
    Array.from({ length: columns }, (_, column) => {
      let height = 0;
      for (let row = rows - 1; row >= 0 && occupancy[row]![column]; row -= 1) {
        height += 1;
      }
      return height;
    }),
  );
}

function floatingPlatforms(
  occupancy: readonly (readonly boolean[])[],
  heights: readonly number[],
  tilePixels: number,
  baselineY: number,
): readonly Omit<UpperPlatform, "thickness">[] {
  const rows = occupancy.length;
  const columns = occupancy[0]!.length;
  const platforms: Omit<UpperPlatform, "thickness">[] = [];
  for (let row = 0; row < rows; row += 1) {
    let column = 0;
    while (column < columns) {
      const belongsToGround = row >= rows - heights[column]!;
      const exposedFloatingSurface =
        occupancy[row]![column]! &&
        !belongsToGround &&
        (row === 0 || !occupancy[row - 1]![column]);
      if (!exposedFloatingSurface) {
        column += 1;
        continue;
      }
      const start = column;
      column += 1;
      while (column < columns) {
        const nextBelongsToGround = row >= rows - heights[column]!;
        if (
          !occupancy[row]![column] ||
          nextBelongsToGround ||
          (row > 0 && occupancy[row - 1]![column])
        ) {
          break;
        }
        column += 1;
      }
      const end = column;
      const deckY = baselineY - (rows - row) * tilePixels;
      platforms.push({
        id: `terrain-platform-r${row}-c${start}`,
        left: start * tilePixels,
        right: end * tilePixels,
        deckY,
        tier: Math.max(1, Math.round((baselineY - deckY) / tilePixels)),
        sourceColumns: Object.freeze({ start, end }),
      });
    }
  }
  return Object.freeze(platforms);
}

/**
 * Compile one prepared map's authored occupancy into the mature controller's
 * heightfield, one-way floating-platform, and ladder geometry contracts.
 */
export function projectPreparedTerrainWorld(
  map: Pick<PreparedMap, "ground" | "climbable">,
  tilePixels: number,
  baselineY: number,
): PreparedTerrainWorld {
  if (
    !Number.isSafeInteger(tilePixels) ||
    tilePixels <= 0 ||
    !Number.isSafeInteger(baselineY)
  ) {
    throw new Error("prepared terrain dimensions must be safe integers");
  }
  const occupancy = parseTerrainOccupancy(map.ground.occupancy);
  const rows = occupancy.length;
  const columns = occupancy[0]!.length;
  const worldWidth = columns * tilePixels;
  const heights = bottomContiguousHeights(occupancy);
  const platforms = floatingPlatforms(
    occupancy,
    heights,
    tilePixels,
    baselineY,
  );
  const variantsById = new Map(
    (map.climbable?.variants ?? []).map((entry) => [entry.variant_id, entry]),
  );
  const climbables = (map.climbable?.placements ?? []).map((placement) => {
    const centerX = Math.round(placement.normalized_x * worldWidth);
    const column = Math.floor(centerX / tilePixels);
    const lowerSurfaceY = terrainSurfaceY(
      heights[column] ?? 0,
      tilePixels,
      baselineY,
    );
    const upperDeckY =
      lowerSurfaceY - placement.rise_tiles * tilePixels;
    const platform = platforms.find(
      (candidate) =>
        candidate.deckY === upperDeckY &&
        centerX >= candidate.left &&
        centerX < candidate.right,
    );
    if (!platform) {
      throw new Error(
        `prepared climbable ${placement.climbable_id} does not attach to an exposed four-tile platform`,
      );
    }
    const variant = variantsById.get(placement.variant_id);
    if (!variant) {
      throw new Error(
        `prepared climbable ${placement.climbable_id} names an undeclared variant`,
      );
    }
    const visualHeight =
      lowerSurfaceY - upperDeckY + CLIMBABLE_VISUAL_OVERSHOOT * 2;
    const visualWidth = climbableVisualWidth(variant.cell, visualHeight);
    return Object.freeze({
      id: placement.climbable_id,
      platformId: platform.id,
      variantId: placement.variant_id,
      role: variant.role,
      centerX,
      upperDeckY,
      lowerSurfaceY,
      visualWidth,
    });
  });
  const verticalWorld = createVerticalWorld({
    platforms,
    climbables,
    heights,
    tilePixels,
    baselineY,
    worldWidth,
  });
  return Object.freeze({
    occupancy,
    columns,
    rows,
    worldWidth,
    topY: baselineY - rows * tilePixels,
    heights,
    verticalWorld,
  });
}
