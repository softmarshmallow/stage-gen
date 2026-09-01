// Per-frame runner intent — the single input the systems act on.
//
// Same seam as the platformer's player intent, owned by the runner: a source
// decides what the player asks for this frame, the systems decide what it
// costs, and neither knows the other. Edge-triggered fields are requests —
// latched when the action is asked for, consumed by exactly one sample — so
// a held key can never read as a stream of fresh jumps. `duck` is held state.

import type { GameSystem } from "./systems";
import type { RunnerWorld } from "./world";

export type RunnerIntent = Readonly<{
  /** Edge-triggered. One jump request; a held key does not repeat it. */
  jump: boolean;
  /** Held. Reserved by the intent contract; the v1 gameplay ignores it. */
  duck: boolean;
  /** Edge-triggered. The restart request (R on the keyboard). */
  action: boolean;
}>;

export const NEUTRAL_RUNNER_INTENT: RunnerIntent = Object.freeze({
  jump: false,
  duck: false,
  action: false,
});

/** Build a frozen intent, defaulting every unstated field to "not asked for". */
export function runnerIntent(requested: Partial<RunnerIntent> = {}): RunnerIntent {
  return Object.freeze({ ...NEUTRAL_RUNNER_INTENT, ...requested });
}

/**
 * The latch between event-driven browser input and the fixed-step frame.
 *
 * Events arrive whenever the browser delivers them; the frame asks once per
 * tick. Edges accumulate until sampled and are consumed by the sample, so a
 * request that lands between two ticks is seen exactly once, never zero or
 * twice.
 */
export interface RunnerIntentLatch {
  requestJump(): void;
  requestAction(): void;
  setDuck(held: boolean): void;
  /** Read this frame's intent, consuming the latched edges. */
  sample(): RunnerIntent;
}

export function createIntentLatch(): RunnerIntentLatch {
  let jump = false;
  let action = false;
  let duck = false;
  return {
    requestJump: () => {
      jump = true;
    },
    requestAction: () => {
      action = true;
    },
    setDuck: (held: boolean) => {
      duck = held;
    },
    sample: () => {
      const sampled = runnerIntent({ jump, action, duck });
      jump = false;
      action = false;
      return sampled;
    },
  };
}

/** Keyboard source: Space/ArrowUp jump, R restarts, ArrowDown holds duck. */
export function attachKeyboardIntentSource(
  latch: RunnerIntentLatch,
  target: Pick<Window, "addEventListener" | "removeEventListener">,
): () => void {
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.repeat) return;
    if (event.code === "Space" || event.code === "ArrowUp") {
      event.preventDefault();
      latch.requestJump();
    } else if (event.code === "KeyR") {
      latch.requestAction();
    } else if (event.code === "ArrowDown") {
      latch.setDuck(true);
    }
  };
  const onKeyUp = (event: KeyboardEvent) => {
    if (event.code === "ArrowDown") latch.setDuck(false);
  };
  target.addEventListener("keydown", onKeyDown as EventListener);
  target.addEventListener("keyup", onKeyUp as EventListener);
  return () => {
    target.removeEventListener("keydown", onKeyDown as EventListener);
    target.removeEventListener("keyup", onKeyUp as EventListener);
  };
}

/** Pointer source: a tap is a jump. The run-loop reads a jump as restart when dead. */
export function attachPointerIntentSource(
  latch: RunnerIntentLatch,
  target: Pick<HTMLElement, "addEventListener" | "removeEventListener">,
): () => void {
  const onPointerDown = () => latch.requestJump();
  target.addEventListener("pointerdown", onPointerDown);
  return () => target.removeEventListener("pointerdown", onPointerDown);
}

/** The intent system: publish this frame's sampled intent as world data. */
export function createIntentSystem(latch: RunnerIntentLatch): GameSystem<RunnerWorld> {
  return {
    id: "runner/intent",
    contractVersion: "intent-system-v1",
    reads: [],
    writes: ["intent"],
    update(world) {
      world.intent = latch.sample();
    },
  };
}
