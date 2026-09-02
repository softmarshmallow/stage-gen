/**
 * Device-pixel rendering for a Phaser game whose design space is fixed in logical pixels.
 *
 * Phaser has no device-pixel-ratio support. The game size is the canvas backing store, and
 * `Scale.FIT` stretches that store over the parent element with the browser's bilinear filter,
 * so on a high-DPI screen every asset is drawn with fewer pixels than the screen has and then
 * blown up. The remedy has two halves that must agree: size the canvas in device pixels, and
 * zoom the camera by the same factor so the scene keeps addressing its design space.
 *
 * The zoom is applied about the camera origin, and this module moves that origin to the
 * top-left. Phaser's default center origin would displace every scroll-factor-zero object by
 * `(canvas - design) / 2` and shift the meaning of `scrollX` by the same amount. With a top-left
 * origin the projection is simply `device = zoom * (world - scroll)`, so HUD positions, direct
 * scroll writes, and parallax reads written in design pixels are untouched.
 *
 * What does not survive the origin move is Phaser's midpoint family - bounds clamping, follow
 * offsets and dead zones, `centerOn`, `worldView` - which still place the visible center half a
 * canvas right of the scroll. A scene that uses them shifts each by `midpointOffset`; a scene
 * that only sets scroll directly needs nothing. At a device pixel ratio of one every helper here
 * is the identity, which is what keeps automation captures byte-stable.
 */

export type LogicalSize = Readonly<{ width: number; height: number }>;
export type Offset = Readonly<{ x: number; y: number }>;
export type DeviceZoom = Readonly<{ x: number; y: number }>;
export type WorldBox = Readonly<{ x: number; y: number; width: number; height: number }>;
export type WorldView = Readonly<{ left: number; top: number; right: number; bottom: number }>;

/**
 * The largest backing-store multiplier a screen is granted. A 1280x720 design space at three
 * is 8.3 megapixels per frame, already past what a phone that reports 3.5 can fill at 60 Hz.
 */
export const MAX_DEVICE_PIXEL_SCALE = 3;

/** The canvas multiplier for a reported device pixel ratio: never below one, capped above. */
export function devicePixelScale(ratio: number | undefined): number {
  if (ratio === undefined || !Number.isFinite(ratio) || ratio <= 1) return 1;
  return Math.min(ratio, MAX_DEVICE_PIXEL_SCALE);
}

/** The multiplier for the screen this code is running on; one anywhere without a window. */
export function currentDevicePixelScale(): number {
  const ratio = typeof window === "undefined" ? undefined : window.devicePixelRatio;
  return devicePixelScale(ratio);
}

/** The Phaser game size for `logical` at `scale`, in whole device pixels. */
export function deviceGameSize(logical: LogicalSize, scale: number): LogicalSize {
  assertSize(logical, "logical size");
  if (!Number.isFinite(scale) || scale < 1) {
    throw new Error("device pixel scale must be a finite number of at least one");
  }
  return Object.freeze({
    width: Math.round(logical.width * scale),
    height: Math.round(logical.height * scale),
  });
}

/**
 * The exact zoom that maps `logical` onto a canvas of `canvas` size. Read back from the canvas
 * rather than from the ratio so rounding to whole device pixels never leaves a seam of
 * uncovered canvas at the right or bottom edge.
 */
export function deviceZoomFor(canvas: LogicalSize, logical: LogicalSize): DeviceZoom {
  assertSize(canvas, "canvas size");
  assertSize(logical, "logical size");
  return Object.freeze({ x: canvas.width / logical.width, y: canvas.height / logical.height });
}

/** The camera surface this module needs: Phaser's `Camera` satisfies it structurally. */
export type DeviceZoomCamera = {
  readonly width: number;
  readonly height: number;
  setOrigin(x: number, y?: number): unknown;
  setZoom(x: number, y?: number): unknown;
};

/**
 * Zoom `camera` so its canvas-sized viewport shows exactly `logical`, about the top-left. Call
 * once per scene in `create`; the camera is the scene's, so a map change inside the scene keeps
 * it.
 */
export function applyDeviceZoom(camera: DeviceZoomCamera, logical: LogicalSize): DeviceZoom {
  const zoom = deviceZoomFor(camera, logical);
  camera.setOrigin(0, 0);
  camera.setZoom(zoom.x, zoom.y);
  return zoom;
}

/**
 * How far Phaser's midpoint helpers sit from the true visible center once the origin is the
 * top-left: half the difference between the canvas and the design space, in design pixels.
 */
export function midpointOffset(canvas: LogicalSize, logical: LogicalSize): Offset {
  assertSize(canvas, "canvas size");
  assertSize(logical, "logical size");
  return Object.freeze({
    x: (canvas.width - logical.width) / 2,
    y: (canvas.height - logical.height) / 2,
  });
}

/** The box to hand `setBounds` so the clamp admits exactly the design-space scroll range. */
export function deviceCameraBounds(bounds: WorldBox, midpoint: Offset): WorldBox {
  return Object.freeze({
    x: bounds.x + midpoint.x,
    y: bounds.y + midpoint.y,
    width: bounds.width,
    height: bounds.height,
  });
}

/** The offset to hand `startFollow` so the dead zone stays where it was in design pixels. */
export function deviceFollowOffset(offset: Offset, midpoint: Offset): Offset {
  return Object.freeze({ x: offset.x - midpoint.x, y: offset.y - midpoint.y });
}

/**
 * The scroll that centers `target` (less its follow offset) in the design space: what Phaser's
 * own follow start would have snapped to under a center origin.
 */
export function centeredScroll(
  target: Offset,
  followOffset: Offset,
  logical: LogicalSize,
): Readonly<{ scrollX: number; scrollY: number }> {
  assertSize(logical, "logical size");
  return Object.freeze({
    scrollX: target.x - followOffset.x - logical.width / 2,
    scrollY: target.y - followOffset.y - logical.height / 2,
  });
}

/** The world rectangle on screen: one design space from the scroll, which `worldView` is not. */
export function logicalWorldView(
  camera: Readonly<{ scrollX: number; scrollY: number }>,
  logical: LogicalSize,
): WorldView {
  assertSize(logical, "logical size");
  return Object.freeze({
    left: camera.scrollX,
    top: camera.scrollY,
    right: camera.scrollX + logical.width,
    bottom: camera.scrollY + logical.height,
  });
}

function assertSize(size: LogicalSize, label: string): void {
  if (
    !Number.isFinite(size.width) ||
    !Number.isFinite(size.height) ||
    size.width <= 0 ||
    size.height <= 0
  ) {
    throw new Error(`${label} must have positive finite width and height`);
  }
}
