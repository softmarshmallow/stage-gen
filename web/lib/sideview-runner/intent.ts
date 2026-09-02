// Per-frame runner intent — the single input the systems act on.
//
// Same seam as the platformer's player intent, owned by the runner: a source
// decides what the player asks for this frame, the systems decide what it
// costs, and neither knows the other. Edge-triggered fields are requests —
// latched when the action is asked for, consumed by exactly one sample — so
// a held key can never read as a stream of fresh jumps. `duck` is held state.

import type { GameSystem } from "@/lib/game-systems/systems";
import type { RunnerWorld } from "./world";

export type RunnerIntent = Readonly<{
  /** Edge-triggered. One jump request; a held key does not repeat it. */
  jump: boolean;
  /** Held. Keeps the grounded avatar in its admitted slide profile. */
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

const POINTER_DUCK_ZONE_START = 0.68;

type PointerIntentTarget = Pick<
  HTMLElement,
  | "addEventListener"
  | "removeEventListener"
  | "getBoundingClientRect"
  | "setPointerCapture"
>;

/**
 * Pointer source with two stable screen-space controls.
 *
 * The upper 68% jumps (and therefore restarts after death); holding the lower
 * 32% ducks until every lower-zone pointer is released. Pointer capture keeps
 * the release observable when a sliding finger leaves the canvas.
 */
export function attachPointerIntentSource(
  latch: RunnerIntentLatch,
  target: PointerIntentTarget,
): () => void {
  const duckPointers = new Set<number>();
  const onPointerDown = (event: PointerEvent) => {
    event.preventDefault();
    const bounds = target.getBoundingClientRect();
    const duckBoundary = bounds.top + bounds.height * POINTER_DUCK_ZONE_START;
    if (event.clientY < duckBoundary) {
      latch.requestJump();
      return;
    }
    duckPointers.add(event.pointerId);
    latch.setDuck(true);
    try {
      target.setPointerCapture(event.pointerId);
    } catch {
      // A synthetic event or an already-cancelled pointer may be uncapturable;
      // pointerup/cancel still releases it when delivered.
    }
  };
  const releaseDuck = (event: PointerEvent) => {
    if (!duckPointers.delete(event.pointerId)) return;
    latch.setDuck(duckPointers.size > 0);
  };
  target.addEventListener("pointerdown", onPointerDown);
  target.addEventListener("pointerup", releaseDuck);
  target.addEventListener("pointercancel", releaseDuck);
  target.addEventListener("lostpointercapture", releaseDuck);
  return () => {
    target.removeEventListener("pointerdown", onPointerDown);
    target.removeEventListener("pointerup", releaseDuck);
    target.removeEventListener("pointercancel", releaseDuck);
    target.removeEventListener("lostpointercapture", releaseDuck);
    duckPointers.clear();
    latch.setDuck(false);
  };
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
