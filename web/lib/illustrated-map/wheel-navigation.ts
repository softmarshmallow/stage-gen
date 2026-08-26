import type View from "ol/View.js";

export interface WheelNavigationInput {
  readonly ctrl_key: boolean;
  readonly shift_key: boolean;
  readonly delta_x: number;
  readonly delta_y: number;
  readonly delta_mode: number;
}

export type WheelNavigationIntent =
  | { readonly kind: "zoom"; readonly delta_zoom_levels: number }
  | { readonly kind: "ignore" }
  | {
      readonly kind: "pan";
      readonly delta_css_pixels: readonly [x: number, y: number];
    };

const DOM_DELTA_PIXEL = 0;
const DOM_DELTA_LINE = 1;
const DOM_DELTA_PAGE = 2;
const CSS_PIXELS_PER_LINE = 16;
const MAX_ZOOM_LEVELS_PER_EVENT = 1;
const CSS_PIXELS_PER_ZOOM_LEVEL = 100;

export function classifyWheelNavigation(
  input: WheelNavigationInput,
  viewportHeightCssPixels: number,
): WheelNavigationIntent {
  if (!Number.isFinite(input.delta_x) || !Number.isFinite(input.delta_y)) {
    return { kind: "ignore" };
  }

  let multiplier = 1;
  if (input.delta_mode === DOM_DELTA_LINE) {
    multiplier = CSS_PIXELS_PER_LINE;
  } else if (input.delta_mode === DOM_DELTA_PAGE) {
    multiplier = Math.max(1, viewportHeightCssPixels);
  } else if (input.delta_mode !== DOM_DELTA_PIXEL) {
    return { kind: "ignore" };
  }

  let deltaX = input.delta_x * multiplier;
  let deltaY = input.delta_y * multiplier;
  if (input.ctrl_key) {
    if (deltaY === 0) {
      return { kind: "ignore" };
    }
    return {
      kind: "zoom",
      delta_zoom_levels: Math.max(
        -MAX_ZOOM_LEVELS_PER_EVENT,
        Math.min(MAX_ZOOM_LEVELS_PER_EVENT, -deltaY / CSS_PIXELS_PER_ZOOM_LEVEL),
      ),
    };
  }
  if (input.shift_key && deltaX === 0) {
    deltaX = deltaY;
    deltaY = 0;
  }
  if (deltaX === 0 && deltaY === 0) {
    return { kind: "ignore" };
  }
  return { kind: "pan", delta_css_pixels: [deltaX, deltaY] };
}

export function screenPanToMapDelta(
  deltaCssPixels: readonly [x: number, y: number],
  resolution: number,
): [x: number, y: number] {
  if (!Number.isFinite(resolution) || resolution <= 0) {
    throw new Error("resolution must be a positive finite number");
  }
  return [deltaCssPixels[0] * resolution, -deltaCssPixels[1] * resolution];
}

export function panCenterFromCurrentView(
  currentCenter: readonly [x: number, y: number],
  deltaCssPixels: readonly [x: number, y: number],
  resolution: number,
): [x: number, y: number] {
  const [deltaX, deltaY] = screenPanToMapDelta(deltaCssPixels, resolution);
  return [currentCenter[0] + deltaX, currentCenter[1] + deltaY];
}

export function adjustConstrainedWheelZoom(
  view: Pick<View, "adjustZoom" | "resolveConstraints">,
  deltaZoomLevels: number,
  anchor?: number[],
): void {
  view.resolveConstraints(0);
  view.adjustZoom(deltaZoomLevels, anchor);
  view.resolveConstraints(0);
}
