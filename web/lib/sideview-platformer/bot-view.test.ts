import { describe, expect, test } from "bun:test";
import { lineOfFireClear } from "./bot-view";

describe("whether a flat shot would reach", () => {
  const TILE = 64;
  const BASELINE = 720;
  // Low ground for six columns, then a four-column ledge two tiles up, then low again.
  const LEDGE = Object.freeze({
    columnSurfaceY: Object.freeze(
      [1, 1, 1, 1, 1, 1, 3, 3, 3, 3, 1, 1].map((height) => BASELINE - height * TILE),
    ),
    tileUnits: TILE,
  });
  const GROUND_Y = BASELINE - TILE;
  /** Chest height for a 154px character standing on the low ground. */
  const FLIGHT_Y = GROUND_Y - 77;

  test("level ground between two points is clear", () => {
    expect(lineOfFireClear(LEDGE, 1.5 * TILE, 4.5 * TILE, FLIGHT_Y)).toBe(true);
  });

  test("a ledge higher than the flight path blocks it", () => {
    // The softlock this exists for: the creature standing on the ledge is close enough and its
    // feet are near enough, so targeting used to accept it and every throw died in the ledge face.
    expect(lineOfFireClear(LEDGE, 4.5 * TILE, 8.5 * TILE, FLIGHT_Y)).toBe(false);
  });

  test("a ledge lower than the flight path does not", () => {
    // Standing on the ledge shooting down: the same geometry, the other way round, and it is clear.
    const fromLedge = BASELINE - 3 * TILE - 77;
    expect(lineOfFireClear(LEDGE, 8.5 * TILE, 4.5 * TILE, fromLedge)).toBe(true);
  });

  test("the character's own column never blocks its own shot", () => {
    // It is standing on that ground, not shooting through it — and its feet are below the flight
    // line by definition, so a naive scan would refuse every shot ever fired from a hill.
    const onLedge = BASELINE - 3 * TILE - 77;
    expect(lineOfFireClear(LEDGE, 7.5 * TILE, 9.5 * TILE, onLedge)).toBe(true);
  });

  test("it samples every column, so a one-column pillar is not flown through", () => {
    const pillar = Object.freeze({
      columnSurfaceY: Object.freeze(
        [1, 1, 5, 1, 1].map((height) => BASELINE - height * TILE),
      ),
      tileUnits: TILE,
    });
    expect(lineOfFireClear(pillar, 0.5 * TILE, 4.5 * TILE, FLIGHT_Y)).toBe(false);
  });

  test("direction does not matter", () => {
    expect(lineOfFireClear(LEDGE, 8.5 * TILE, 4.5 * TILE, FLIGHT_Y)).toBe(false);
  });

  test("a scene reporting no terrain blocks nothing", () => {
    // Refusing every shot would be a worse failure than the one this prevents.
    const none = Object.freeze({ columnSurfaceY: Object.freeze([]), tileUnits: TILE });
    expect(lineOfFireClear(none, 0, 500, FLIGHT_Y)).toBe(true);
  });
});
