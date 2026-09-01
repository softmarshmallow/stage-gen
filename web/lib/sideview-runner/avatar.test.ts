import { describe, expect, test } from "bun:test";
import { jumpArcFor, stepAvatar } from "./avatar";
import { BASE_SPEED_COLUMNS_PER_SECOND } from "./difficulty";
import { parseRunnerRuntimeManifest } from "./contract";
import { runnerManifestFixture } from "./fixture";
import { runnerIntent } from "./intent";
import { createSegmentStream, streamAhead } from "./segments";
import { createRunnerWorld, mulberry32, type RunnerWorld } from "./world";

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
    if (world.avatar.deathCause !== null) return { died: true, landed: false };
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
    expect(world.avatar.deathCause).toBe("pit");
    expect(world.avatar.motion).toBe("death");
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
    expect(crashWorld.avatar.deathCause).toBe("step");
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
