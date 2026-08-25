import { describe, expect, test } from "bun:test";
import {
  MOB_HEALTH_BAR_STYLE,
  PLAYER_HEALTH_BAR_STYLE,
  healthBarFillWidth,
  healthBarPlacement,
} from "./health-bar";

/** An actor standing on a ground column at y=592. */
const ACTOR = { actorX: 4_096, actorFootY: 592 } as const;
const PLAYER = { ...ACTOR, style: PLAYER_HEALTH_BAR_STYLE } as const;

describe("floating health bar placement", () => {
  test("centres on the body and hangs below its feet", () => {
    const placement = healthBarPlacement(PLAYER);
    expect(placement.x).toBe(ACTOR.actorX);
    // Below, not above: actor origins are (0.5, 1), so a larger y is further down the screen.
    expect(placement.y).toBeGreaterThan(ACTOR.actorFootY);
    expect(placement.y).toBe(ACTOR.actorFootY + PLAYER_HEALTH_BAR_STYLE.footGap);
  });

  test("stays under the body wherever it stands", () => {
    for (const [x, footY] of [
      [0, 592],
      [12_576, 336],
      [4_096, 656],
    ] as const) {
      const placement = healthBarPlacement({
        actorX: x,
        actorFootY: footY,
        style: MOB_HEALTH_BAR_STYLE,
      });
      expect(placement.x).toBe(x);
      expect(placement.y - footY).toBe(MOB_HEALTH_BAR_STYLE.footGap);
    }
  });

  test("keeps the player's bar narrower than the character it sits under", () => {
    // The player draws at TILE_PX * 2.2 = 140.8px tall and about 57px of alpha across. A strip
    // much wider than the body stops reading as the character's own.
    expect(PLAYER_HEALTH_BAR_STYLE.width).toBeLessThan(80);
    // And a mob's is smaller again, so several on screen never compete with the player's own.
    expect(MOB_HEALTH_BAR_STYLE.width).toBeLessThan(PLAYER_HEALTH_BAR_STYLE.width);
    expect(MOB_HEALTH_BAR_STYLE.height).toBeLessThan(PLAYER_HEALTH_BAR_STYLE.height);
  });
});

describe("floating health bar fill", () => {
  const fill = (hp: number, maxHp = 6, style = PLAYER_HEALTH_BAR_STYLE) =>
    healthBarFillWidth({ hp, maxHp, style });

  test("covers the whole capsule at full health and nothing at zero", () => {
    expect(fill(6)).toBe(PLAYER_HEALTH_BAR_STYLE.width);
    expect(fill(0)).toBe(0);
  });

  test("drains in proportion to what is left", () => {
    expect(fill(3)).toBeCloseTo(PLAYER_HEALTH_BAR_STYLE.width / 2, 10);
    expect(fill(5)).toBeGreaterThan(fill(4));
    expect(fill(4)).toBeGreaterThan(fill(3));
  });

  test("never draws a living actor as empty", () => {
    // One point out of forty would round to a sliver too thin to have ends. A mob one hit from
    // death has to look different from a dead one.
    const sliver = fill(1, 40);
    expect(sliver).toBeGreaterThan(0);
    expect(sliver).toBeGreaterThanOrEqual(PLAYER_HEALTH_BAR_STYLE.height);
    expect(sliver).toBeLessThan(PLAYER_HEALTH_BAR_STYLE.width);
  });

  test("clamps health that overruns its own capacity", () => {
    expect(fill(99)).toBe(PLAYER_HEALTH_BAR_STYLE.width);
    expect(fill(-3)).toBe(0);
    expect(fill(1, 0)).toBe(0);
  });

  test("gives a one-hit mob a full bar rather than a sliver", () => {
    // Mob health is ladderIndex + 1, so the weakest mob in a stage has a capacity of one.
    expect(fill(1, 1, MOB_HEALTH_BAR_STYLE)).toBe(MOB_HEALTH_BAR_STYLE.width);
    expect(fill(0, 1, MOB_HEALTH_BAR_STYLE)).toBe(0);
  });
});
