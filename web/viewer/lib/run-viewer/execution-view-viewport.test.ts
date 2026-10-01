import { describe, expect, test } from "bun:test";
import {
  centerOn,
  clampScale,
  fitViewport,
  initialViewport,
  LEGIBLE_SCALE,
  MAX_SCALE,
  MIN_SCALE,
  panBy,
  toContent,
  wheelPanDelta,
  wheelZoomFactor,
  zoomAt,
} from "./execution-view-viewport";

describe("clampScale", () => {
  test("holds the zoom inside the usable band", () => {
    expect(clampScale(0.000001)).toBe(MIN_SCALE);
    expect(clampScale(99)).toBe(MAX_SCALE);
    expect(clampScale(0.5)).toBe(0.5);
    expect(clampScale(Number.NaN)).toBe(1);
  });
});

describe("panBy", () => {
  test("moves the layer without touching the zoom", () => {
    expect(panBy({ x: 10, y: -4, scale: 0.5 }, 5, 6)).toEqual({ x: 15, y: 2, scale: 0.5 });
  });
});

describe("zoomAt", () => {
  test("keeps the content under the pinch anchor stationary", () => {
    const before = { x: -120, y: 40, scale: 0.6 };
    const anchor = { x: 300, y: 220 };
    const under = toContent(before, anchor);

    const after = zoomAt(before, 1.4, anchor);

    expect(after.scale).toBeCloseTo(0.84, 10);
    expect(toContent(after, anchor).x).toBeCloseTo(under.x, 8);
    expect(toContent(after, anchor).y).toBeCloseTo(under.y, 8);
  });

  test("stops at the zoom limits without drifting the anchor", () => {
    const anchor = { x: 500, y: 300 };
    const floored = zoomAt({ x: 0, y: 0, scale: MIN_SCALE }, 0.1, anchor);
    expect(floored.scale).toBe(MIN_SCALE);
    expect(toContent(floored, anchor)).toEqual(toContent({ x: 0, y: 0, scale: MIN_SCALE }, anchor));
  });
});

describe("fitViewport", () => {
  test("centres the graph and shrinks it to the frame", () => {
    const viewport = fitViewport({ width: 4000, height: 2000 }, { width: 1000, height: 800 }, 50);

    expect(viewport.scale).toBeCloseTo(900 / 4000, 10);
    expect(viewport.x).toBeCloseTo((1000 - 4000 * viewport.scale) / 2, 10);
    expect(viewport.y).toBeCloseTo((800 - 2000 * viewport.scale) / 2, 10);
  });

  test("never magnifies a small graph past 1:1", () => {
    expect(fitViewport({ width: 200, height: 100 }, { width: 1600, height: 900 }).scale).toBe(1);
  });

  test("survives an unmeasured frame", () => {
    expect(fitViewport({ width: 400, height: 200 }, { width: 0, height: 0 })).toEqual({
      x: 0,
      y: 0,
      scale: 1,
    });
  });
});

describe("centerOn", () => {
  test("puts the point in the middle of the frame at the current zoom", () => {
    const viewport = centerOn({ x: 0, y: 0, scale: 0.5 }, { x: 400, y: 200 }, {
      width: 1000,
      height: 600,
    });
    expect(viewport.scale).toBe(0.5);
    expect(400 * 0.5 + viewport.x).toBe(500);
    expect(200 * 0.5 + viewport.y).toBe(300);
  });
});

describe("wheel normalisation", () => {
  test("converts line and page deltas to pixels", () => {
    expect(wheelPanDelta(3, -2, 0)).toEqual({ dx: 3, dy: -2 });
    expect(wheelPanDelta(1, 2, 1)).toEqual({ dx: 16, dy: 32 });
    expect(wheelPanDelta(0, 1, 2)).toEqual({ dx: 0, dy: 400 });
  });

  test("pinch out magnifies, pinch in shrinks, and a mouse notch is capped", () => {
    expect(wheelZoomFactor(-10, 0)).toBeGreaterThan(1);
    expect(wheelZoomFactor(10, 0)).toBeLessThan(1);
    expect(wheelZoomFactor(-1000, 0)).toBe(wheelZoomFactor(-50, 0));
    expect(wheelZoomFactor(0, 0)).toBe(1);
  });
});

describe("initialViewport", () => {
  test("shows the whole graph when the whole graph still reads", () => {
    const frame = { width: 1600, height: 900 };
    const content = { width: 1200, height: 600 };
    expect(initialViewport(content, frame)).toEqual(fitViewport(content, frame));
  });

  test("opens a huge graph at its first column, legibly, instead of as a texture", () => {
    const viewport = initialViewport(
      { width: 9000, height: 40000 },
      { width: 1600, height: 900 },
      { x: 24, y: 88 },
    );
    expect(viewport).toEqual({ x: 24, y: 88, scale: LEGIBLE_SCALE });
  });
});
