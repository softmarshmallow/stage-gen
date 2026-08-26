import { describe, expect, test } from "bun:test";
import View from "ol/View.js";
import {
  adjustConstrainedWheelZoom,
  classifyWheelNavigation,
  panCenterFromCurrentView,
  screenPanToMapDelta,
} from "./wheel-navigation";

describe("illustrated map wheel navigation", () => {
  test("routes the browser trackpad-pinch signal to zoom", () => {
    expect(
      classifyWheelNavigation(
        {
          ctrl_key: true,
          shift_key: false,
          delta_x: 0,
          delta_y: -1.25,
          delta_mode: 0,
        },
        720,
      ),
    ).toEqual({ kind: "zoom", delta_zoom_levels: 0.0125 });
  });

  test("caps a single pinch event to one zoom level", () => {
    expect(
      classifyWheelNavigation(
        {
          ctrl_key: true,
          shift_key: false,
          delta_x: 0,
          delta_y: 400,
          delta_mode: 0,
        },
        720,
      ),
    ).toEqual({ kind: "zoom", delta_zoom_levels: -1 });
  });

  test("routes two-axis pixel wheel input to pan", () => {
    expect(
      classifyWheelNavigation(
        {
          ctrl_key: false,
          shift_key: false,
          delta_x: 12.5,
          delta_y: -8,
          delta_mode: 0,
        },
        720,
      ),
    ).toEqual({ kind: "pan", delta_css_pixels: [12.5, -8] });
  });

  test("normalizes line and page wheel deltas", () => {
    expect(
      classifyWheelNavigation(
        {
          ctrl_key: false,
          shift_key: false,
          delta_x: 1,
          delta_y: 2,
          delta_mode: 1,
        },
        720,
      ),
    ).toEqual({ kind: "pan", delta_css_pixels: [16, 32] });
    expect(
      classifyWheelNavigation(
        {
          ctrl_key: false,
          shift_key: false,
          delta_x: 0,
          delta_y: 1,
          delta_mode: 2,
        },
        720,
      ),
    ).toEqual({ kind: "pan", delta_css_pixels: [0, 720] });
  });

  test("maps shift-wheel to a horizontal pan when no x delta is present", () => {
    expect(
      classifyWheelNavigation(
        {
          ctrl_key: false,
          shift_key: true,
          delta_x: 0,
          delta_y: 20,
          delta_mode: 0,
        },
        720,
      ),
    ).toEqual({ kind: "pan", delta_css_pixels: [20, 0] });
  });

  test("converts screen movement to the OpenLayers coordinate orientation", () => {
    expect(screenPanToMapDelta([15, 20], 2)).toEqual([30, -40]);
    expect(() => screenPanToMapDelta([1, 1], 0)).toThrow(
      "resolution must be a positive finite number",
    );
  });

  test("computes pan from the current constrained center", () => {
    expect(panCenterFromCurrentView([100, 200], [-12, 8], 2)).toEqual([76, 184]);
  });

  test("does not accumulate reverse-direction debt at zoom constraints", () => {
    const view = new View({
      center: [0, 0],
      resolution: 1,
      minResolution: 0.5,
      maxResolution: 2,
    });
    view.setViewportSize([100, 100]);

    for (let index = 0; index < 20; index += 1) {
      adjustConstrainedWheelZoom(view, 1, [0, 0]);
    }
    expect(view.getResolution()).toBe(0.5);

    adjustConstrainedWheelZoom(view, -0.5, [0, 0]);
    expect(view.getResolution()).toBeCloseTo(Math.SQRT1_2);

    for (let index = 0; index < 20; index += 1) {
      adjustConstrainedWheelZoom(view, -1, [0, 0]);
    }
    expect(view.getResolution()).toBe(2);

    adjustConstrainedWheelZoom(view, 0.5, [0, 0]);
    expect(view.getResolution()).toBeCloseTo(Math.SQRT2);
  });
});
