/** Return the world-space Y coordinate of a terrain surface. */
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
  return baselineY - height * tilePixels;
}
