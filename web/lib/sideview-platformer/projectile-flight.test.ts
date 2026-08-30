import { describe, expect, test } from "bun:test";
import { attackFootLevelsOverlap } from "./combat";
import {
  advanceShot,
  boxesOverlap,
  firstOverlappingTarget,
  launchShot,
  shotBounds,
  shotExpiry,
  type ShotState,
  type WorldLimits,
} from "./projectile-flight";
import { projectileFlightProfile } from "./projectile-class";

const TILE = 64;
/** The controller's own drawn height, which the release height is a fraction of. */
const PLAYER_HEIGHT = 154;
const FOOT_Y = 656;
const ORIGIN_X = 500;

// The flight is the projectile's, not the weapon's: `flat_bolt_v1` is the profile that transcribes
// the numbers the ranged class used to carry inline.
const DELIVERY = projectileFlightProfile("flat_bolt_v1");

function shot(dirSign: 1 | -1 = 1, footY = FOOT_Y): ShotState {
  return launchShot({
    id: "shot_1",
    originX: ORIGIN_X,
    footY,
    bodyHeightPx: PLAYER_HEIGHT,
    dirSign,
    tilePixels: TILE,
    speedTilesPerSecond: DELIVERY.speedTilesPerSecond,
    maxRangeTiles: DELIVERY.maxRangeTiles,
    releaseForwardTiles: DELIVERY.releaseForwardTiles,
    releaseHeightFraction: DELIVERY.releaseHeightFraction,
    halfWidthTiles: DELIVERY.halfWidthTiles,
    halfHeightTiles: DELIVERY.halfHeightTiles,
  });
}

const OPEN_WORLD: WorldLimits = { minX: -10_000, maxX: 10_000, surfaceYAt: null };

/** A mob's alpha box, in the shape `Mob.snapshot().renderBounds` returns. */
function mobBounds(x: number, footY: number, heightPx: number, halfWidth = 40) {
  return {
    left: x - halfWidth,
    right: x + halfWidth,
    top: footY - heightPx,
    bottom: footY,
  };
}

describe("the throw leaves the hand where the character is", () => {
  test("it appears half a tile ahead, at chest height, travelling forward", () => {
    const forward = shot(1);
    expect(forward.x).toBe(ORIGIN_X + 0.5 * TILE);
    expect(forward.y).toBe(FOOT_Y - 0.5 * PLAYER_HEIGHT);
    expect(forward.vxPx).toBe(DELIVERY.speedTilesPerSecond * TILE);
  });

  test("facing left mirrors the release and the velocity", () => {
    const back = shot(-1);
    expect(back.x).toBe(ORIGIN_X - 0.5 * TILE);
    expect(back.vxPx).toBeLessThan(0);
  });

  test("a body height of zero is refused rather than releasing at the feet", () => {
    expect(() =>
      launchShot({
        id: "shot_1",
        originX: 0,
        footY: 0,
        bodyHeightPx: 0,
        dirSign: 1,
        tilePixels: TILE,
        speedTilesPerSecond: 1,
        maxRangeTiles: 1,
        releaseForwardTiles: 0,
        releaseHeightFraction: 0.5,
        halfWidthTiles: 0.1,
        halfHeightTiles: 0.1,
      }),
    ).toThrow("body height must be positive");
  });
});

describe("flight is a pure function of the frame delta", () => {
  test("one long step and many short ones land in the same place", () => {
    // The whole reason motion is sampled from `dtMs` rather than a clock: a replay stepped at a
    // different frame rate must still put the object in the same place.
    const coarse = advanceShot(shot(), 100, 0);
    let fine = shot();
    for (let step = 0; step < 10; step += 1) fine = advanceShot(fine, 10, 0);
    expect(fine.x).toBeCloseTo(coarse.x, 6);
    expect(fine.remainingPx).toBeCloseTo(coarse.remainingPx, 6);
  });

  test("a flat throw does not fall", () => {
    const flown = advanceShot(shot(), 250, DELIVERY.gravityPxPerSecond2);
    expect(flown.y).toBe(shot().y);
  });

  test("a negative delta is refused rather than flying backwards", () => {
    expect(() => advanceShot(shot(), -1, 0)).toThrow("nonnegative");
  });

  test("the range budget is spent on the path, so an arc could not buy extra reach", () => {
    // With gravity the vertical component is real travel. Spending the budget on displacement
    // would let a later arcing class reach further than its own stated range by falling.
    const falling = advanceShot(shot(), 100, 900);
    const flat = advanceShot(shot(), 100, 0);
    expect(falling.remainingPx).toBeLessThan(flat.remainingPx);
  });
});

describe("when a shot gives up", () => {
  test("it expires at its stated range and not before", () => {
    let flying = shot();
    // 6 tiles at 11 tiles/s is a little over half a second.
    for (let step = 0; step < 100 && shotExpiry(flying, OPEN_WORLD) === null; step += 1) {
      flying = advanceShot(flying, 10, 0);
    }
    expect(shotExpiry(flying, OPEN_WORLD)).toBe("range");
    const travelled = Math.abs(flying.x - flying.spawnX);
    expect(travelled).toBeGreaterThanOrEqual(DELIVERY.maxRangeTiles * TILE);
    // Overshoot is bounded by one frame of travel, not unbounded.
    expect(travelled).toBeLessThan(DELIVERY.maxRangeTiles * TILE + DELIVERY.speedTilesPerSecond * TILE * 0.02);
  });

  test("leaving the map is a separate reason from running out of range", () => {
    expect(shotExpiry(shot(), { minX: 600, maxX: 10_000, surfaceYAt: null })).toBe("world");
  });

  test("a throw into a rising hillside stops at the hill", () => {
    // The identical terrain query a dropped item uses to settle on the ground.
    const uphill: WorldLimits = {
      ...OPEN_WORLD,
      surfaceYAt: (x) => (x > ORIGIN_X + 100 ? FOOT_Y - 200 : FOOT_Y),
    };
    expect(shotExpiry(shot(), uphill)).toBeNull();
    const flown = advanceShot(shot(), 200, 0);
    expect(flown.x).toBeGreaterThan(ORIGIN_X + 100);
    expect(shotExpiry(flown, uphill)).toBe("terrain");
  });

  test("range is reported before terrain, so the stated reason is the true one", () => {
    const spent = { ...shot(), remainingPx: 0 };
    expect(shotExpiry(spent, { ...OPEN_WORLD, surfaceYAt: () => -10_000 })).toBe("range");
  });
});

describe("what a flat throw can actually reach", () => {
  // The shot flies at 77px above the character's feet with a ±44.8px box, so its band is
  // [-121.8, -32.2] relative to the foot line. What that overlaps depends on how tall the target
  // is, which is why the reachable decks are asserted per rank rather than pinned once.
  const RANKS = [
    { rank: "common", heightPx: 110 },
    { rank: "boss", heightPx: 110 * 1.45 },
  ] as const;

  function connects(deckOffsetPx: number, heightPx: number): boolean {
    const flying = advanceShot(shot(), 100, 0);
    return boxesOverlap(
      shotBounds(flying),
      mobBounds(flying.x, FOOT_Y + deckOffsetPx, heightPx),
    );
  }

  for (const { rank, heightPx } of RANKS) {
    test(`a ${rank} target on the same deck and one deck either way is struck`, () => {
      expect(connects(0, heightPx)).toBe(true);
      expect(connects(-TILE, heightPx)).toBe(true);
      expect(connects(TILE, heightPx)).toBe(true);
    });

    test(`a ${rank} target two decks up is out of reach`, () => {
      expect(connects(-TILE * 2, heightPx)).toBe(false);
    });
  }

  test("a tall target reaches up to the shot from further below than a short one does", () => {
    // Stated rather than implied: the reachable band is a property of the *pair*, not of the shot.
    // A rule written as four fixed deck cases at one height would be quietly wrong for a boss —
    // measured, the common band ends 77.8px below the character and the boss band 127.3px below,
    // and one and a half decks falls between them.
    const between = TILE * 1.5;
    expect(connects(between, 110)).toBe(false);
    expect(connects(between, 110 * 1.45)).toBe(true);
  });

  test("a common target two decks down is out of reach", () => {
    // Asserted for the common rank only. A boss two decks down misses by well under a pixel, and
    // pinning a margin that fine would make this a test of floating-point rather than of reach.
    expect(connects(TILE * 2, 110)).toBe(false);
  });

  test("it reaches a target the foot-level rule would have refused", () => {
    // The case the two vertical rules genuinely disagree about: 1.25 tiles up. A swing compares
    // feet and declines; a thrown object is simply where it is, and it is inside that body.
    const deckOffset = -TILE * 1.25;
    expect(connects(deckOffset, 110)).toBe(true);
    expect(attackFootLevelsOverlap(FOOT_Y, FOOT_Y + deckOffset, TILE)).toBe(false);
  });
});

describe("choosing among several targets", () => {
  test("the first overlapping target in the caller's order wins", () => {
    const flying = advanceShot(shot(), 100, 0);
    const targets = [
      { bounds: mobBounds(flying.x + 500, FOOT_Y, 110) },
      { bounds: mobBounds(flying.x, FOOT_Y, 110) },
      { bounds: mobBounds(flying.x + 2, FOOT_Y, 110) },
    ];
    expect(firstOverlappingTarget(flying, targets)).toBe(1);
  });

  test("nothing in the way is -1, an ordinary answer", () => {
    expect(firstOverlappingTarget(shot(), [])).toBe(-1);
  });

  test("edge contact counts, so a grazing hit connects", () => {
    const box = shotBounds(shot());
    expect(
      boxesOverlap(box, { left: box.right, right: box.right + 10, top: box.top, bottom: box.bottom }),
    ).toBe(true);
    expect(
      boxesOverlap(box, {
        left: box.right + 0.001,
        right: box.right + 10,
        top: box.top,
        bottom: box.bottom,
      }),
    ).toBe(false);
  });
});

describe("the seed a critical is rolled from", () => {
  test("it stays at the release point for the whole flight", () => {
    // A throw seeded at the impact point would roll a different critical depending on how far the
    // target had walked while the object was in the air, which is exactly the divergence the
    // deterministic seed exists to prevent.
    let flying = shot();
    const spawnX = flying.spawnX;
    for (let step = 0; step < 20; step += 1) flying = advanceShot(flying, 10, 0);
    expect(flying.spawnX).toBe(spawnX);
    expect(flying.x).not.toBe(spawnX);
  });
});
