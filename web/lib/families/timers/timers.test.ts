import { describe, expect, test } from "bun:test";
import { sealSystems } from "@/lib/kernel/systems";
import {
  advanceTimers,
  createTimersState,
  createTimersSystem,
  resetTimers,
  shownTimer,
  type TimerParams,
  type TimersState,
} from "./timers";
import { parseTimersBlock, timerParamsFromBlock } from "./manifest";
import { PREPARED_RUNTIME_BLOCKS, type TimersBlock } from "@/lib/manifest/prepared-manifest";

const STEP = { dt: 1 / 30, now: 0, frame: 1 } as const;
/** The platformer's own step, in milliseconds. */
const FRAME_MS = 1000 / 30;

// --- E4: one countdown, two worlds ---------------------------------------------------------------
//
// Neither shipped genre counts down today, so the second instantiation is a
// hand-built world rather than a second roster — the same shape `session`'s E4
// took in step 3, and for the same reason: a family proven against one world is
// a function, and against two is a family.

/** A minigame-shaped world: one visible clock, and its end ends the run. */
type WaveWorld = {
  timers: TimersState;
  clock: { simulationDt: number };
  ended: string | null;
};

const WAVE_TIMERS: readonly TimerParams[] = [
  { timerId: "round", durationMs: 90_000, onEnd: "session_ended", shown: true },
];

/** A runner-shaped world: two clocks, one of them invisible, and a hold. */
type FeverWorld = {
  countdowns: TimersState;
  dt: number;
  held: boolean;
  heard: string[];
};

const FEVER_TIMERS: readonly TimerParams[] = [
  { timerId: "fever", durationMs: 4_000, onEnd: "session_ended", shown: false },
  { timerId: "grace", durationMs: 1_000, onEnd: "session_ended", shown: true },
];

describe("E4: the same countdown in a timed round and a fever window", () => {
  test("a minigame-shaped world: ninety seconds at the platformer's own step", () => {
    const world: WaveWorld = {
      timers: createTimersState(WAVE_TIMERS),
      clock: { simulationDt: FRAME_MS },
      ended: null,
    };
    const system = createTimersSystem<WaveWorld>({
      slice: "timers",
      params: WAVE_TIMERS,
      simulationDt: (w) => w.clock.simulationDt,
      onExpired: (w, timerId, onEnd) => {
        w.ended = `${timerId}:${onEnd}`;
      },
    });
    // Ninety seconds is 2701 frames of 1/30s, not 2700, and the extra frame is
    // measured rather than tolerated: 1000/30 is not representable, the sum of
    // 2700 of them falls a few nanoseconds SHORT of ninety seconds, and a
    // countdown expires when the time has elapsed rather than when it nearly
    // has. The frame the ninetieth second passes during is the 2701st.
    for (let frame = 1; frame <= 2700; frame += 1) system.update(world, STEP);
    expect(world.ended).toBeNull();
    expect(world.timers.entries[0]?.remainingMs).toBeGreaterThan(0);
    expect(world.timers.entries[0]?.remainingMs).toBeLessThan(1e-6);
    system.update(world, STEP);
    expect(world.ended).toBe("round:session_ended");
    expect(world.timers.entries[0]).toEqual({
      timerId: "round",
      remainingMs: 0,
      elapsedMs: 90_000,
      expired: true,
    });
    // And it says so exactly once, however long the world takes to tear down.
    world.ended = null;
    for (let frame = 0; frame < 30; frame += 1) system.update(world, STEP);
    expect(world.ended).toBeNull();
  });

  test("a runner-shaped world: two clocks, a hold, and an edge each", () => {
    const world: FeverWorld = {
      countdowns: createTimersState(FEVER_TIMERS),
      dt: 100,
      held: false,
      heard: [],
    };
    const system = createTimersSystem<FeverWorld>({
      slice: "countdowns",
      params: FEVER_TIMERS,
      simulationDt: (w) => w.dt,
      counting: (w) => !w.held,
      onExpired: (w, timerId) => w.heard.push(timerId),
    });
    for (let tick = 0; tick < 10; tick += 1) system.update(world, STEP);
    // The shorter one ended; the longer one is still running.
    expect(world.heard).toEqual(["grace"]);
    // A hold stops the clock the player is racing. This is the half a deadline
    // stamped against `step.now` cannot buy: under a hold, nothing counts.
    world.held = true;
    for (let tick = 0; tick < 100; tick += 1) system.update(world, STEP);
    expect(world.countdowns.entries[0]?.remainingMs).toBe(3_000);
    world.held = false;
    for (let tick = 0; tick < 30; tick += 1) system.update(world, STEP);
    expect(world.heard).toEqual(["grace", "fever"]);
  });

  test("the two worlds share no field but the slice the family owns", () => {
    const wave = new Set(["timers", "clock", "ended"]);
    const fever = new Set(["countdowns", "dt", "held", "heard"]);
    expect([...wave].filter((key) => fever.has(key))).toEqual([]);
  });
});

// --- the arithmetic -----------------------------------------------------------------------------

describe("a countdown is a value, not a stamp", () => {
  test("a frame long enough to cross the whole remainder still reports one edge", () => {
    const state = createTimersState(WAVE_TIMERS);
    expect(advanceTimers(state, WAVE_TIMERS, 500_000)).toEqual(["round"]);
    expect(advanceTimers(state, WAVE_TIMERS, 500_000)).toEqual([]);
    expect(state.entries[0]?.elapsedMs).toBe(90_000);
  });

  test("a frame with no simulation time advances nothing", () => {
    // Which is the hold, seen from the other side: a zero delta is a frame the
    // countdown did not happen on.
    const state = createTimersState(FEVER_TIMERS);
    expect(advanceTimers(state, FEVER_TIMERS, 0)).toEqual([]);
    expect(state.entries[1]?.remainingMs).toBe(1_000);
  });

  test("the shown entry is the one a readout draws, and there may be none", () => {
    const state = createTimersState(FEVER_TIMERS);
    expect(shownTimer(state, FEVER_TIMERS)?.timerId).toBe("grace");
    const hidden = FEVER_TIMERS.map((entry) => ({ ...entry, shown: false }));
    expect(shownTimer(createTimersState(hidden), hidden)).toBeNull();
  });

  test("a reset puts every countdown back to its authored duration, in place", () => {
    const state = createTimersState(WAVE_TIMERS);
    const held = state;
    advanceTimers(state, WAVE_TIMERS, 60_000);
    resetTimers(state, WAVE_TIMERS);
    expect(held.entries[0]).toEqual({
      timerId: "round",
      remainingMs: 90_000,
      elapsedMs: 0,
      expired: false,
    });
  });
});

// --- E7: the subtraction ------------------------------------------------------------------------

describe("E7: a roster with no countdown", () => {
  test("the roster with `timers/countdown` removed seals to the identical order minus it", () => {
    type W = { timers: TimersState; clock: { simulationDt: number } };
    const timers = createTimersSystem<W>({
      slice: "timers",
      params: WAVE_TIMERS,
      reads: ["clock"],
      simulationDt: (w) => w.clock.simulationDt,
    });
    const noop = { update: () => {} };
    const clock = { id: "clock/step", contractVersion: "v1", reads: [], writes: ["clock"], ...noop } as const;
    const readout = {
      id: "hud/readout",
      contractVersion: "v1",
      reads: ["timers"],
      writes: [],
      ...noop,
    } as const;
    const full = sealSystems<W>([clock, timers, readout]);
    const quiet = sealSystems<W>([clock, { ...readout, reads: [] }]);
    expect(full.order).toEqual(["clock/step", "timers/countdown", "hud/readout"]);
    expect(quiet.order).toEqual(full.order.filter((id) => id !== "timers/countdown"));
  });

  test("a package that authors no timers seals the system quiet rather than absent", () => {
    // Rule 6's shape: the system is in the roster, its parameters are empty, and
    // it returns at its first line. The subtraction is the empty list, not a
    // countdown from a default nobody wrote.
    type W = { timers: TimersState; dt: number };
    const params = timerParamsFromBlock(null);
    expect(params).toEqual([]);
    const world: W = { timers: createTimersState(params), dt: 16 };
    const system = createTimersSystem<W>({
      slice: "timers",
      params,
      simulationDt: (w) => w.dt,
      onExpired: () => {
        throw new Error("a package with no timers has nothing to expire");
      },
    });
    for (let tick = 0; tick < 100; tick += 1) system.update(world, STEP);
    expect(world.timers.entries).toEqual([]);
  });
});

// --- the block, and the refusal -----------------------------------------------------------------

describe("the family gates its own block", () => {
  const binding = { block: "timers", version: PREPARED_RUNTIME_BLOCKS.timers, optional: true };

  test("an absent optional block is an answer, not a refusal", () => {
    const view = parseTimersBlock({ gameplay: PREPARED_RUNTIME_BLOCKS.gameplay }, binding);
    expect(view).toEqual({ block: "timers", version: null, published: false });
  });

  test("a block at a version this build does not read is refused by name", () => {
    expect(() => parseTimersBlock({ timers: "platformer-timers-block-v2" }, binding)).toThrow(
      'manifest block "timers" is published as platformer-timers-block-v2; this build reads platformer-timers-block-v1',
    );
  });

  test("seconds in, milliseconds out, and the conversion happens once", () => {
    const block: TimersBlock = {
      entries: [
        { timer_id: "round", seconds: 90, on_end: "session_ended", display: "hud" },
        { timer_id: "grace", seconds: 3, on_end: "session_ended", display: "hidden" },
      ],
    };
    expect(timerParamsFromBlock(block)).toEqual([
      { timerId: "round", durationMs: 90_000, onEnd: "session_ended", shown: true },
      { timerId: "grace", durationMs: 3_000, onEnd: "session_ended", shown: false },
    ]);
  });
});
