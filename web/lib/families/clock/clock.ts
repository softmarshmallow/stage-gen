// The `clock` family: a hold is state, not a skipped tick — and it has a clock
// of its own.
//
// Four mechanisms did this job before, one per holder and none of them named:
// the runner returned early on `run.phase === "intro"` in five systems, the
// platformer wrote a zero delta for hitstop, the platformer's dialogue put a
// bare `return` at the top of every step below it, and the dead phase stopped
// the world by being checked everywhere. What they have in common is not "skip
// the tick" — presentation keeps sampling through all four — it is that the
// *simulation's* clock stops while the frame's does not.
//
// So the holders write flags on their own slices, this system reads every
// holder the genre lists, and it writes two numbers:
//
//   - `simulationDt`, this frame's elapsed simulation time (zero under a
//     hold), which every integrator reads instead of `step.dt`; and
//   - `simulationNow`, its integral, which everything that stamps a deadline
//     reads instead of `step.now`. The integral is the half that is easy to
//     leave out and expensive to leave out: a refractory window stamped
//     against the frame clock keeps expiring while the simulation is held, so
//     a two-second cut-in burns straight through a nine-hundred-millisecond
//     immunity that never got to protect anything.
//
// Systems that must run *through* a hold read `step` instead: the one that
// ends the hold, and the presentation that plays over it.
//
// The unit is the host's. The runner steps in seconds and the platformer in
// milliseconds, and this family never divides by anything, so both are the
// same arithmetic and neither has to convert to hold a clock.

import type { FixedStep, GameSystem } from "@/lib/kernel/systems";

export interface ClockState {
  /** Elapsed simulation time for this frame's integrators; zero under a hold. */
  simulationDt: number;
  /**
   * The integral of `simulationDt`: the clock a deadline is stamped against.
   *
   * Never rewound by a hold and never advanced through one, which is the
   * property `step.now` does not have and the reason this field exists.
   */
  simulationNow: number;
  /** Whether any holder is in force this frame. */
  held: boolean;
  /** The first holder in force, named; null while the simulation is running. */
  heldBy: string | null;
}

/** A fresh clock: nothing elapsed, nothing holding. */
export function createClock(): ClockState {
  return { simulationDt: 0, simulationNow: 0, held: false, heldBy: null };
}

/**
 * One thing that can hold the simulation.
 *
 * Named rather than anonymous because "who is holding this" is the first
 * question asked of a frozen frame, and a boolean cannot answer it. The
 * predicate reads the holder's own slice; whether that read is declared or is
 * a feedback read is the genre's business, and it says so at the binding.
 *
 * The step is handed over as well as the world, because a holder whose
 * deadline was armed from the frame clock has to be asked against the frame
 * clock — a hold cannot be measured against the clock it is holding.
 */
export interface ClockHold<W> {
  readonly name: string;
  held(world: W, step: FixedStep): boolean;
}

export interface ClockBinding<W> {
  /** Where the clock lives on this world. */
  readonly slice: keyof W & string;
  /** The holders, in the order the genre lists them; the first one wins the name. */
  readonly holders: readonly ClockHold<W>[];
  /** Slices the predicates read *this* frame, so the sealer can order them. */
  readonly reads?: readonly (keyof W & string)[];
  readonly after?: readonly string[];
}

export const CLOCK_SYSTEM_ID = "clock/step";

/**
 * The clock system: ask every holder, then write the two numbers.
 *
 * It owns the clock slice outright. A holder that wanted to write the delta
 * itself — which is what the platformer's hitstop did — would be a second
 * author of a slice whose whole value is that exactly one thing decides how
 * much time passed.
 */
export function createClockSystem<W extends object>(
  binding: ClockBinding<W>,
): GameSystem<W, never> {
  const slice = binding.slice;
  return {
    id: CLOCK_SYSTEM_ID,
    contractVersion: "clock-system-v1",
    reads: binding.reads ?? [],
    writes: [],
    owns: [slice],
    ...(binding.after ? { after: binding.after } : {}),
    update(world, step) {
      const clock = (world as Record<string, unknown>)[slice] as ClockState;
      let heldBy: string | null = null;
      for (const holder of binding.holders) {
        if (holder.held(world, step)) {
          heldBy = holder.name;
          break;
        }
      }
      clock.held = heldBy !== null;
      clock.heldBy = heldBy;
      clock.simulationDt = heldBy === null ? step.dt : 0;
      clock.simulationNow += clock.simulationDt;
    },
    reset(world, scope) {
      const clock = (world as Record<string, unknown>)[slice] as ClockState;
      clock.held = false;
      clock.heldBy = null;
      clock.simulationDt = 0;
      // A run starts over inside a session the simulation has already been
      // running in: the integral is the session's, and rewinding it would put
      // a moment still in flight over the restart on a clock that went
      // backwards. A session starts the clock again because there is no
      // earlier simulation for it to be continuous with.
      if (scope === "session") clock.simulationNow = 0;
    },
  };
}
