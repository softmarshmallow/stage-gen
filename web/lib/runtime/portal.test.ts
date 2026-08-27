import { describe, expect, test } from "bun:test";
import {
  portalEndpointSurfacePosition,
  portalMouthContainsFoot,
} from "./portal";

// A 3.6-tile portal standing on a ground column at y=592.
const PORTAL = {
  portalX: 12_576,
  portalFootY: 592,
  width: 200,
  height: 230,
} as const;

describe("portal mouth", () => {
  test("accepts a player standing in the mouth", () => {
    expect(
      portalMouthContainsFoot({
        ...PORTAL,
        playerX: PORTAL.portalX,
        playerFootY: PORTAL.portalFootY,
      }),
    ).toBeTrue();
    // The mouth is narrower than the sprite, so the art may overlap the player
    // well before the portal claims them.
    const halfMouth = (PORTAL.width * 0.6) / 2;
    expect(
      portalMouthContainsFoot({
        ...PORTAL,
        playerX: PORTAL.portalX + halfMouth - 1,
        playerFootY: PORTAL.portalFootY,
      }),
    ).toBeTrue();
    expect(
      portalMouthContainsFoot({
        ...PORTAL,
        playerX: PORTAL.portalX + halfMouth + 1,
        playerFootY: PORTAL.portalFootY,
      }),
    ).toBeFalse();
  });

  test("rejects a player on a deck that only shares the portal's column", () => {
    // The whole point of the vertical test: an upper platform above the portal
    // is not the portal. With X alone, walking a sky bridge over the exit
    // teleported the player to the next stage.
    expect(
      portalMouthContainsFoot({
        ...PORTAL,
        playerX: PORTAL.portalX,
        playerFootY: PORTAL.portalFootY - PORTAL.height - 64,
      }),
    ).toBeFalse();
    // A player mid-jump through the portal's own body still counts.
    expect(
      portalMouthContainsFoot({
        ...PORTAL,
        playerX: PORTAL.portalX,
        playerFootY: PORTAL.portalFootY - PORTAL.height + 10,
      }),
    ).toBeTrue();
    // And one who has fallen well below its base does not.
    expect(
      portalMouthContainsFoot({
        ...PORTAL,
        playerX: PORTAL.portalX,
        playerFootY: PORTAL.portalFootY + 200,
      }),
    ).toBeFalse();
  });

  test("rejects malformed footprints instead of guessing one", () => {
    expect(() =>
      portalMouthContainsFoot({
        ...PORTAL,
        width: 0,
        playerX: PORTAL.portalX,
        playerFootY: PORTAL.portalFootY,
      }),
    ).toThrow("positive");
    expect(() =>
      portalMouthContainsFoot({
        ...PORTAL,
        playerX: Number.NaN,
        playerFootY: PORTAL.portalFootY,
      }),
    ).toThrow("finite");
  });
});

describe("portal endpoint placement", () => {
  test("bottom-anchors an explicit map-owned world position", () => {
    expect(
      portalEndpointSurfacePosition({
        x: 640,
        tilePx: 64,
        baselineY: 674,
        stageWidthPx: 12_800,
        heightFn: (column) => (column === 10 ? 2 : 1),
      }),
    ).toEqual({ x: 640, y: 546 });
  });

  test("rejects an endpoint outside the map instead of clamping it", () => {
    expect(() =>
      portalEndpointSurfacePosition({
        x: 12_801,
        tilePx: 64,
        baselineY: 674,
        stageWidthPx: 12_800,
        heightFn: () => 1,
      }),
    ).toThrow("outside its world");
  });
});
