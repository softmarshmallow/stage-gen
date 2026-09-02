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
  /**
   * Held. The same key as `jump`, read only by thrust locomotion.
   *
   * One control wearing two meanings rather than a second button, because the
   * verb never changes: press to go up. While running that is an edge, because
   * a jump is an event; while flying it is a level, because thrust is a
   * condition. Keeping them as separate fields means the edge semantics of
   * `jump` survive - a held key must never read as a stream of fresh jumps -
   * while thrust gets the level it needs.
   */
  thrust: boolean;
  /** Edge-triggered. The restart request (R on the keyboard). */
  action: boolean;
}>;

export const NEUTRAL_RUNNER_INTENT: RunnerIntent = Object.freeze({
  jump: false,
  duck: false,
  thrust: false,
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
  setThrust(held: boolean): void;
  /** Read this frame's intent, consuming the latched edges. */
  sample(): RunnerIntent;
}

export function createIntentLatch(): RunnerIntentLatch {
  let jump = false;
  let action = false;
  let duck = false;
  let thrust = false;
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
    setThrust: (held: boolean) => {
      thrust = held;
    },
    sample: () => {
      const sampled = runnerIntent({ jump, action, duck, thrust });
      jump = false;
      action = false;
      return sampled;
    },
  };
}

/**
 * Keyboard source: Space/ArrowUp jump and hold thrust, R restarts, ArrowDown
 * holds duck.
 */
export function attachKeyboardIntentSource(
  latch: RunnerIntentLatch,
  target: Pick<Window, "addEventListener" | "removeEventListener">,
): () => void {
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.repeat) return;
    if (event.code === "Space" || event.code === "ArrowUp") {
      event.preventDefault();
      latch.requestJump();
      latch.setThrust(true);
    } else if (event.code === "KeyR") {
      latch.requestAction();
    } else if (event.code === "ArrowDown") {
      latch.setDuck(true);
    }
  };
  const onKeyUp = (event: KeyboardEvent) => {
    if (event.code === "ArrowDown") latch.setDuck(false);
    if (event.code === "Space" || event.code === "ArrowUp") latch.setThrust(false);
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
 * The upper 68% jumps (and therefore restarts after death) and holds thrust
 * for as long as it is held; the lower 32% ducks until every lower-zone
 * pointer is released. Pointer capture keeps both releases observable when a
 * sliding finger leaves the canvas.
 */
export function attachPointerIntentSource(
  latch: RunnerIntentLatch,
  target: PointerIntentTarget,
): () => void {
  const duckPointers = new Set<number>();
  const thrustPointers = new Set<number>();
  const capture = (pointerId: number) => {
    try {
      target.setPointerCapture(pointerId);
    } catch {
      // A synthetic event or an already-cancelled pointer may be uncapturable;
      // pointerup/cancel still releases it when delivered.
    }
  };
  const onPointerDown = (event: PointerEvent) => {
    event.preventDefault();
    const bounds = target.getBoundingClientRect();
    const duckBoundary = bounds.top + bounds.height * POINTER_DUCK_ZONE_START;
    if (event.clientY < duckBoundary) {
      // The jump edge fires once; the thrust level is held, so the upper zone
      // is captured now rather than forgotten the way a pure edge could be.
      latch.requestJump();
      thrustPointers.add(event.pointerId);
      latch.setThrust(true);
      capture(event.pointerId);
      return;
    }
    duckPointers.add(event.pointerId);
    latch.setDuck(true);
    capture(event.pointerId);
  };
  const releasePointer = (event: PointerEvent) => {
    if (duckPointers.delete(event.pointerId)) latch.setDuck(duckPointers.size > 0);
    if (thrustPointers.delete(event.pointerId)) latch.setThrust(thrustPointers.size > 0);
  };
  target.addEventListener("pointerdown", onPointerDown);
  target.addEventListener("pointerup", releasePointer);
  target.addEventListener("pointercancel", releasePointer);
  target.addEventListener("lostpointercapture", releasePointer);
  return () => {
    target.removeEventListener("pointerdown", onPointerDown);
    target.removeEventListener("pointerup", releasePointer);
    target.removeEventListener("pointercancel", releasePointer);
    target.removeEventListener("lostpointercapture", releasePointer);
    duckPointers.clear();
    thrustPointers.clear();
    latch.setDuck(false);
    latch.setThrust(false);
  };
}

/** The intent system: publish this frame's sampled intent as world data. */
export function createIntentSystem(latch: RunnerIntentLatch): GameSystem<RunnerWorld> {
  return {
    id: "runner/intent",
    contractVersion: "intent-system-v2",
    reads: [],
    writes: ["intent"],
    update(world) {
      world.intent = latch.sample();
    },
  };
}
