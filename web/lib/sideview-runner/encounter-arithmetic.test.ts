import { describe, expect, test } from "bun:test";

import {
  BOSS_APPROACH_COLUMNS_PER_SECOND,
  BOSS_RETREAT_COLUMNS_PER_SECOND,
  type EncounterConfig,
  type EncounterShot,
  advanceShot,
  bossApproach,
  bossBox,
  bossHoverFeetRow,
  bossRetreat,
  boxesOverlap,
  createBossState,
  createEncounterState,
  encounterStreamsArena,
  laneSeedFor,
  mulberry32,
  salvoRows,
  shotBox,
  shotExpired,
  thrustVelocity,
} from "./encounter-arithmetic";

const THRUST = Object.freeze({
  maxClimbRowsPerSecond: 9,
  maxFallRowsPerSecond: 10,
  climbAccelerationRowsPerSecondSquared: 24,
});

const CONFIG: EncounterConfig = Object.freeze({
  profile: "barrage_boss_v1",
  locomotion: "thrust_v1",
  intervalColumns: 400,
  arenaSegmentId: "boss_arena",
  bossId: "root_warden",
  bossProjectileId: "spore_bolt",
  playerProjectileId: "seed_dart",
  thrust: THRUST,
  firingDistanceColumns: 10,
  projectileSpeedColumnsPerSecond: 7.5,
  projectileHeightRows: 1,
  salvoShots: 3,
  salvoPeriodSeconds: 1.5,
  salvoBudget: 8,
  laneMarginRows: 0.5,
  hitsToDefeat: 10,
  playerFirePeriodSeconds: 0.5,
  playerShotSpeedColumnsPerSecond: 12,
  bossHeightRows: 5,
});

function bossShot(overrides: Partial<EncounterShot> = {}): EncounterShot {
  return {
    id: 1,
    owner: "boss",
    x: 10,
    row: 4,
    vx: -7.5,
    halfLengthColumns: 0.2,
    halfHeightRows: 0.5,
    ...overrides,
  };
}

describe("the encounter's own state", () => {
  test("is born idle with the first arena armed at the authored interval", () => {
    const state = createEncounterState(CONFIG);

    expect(state.phase).toBe("idle");
    expect(state.nextArenaAtColumn).toBe(400);
    expect(state.boss).toBeNull();
    expect(state.shots).toEqual([]);
  });

  test("streams the arena from the moment it is asked for until the boss is gone", () => {
    expect(encounterStreamsArena("idle")).toBe(false);
    expect(encounterStreamsArena("arena_pending")).toBe(true);
    expect(encounterStreamsArena("cut_in")).toBe(true);
    expect(encounterStreamsArena("battle")).toBe(true);
    expect(encounterStreamsArena("retreat")).toBe(true);
    // Cooldown is the arena playing out, not the arena being asked for.
    expect(encounterStreamsArena("cooldown")).toBe(false);
  });

  test("the boss arrives at full health wearing its hover", () => {
    const boss = createBossState(CONFIG, 24, 9);

    expect(boss.offsetColumns).toBe(24);
    expect(boss.motion).toBe("hover");
    expect(boss.hp.value).toBe(10);
    expect(boss.hp.depleted).toBe(false);
  });
});

describe("where the boss stands", () => {
  test("centres a boss shorter than the band, and never sinks it below the floor", () => {
    // A five-row boss in a nine-row band leaves four rows of slack, half above.
    expect(bossHoverFeetRow(CONFIG, 9)).toBeCloseTo(7, 6);
    // Exactly as tall as the band: it stands on the floor.
    expect(bossHoverFeetRow(CONFIG, 5)).toBeCloseTo(5, 6);
    // Taller than the band: still the floor, never below it.
    expect(bossHoverFeetRow(CONFIG, 3)).toBeCloseTo(3, 6);
  });

  test("closes at the entry speed and then locks at its firing distance", () => {
    const afterOneSecond = bossApproach(24, 10, 1);

    expect(afterOneSecond).toBeCloseTo(24 - BOSS_APPROACH_COLUMNS_PER_SECOND, 6);
    expect(bossApproach(10.5, 10, 1)).toBe(10);
    expect(bossApproach(10, 10, 1)).toBe(10);
  });

  test("retreats away from the avatar", () => {
    expect(bossRetreat(10, 1)).toBeCloseTo(10 + BOSS_RETREAT_COLUMNS_PER_SECOND, 6);
  });
});

describe("a salvo always leaves a lane", () => {
  const walkSurfaceRow = 8;
  const avatarHeightRows = 2.8;

  test("leaves a lane at least the avatar plus twice its margin, for many seeds", () => {
    const laneHeight = avatarHeightRows + 2 * CONFIG.laneMarginRows;
    for (let seed = 0; seed < 500; seed += 1) {
      const salvo = salvoRows(mulberry32(seed), {
        walkSurfaceRow,
        avatarHeightRows,
        laneMarginRows: CONFIG.laneMarginRows,
        projectileHeightRows: CONFIG.projectileHeightRows,
        shots: CONFIG.salvoShots,
      });

      expect(salvo.lane.bottom - salvo.lane.top).toBeCloseTo(laneHeight, 9);
      expect(salvo.lane.top).toBeGreaterThanOrEqual(0);
      expect(salvo.lane.bottom).toBeLessThanOrEqual(walkSurfaceRow + 1e-9);
      for (const row of salvo.rows) {
        const top = row - CONFIG.projectileHeightRows / 2;
        const bottom = row + CONFIG.projectileHeightRows / 2;
        // Every shot is inside the band ...
        expect(top).toBeGreaterThanOrEqual(-1e-9);
        expect(bottom).toBeLessThanOrEqual(walkSurfaceRow + 1e-9);
        // ... and outside the lane.
        const overlapsLane = top < salvo.lane.bottom - 1e-9 && bottom > salvo.lane.top + 1e-9;
        expect(overlapsLane).toBe(false);
      }
    }
  });

  test("never returns more shots than the band has room for beside the lane", () => {
    const salvo = salvoRows(mulberry32(7), {
      walkSurfaceRow: 4,
      avatarHeightRows: 2.8,
      laneMarginRows: 0.5,
      projectileHeightRows: 1,
      shots: 6,
    });

    expect(salvo.rows.length).toBeLessThanOrEqual(6);
    for (const row of salvo.rows) {
      expect(row - 0.5).toBeGreaterThanOrEqual(-1e-9);
      expect(row + 0.5).toBeLessThanOrEqual(4 + 1e-9);
    }
  });

  test("is reproducible from its seed", () => {
    const options = {
      walkSurfaceRow,
      avatarHeightRows,
      laneMarginRows: 0.5,
      projectileHeightRows: 1,
      shots: 3,
    };

    expect(salvoRows(mulberry32(99), options)).toEqual(salvoRows(mulberry32(99), options));
  });

  test("differs between the encounters of one run", () => {
    const first = laneSeedFor(1234, 0);
    const second = laneSeedFor(1234, 1);

    expect(first).not.toBe(second);
    // And the same ordinal of the same run is the same fight.
    expect(laneSeedFor(1234, 1)).toBe(second);
  });
});

describe("shots in the air", () => {
  test("a boss shot closes on the avatar at its published speed", () => {
    const shot = bossShot({ x: 10 });

    advanceShot(shot, 1);

    // Ten columns of stand-off at 7.5 columns per second: the flight is the
    // 1.333s the offline dodge proof was written against.
    expect(shot.x).toBeCloseTo(2.5, 6);
    expect(10 / CONFIG.projectileSpeedColumnsPerSecond).toBeCloseTo(1.3333, 3);
  });

  test("a boss shot is spent once it is behind the avatar", () => {
    const limits = { behindColumns: 4, aheadColumns: 20 };

    expect(shotExpired(bossShot({ x: 0 }), limits)).toBe(false);
    expect(shotExpired(bossShot({ x: -3.9 }), limits)).toBe(false);
    expect(shotExpired(bossShot({ x: -4.1 }), limits)).toBe(true);
  });

  test("a player shot is spent once it has passed the boss", () => {
    const player = bossShot({ owner: "player", vx: 12, x: 21 });

    expect(shotExpired(player, { behindColumns: 4, aheadColumns: 20 })).toBe(true);
    expect(shotExpired({ ...player, x: 19 }, { behindColumns: 4, aheadColumns: 20 })).toBe(false);
  });

  test("overlap is strict, so a box resting exactly on an edge does not hit", () => {
    const a = { left: 0, right: 1, top: 0, bottom: 1 };

    expect(boxesOverlap(a, { left: 1, right: 2, top: 0, bottom: 1 })).toBe(false);
    expect(boxesOverlap(a, { left: 0.99, right: 2, top: 0, bottom: 1 })).toBe(true);
  });

  test("a shot's box is centred on its own row", () => {
    expect(shotBox(bossShot({ x: 3, row: 4 }))).toEqual({
      left: 2.8,
      right: 3.2,
      top: 3.5,
      bottom: 4.5,
    });
  });

  test("the boss's box hangs from its feet row", () => {
    const boss = createBossState(CONFIG, 10, 9);
    boss.y = 7;

    const box = bossBox(boss, CONFIG);

    expect(box.bottom).toBe(7);
    expect(box.top).toBe(2);
    expect(box.right - box.left).toBeCloseTo(2 * 5 * 0.35, 6);
  });
});

describe("thrust", () => {
  test("climbs toward its cap while held", () => {
    let vy = 0;
    for (let i = 0; i < 60; i += 1) vy = thrustVelocity(vy, true, 1 / 60, THRUST);

    expect(vy).toBeCloseTo(-THRUST.maxClimbRowsPerSecond, 6);
  });

  test("falls toward its own, faster cap when released", () => {
    let vy = 0;
    for (let i = 0; i < 60; i += 1) vy = thrustVelocity(vy, false, 1 / 60, THRUST);

    expect(vy).toBeCloseTo(THRUST.maxFallRowsPerSecond, 6);
  });

  test("accelerates at the published rate before either cap is reached", () => {
    expect(thrustVelocity(0, true, 0.1, THRUST)).toBeCloseTo(-2.4, 6);
    expect(thrustVelocity(0, false, 0.1, THRUST)).toBeCloseTo(2.4, 6);
  });

  test("the climb cap is the slower of the two, which is what a dodge costs", () => {
    expect(THRUST.maxClimbRowsPerSecond).toBeLessThan(THRUST.maxFallRowsPerSecond);
  });
});
