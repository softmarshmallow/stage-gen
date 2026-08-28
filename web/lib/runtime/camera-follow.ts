/** Deterministic player-follow camera framing for the optional scrolling adapter. */

import type { PreparedCameraAxis } from "./prepared-manifest";

export const HORIZONTAL_CAMERA_DEAD_ZONE = Object.freeze({
  leftViewportRatio: 0.375,
  rightViewportRatio: 0.625,
});

/**
 * Keep the tracked actor inside a screen-space dead zone and move only on boundary crossing.
 *
 * Phaser stores scroll in zoom-independent world coordinates. Projecting the target to screen
 * space before applying the soft-zone boundary keeps the same visible framing at every zoom.
 */
export function horizontalCameraScrollX(input: Readonly<{
  currentScrollX: number;
  targetX: number;
  zoom: number;
  viewportWidth: number;
  worldWidth: number;
}>): number {
  for (const value of [
    input.currentScrollX,
    input.targetX,
    input.zoom,
    input.viewportWidth,
    input.worldWidth,
  ]) {
    if (!Number.isFinite(value)) throw new Error("camera inputs must be finite");
  }
  if (input.zoom <= 0 || input.viewportWidth <= 0 || input.worldWidth <= 0) {
    throw new Error("camera zoom, viewport width, and world width must be positive");
  }

  const originX = input.viewportWidth / 2;
  const projectedX =
    originX + (input.targetX - input.currentScrollX - originX) * input.zoom;
  const left = input.viewportWidth * HORIZONTAL_CAMERA_DEAD_ZONE.leftViewportRatio;
  const right = input.viewportWidth * HORIZONTAL_CAMERA_DEAD_ZONE.rightViewportRatio;
  let next = input.currentScrollX;
  if (projectedX < left) {
    next = input.targetX - originX - (left - originX) / input.zoom;
  } else if (projectedX > right) {
    next = input.targetX - originX - (right - originX) / input.zoom;
  }

  // Phaser's scroll coordinate is center-origin under zoom: clampX permits a negative half-
  // gutter on the left and subtracts the same gutter from the right. Mirroring those bounds here
  // prevents preRender from silently changing a value this deterministic helper just returned.
  const visibleWorldWidth = input.viewportWidth / input.zoom;
  const minimumScrollX = (visibleWorldWidth - input.viewportWidth) / 2;
  const maximumScrollX = Math.max(
    minimumScrollX,
    minimumScrollX + input.worldWidth - visibleWorldWidth,
  );
  return Math.max(minimumScrollX, Math.min(maximumScrollX, next));
}

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
