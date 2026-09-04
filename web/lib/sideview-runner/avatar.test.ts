import { describe, expect, test } from "bun:test";
import { jumpArcFor, stepAvatar } from "./avatar";
import { BASE_SPEED_COLUMNS_PER_SECOND } from "./difficulty";
import { parseRunnerRuntimeManifest } from "./contract";
import { runnerManifestFixture } from "./fixture";
import { runnerIntent } from "./intent";
import { createSegmentStream, streamAhead } from "./segments";
import { mulberry32 } from "@/lib/kernel/rng";
import { createRunnerWorld, type RunnerWorld } from "./world";

const DT = 1 / 60;
const manifest = parseRunnerRuntimeManifest(runnerManifestFixture());

/** A world whose track is one long crafted chunk instead of the streamed catalog. */
function craftedWorld(occupancyRow5: string, worldManifest = manifest): RunnerWorld {
  const world = createRunnerWorld(worldManifest, 1);
  const width = occupancyRow5.length;
  const empty = "0".repeat(width);
  const stream = createSegmentStream(8, 5);
  streamAhead(
    stream,
    [
      {
        segmentId: "crafted",
        difficulty: 1,
        occupancy: [empty, empty, empty, empty, empty, occupancyRow5, occupancyRow5, occupancyRow5],
        hazards: [],
        pickups: [],
      },
    ],
    { ceiling: 1 },
    mulberry32(1),
    width - 1,
  );
  world.segments = stream;
  return world;
}

/** Tick until death, arrival at `untilColumn`, or the time budget runs out. */
function simulate(
  world: RunnerWorld,
  options: { jumpAtColumn?: number; untilColumn: number; maxSeconds?: number },
): { died: boolean; landed: boolean } {
  const budget = Math.ceil((options.maxSeconds ?? 30) / DT);
  let jumped = false;
  for (let tick = 0; tick < budget; tick += 1) {
    const wantsJump =
      options.jumpAtColumn !== undefined &&
      !jumped &&
      world.avatar.grounded &&
      world.avatar.distanceColumns >= options.jumpAtColumn;
    if (wantsJump) jumped = true;
    world.intent = runnerIntent({ jump: wantsJump });
    stepAvatar(world, DT);
    // A death is an occurrence now: the avatar says what happened and the
    // vitals system decides what it costs, so the test reads the queue.
    if (world.events.frame.some((e) => e.type === "pit" || e.type === "crush")) {
      return { died: true, landed: false };
    }
    if (world.avatar.distanceColumns >= options.untilColumn) {
      return { died: false, landed: world.avatar.grounded };
    }
  }
  throw new Error("simulation ran out of time");
}

describe("jumpArcFor", () => {
  test("derives an arc that satisfies the admission arithmetic", () => {
    const arc = jumpArcFor(2, 3);
    // Flat-ground airtime carries the avatar across gap + 1 columns at the
    // slowest admitted speed, with headroom.
    expect(arc.airtimeSeconds * BASE_SPEED_COLUMNS_PER_SECOND).toBeGreaterThan(4);
    // The peak clears the tallest admitted rise.
    expect(arc.peakRows).toBeGreaterThan(2);
    // The closed forms agree with the kinematics they were solved from.
    expect(
      (arc.initialSpeedRowsPerSecond * arc.initialSpeedRowsPerSecond) /
        (2 * arc.gravityRowsPerSecondSquared),
    ).toBeCloseTo(arc.peakRows, 10);
    expect((2 * arc.initialSpeedRowsPerSecond) / arc.gravityRowsPerSecondSquared).toBeCloseTo(
      arc.airtimeSeconds,
      10,
    );
  });

  test("refuses a nonsensical speed", () => {
    expect(() => jumpArcFor(2, 3, { baseSpeedColumnsPerSecond: 0 })).toThrow("positive minimum speed");
  });
});

describe("stepAvatar", () => {
  test("runs level ground without drama", () => {
    const world = craftedWorld("1".repeat(40));
    const result = simulate(world, { untilColumn: 30 });
    expect(result.died).toBe(false);
    expect(world.avatar.y).toBe(5);
    expect(world.avatar.motion).toBe("run");
  });

  test("clears a max_clear_gap_columns pit when jumped at the edge, at base speed", () => {
    //                     runway     pit(3)   landing
    const world = craftedWorld("1111111111" + "000" + "111111111111111");
    const result = simulate(world, { jumpAtColumn: 9.5, untilColumn: 16 });
    expect(result.died).toBe(false);
    expect(result.landed).toBe(true);
  });

  test("clears the same pit at the fully ramped speed", () => {
    const world = craftedWorld("1111111111" + "000" + "111111111111111");
    world.difficulty.speedMultiplier = 1.5;
    world.difficulty.speedColumnsPerSecond = BASE_SPEED_COLUMNS_PER_SECOND * 1.5;
    const result = simulate(world, { jumpAtColumn: 9.5, untilColumn: 16 });
    expect(result.died).toBe(false);
  });

  test("dies in the pit when the jump never comes", () => {
    const world = craftedWorld("1111111111" + "000" + "111111111111111");
    const result = simulate(world, { untilColumn: 16 });
    expect(result.died).toBe(true);
    expect(world.events.ofType("pit")).toHaveLength(1);
  });

  test("lands a max_rise_tiles step when jumped, dies into its face when not", () => {
    const width = 30;
    const empty = "0".repeat(width);
    const low = "1".repeat(width);
    // The step raises the surface by two rows starting at column 12.
    const raisedRow3 = "0".repeat(12) + "1".repeat(width - 12);
    const stream = createSegmentStream(8, 5);
    streamAhead(
      stream,
      [
        {
          segmentId: "step",
          difficulty: 1,
          occupancy: [empty, empty, empty, raisedRow3, raisedRow3, low, low, low],
          hazards: [],
          pickups: [],
        },
      ],
      { ceiling: 1 },
      mulberry32(1),
      width - 1,
    );
    const jumpWorld = createRunnerWorld(manifest, 1);
    jumpWorld.segments = stream;
    const jumped = simulate(jumpWorld, { jumpAtColumn: 10.8, untilColumn: 16 });
    expect(jumped.died).toBe(false);
    expect(jumpWorld.avatar.y).toBe(3);

    const crashWorld = createRunnerWorld(manifest, 1);
    crashWorld.segments = createSegmentStream(8, 5);
    streamAhead(
      crashWorld.segments,
      [
        {
          segmentId: "step",
          difficulty: 1,
          occupancy: [empty, empty, empty, raisedRow3, raisedRow3, low, low, low],
          hazards: [],
          pickups: [],
        },
      ],
      { ceiling: 1 },
      mulberry32(1),
      width - 1,
    );
    const crashed = simulate(crashWorld, { untilColumn: 16 });
    expect(crashed.died).toBe(true);
    expect(crashWorld.events.ofType("crush")).toHaveLength(1);
  });

  test("holds the death pose and stops advancing once the run is dead", () => {
    const world = craftedWorld("1".repeat(40));
    world.run.phase = "dead";
    const before = world.avatar.distanceColumns;
    world.intent = runnerIntent({ jump: true });
    stepAvatar(world, DT);
    expect(world.avatar.distanceColumns).toBe(before);
    expect(world.avatar.motion).toBe("death");
  });

  test("the air jump relaunches once, then the well is dry until landing", () => {
    // The fixture plays double_arc_v1: one recovery hop in the air.
    const world = craftedWorld("1".repeat(60));
    world.intent = runnerIntent({ jump: true });
    stepAvatar(world, DT);
    expect(world.avatar.grounded).toBe(false);
    expect(world.avatar.jumpImpulses).toBe(1);
    const arc = jumpArcFor(2, 3, world.config.arithmetic);
    // A second press mid-air relaunches to exactly the initial speed.
    stepAvatar(world, DT);
    expect(world.avatar.airJumpsUsed).toBe(1);
    expect(world.avatar.jumpImpulses).toBe(2);
    expect(world.avatar.vy).toBeCloseTo(
      -arc.initialSpeedRowsPerSecond + arc.gravityRowsPerSecondSquared * DT,
      6,
    );
    // A third press finds the well dry: gravity alone.
    const vyBefore = world.avatar.vy;
    stepAvatar(world, DT);
    expect(world.avatar.jumpImpulses).toBe(2);
    expect(world.avatar.vy).toBeGreaterThan(vyBefore);
  });

  test("landing refills the air jump", () => {
    const world = craftedWorld("1".repeat(120));
    world.intent = runnerIntent({ jump: true });
    stepAvatar(world, DT);
    stepAvatar(world, DT);
    expect(world.avatar.airJumpsUsed).toBe(1);
    world.intent = runnerIntent();
    for (let tick = 0; tick < 600 && !world.avatar.grounded; tick += 1) {
      stepAvatar(world, DT);
    }
    expect(world.avatar.grounded).toBe(true);
    expect(world.avatar.airJumpsUsed).toBe(0);
  });

  test("a single_arc_v1 world refuses the air jump", () => {
    const singleHop = runnerManifestFixture();
    (singleHop.gameplay as Record<string, unknown>).jump_profile = "single_arc_v1";
    const world = craftedWorld("1".repeat(60), parseRunnerRuntimeManifest(singleHop));
    world.intent = runnerIntent({ jump: true });
    stepAvatar(world, DT);
    const risingVy = world.avatar.vy;
    stepAvatar(world, DT);
    expect(world.avatar.jumpImpulses).toBe(1);
    expect(world.avatar.vy).toBeGreaterThan(risingVy);
  });

  test("the slide holds while duck is held and releases with it", () => {
    const world = craftedWorld("1".repeat(60));
    world.intent = runnerIntent({ duck: true });
    stepAvatar(world, DT);
    expect(world.avatar.sliding).toBe(true);
    expect(world.avatar.motion).toBe("slide");
    world.intent = runnerIntent();
    stepAvatar(world, DT);
    expect(world.avatar.sliding).toBe(false);
    expect(world.avatar.motion).toBe("run");
  });

  test("a jump cancels the slide", () => {
    const world = craftedWorld("1".repeat(60));
    world.intent = runnerIntent({ duck: true });
    stepAvatar(world, DT);
    expect(world.avatar.sliding).toBe(true);
    world.intent = runnerIntent({ jump: true, duck: true });
    stepAvatar(world, DT);
    expect(world.avatar.sliding).toBe(false);
    expect(world.avatar.motion).toBe("jump");
  });
});

describe("thrust locomotion", () => {
  const THRUST = Object.freeze({
    maxClimbRowsPerSecond: 9,
    maxFallRowsPerSecond: 10,
    climbAccelerationRowsPerSecondSquared: 24,
  });

  const ARENA_WIDTH = 240;
  const ARENA_ROW = "1".repeat(ARENA_WIDTH);
  const EMPTY_ROW = "0".repeat(ARENA_WIDTH);
  const ARENA_CHUNK = {
    segmentId: "crafted_arena",
    difficulty: 1,
    role: "arena" as const,
    occupancy: [
      EMPTY_ROW,
      EMPTY_ROW,
      EMPTY_ROW,
      EMPTY_ROW,
      EMPTY_ROW,
      ARENA_ROW,
      ARENA_ROW,
      ARENA_ROW,
    ],
    hazards: [],
    pickups: [],
  };

  const ENCOUNTER_CONFIG = {
    profile: "barrage_boss_v1",
    locomotion: "thrust_v1",
    intervalColumns: 400,
    arenaSegmentId: "crafted_arena",
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
    bossHeightRows: 4,
    bossHalfWidthColumns: 0,
  };

  /** A flat arena world already switched into thrust. */
  function flyingWorld(): RunnerWorld {
    const world = createRunnerWorld(manifest, 1, {
      encounter: { encounter: ENCOUNTER_CONFIG, arenaChunk: ARENA_CHUNK, moment: null },
    });
    const stream = createSegmentStream(8, 5);
    streamAhead(stream, [ARENA_CHUNK], { ceiling: 1 }, mulberry32(1), ARENA_WIDTH - 1);
    world.segments = stream;
    world.locomotion = "thrust";
    return world;
  }

  test("a held thrust lifts the avatar off the arena floor and wears fly", () => {
    const world = flyingWorld();
    const floor = world.avatar.y;
    world.intent = runnerIntent({ thrust: true });

    for (let tick = 0; tick < 20; tick += 1) stepAvatar(world, DT);

    expect(world.avatar.y).toBeLessThan(floor);
    expect(world.avatar.grounded).toBe(false);
    expect(world.avatar.motion).toBe("fly");
  });

  test("releasing it falls back to the floor and wears run again", () => {
    const world = flyingWorld();
    const floor = world.avatar.y;
    world.intent = runnerIntent({ thrust: true });
    for (let tick = 0; tick < 20; tick += 1) stepAvatar(world, DT);

    world.intent = runnerIntent({ thrust: false });
    for (let tick = 0; tick < 240; tick += 1) stepAvatar(world, DT);

    expect(world.avatar.y).toBeCloseTo(floor, 6);
    expect(world.avatar.grounded).toBe(true);
    expect(world.avatar.motion).toBe("run");
    expect(world.avatar.vy).toBe(0);
  });

  test("the head never crosses the top of the band", () => {
    const world = flyingWorld();
    world.intent = runnerIntent({ thrust: true });

    for (let tick = 0; tick < 600; tick += 1) {
      stepAvatar(world, DT);
      expect(world.avatar.y - world.config.playerHeightTiles).toBeGreaterThanOrEqual(-1e-9);
    }
    // Pinned at the ceiling, not drifting through it.
    expect(world.avatar.y).toBeCloseTo(world.config.playerHeightTiles, 6);
    expect(world.avatar.vy).toBe(0);
  });

  test("it ignores the jump edge and spends no impulse", () => {
    const world = flyingWorld();
    const before = world.avatar.jumpImpulses;
    world.intent = runnerIntent({ jump: true });

    for (let tick = 0; tick < 20; tick += 1) stepAvatar(world, DT);

    expect(world.avatar.jumpImpulses).toBe(before);
    expect(world.avatar.grounded).toBe(true);
    expect(world.avatar.motion).toBe("run");
  });

  test("it never slides, whatever the duck intent says", () => {
    const world = flyingWorld();
    world.intent = runnerIntent({ duck: true });

    stepAvatar(world, DT);

    expect(world.avatar.sliding).toBe(false);
  });

  test("the run keeps carrying the avatar forward while it flies", () => {
    const world = flyingWorld();
    const start = world.avatar.distanceColumns;
    world.intent = runnerIntent({ thrust: true });

    for (let tick = 0; tick < 60; tick += 1) stepAvatar(world, DT);

    expect(world.avatar.distanceColumns).toBeCloseTo(
      start + world.difficulty.speedColumnsPerSecond,
      6,
    );
  });

  test("run locomotion ignores a held thrust", () => {
    const world = craftedWorld("1".repeat(240));
    const floor = world.avatar.y;
    world.intent = runnerIntent({ thrust: true });

    for (let tick = 0; tick < 30; tick += 1) stepAvatar(world, DT);

    expect(world.avatar.y).toBe(floor);
    expect(world.avatar.motion).toBe("run");
  });
});
