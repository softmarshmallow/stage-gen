/** The world box the prepared scene hands Phaser's own player-follow camera. */

import type { PreparedCameraAxis } from "@/lib/manifest/prepared-manifest";

/**
 * The world box the camera is allowed to move inside, from the map's declared axes.
 *
 * This is the whole of axis enablement. The follow itself is unconditional - the scene asks
 * Phaser to track the player on both axes with one dead zone - so an axis is switched off by
 * giving the camera no room to travel along it rather than by a second code path. A map with no
 * vertical axis gets a box exactly one viewport tall, and Phaser's own clamp then pins the camera
 * to the floor for free.
 *
 * `terrainTopY` and `groundBaselineY` are world coordinates from the terrain projection, so the
 * vertical box is the authored grid itself: every row a designer may build on is reachable, and
 * nothing above or below it is.
 */
export function cameraWorldBounds(input: Readonly<{
  followAxes: readonly PreparedCameraAxis[];
  worldWidth: number;
  terrainTopY: number;
  groundBaselineY: number;
  viewportHeight: number;
}>): Readonly<{ x: number; y: number; width: number; height: number }> {
  for (const value of [
    input.worldWidth,
    input.terrainTopY,
    input.groundBaselineY,
    input.viewportHeight,
  ]) {
    if (!Number.isFinite(value)) throw new Error("camera bounds inputs must be finite");
  }
  if (input.worldWidth <= 0 || input.viewportHeight <= 0) {
    throw new Error("camera world width and viewport height must be positive");
  }
  if (input.groundBaselineY <= input.terrainTopY) {
    throw new Error("camera bounds require a floor below the top of the terrain");
  }
  const followsVertically = input.followAxes.includes("y");
  return Object.freeze({
    x: 0,
    y: followsVertically ? input.terrainTopY : 0,
    width: input.worldWidth,
    height: followsVertically
      ? input.groundBaselineY - input.terrainTopY
      : input.viewportHeight,
  });
}
