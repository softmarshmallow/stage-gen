// The fixed-timestep accumulator: variable frame deltas in, deterministic
// fixed steps out.
//
// Distance, score, and every physics integration in the runner are functions
// of how many fixed steps have elapsed, never of the display's frame pacing —
// which is what makes a run reproducible from its seed. The renderer hands in
// whatever delta the browser produced; this module converts it into zero or
// more identical 1/60s steps and carries the remainder forward.
//
// The max-substep clamp is the spiral-of-death guard: after a stall (a
// backgrounded tab, a debugger pause) the accumulator refuses to replay the
// entire gap, emits at most the clamp, and drops the rest. Time skipped this
// way is simply lost, which for an arcade runner is the correct trade — the
// alternative is a burst of catch-up steps the player never saw.

import type { FixedStep } from "@/lib/game-systems/systems";

export const FIXED_STEP_SECONDS = 1 / 60;
export const MAX_SUBSTEPS_PER_ADVANCE = 5;

export interface FixedStepAccumulator {
  /** Convert one variable frame delta (milliseconds) into fixed steps. */
  advance(elapsedMs: number): readonly FixedStep[];
  /** Forget accumulated time and step identity, e.g. across a restart. */
  reset(): void;
}

export function createFixedStepAccumulator(
  stepSeconds: number = FIXED_STEP_SECONDS,
  maxSubSteps: number = MAX_SUBSTEPS_PER_ADVANCE,
): FixedStepAccumulator {
  if (!Number.isFinite(stepSeconds) || stepSeconds <= 0) {
    throw new Error("fixed step size must be positive and finite");
  }
  if (!Number.isSafeInteger(maxSubSteps) || maxSubSteps < 1) {
    throw new Error("max substeps must be a positive integer");
  }
  let pendingSeconds = 0;
  let now = 0;
  let frame = 0;
  return {
    advance(elapsedMs: number): readonly FixedStep[] {
      // A negative or non-finite delta is a clock hiccup, not time.
      if (Number.isFinite(elapsedMs) && elapsedMs > 0) {
        pendingSeconds += elapsedMs / 1000;
      }
      const steps: FixedStep[] = [];
      while (pendingSeconds >= stepSeconds && steps.length < maxSubSteps) {
        pendingSeconds -= stepSeconds;
        now += stepSeconds;
        frame += 1;
        steps.push(Object.freeze({ dt: stepSeconds, now, frame }));
      }
      if (pendingSeconds >= stepSeconds) {
        // The clamp fired: drop the backlog, keep only a sub-step remainder.
        pendingSeconds = pendingSeconds % stepSeconds;
      }
      return steps;
    },
    reset(): void {
      pendingSeconds = 0;
      now = 0;
      frame = 0;
    },
  };
}
