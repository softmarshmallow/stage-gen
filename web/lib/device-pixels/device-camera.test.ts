import { describe, expect, test } from "bun:test";
import {
  MAX_DEVICE_PIXEL_SCALE,
  applyDeviceZoom,
  centeredScroll,
  deviceCameraBounds,
  deviceFollowOffset,
  deviceGameSize,
  devicePixelScale,
  deviceZoomFor,
  logicalWorldView,
  midpointOffset,
} from "./device-camera";

const LOGICAL = Object.freeze({ width: 1280, height: 720 });
const SCALES = [1, 1.25, 1.5, 2, 2.625, 3] as const;

/** Phaser's `Camera.preRender` projection along one axis: zoom about the origin, then scroll. */
function phaserProject(
  camera: Readonly<{ width: number; originX: number; zoom: number; scrollX: number }>,
  worldX: number,
  scrollFactor: number,
): number {
  const origin = camera.width * camera.originX;
  return origin + camera.zoom * (worldX - camera.scrollX * scrollFactor - origin);
}

/** Phaser's `BaseCamera.clampX`, verbatim. */
function phaserClampX(
  x: number,
  bounds: Readonly<{ x: number; width: number }>,
  camera: Readonly<{ width: number; zoom: number }>,
): number {
  const dw = camera.width / camera.zoom;
  const bx = bounds.x + (dw - camera.width) / 2;
  const bw = Math.max(bx, bx + bounds.width - dw);
  return x < bx ? bx : x > bw ? bw : x;
}

/** Whether Phaser's dead zone, centered on its midpoint, contains a followed x. */
function phaserDeadZoneContains(
  followX: number,
  camera: Readonly<{ width: number; scrollX: number }>,
  deadZoneWidth: number,
): boolean {
  const mid = camera.scrollX + camera.width / 2;
  return followX >= mid - deadZoneWidth / 2 && followX <= mid + deadZoneWidth / 2;
}

function fakeCamera(scale: number) {
  const canvas = deviceGameSize(LOGICAL, scale);
  const state = { originX: 0.5, originY: 0.5, zoomX: 1, zoomY: 1 };
  return {
    canvas,
    state,
    camera: {
      width: canvas.width,
      height: canvas.height,
      setOrigin(x: number, y?: number) {
        state.originX = x;
        state.originY = y ?? x;
      },
      setZoom(x: number, y?: number) {
        state.zoomX = x;
        state.zoomY = y ?? x;
      },
    },
  };
}

describe("device pixel scale", () => {
  test("is one without a ratio, for a broken one, and below one", () => {
    expect(devicePixelScale(undefined)).toBe(1);
    expect(devicePixelScale(Number.NaN)).toBe(1);
    expect(devicePixelScale(0.5)).toBe(1);
  });

  test("passes an ordinary ratio through and caps an extreme one", () => {
    expect(devicePixelScale(2)).toBe(2);
    expect(devicePixelScale(2.625)).toBe(2.625);
    expect(devicePixelScale(4)).toBe(MAX_DEVICE_PIXEL_SCALE);
  });

  test("sizes the canvas in whole device pixels", () => {
    expect(deviceGameSize(LOGICAL, 2)).toEqual({ width: 2560, height: 1440 });
    expect(deviceGameSize({ width: 960, height: 540 }, 4 / 3)).toEqual({ width: 1280, height: 720 });
    expect(() => deviceGameSize(LOGICAL, 0.5)).toThrow();
  });
});

describe("device zoom camera", () => {
  test("zooms about the top-left by exactly the canvas-to-design ratio", () => {
    for (const scale of SCALES) {
      const { camera, state, canvas } = fakeCamera(scale);
      const zoom = applyDeviceZoom(camera, LOGICAL);
      expect(state.originX).toBe(0);
      expect(state.originY).toBe(0);
      expect(state.zoomX).toBe(canvas.width / LOGICAL.width);
      expect(state.zoomY).toBe(canvas.height / LOGICAL.height);
      expect(zoom).toEqual(deviceZoomFor(canvas, LOGICAL));
    }
  });

  test("a screen-locked object lands at its design position in device pixels", () => {
    for (const scale of SCALES) {
      const { camera, state } = fakeCamera(scale);
      applyDeviceZoom(camera, LOGICAL);
      const projected = phaserProject(
        { width: camera.width, originX: state.originX, zoom: state.zoomX, scrollX: 4321 },
        300,
        0,
      );
      expect(projected).toBeCloseTo(300 * state.zoomX, 9);
    }
  });

  test("the default center origin would have displaced that same object", () => {
    const { camera, state } = fakeCamera(2);
    camera.setZoom(2);
    const projected = phaserProject(
      { width: camera.width, originX: state.originX, zoom: state.zoomX, scrollX: 0 },
      300,
      0,
    );
    expect(projected).not.toBeCloseTo(600, 9);
  });

  test("a world object projects to zoom times its scroll-relative position", () => {
    for (const scale of SCALES) {
      const { camera, state } = fakeCamera(scale);
      applyDeviceZoom(camera, LOGICAL);
      const projected = phaserProject(
        { width: camera.width, originX: state.originX, zoom: state.zoomX, scrollX: 1000 },
        1640,
        1,
      );
      expect(projected).toBeCloseTo(640 * state.zoomX, 9);
    }
  });

  test("scale one is the identity for every midpoint helper", () => {
    const { canvas } = fakeCamera(1);
    const midpoint = midpointOffset(canvas, LOGICAL);
    expect(midpoint).toEqual({ x: 0, y: 0 });
    const bounds = { x: 0, y: -400, width: 12_800, height: 1120 };
    expect(deviceCameraBounds(bounds, midpoint)).toEqual(bounds);
    expect(deviceFollowOffset({ x: 0, y: 50 }, midpoint)).toEqual({ x: 0, y: 50 });
  });
});

describe("midpoint helpers under device zoom", () => {
  test("bounds clamp admits exactly the design-space scroll range", () => {
    const bounds = { x: 0, y: 0, width: 12_800, height: 720 };
    for (const scale of SCALES) {
      const { camera, state, canvas } = fakeCamera(scale);
      applyDeviceZoom(camera, LOGICAL);
      const shifted = deviceCameraBounds(bounds, midpointOffset(canvas, LOGICAL));
      const view = { width: camera.width, zoom: state.zoomX };
      expect(phaserClampX(-500, shifted, view)).toBeCloseTo(0, 9);
      expect(phaserClampX(5000, shifted, view)).toBeCloseTo(5000, 9);
      expect(phaserClampX(1e9, shifted, view)).toBeCloseTo(12_800 - 1280, 9);
    }
  });

  test("a world narrower than the viewport pins the scroll to its left edge", () => {
    const bounds = { x: 0, y: 0, width: 800, height: 720 };
    const { camera, state, canvas } = fakeCamera(2);
    applyDeviceZoom(camera, LOGICAL);
    const shifted = deviceCameraBounds(bounds, midpointOffset(canvas, LOGICAL));
    expect(phaserClampX(300, shifted, { width: camera.width, zoom: state.zoomX })).toBe(0);
  });

  test("the follow offset keeps the dead zone in design screen space", () => {
    const deadZoneWidth = 300;
    for (const scale of SCALES) {
      const { camera, canvas } = fakeCamera(scale);
      applyDeviceZoom(camera, LOGICAL);
      const follow = deviceFollowOffset({ x: 0, y: 50 }, midpointOffset(canvas, LOGICAL));
      const scrollX = 2000;
      const view = { width: camera.width, scrollX };
      // Player projected to the design-space center, and just inside either edge of the zone.
      for (const screenX of [640, 640 - 149, 640 + 149]) {
        expect(phaserDeadZoneContains(scrollX + screenX - follow.x, view, deadZoneWidth)).toBe(true);
      }
      for (const screenX of [640 - 151, 640 + 151]) {
        expect(phaserDeadZoneContains(scrollX + screenX - follow.x, view, deadZoneWidth)).toBe(false);
      }
    }
  });

  test("the centered scroll matches Phaser's own follow snap at scale one", () => {
    const target = { x: 500, y: 400 };
    const offset = { x: 0, y: 50 };
    const snap = centeredScroll(target, offset, LOGICAL);
    expect(snap.scrollX).toBe(target.x - offset.x - LOGICAL.width / 2);
    expect(snap.scrollY).toBe(target.y - offset.y - LOGICAL.height / 2);
    // Under a top-left origin that scroll puts the target at the design-space center.
    const { camera, state } = fakeCamera(3);
    applyDeviceZoom(camera, LOGICAL);
    const projected = phaserProject(
      { width: camera.width, originX: state.originX, zoom: state.zoomX, scrollX: snap.scrollX },
      target.x,
      1,
    );
    expect(projected).toBeCloseTo(640 * state.zoomX, 9);
  });

  test("the logical world view spans one design space from the scroll", () => {
    expect(logicalWorldView({ scrollX: 100, scrollY: -20 }, LOGICAL)).toEqual({
      left: 100,
      top: -20,
      right: 1380,
      bottom: 700,
    });
  });
});
