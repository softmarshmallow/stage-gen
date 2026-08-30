// Pure viewport math for the run canvas: pan, zoom about a point, fit, and
// the normalisation of raw wheel/trackpad deltas.
//
// The canvas is one transformed layer, not a scroll container, because a
// macOS trackpad's horizontal scroll over a scroller is the browser's
// back-navigation gesture. Owning the gesture means owning the arithmetic,
// so it lives here where it can be tested without a DOM.

export interface Viewport {
  readonly x: number;
  readonly y: number;
  readonly scale: number;
}

export interface Size {
  readonly width: number;
  readonly height: number;
}

export interface Point {
  readonly x: number;
  readonly y: number;
}

export const MIN_SCALE = 0.08;
export const MAX_SCALE = 2.5;

/** Fit leaves this much frame edge free, so chips never touch the bezel. */
const FIT_PADDING = 56;

/** Below this, chip labels stop being readable and the graph is a texture. */
export const LEGIBLE_SCALE = 0.3;

/** Wheel deltas arrive in lines or pages on some browsers; normalise to px. */
const LINE_PX = 16;
const PAGE_PX = 400;

/** One pinch notch is small; this maps it to a comfortable zoom rate. */
const ZOOM_SENSITIVITY = 0.01;

/** A mouse wheel with ctrl held reports whole notches: cap the jump. */
const MAX_ZOOM_DELTA_PX = 50;

export const IDENTITY_VIEWPORT: Viewport = { x: 0, y: 0, scale: 1 };

export function clampScale(scale: number): number {
  if (!Number.isFinite(scale)) return 1;
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
}

export function panBy(viewport: Viewport, dx: number, dy: number): Viewport {
  return { x: viewport.x + dx, y: viewport.y + dy, scale: viewport.scale };
}

/**
 * Zoom by `factor` while the content under the frame point `at` stays put —
 * the property that makes pinch feel like the graph and not the camera moved.
 */
export function zoomAt(viewport: Viewport, factor: number, at: Point): Viewport {
  const scale = clampScale(viewport.scale * factor);
  const applied = scale / viewport.scale;
  return {
    scale,
    x: at.x - (at.x - viewport.x) * applied,
    y: at.y - (at.y - viewport.y) * applied,
  };
}

/** Scale `content` to sit inside `frame`, centred, never magnified past 1:1. */
export function fitViewport(content: Size, frame: Size, padding: number = FIT_PADDING): Viewport {
  if (content.width <= 0 || content.height <= 0 || frame.width <= 0 || frame.height <= 0) {
    return IDENTITY_VIEWPORT;
  }
  const usableWidth = Math.max(1, frame.width - padding * 2);
  const usableHeight = Math.max(1, frame.height - padding * 2);
  const scale = clampScale(
    Math.min(1, usableWidth / content.width, usableHeight / content.height),
  );
  return {
    scale,
    x: (frame.width - content.width * scale) / 2,
    y: (frame.height - content.height * scale) / 2,
  };
}

/** Put a content-space point in the middle of `frame` at the current scale. */
export function centerOn(viewport: Viewport, point: Point, frame: Size): Viewport {
  return {
    scale: viewport.scale,
    x: frame.width / 2 - point.x * viewport.scale,
    y: frame.height / 2 - point.y * viewport.scale,
  };
}

/** Where a frame point lands in content space. Used by the tests as the oracle. */
export function toContent(viewport: Viewport, at: Point): Point {
  return { x: (at.x - viewport.x) / viewport.scale, y: (at.y - viewport.y) / viewport.scale };
}

/** Wheel/trackpad scroll, in device pixels whatever the browser reports in. */
export function wheelPanDelta(
  deltaX: number,
  deltaY: number,
  deltaMode: number,
): { readonly dx: number; readonly dy: number } {
  const unit = deltaMode === 1 ? LINE_PX : deltaMode === 2 ? PAGE_PX : 1;
  return { dx: deltaX * unit, dy: deltaY * unit };
}

/** A pinch (ctrl-flagged wheel) as a multiplicative zoom factor. */
export function wheelZoomFactor(deltaY: number, deltaMode: number): number {
  const { dy } = wheelPanDelta(0, deltaY, deltaMode);
  const capped = Math.max(-MAX_ZOOM_DELTA_PX, Math.min(MAX_ZOOM_DELTA_PX, dy));
  return Math.exp(-capped * ZOOM_SENSITIVITY);
}

/**
 * The camera a run opens with: the whole graph when it still reads at a
 * glance, otherwise its first column at a legible zoom. A 217-node graph
 * fitted to a laptop window is a texture, not a map — `fit` is one keypress
 * away for whoever wants the texture.
 */
export function initialViewport(
  content: Size,
  frame: Size,
  inset: Point = { x: FIT_PADDING, y: FIT_PADDING },
): Viewport {
  const fitted = fitViewport(content, frame);
  if (fitted.scale >= LEGIBLE_SCALE) return fitted;
  return { scale: LEGIBLE_SCALE, x: inset.x, y: inset.y };
}
