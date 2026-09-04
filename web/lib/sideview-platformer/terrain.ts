import { surfaceDatum } from "@/lib/families/sideview/traversal";

/**
 * Return the world-space Y coordinate of a terrain surface.
 *
 * The projection is the family's — a height off a datum, in whatever unit the
 * caller measures in. What this genre adds is the integer contract: its
 * heightfield steps in whole tiles off an integer baseline, and a fractional
 * one is a mis-authored map rather than a slope.
 */
export function terrainSurfaceY(
  height: number,
  tilePixels: number,
  baselineY: number,
): number {
  if (!Number.isSafeInteger(height) || height < 0) {
    throw new Error("terrain height must be a nonnegative safe integer");
  }
  if (!Number.isSafeInteger(tilePixels) || tilePixels <= 0) {
    throw new Error("terrain tile pixels must be a positive safe integer");
  }
  if (!Number.isSafeInteger(baselineY)) {
    throw new Error("terrain baseline must be a safe integer");
  }
  return surfaceDatum(height, tilePixels, baselineY);
}
