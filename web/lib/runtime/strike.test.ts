import { describe, expect, test } from "bun:test";
import { resolveInstantStrike, type StrikeTarget } from "./strike";
import { weaponClassProfile } from "./weapon-class";

const TILE = 64;
const MELEE = weaponClassProfile("melee_dps_v1");
const RANGED = weaponClassProfile("ranged_dps_v1");

/** A character standing on flat ground at x = 500, facing right. */
const ATTACKER = { attackerX: 500, attackerFootY: 656, dirSign: 1 as const, tilePixels: TILE };

function hits(targets: readonly StrikeTarget[], dirSign: 1 | -1 = 1): readonly number[] {
  return resolveInstantStrike({ ...ATTACKER, dirSign, profile: MELEE, targets });
}

describe("the swing band is exactly the one the scene resolved inline", () => {
  test("it reaches much further forward than back, because it is centred ahead", () => {
    // Band half-width 1.4 tiles = 89.6px, centred 0.7 tiles = 44.8px ahead. So the shipped reach
    // is (-44.8, +134.4) about the character, and the asymmetry is deliberate: a swing that
    // reached as far backwards would kill things the player had already walked past.
    expect(hits([{ x: 500 + 134, footY: 656 }])).toEqual([0]);
    expect(hits([{ x: 500 + 135, footY: 656 }])).toEqual([]);
    expect(hits([{ x: 500 - 44, footY: 656 }])).toEqual([0]);
    expect(hits([{ x: 500 - 45, footY: 656 }])).toEqual([]);
  });

  test("facing left mirrors the band rather than widening it", () => {
    expect(hits([{ x: 500 - 134, footY: 656 }], -1)).toEqual([0]);
    expect(hits([{ x: 500 + 134, footY: 656 }], -1)).toEqual([]);
  });

  test("one deck up or down connects and two decks do not", () => {
    expect(hits([{ x: 540, footY: 656 - TILE }])).toEqual([0]);
    expect(hits([{ x: 540, footY: 656 + TILE }])).toEqual([0]);
    expect(hits([{ x: 540, footY: 656 - TILE * 2 }])).toEqual([]);
    expect(hits([{ x: 540, footY: 656 + TILE * 2 }])).toEqual([]);
  });

  test("the vertical band is the profile's, not the module constant", () => {
    // The reach parameter exists so a class can declare its own band; a resolver that ignored it
    // and used the module default would pass every other test in this file.
    const tall = {
      ...MELEE,
      verticalReach: { kind: "foot_band", tiles: 2, targetingToleranceTiles: 2 } as const,
    };
    expect(
      resolveInstantStrike({ ...ATTACKER, profile: tall, targets: [{ x: 540, footY: 656 - TILE * 2 }] }),
    ).toEqual([0]);
    expect(hits([{ x: 540, footY: 656 - TILE * 2 }])).toEqual([]);
  });

  test("a target in range but on the wrong deck is refused, however close it looks", () => {
    // The rule the whole vertical band exists for: screen proximity is not reach.
    expect(hits([{ x: 501, footY: 656 - TILE * 3 }])).toEqual([]);
  });
});

describe("how many things one action may kill", () => {
  test("one swing takes the first target in the caller's order, not the nearest", () => {
    // Scene order is ladder-index order, and it is deterministic. Picking the geometrically
    // nearest would make a replay diverge whenever two mobs stood at the same distance.
    const far = { x: 560, footY: 656 };
    const near = { x: 520, footY: 656 };
    expect(hits([far, near])).toEqual([0]);
  });

  test("the cap is the profile's, so a class that cleaved would not need a new call site", () => {
    const cleaving = { ...MELEE, maxTargetsPerAction: 2 };
    const targets = [
      { x: 520, footY: 656 },
      { x: 540, footY: 656 },
      { x: 560, footY: 656 },
    ];
    expect(
      resolveInstantStrike({ ...ATTACKER, profile: cleaving, targets }),
    ).toEqual([0, 1]);
  });
});

describe("a class that does not strike instantly", () => {
  test("resolves nothing here, so the caller branches on delivery once", () => {
    expect(
      resolveInstantStrike({ ...ATTACKER, profile: RANGED, targets: [{ x: 510, footY: 656 }] }),
    ).toEqual([]);
  });
});

describe("refusals", () => {
  test("a non-positive tile size is refused rather than producing a zero-width band", () => {
    expect(() =>
      resolveInstantStrike({ ...ATTACKER, tilePixels: 0, profile: MELEE, targets: [] }),
    ).toThrow("positive tile size");
  });

  test("an empty roster is an ordinary answer, not an error", () => {
    expect(hits([])).toEqual([]);
  });
});
