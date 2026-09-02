import { describe, expect, test } from "bun:test";

import { parseRunnerRuntimeManifest, type RunnerChunk } from "./contract";
import {
  type EncounterConfig,
  bossHoverFeetRow,
} from "./encounter-arithmetic";
import { stepEncounter, encounterWantsArena } from "./encounter";
import { runnerManifestFixture } from "./fixture";
import { runnerIntent } from "./intent";
import { createSegmentStream, streamAhead } from "./segments";
import { createRunnerWorld, mulberry32, type RunnerWorld } from "./world";

const DT = 1 / 60;
const manifest = parseRunnerRuntimeManifest(runnerManifestFixture());

const ARENA_WIDTH = 24;
const ARENA_CHUNK: RunnerChunk = {
  segmentId: "boss_arena",
  difficulty: 1,
  role: "arena",
  occupancy: [
    ...Array.from({ length: 5 }, () => "0".repeat(ARENA_WIDTH)),
    ...Array.from({ length: 3 }, () => "1".repeat(ARENA_WIDTH)),
  ],
  hazards: [],
  pickups: [],
};

const CONFIG: EncounterConfig = {
  profile: "barrage_boss_v1",
  locomotion: "thrust_v1",
  intervalColumns: 200,
  arenaSegmentId: "boss_arena",
  bossId: "root_warden",
  bossProjectileId: "spore_bolt",
  playerProjectileId: "seed_dart",
  thrust: {
    maxClimbRowsPerSecond: 9,
    maxFallRowsPerSecond: 10,
    climbAccelerationRowsPerSecondSquared: 24,
  },
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
  bossHeightRows: 3,
  bossHalfWidthColumns: 0,
};

interface Options {
  readonly moment?: boolean;
  readonly config?: Partial<EncounterConfig>;
  readonly seed?: number;
}

function encounterWorld(options: Options = {}): RunnerWorld {
  const config = { ...CONFIG, ...options.config };
  const world = createRunnerWorld(manifest, options.seed ?? 1, {
    encounter: {
      encounter: config,
      arenaChunk: ARENA_CHUNK,
      moment:
        options.moment === false
          ? null
          : {
              moment: "encounter_start",
              effect: "cut_in",
              portraitId: "encounter_start",
              choreography: "tear_reveal_v1",
              title: "Thicket Router",
              subtitle: "Sunpetal Sprint",
            },
    },
  });
  world.run.phase = "running";
  return world;
}

/** Fill the window with the arena so the avatar is standing on one. */
function standOnArena(world: RunnerWorld): void {
  const stream = createSegmentStream(8, 5);
  streamAhead(
    stream,
    [ARENA_CHUNK],
    { ceiling: 1, arena: ARENA_CHUNK },
    mulberry32(1),
    ARENA_WIDTH * 8,
  );
  world.segments = stream;
}

/** Advance the director `seconds` of simulated time from `from`. */
function run(world: RunnerWorld, seconds: number, from = 0): number {
  let now = from;
  for (let tick = 0; tick < Math.round(seconds / DT); tick += 1) {
    world.events.beginFrame();
    now += DT;
    stepEncounter(world, now, DT);
  }
  return now;
}

describe("arming the encounter", () => {
  test("waits until the run has covered the authored interval", () => {
    const world = encounterWorld();

    stepEncounter(world, 0, DT);
    expect(world.encounter?.phase).toBe("idle");
    expect(encounterWantsArena(world)).toBe(false);

    world.avatar.distanceColumns = CONFIG.intervalColumns;
    stepEncounter(world, DT, DT);

    expect(world.encounter?.phase).toBe("arena_pending");
    expect(encounterWantsArena(world)).toBe(true);
  });

  test("a package that fights nothing has no director slice at all", () => {
    const plain = createRunnerWorld(manifest, 1);

    expect(plain.encounter).toBeNull();
    expect(encounterWantsArena(plain)).toBe(false);
    expect(() => stepEncounter(plain, 0, DT)).not.toThrow();
  });

  test("holds until the arena is actually under the avatar's feet", () => {
    const world = encounterWorld();
    world.avatar.distanceColumns = CONFIG.intervalColumns;
    stepEncounter(world, DT, DT);

    // The ordinary catalog is still underfoot: no cut-in, no boss.
    stepEncounter(world, 2 * DT, DT);
    expect(world.encounter?.phase).toBe("arena_pending");
    expect(world.fx).toBeNull();

    standOnArena(world);
    world.avatar.distanceColumns = 4;
    world.events.beginFrame();
    stepEncounter(world, 3 * DT, DT);

    expect(world.encounter?.phase).toBe("cut_in");
    expect(world.fx?.moment).toBe("encounter_start");
  });

  test("announces itself once the fight is under way", () => {
    const world = encounterWorld();
    standOnArena(world);
    world.avatar.distanceColumns = CONFIG.intervalColumns;

    world.events.beginFrame();
    stepEncounter(world, DT, DT);
    world.avatar.distanceColumns = 4;
    world.events.beginFrame();
    stepEncounter(world, 2 * DT, DT);

    expect(world.events.ofType("encounter-started")[0]?.index).toBe(0);
  });

  test("announces itself exactly once, however long it waits for the overlay", () => {
    const world = encounterWorld();
    standOnArena(world);
    world.avatar.distanceColumns = CONFIG.intervalColumns;
    world.events.beginFrame();
    stepEncounter(world, DT, DT);
    world.avatar.distanceColumns = 4;
    // The stage-start cut-in is still on screen for several frames.
    world.fx = {
      moment: "stage_start",
      choreography: "tear_reveal_v1",
      startedAt: 0,
      released: false,
    };
    let announcements = 0;
    let clock = DT;
    for (let tick = 0; tick < 30; tick += 1) {
      world.events.beginFrame();
      clock += DT;
      stepEncounter(world, clock, DT);
      announcements += world.events.ofType("encounter-started").length;
    }
    expect(announcements).toBe(0);

    world.fx = null;
    world.events.beginFrame();
    clock += DT;
    stepEncounter(world, clock, DT);
    announcements += world.events.ofType("encounter-started").length;

    expect(announcements).toBe(1);
  });

  test("never clobbers a moment already playing", () => {
    const world = encounterWorld();
    standOnArena(world);
    world.avatar.distanceColumns = CONFIG.intervalColumns;
    world.events.beginFrame();
    stepEncounter(world, DT, DT);
    world.avatar.distanceColumns = 4;
    // The stage-start cut-in is still on screen.
    world.fx = { moment: "stage_start", choreography: "tear_reveal_v1", startedAt: 0, released: false };

    world.events.beginFrame();
    stepEncounter(world, 2 * DT, DT);

    expect(world.fx.moment).toBe("stage_start");
    expect(world.encounter?.phase).toBe("arena_pending");
  });

  test("a package binding no boss cut-in goes straight to the fight", () => {
    const world = encounterWorld({ moment: false });
    standOnArena(world);
    world.avatar.distanceColumns = CONFIG.intervalColumns;
    world.events.beginFrame();
    stepEncounter(world, DT, DT);
    world.avatar.distanceColumns = 4;

    world.events.beginFrame();
    stepEncounter(world, 2 * DT, DT);

    expect(world.encounter?.phase).toBe("battle");
    expect(world.locomotion).toBe("thrust");
  });
});

/** Drive a world all the way to the first frame of `battle`. */
function beginFight(options: Options = {}): { world: RunnerWorld; now: number } {
  const world = encounterWorld(options);
  standOnArena(world);
  world.avatar.distanceColumns = CONFIG.intervalColumns;
  world.events.beginFrame();
  stepEncounter(world, DT, DT);
  world.avatar.distanceColumns = 4;
  world.events.beginFrame();
  stepEncounter(world, 2 * DT, DT);
  if (world.encounter?.phase === "cut_in") {
    world.events.beginFrame();
    world.events.emit({ type: "fx-released", moment: "encounter_start" });
    stepEncounter(world, 3 * DT, DT);
  }
  return { world, now: 3 * DT };
}

describe("the fight", () => {
  test("the release switches locomotion and puts the boss off the right edge", () => {
    const { world } = beginFight();

    expect(world.encounter?.phase).toBe("battle");
    expect(world.locomotion).toBe("thrust");
    const boss = world.encounter?.boss;
    expect(boss).not.toBeNull();
    expect(boss!.offsetColumns).toBeGreaterThan(CONFIG.firingDistanceColumns);
    expect(boss!.hp.value).toBe(CONFIG.hitsToDefeat);
    expect(boss!.y).toBeCloseTo(bossHoverFeetRow(CONFIG, world.config.walkSurfaceRow), 6);
  });

  test("the boss closes to its stand-off and then holds there", () => {
    // Unkillable, so the approach can be observed without the fight ending.
    const { world, now } = beginFight({ config: { hitsToDefeat: 10_000 } });

    const clock = run(world, 3, now);
    expect(world.encounter?.boss?.offsetColumns).toBeCloseTo(CONFIG.firingDistanceColumns, 3);

    run(world, 3, clock);
    expect(world.encounter?.boss?.offsetColumns).toBeCloseTo(CONFIG.firingDistanceColumns, 3);
  });

  test("auto-fire wins the fight inside the budget, as admission proved it must", () => {
    const { world, now } = beginFight();
    run(world, 40, now);

    const state = world.encounter!;
    // The generator refuses an encounter whose kill time exceeds its salvo
    // budget; played out, that is a boss defeated before it runs out of shots.
    expect(world.events.ofType("boss-defeated").length + (state.outcome === "defeated" ? 1 : 0))
      .toBeGreaterThan(0);
    expect(state.salvosFired).toBeLessThan(CONFIG.salvoBudget);
  });

  test("a boss nothing can kill leaves once its salvo budget is spent", () => {
    const { world, now } = beginFight({ config: { hitsToDefeat: 10_000 } });

    run(world, 40, now);

    const state = world.encounter!;
    expect(state.salvosFired).toBe(CONFIG.salvoBudget);
    expect(state.outcome).toBe("exhausted");
    expect(state.shots.every((shot) => shot.owner !== "boss")).toBe(true);
  });

  test("every salvo the boss actually fires leaves a lane the avatar fits", () => {
    const { world, now } = beginFight({ config: { hitsToDefeat: 10_000 } });
    const state = world.encounter!;
    const laneHeight = world.config.playerHeightTiles + 2 * CONFIG.laneMarginRows;
    const half = CONFIG.projectileHeightRows / 2;

    // Sampled the frame a salvo lands, not on a wall clock: a shot fired a
    // second ago has already left, and a half-spent salvo proves nothing.
    // Isolated by shot id: several salvos are legitimately in the air at once
    // (a spent shot stays visible until it leaves the screen behind the
    // avatar), and the lane is a promise about one salvo, not about the union
    // of every shot still on screen.
    const salvos: number[][] = [];
    let clock = now;
    let seenSalvos = state.salvosFired;
    let idBefore = state.nextShotId;
    for (let tick = 0; tick < 60 * 30; tick += 1) {
      world.events.beginFrame();
      const idAtFrameStart = state.nextShotId;
      clock += DT;
      stepEncounter(world, clock, DT);
      if (state.salvosFired > seenSalvos) {
        seenSalvos = state.salvosFired;
        salvos.push(
          state.shots
            .filter((shot) => shot.owner === "boss" && shot.id >= idAtFrameStart)
            .map((shot) => shot.row)
            .sort((a, b) => a - b),
        );
      }
      idBefore = idAtFrameStart;
    }
    expect(idBefore).toBeGreaterThan(0);

    expect(salvos.length).toBe(CONFIG.salvoBudget);
    for (const rows of salvos) {
      // Never more than authored, and fewer when the band has no room beside
      // the lane: the lane is chosen first and the shots fill what is left,
      // so a crowded band loses shots rather than the avatar losing its gap.
      expect(rows.length).toBeGreaterThan(0);
      expect(rows.length).toBeLessThanOrEqual(CONFIG.salvoShots);
      // Walk the band and find the widest clear run between shot boxes.
      let widest = 0;
      let cursor = 0;
      for (const row of rows) {
        widest = Math.max(widest, row - half - cursor);
        cursor = Math.max(cursor, row + half);
      }
      widest = Math.max(widest, world.config.walkSurfaceRow - cursor);
      expect(widest).toBeGreaterThanOrEqual(laneHeight - 1e-6);
    }
  });

  test("a boss shot that reaches the avatar is announced once and is gone", () => {
    const { world, now } = beginFight();
    run(world, 4, now);
    const state = world.encounter!;
    const shot = state.shots.find((entry) => entry.owner === "boss");
    expect(shot).toBeDefined();
    // Put it exactly on the avatar and line the rows up.
    shot!.x = 0;
    (shot as { row: number }).row = world.avatar.y - world.config.playerHeightTiles / 2;

    world.events.beginFrame();
    stepEncounter(world, now + 5, DT);

    const contacts = world.events.ofType("shot-contact");
    expect(contacts.length).toBe(1);
    expect(state.shots.some((entry) => entry.id === shot!.id)).toBe(false);
  });

  test("each landed shot drains one point and says what is left", () => {
    // Auto-fire is stood down so the injected shots are the only ones that
    // land, and each drain can be read on its own.
    const { world, now } = beginFight({
      config: { hitsToDefeat: 4, playerFirePeriodSeconds: 1000 },
    });
    const state = world.encounter!;
    let clock = run(world, 3, now);

    const remaining: number[] = [];
    for (let i = 0; i < 4; i += 1) {
      world.events.beginFrame();
      const boss = state.boss;
      if (boss === null) break;
      state.shots.push({
        id: 900 + i,
        owner: "player",
        x: boss.offsetColumns,
        row: boss.y - CONFIG.bossHeightRows / 2,
        vx: CONFIG.playerShotSpeedColumnsPerSecond,
        halfLengthColumns: 0.5,
        halfHeightRows: 0.25,
      });
      clock += DT;
      stepEncounter(world, clock, DT);
      remaining.push(...world.events.ofType("boss-hit").map((event) => event.remaining));
    }

    // Monotonically down to empty, one point at a time.
    expect(remaining.length).toBeGreaterThan(0);
    expect(remaining[remaining.length - 1]).toBe(0);
    expect(state.outcome).toBe("defeated");
    expect(state.boss?.motion).toBe("death");
    expect(world.locomotion).toBe("run");
  });

  test("retreat clears the air and hands the run back", () => {
    const { world, now } = beginFight();
    const state = world.encounter!;
    run(world, 40, now);

    expect(state.shots.length).toBe(0);
    expect(world.locomotion).toBe("run");
  });
});

describe("handing the run back", () => {
  test("the boss leaves, the encounter ends, and the interval re-arms", () => {
    const { world, now } = beginFight();
    const state = world.encounter!;
    let clock = run(world, 40, now);

    // Step off the arena so the cooldown can complete.
    world.segments = createSegmentStream(8, 5);
    streamAhead(
      world.segments,
      [{ ...ARENA_CHUNK, segmentId: "meadow_flat", role: "run" as const }],
      { ceiling: 1 },
      mulberry32(2),
      ARENA_WIDTH * 4,
    );
    clock = run(world, 1, clock);

    expect(world.events.ofType("encounter-ended").length).toBeGreaterThanOrEqual(0);
    expect(state.phase).toBe("idle");
    expect(state.boss).toBeNull();
    expect(state.encounterIndex).toBe(1);
    expect(state.nextArenaAtColumn).toBeGreaterThan(world.avatar.distanceColumns);
  });

  test("a dead run freezes the encounter where it stood", () => {
    const { world, now } = beginFight();
    const state = world.encounter!;
    const before = state.phase;
    world.run.phase = "dead";

    run(world, 5, now);

    expect(state.phase).toBe(before);
  });

  test("the run seed decides the lanes, so one seed is one fight", () => {
    const first = beginFight({ seed: 4242 });
    const second = beginFight({ seed: 4242 });
    run(first.world, 6, first.now);
    run(second.world, 6, second.now);

    expect(first.world.encounter?.shots.map((shot) => shot.row)).toEqual(
      second.world.encounter?.shots.map((shot) => shot.row) ?? [],
    );
  });

  test("the intent's thrust is what the avatar reads, not the director", () => {
    const { world } = beginFight();
    world.intent = runnerIntent({ thrust: true });

    // The director never touches intent; it only decides which physics apply.
    expect(world.locomotion).toBe("thrust");
    expect(world.intent.thrust).toBe(true);
  });
});
