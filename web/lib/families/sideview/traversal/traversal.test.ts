import { describe, expect, test } from "bun:test";

import {
  advanceClimbMotion,
  belongsToBottomStack,
  booleanOccupancy,
  bottomContiguousGrid,
  bottomContiguousHeights,
  bottomContiguousSurfaceRow,
  climbEntryAt,
  climbJumpOffVelocity,
  deckAtX,
  dropThroughActive,
  jumpArcFromAdmission,
  resolveCrouchHorizontalVelocity,
  resolveJumpRequest,
  resolveTerrainStep,
  resolveTerrainWalk,
  resolveVerticalLanding,
  simulateJumpArc,
  stringOccupancy,
  surfaceDatum,
  TRAVERSAL_CAPABILITIES,
  TRAVERSAL_LOCOMOTIONS,
  UNIMPLEMENTED_CAPABILITIES,
  type ClimbGeometry,
  type ClimbProfile,
  type OneWayDeck,
} from "./index";

// E4 for `sideview/traversal`: one core, two bodies, and the two bodies do not
// share a length unit.
//
// The runner-shaped body lives *inside* the occupancy grid — its foot is a row
// index, its speeds are rows and columns per second, and its arc is derived
// from the admission arithmetic because nothing authored one. The
// platformer-shaped body lives in pixels projected off the grid — its foot is a
// pixel, its arc is authored as four constants, and it has decks, a ladder, a
// crouch and a coyote window the runner has never heard of. Every function
// below is called by both, and no function knows which is calling.

/** The runner-shaped world: an occupancy grid, and the body is a row in it. */
const RUNNER_GRID = stringOccupancy([
  "0000000000",
  "0000000000",
  "0011000000",
  "1111001111",
]);

/** The platformer-shaped world: the same rule, parsed cells, projected to pixels. */
const PLATFORMER_GRID = booleanOccupancy([
  [false, false, false, false, false, false],
  [false, true, true, false, false, false],
  [true, true, true, false, true, true],
]);
const TILE_PX = 32;
const BASELINE_PX = 720;

describe("the one bottom-contiguous rule answers in both units", () => {
  test("a row for the body that lives in the grid, a height for the body that does not", () => {
    // Runner: the surface is a row, and a pit is null rather than zero, because
    // a body integrating in rows has to be told there is no row.
    expect(bottomContiguousSurfaceRow(RUNNER_GRID, 0)).toBe(3);
    expect(bottomContiguousSurfaceRow(RUNNER_GRID, 2)).toBe(2);
    expect(bottomContiguousSurfaceRow(RUNNER_GRID, 4)).toBeNull();

    // Platformer: the same walk read from the other end, then projected.
    const heights = bottomContiguousHeights(PLATFORMER_GRID);
    expect([...heights]).toEqual([1, 2, 2, 0, 1, 1]);
    expect(surfaceDatum(heights[1]!, TILE_PX, BASELINE_PX)).toBe(BASELINE_PX - 64);
    expect(surfaceDatum(heights[3]!, TILE_PX, BASELINE_PX)).toBe(BASELINE_PX);
  });

  test("a floating cell above a gap is scenery in both readings", () => {
    const floating = stringOccupancy(["0100", "0000", "1001"]);
    expect(bottomContiguousSurfaceRow(floating, 1)).toBeNull();
    expect([...bottomContiguousHeights(floating)]).toEqual([1, 0, 0, 1]);
  });

  test("the projection round-trips, which is what makes it one rule and not three", () => {
    const heights = bottomContiguousHeights(PLATFORMER_GRID);
    const rebuilt = bottomContiguousGrid(heights);
    expect([...bottomContiguousHeights(booleanOccupancy(rebuilt))]).toEqual([...heights]);
    // And the membership predicate the scan uses is the same predicate the
    // projection is built out of.
    for (let row = 0; row < rebuilt.length; row += 1) {
      for (let column = 0; column < heights.length; column += 1) {
        expect(rebuilt[row]![column]).toBe(
          belongsToBottomStack(row, rebuilt.length, heights[column]!),
        );
      }
    }
  });
});

describe("the standing foot, in either unit", () => {
  test("a runner row and a platformer pixel resolve by the same three cases", () => {
    // Rows: zero tolerance, because this track steps in whole rows.
    expect(resolveTerrainStep({ footY: 3, surfaceY: 3, tolerance: 0 })).toEqual({
      footY: 3,
      support: "terrain",
    });
    expect(resolveTerrainStep({ footY: 3, surfaceY: 4, tolerance: 0 }).support).toBe("air");
    expect(resolveTerrainStep({ footY: 3, surfaceY: 2, tolerance: 0 }).footY).toBe(2);

    // Pixels: a one-pixel kerb is absorbed, a tile is a fall.
    expect(resolveTerrainStep({ footY: 688, surfaceY: 689, tolerance: 1 }).support).toBe("terrain");
    expect(resolveTerrainStep({ footY: 688, surfaceY: 720, tolerance: 1 })).toEqual({
      footY: 688,
      support: "air",
    });
  });

  test("a wall is a wall in whatever unit the columns are measured in", () => {
    const heights = bottomContiguousHeights(PLATFORMER_GRID);
    const surfaceAt = (column: number) =>
      surfaceDatum(heights[Math.min(Math.max(column, 0), heights.length - 1)]!, TILE_PX, BASELINE_PX);
    // Walking right off column 2 (height 2) into column 3 (a pit) is a descent,
    // which is a fall and not a wall.
    expect(
      resolveTerrainWalk({
        previousX: 80,
        nextX: 100,
        footY: BASELINE_PX - 64,
        tileUnits: TILE_PX,
        surfaceAt,
        tolerance: 1,
        contactGap: 1,
      }).blocked,
    ).toBe(false);
    // Walking left off column 3 into column 2's face is a wall, and the foot is
    // left one unit clear of it so the column lookup still resolves left.
    const blocked = resolveTerrainWalk({
      previousX: 100,
      nextX: 90,
      footY: BASELINE_PX,
      tileUnits: TILE_PX,
      surfaceAt,
      tolerance: 1,
      contactGap: 1,
    });
    expect(blocked).toEqual({ x: 96, blocked: true, blockedColumn: 2 });
  });
});

describe("the two terrain entries, which is the family's one real disagreement", () => {
  const arriving = {
    x: 4,
    previousFootY: 3.5,
    nextFootY: 4.2,
    vy: 6,
    terrainY: 4,
  } as const;

  test("clamp lands a descending foot that never crossed; crossing buries it", () => {
    // Crossed from above: both entries land it, identically.
    expect(
      resolveVerticalLanding({ ...arriving, terrainEntry: "clamp" }),
    ).toEqual({ footY: 4, vy: 0, support: "terrain", supportId: null });
    expect(
      resolveVerticalLanding({ ...arriving, terrainEntry: "crossing" }),
    ).toEqual({ footY: 4, vy: 0, support: "terrain", supportId: null });

    // Already below the surface when the step began — a horizontal step carried
    // the foot into a raised column. The platformer forgives it; the runner
    // calls it buried, and its own consequence table answers for that.
    const inside = { ...arriving, previousFootY: 4.4, nextFootY: 4.6 };
    expect(resolveVerticalLanding({ ...inside, terrainEntry: "clamp" }).support).toBe("terrain");
    expect(resolveVerticalLanding({ ...inside, terrainEntry: "crossing" }).support).toBe("buried");

    // Ascending into a face is only ever buried, and only crossing can say so.
    const ascending = { ...arriving, vy: -3, previousFootY: 4.6, nextFootY: 4.3 };
    expect(resolveVerticalLanding({ ...ascending, terrainEntry: "clamp" }).support).toBe("air");
    expect(resolveVerticalLanding({ ...ascending, terrainEntry: "crossing" }).support).toBe(
      "buried",
    );
  });

  test("a deck is taken only while descending across it, and never on the way up", () => {
    const decks: readonly OneWayDeck[] = [
      { id: "low", left: 0, right: 200, deckY: 500 },
      { id: "high", left: 0, right: 200, deckY: 400 },
    ];
    // Descending across both: the shallower deck wins, by deckY then by id.
    expect(
      resolveVerticalLanding({
        x: 100,
        previousFootY: 390,
        nextFootY: 510,
        vy: 400,
        terrainY: 720,
        decks,
        terrainEntry: "clamp",
      }),
    ).toEqual({ footY: 400, vy: 0, support: "platform", supportId: "high" });
    // The one it asked to drop through is not there for it.
    expect(
      resolveVerticalLanding({
        x: 100,
        previousFootY: 390,
        nextFootY: 510,
        vy: 400,
        terrainY: 720,
        decks,
        ignoredDeckId: "high",
        terrainEntry: "clamp",
      }).supportId,
    ).toBe("low");
    // Rising through both: neither.
    expect(
      resolveVerticalLanding({
        x: 100,
        previousFootY: 510,
        nextFootY: 390,
        vy: -400,
        terrainY: 720,
        decks,
        terrainEntry: "clamp",
      }).support,
    ).toBe("air");
  });
});

describe("one press, two budgets", () => {
  test("the runner relaunches at one speed; the platformer spends a weaker second impulse", () => {
    const runner = {
      airJumpsUsed: 0,
      nowMs: 0,
      coyoteExpiresAtMs: null,
      crouching: false,
      maximumAirJumps: 1,
      // Rows per second, and the same arc twice: the air jump is a full relaunch.
      jumpVelocity: 18.4,
      airJumpVelocity: 18.4,
    } as const;
    expect(resolveJumpRequest({ ...runner, support: "terrain" })).toEqual({
      kind: "ground",
      vy: -18.4,
      airJumpsUsed: 0,
    });
    expect(resolveJumpRequest({ ...runner, support: "air" })).toEqual({
      kind: "air",
      vy: -18.4,
      airJumpsUsed: 1,
    });
    expect(
      resolveJumpRequest({ ...runner, support: "air", airJumpsUsed: 1 }).kind,
    ).toBe("none");

    const platformer = {
      airJumpsUsed: 0,
      nowMs: 1000,
      coyoteExpiresAtMs: null,
      crouching: false,
      maximumAirJumps: 1,
      // Pixels per second, and deliberately unequal.
      jumpVelocity: 520,
      airJumpVelocity: 440,
    } as const;
    expect(resolveJumpRequest({ ...platformer, support: "air" }).vy).toBe(-440);
    // A grace window is the platformer's alone; the runner passes null and the
    // branch is never open at all.
    expect(
      resolveJumpRequest({ ...platformer, support: "air", coyoteExpiresAtMs: 1080 }),
    ).toEqual({ kind: "ground", vy: -520, airJumpsUsed: 0 });
    // Crouched on the ground, and hanging on a climbable, both refuse.
    expect(resolveJumpRequest({ ...platformer, support: "terrain", crouching: true }).kind).toBe(
      "none",
    );
    expect(resolveJumpRequest({ ...platformer, support: "climbable" }).kind).toBe("none");
  });
});

describe("the two ways to know an arc", () => {
  test("the platformer proves an authored one step by step", () => {
    const reach = simulateJumpArc({
      rise: 64,
      gap: 100,
      horizontalSpeed: 540,
      jumpVelocity: 520,
      airJumpVelocity: null,
      gravity: 1500,
      stepSeconds: 1 / 30,
      maximumSteps: 120,
    });
    expect(reach.reachable).toBe(true);
    expect(reach.landingStep).toBeGreaterThan(0);
    expect(reach.apexRise).toBeGreaterThan(64);
    // A two-tile rise is out of reach on one impulse and inside it on two,
    // which is the whole reason the air jump is load-bearing rather than feel.
    const single = { rise: 128, gap: 0, horizontalSpeed: 540, jumpVelocity: 520, gravity: 1500, stepSeconds: 1 / 30, maximumSteps: 120 };
    expect(simulateJumpArc({ ...single, airJumpVelocity: null }).reachable).toBe(false);
    expect(simulateJumpArc({ ...single, airJumpVelocity: 440 }).reachable).toBe(true);
  });

  test("the runner derives one from admission, and the closure holds", () => {
    const arc = jumpArcFromAdmission({
      maxRise: 2,
      maxClearGap: 3,
      minSpeed: 6,
      peakMargin: 0.75,
      airtimeHeadroom: 1.15,
    });
    expect(arc.peakUnits).toBeCloseTo(2.75, 12);
    expect(arc.airtimeSeconds).toBeCloseTo((4 / 6) * 1.15, 12);
    // v0 = 4P/T and g = 8P/T² is the closure; the apex of that arc is P.
    expect((arc.initialSpeedPerSecond * arc.initialSpeedPerSecond) /
      (2 * arc.gravityPerSecondSquared)).toBeCloseTo(arc.peakUnits, 9);
    // Nothing about it is in rows: the identical call in a pixel genre gives a
    // pixel arc, which is the whole of what the unit being a parameter buys.
    const pixels = jumpArcFromAdmission({
      maxRise: 2 * 32,
      maxClearGap: 3,
      minSpeed: 6,
      peakMargin: 0.75 * 32,
      airtimeHeadroom: 1.15,
    });
    expect(pixels.initialSpeedPerSecond).toBeCloseTo(arc.initialSpeedPerSecond * 32, 9);
  });
});

describe("the named capabilities, and the body that has none of them", () => {
  const zones = [
    { id: "ladder-1", platformId: "deck-1", centerX: 320, upperDeckY: 500, lowerSurfaceY: 628 },
  ] as const;
  const geometry = (zone: (typeof zones)[number]): ClimbGeometry => ({
    centerX: zone.centerX,
    activationHalfWidth: 30,
    upperY: zone.upperDeckY,
    lowerY: zone.lowerSurfaceY,
    deckId: zone.platformId,
  });
  const profile: ClimbProfile = {
    speed: 180,
    endpointTolerance: 12,
    jumpVelocity: -350,
    jumpHorizontalSpeed: 200,
  };

  test("climb is three ways in and two ways out", () => {
    const base = { zones, geometry, profile, x: 320, up: true, down: false } as const;
    expect(
      climbEntryAt({ ...base, support: "terrain", supportId: null, footY: 628 })?.direction,
    ).toBe("up");
    expect(
      climbEntryAt({ ...base, support: "air", supportId: null, footY: 560 })?.direction,
    ).toBe("up");
    expect(
      climbEntryAt({
        ...base,
        support: "platform",
        supportId: "deck-1",
        footY: 500,
        up: false,
        down: true,
      })?.direction,
    ).toBe("down");
    // Both directions held takes nothing, which is what keeps the rule
    // re-askable every frame without an edge.
    expect(
      climbEntryAt({ ...base, support: "terrain", supportId: null, footY: 628, down: true }),
    ).toBeNull();
    // Off the axis by more than the activation width takes nothing either.
    expect(
      climbEntryAt({ ...base, support: "terrain", supportId: null, footY: 628, x: 400 }),
    ).toBeNull();

    const climbing = advanceClimbMotion({
      geometry: geometry(zones[0]),
      profile,
      footY: 600,
      deltaSeconds: 1 / 30,
      up: true,
      down: false,
    });
    expect(climbing).toEqual({ footY: 600 - 6, vy: -180, exit: null });
    expect(
      advanceClimbMotion({
        geometry: geometry(zones[0]),
        profile,
        footY: 502,
        deltaSeconds: 1 / 30,
        up: true,
        down: false,
      }),
    ).toEqual({ footY: 500, vy: 0, exit: "platform" });
    expect(
      advanceClimbMotion({
        geometry: geometry(zones[0]),
        profile,
        footY: 626,
        deltaSeconds: 1 / 30,
        up: false,
        down: true,
      }),
    ).toEqual({ footY: 628, vy: 0, exit: "terrain" });
    // Letting go without steering leaves on the side the body was looking at.
    expect(climbJumpOffVelocity({ profile, left: false, right: false, facing: "left" })).toEqual({
      vx: -200,
      vy: -350,
    });
    expect(climbJumpOffVelocity({ profile, left: false, right: true, facing: "left" })).toEqual({
      vx: 200,
      vy: -350,
    });
  });

  test("crouch, decks and drop-through are each one rule with the genre's number in it", () => {
    expect(resolveCrouchHorizontalVelocity(-540, 80)).toBe(-80);
    expect(resolveCrouchHorizontalVelocity(-40, 80)).toBe(-40);
    expect(resolveCrouchHorizontalVelocity(0, 80)).toBe(0);
    const decks: readonly OneWayDeck[] = [{ id: "d", left: 100, right: 200, deckY: 400 }];
    expect(deckAtX(decks, 150)?.id).toBe("d");
    expect(deckAtX(decks, 250)).toBeUndefined();
    // Still inside the drop while the timer runs, and still inside it after the
    // timer while the feet have not cleared the deck.
    expect(dropThroughActive({ nowMs: 100, expiresAtMs: 180, footY: 600, deckY: 400, clearance: 16 })).toBe(true);
    expect(dropThroughActive({ nowMs: 500, expiresAtMs: 180, footY: 410, deckY: 400, clearance: 16 })).toBe(true);
    expect(dropThroughActive({ nowMs: 500, expiresAtMs: 180, footY: 600, deckY: 400, clearance: 16 })).toBe(false);
  });

  // E7, at the grain this family has one: a body with every capability quiet is
  // the core alone, and the core alone still answers. No decks is exactly the
  // terrain landing, no air budget refuses in the air, no zones is no climb, a
  // crouch cap of zero stops nothing that was not already stopped. There is no
  // roster entry to filter out — traversal is a core, not a frame step — so the
  // subtraction is stated where it can be: the same six hundred frames of both
  // goldens are the proof that removing nothing removed nothing.
  test("subtraction: the core with every capability quiet", () => {
    const bare = {
      x: 0,
      previousFootY: 10,
      nextFootY: 20,
      vy: 5,
      terrainY: 15,
      terrainEntry: "clamp",
    } as const;
    expect(resolveVerticalLanding(bare)).toEqual(
      resolveVerticalLanding({ ...bare, decks: [] }),
    );
    expect(
      resolveJumpRequest({
        support: "air",
        airJumpsUsed: 0,
        nowMs: 0,
        coyoteExpiresAtMs: null,
        crouching: false,
        maximumAirJumps: 0,
        jumpVelocity: 1,
        airJumpVelocity: 1,
      }).kind,
    ).toBe("none");
    expect(
      climbEntryAt({
        zones: [] as readonly (typeof zones)[number][],
        geometry,
        profile,
        support: "terrain",
        supportId: null,
        x: 0,
        footY: 0,
        up: true,
        down: false,
      }),
    ).toBeNull();
    expect(deckAtX([], 0)).toBeUndefined();
  });

  test("the vocabulary is a list, and one entry of it is honestly empty", () => {
    expect([...TRAVERSAL_CAPABILITIES]).toEqual([
      "climb",
      "one-way-decks",
      "crouch",
      "drop-through",
      "wrap",
    ]);
    expect([...TRAVERSAL_LOCOMOTIONS]).toEqual(["ground_v1", "momentum_v1", "thrust_v1"]);
    // `wrap` is named and unimplemented, and saying so is the point: the
    // platformer's contract pins `logical_world_wrap` to false, so a package
    // that asks for it is refused at parse and no runtime ever sees one.
    expect([...UNIMPLEMENTED_CAPABILITIES]).toEqual(["wrap"]);
  });
});
