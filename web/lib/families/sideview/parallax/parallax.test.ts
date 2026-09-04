import { describe, expect, test } from "bun:test";

import {
  bandDepth,
  bandTilePosition,
  DEPTH_LADDER,
  layerLayout,
  sealDepthLadder,
  type LayerPlacement,
} from "./index";

// E4 for `sideview/parallax`: one placement contract, two genres whose bands
// have nothing in common but the viewport.
//
// The platformer-shaped case is a producer-measured band on a map with a walk
// surface well above the viewport floor — a camera that has left the ground —
// so the difference between a screen band and a world band is visible at all.
// The runner-shaped case is an endless track whose camera never leaves the
// floor: the walk surface *is* the viewport bottom, every band is a screen
// band, and the vertical scroll factor it gets back is a number nothing there
// reads. Both go through the same five anchors.

const VIEWPORT = 720;

/** The runner's case: the ground line is the floor, so the two spaces coincide. */
const RUNNER_CONTEXT = { viewportHeight: VIEWPORT, walkSurfaceY: VIEWPORT, parallax: 0.35 };
/** The platformer's case: the camera has climbed, so they do not. */
const PLATFORMER_CONTEXT = { viewportHeight: VIEWPORT, walkSurfaceY: 512, parallax: 0.35 };

function band(overrides: Partial<LayerPlacement> = {}): LayerPlacement {
  return {
    verticalAnchor: "screen_bottom",
    verticalOffset: 0,
    sourceHeight: 1080,
    trimmedHeight: 540,
    ...overrides,
  };
}

describe("one placement contract, five anchors", () => {
  test("the painted frame stays the scale datum after trimming", () => {
    const layout = layerLayout(band(), RUNNER_CONTEXT);
    expect(layout.scale).toBe(VIEWPORT / 1080);
    expect(layout.renderedHeight).toBe(540 * (VIEWPORT / 1080));
    // `sourceHeight` on the way out is the *texture* height, which is the
    // trimmed one: it is what stops a tile sprite repeating vertically.
    expect(layout.sourceHeight).toBe(540);
  });

  test("every anchor registers the edge it names", () => {
    const rendered = 540 * (VIEWPORT / 1080);
    expect(layerLayout(band({ verticalAnchor: "canvas_cover" }), RUNNER_CONTEXT).topY).toBe(0);
    expect(layerLayout(band({ verticalAnchor: "screen_top" }), RUNNER_CONTEXT).topY).toBe(0);
    expect(layerLayout(band({ verticalAnchor: "screen_center" }), RUNNER_CONTEXT).topY).toBe(
      VIEWPORT / 2 - rendered / 2,
    );
    expect(layerLayout(band({ verticalAnchor: "screen_bottom" }), RUNNER_CONTEXT).topY).toBe(
      VIEWPORT - rendered,
    );
    // The one anchor that resolves against the world rather than the screen.
    expect(layerLayout(band({ verticalAnchor: "walk_surface" }), PLATFORMER_CONTEXT).topY).toBe(
      512 - rendered,
    );
    // A positive offset slides the layer down by that fraction of its rendered
    // height, and it reads the same way on every anchor that has an edge.
    for (const anchor of ["screen_top", "screen_bottom", "screen_center", "walk_surface"] as const) {
      const flat = layerLayout(band({ verticalAnchor: anchor }), PLATFORMER_CONTEXT).topY;
      const slid = layerLayout(
        band({ verticalAnchor: anchor, verticalOffset: 0.25 }),
        PLATFORMER_CONTEXT,
      ).topY;
      expect(slid - flat).toBeCloseTo(0.25 * rendered, 9);
    }
  });

  test("the anchor chooses the space, and the space chooses the vertical travel", () => {
    // The fact the runner's placement never had. Only `walk_surface` is
    // registered to the terrain, so only it travels with the camera exactly.
    expect(layerLayout(band({ verticalAnchor: "walk_surface" }), PLATFORMER_CONTEXT)).toMatchObject({
      space: "world",
      verticalScrollFactor: 1,
    });
    for (const anchor of ["canvas_cover", "screen_top", "screen_center", "screen_bottom"] as const) {
      expect(layerLayout(band({ verticalAnchor: anchor }), PLATFORMER_CONTEXT)).toMatchObject({
        space: "screen",
        verticalScrollFactor: 0.35,
      });
    }
    // In the runner's world the two spaces coincide, which is exactly why one
    // anchor vocabulary could stand for both until a camera left the floor: the
    // same band resolves to the same y under both contexts.
    expect(layerLayout(band({ verticalAnchor: "walk_surface" }), RUNNER_CONTEXT).topY).toBe(
      layerLayout(band({ verticalAnchor: "screen_bottom" }), RUNNER_CONTEXT).topY,
    );
  });

  test("horizontal parallax is a texture offset, divided by the scale that stretched it", () => {
    expect(bandTilePosition(1000, 0.35, 0.5)).toBe(700);
    // A band at zero parallax never moves inside itself, however far the world
    // scrolls, which is what a sky plate is.
    expect(bandTilePosition(1e6, 0, 0.5)).toBe(0);
  });

  test("the resolution refuses what it cannot resolve", () => {
    expect(() => layerLayout(band(), { ...RUNNER_CONTEXT, parallax: -1 })).toThrow(
      "non-negative parallax",
    );
    expect(() => layerLayout(band(), { ...RUNNER_CONTEXT, viewportHeight: 0 })).toThrow(
      "positive viewport height",
    );
    expect(() =>
      layerLayout(band(), { ...RUNNER_CONTEXT, walkSurfaceY: Number.NaN }),
    ).toThrow("finite walk surface");
    expect(() => layerLayout(band({ trimmedHeight: 0 }), RUNNER_CONTEXT)).toThrow(
      "positive raster heights",
    );
    expect(() => layerLayout(band({ verticalOffset: Number.NaN }), RUNNER_CONTEXT)).toThrow(
      "finite vertical offset",
    );
  });
});

describe("the depth ladder is an ordered vocabulary", () => {
  test("a genre supplies numbers; the family supplies the order", () => {
    // The runner's shape: tens from zero, and no readouts drawn in the world.
    const runner = sealDepthLadder({
      background: 0,
      world: 20,
      actors: 30,
      foreground: 40,
      hud: 100,
      overlay: 120,
    });
    // The platformer's shape: hundreds, and every rung present.
    const platformer = sealDepthLadder({
      background: 0,
      world: 500,
      actors: 700,
      foreground: 1200,
      actorHud: 1300,
      hud: 2000,
      overlay: 2100,
    });
    // No value in common past the first, and the same ladder.
    expect(Object.keys(platformer).length).toBe(DEPTH_LADDER.length);
    expect(bandDepth(runner, "background", 3)).toBe(3);
    expect(bandDepth(runner, "foreground", 3)).toBe(43);
    expect(bandDepth(platformer, "foreground", 3)).toBe(1203);
  });

  test("an inverted rung is refused, and a skipped one is not", () => {
    // A foreground band under the terrain it is supposed to stand in front of.
    expect(() =>
      sealDepthLadder({ background: 0, world: 500, foreground: 400, hud: 2000 }),
    ).toThrow("depth ladder is out of order: foreground at 400 is not above world at 500");
    // Two rungs at the same number is the same defect: neither is in front.
    expect(() => sealDepthLadder({ world: 500, actors: 500 })).toThrow("is not above");
    expect(() => sealDepthLadder({ world: Number.NaN })).toThrow("must be a finite number");
    // Skipping is allowed: a genre that draws no world-anchored readout has no
    // `actorHud`, and that is an answer rather than a hole.
    expect(() => sealDepthLadder({ background: 0, foreground: 40, hud: 100 })).not.toThrow();
    // E7 at this family's grain: the empty ladder seals, and a band on it is
    // refused by name rather than silently drawn at zero.
    expect(sealDepthLadder({})).toEqual({});
    expect(() => bandDepth({}, "background", 0)).toThrow(
      "depth ladder has no background rung",
    );
  });
});
