/** Deterministic player-follow camera framing for the optional scrolling adapter. */

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
