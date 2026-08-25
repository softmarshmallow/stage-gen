import { describe, expect, test } from "bun:test";
import {
  HORIZONTAL_CAMERA_DEAD_ZONE,
  horizontalCameraScrollX,
} from "./camera-follow";

const VIEWPORT_WIDTH = 1280;
const WORLD_WIDTH = 12_800;

function projectedX(targetX: number, scrollX: number, zoom: number): number {
  const originX = VIEWPORT_WIDTH / 2;
  return originX + (targetX - scrollX - originX) * zoom;
}

describe("horizontal player-follow dead zone", () => {
  test("holds the camera while the target remains inside the soft zone", () => {
    expect(
      horizontalCameraScrollX({
        currentScrollX: 1000,
        targetX: 1640,
        zoom: 1,
        viewportWidth: VIEWPORT_WIDTH,
        worldWidth: WORLD_WIDTH,
      }),
    ).toBe(1000);
  });

  test.each([
    { targetX: 1400, boundary: HORIZONTAL_CAMERA_DEAD_ZONE.leftViewportRatio },
    { targetX: 1840, boundary: HORIZONTAL_CAMERA_DEAD_ZONE.rightViewportRatio },
  ])("tracks exactly to the crossed $boundary boundary", ({ targetX, boundary }) => {
    const next = horizontalCameraScrollX({
      currentScrollX: 1000,
      targetX,
      zoom: 1,
      viewportWidth: VIEWPORT_WIDTH,
      worldWidth: WORLD_WIDTH,
    });
    expect(projectedX(targetX, next, 1)).toBe(VIEWPORT_WIDTH * boundary);
  });

  test("preserves screen-space framing under zoom and clamps to world bounds", () => {
    const zoom = 1.25;
    const minimumScrollX = (VIEWPORT_WIDTH / zoom - VIEWPORT_WIDTH) / 2;
    const maximumScrollX =
      minimumScrollX + WORLD_WIDTH - VIEWPORT_WIDTH / zoom;
    const next = horizontalCameraScrollX({
      currentScrollX: 1000,
      targetX: 1900,
      zoom,
      viewportWidth: VIEWPORT_WIDTH,
      worldWidth: WORLD_WIDTH,
    });
    expect(projectedX(1900, next, zoom)).toBe(
      VIEWPORT_WIDTH * HORIZONTAL_CAMERA_DEAD_ZONE.rightViewportRatio,
    );
    expect(
      horizontalCameraScrollX({
        currentScrollX: -100,
        targetX: -50,
        zoom,
        viewportWidth: VIEWPORT_WIDTH,
        worldWidth: WORLD_WIDTH,
      }),
    ).toBe(minimumScrollX);
    expect(
      horizontalCameraScrollX({
        currentScrollX: WORLD_WIDTH,
        targetX: WORLD_WIDTH + 50,
        zoom,
        viewportWidth: VIEWPORT_WIDTH,
        worldWidth: WORLD_WIDTH,
      }),
    ).toBe(maximumScrollX);
  });

  test("rejects non-finite and non-positive camera geometry", () => {
    expect(() =>
      horizontalCameraScrollX({
        currentScrollX: 0,
        targetX: Number.NaN,
        zoom: 1,
        viewportWidth: VIEWPORT_WIDTH,
        worldWidth: WORLD_WIDTH,
      }),
    ).toThrow("finite");
    expect(() =>
      horizontalCameraScrollX({
        currentScrollX: 0,
        targetX: 0,
        zoom: 0,
        viewportWidth: VIEWPORT_WIDTH,
        worldWidth: WORLD_WIDTH,
      }),
    ).toThrow("positive");
  });
});
