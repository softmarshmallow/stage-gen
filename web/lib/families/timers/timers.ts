// The `timers` family: a countdown, and what its end means to the run.
//
// The composition table's entry for it is one word long — "none" — and that is
// the honest state of the code before this file: nothing in either genre counts
// down. The platformer has a nine-hundred-millisecond immunity window, a
// fifteen-hundred-millisecond banner and a hitstop deadline, and every one of
// them is a *stamp* — a millisecond value compared against `step.now` — which
// is the right shape for a refractory window and the wrong shape for a clock
// the player is reading. A timer the player reads has to be a value: it is
// drawn, it is authored in seconds, and the run ends when it reaches zero.
//
// Two things the family is careful about, both learned from earlier steps:
//
//   - It counts on the SIMULATION clock, not the step clock. A hold is state
//     (rule 4) and a countdown is a simulation fact, so a conversation, a
//     hitstop or a cut-in stops the clock the player is racing. The alternative
//     — stamping a deadline against `step.now` — is the exact defect step 3
//     named when it said a refractory window would "burn through a hold".
//   - It expires ONCE. `expired` is a latch on the entry rather than a
//     recomputation from the remaining time, because a genre that ends its
//     session on the expiry must hear the edge exactly once no matter how many
//     frames the world takes to tear down.
//
// What the family does not own: what an expiry *means*. `on_end` is authored,
// the vocabulary has one member today (`session_ended`), and the family reports
// the edge to a binding rather than reaching for a lifecycle it cannot see.

import type { GameSystem } from "@/lib/kernel/systems";

/** One authored countdown, as the family holds it. */
export interface TimerParams {
  readonly timerId: string;
  /** How long it runs, in milliseconds; the authored form is seconds. */
  readonly durationMs: number;
  /** What its end is, in the authored vocabulary. */
  readonly onEnd: "session_ended";
  /** Whether the run draws it. */
  readonly shown: boolean;
}

export interface TimerEntryState {
  readonly timerId: string;
  /** Milliseconds left, clamped at zero. */
  remainingMs: number;
  /** Milliseconds counted so far, clamped at the duration. */
  elapsedMs: number;
  /** True from the frame it reaches zero onward. */
  expired: boolean;
}

export interface TimersState {
  entries: TimerEntryState[];
}

export function createTimersState(params: readonly TimerParams[]): TimersState {
  return {
    entries: params.map((entry) => ({
      timerId: entry.timerId,
      remainingMs: entry.durationMs,
      elapsedMs: 0,
      expired: false,
    })),
  };
}

/** Put every countdown back to its authored duration, in place. */
export function resetTimers(state: TimersState, params: readonly TimerParams[]): void {
  state.entries = createTimersState(params).entries;
}

/**
 * Advance every countdown by one frame's simulation time.
 *
 * Returns the ids that reached zero on THIS frame, in authored order, which is
 * the edge and not the condition: an entry already expired reports nothing, and
 * a frame long enough to cross the whole remainder still reports it once.
 */
export function advanceTimers(
  state: TimersState,
  params: readonly TimerParams[],
  simulationDtMs: number,
): readonly string[] {
  if (!(simulationDtMs > 0)) return [];
  const expired: string[] = [];
  for (const [index, entry] of state.entries.entries()) {
    if (entry.expired) continue;
    const duration = params[index]?.durationMs ?? 0;
    entry.elapsedMs = Math.min(duration, entry.elapsedMs + simulationDtMs);
    entry.remainingMs = Math.max(0, entry.remainingMs - simulationDtMs);
    if (entry.remainingMs > 0) continue;
    entry.expired = true;
    expired.push(entry.timerId);
  }
  return expired;
}

/** The one entry a genre draws, or null when nothing is shown. */
export function shownTimer(
  state: TimersState,
  params: readonly TimerParams[],
): TimerEntryState | null {
  for (const [index, entry] of state.entries.entries()) {
    if (params[index]?.shown) return entry;
  }
  return null;
}

export const TIMERS_SYSTEM_ID = "timers/countdown";

export interface TimersBinding<W> {
  /** Where the countdowns live on this world. */
  readonly slice: keyof W & string;
  readonly params: readonly TimerParams[];
  readonly id?: string;
  readonly contractVersion?: string;
  readonly reads?: readonly (keyof W & string)[];
  readonly writes?: readonly (keyof W & string)[];
  readonly after?: readonly string[];
  readonly emits?: readonly string[];
  readonly consumes?: readonly string[];
  readonly consumesDeferred?: readonly string[];
  /** How much simulation time passed this frame. The clock family's answer, in ms. */
  simulationDt(world: W): number;
  /** Whether the countdowns are running at all this frame. */
  counting?(world: W): boolean;
  /** One timer reached zero. The genre says what `session_ended` means to it. */
  onExpired?(world: W, timerId: string, onEnd: "session_ended"): void;
}

/**
 * The countdown system, generic over the world it counts on.
 *
 * It owns its slice and nothing else. Where the simulation delta comes from is
 * the binding's, which is what lets one genre hand it `clock.simulationDt` and
 * another hand it a delta it computed for its own reasons, without the family
 * taking a dependency on a clock slice that a second genre might not have.
 */
export function createTimersSystem<W extends object>(
  binding: TimersBinding<W>,
): GameSystem<W, never> {
  const { slice, params } = binding;
  const state = (world: W): TimersState =>
    (world as Record<string, unknown>)[slice] as TimersState;
  const endFor = (timerId: string): "session_ended" =>
    params.find((entry) => entry.timerId === timerId)?.onEnd ?? "session_ended";
  return {
    id: binding.id ?? TIMERS_SYSTEM_ID,
    contractVersion: binding.contractVersion ?? "timers-system-v1",
    reads: binding.reads ?? [],
    writes: binding.writes ?? [],
    owns: [slice],
    ...(binding.emits ? { emits: binding.emits as never } : {}),
    ...(binding.consumes ? { consumes: binding.consumes as never } : {}),
    ...(binding.consumesDeferred ? { consumesDeferred: binding.consumesDeferred as never } : {}),
    ...(binding.after ? { after: binding.after } : {}),
    update(world) {
      if (params.length === 0) return;
      if (binding.counting && !binding.counting(world)) return;
      const expired = advanceTimers(state(world), params, binding.simulationDt(world));
      for (const timerId of expired) binding.onExpired?.(world, timerId, endFor(timerId));
    },
    reset(world) {
      resetTimers(state(world), params);
    },
  };
}
