// The generic FX moment system: hold a moment, drive its view, say when it lets go.
//
// A genre puts an `fx` slice on its world and points this system at a view.
// The system stamps the moment's start from the fixed-step clock it is handed
// (never from zero: a runner's accumulator is never reset across restarts),
// evaluates the pure choreography every tick, and emits two events the
// genre's own loop can consume: `fx-released` when the simulation may resume,
// and `fx-finished` when the overlay is gone. It reads nothing else about the
// world, which is what makes it the same system for a runner's stage start
// and a visual novel's scene entry.
//
// It also *owns* the `fx` slice, which is the whole reason `fx-requested`
// exists. A director that wants a moment played used to write the slice
// itself, which made two authors of one piece of state and hid the fact that
// the moment could not start until this system next ran anyway. Now the
// director asks. The ask is a deferred consume: a director is sealed after
// this system — it has to be, because it reads the release this system emits
// — so its request cannot be heard until the following frame, and saying that
// out loud is better than a write that pretended otherwise.

import type { GameSystem } from "@/lib/kernel/systems";
import { CUT_IN_CHOREOGRAPHIES, type CutInChoreographyName, type CutInFrame, cutInFrame } from "./cut-in";

export interface FxState {
  /** The moment being played, e.g. "stage_start". */
  readonly moment: string;
  readonly choreography: CutInChoreographyName;
  /** Step-clock seconds the moment started at; null until the first held tick. */
  startedAt: number | null;
  /** Whether `fx-released` was already emitted for this moment. */
  released: boolean;
}

/** Somebody wants a moment played; the fx system decides when it starts. */
export interface FxRequestedEvent {
  readonly type: "fx-requested";
  readonly moment: string;
  readonly choreography: CutInChoreographyName;
}

export type FxEvent =
  /** A director asked for a moment. Heard on the next frame; see below. */
  | FxRequestedEvent
  /** The simulation may resume; the overlay is tearing away. */
  | { readonly type: "fx-released"; readonly moment: string }
  /** The overlay is gone. */
  | { readonly type: "fx-finished"; readonly moment: string };

/** What the system needs from a host's queue: somewhere to emit, and last frame's asks. */
export interface FxEmitter {
  emit(event: FxEvent): void;
  previous(type: "fx-requested"): readonly FxRequestedEvent[];
}

/** What a world must carry to host the system: one slice and the shared queue. */
export interface FxWorld {
  fx: FxState | null;
  readonly events: FxEmitter;
}

/** Ask for a moment. The fx system starts it on the next frame, and owns it. */
export function requestFxMoment(
  world: { readonly events: FxEmitter },
  moment: string,
  choreography: CutInChoreographyName,
): void {
  world.events.emit({ type: "fx-requested", moment, choreography });
}

/** What a scene must provide: apply one frame, and clear when nothing plays. */
export interface FxView {
  sync(frame: CutInFrame, moment: string): void;
  hide(): void;
}

export const FX_MOMENT_SYSTEM_ID = "fx/moment";

/** Start one moment on a world; the next tick stamps its clock. */
export function beginFxMoment(
  world: FxWorld,
  moment: string,
  choreography: CutInChoreographyName,
): void {
  world.fx = { moment, choreography, startedAt: null, released: false };
}

export function createFxSystem<W extends FxWorld>(
  view: FxView,
  options: { readonly after?: readonly string[] } = {},
  // The event parameter is spelled out rather than derived from `W`: inside a
  // generic, a host world's union is not yet known, and what this system says
  // and hears is its own vocabulary in any case. A host whose union lacks
  // these types cannot seal it, which is the check that matters.
): GameSystem<W, FxEvent["type"]> {
  return {
    id: FX_MOMENT_SYSTEM_ID,
    contractVersion: "fx-moment-system-v2",
    reads: [],
    writes: [],
    owns: ["fx"],
    emits: ["fx-released", "fx-finished"],
    consumesDeferred: ["fx-requested"],
    ...(options.after ? { after: options.after } : {}),
    update(world, step) {
      // Last frame's asks, honoured before anything is drawn: a moment already
      // in flight is never clobbered, which is the guard every director used
      // to have to write for itself.
      if (world.fx === null) {
        const asked = world.events.previous("fx-requested")[0];
        if (asked !== undefined) beginFxMoment(world, asked.moment, asked.choreography);
      }
      const fx = world.fx;
      if (fx === null) {
        view.hide();
        return;
      }
      if (fx.startedAt === null) fx.startedAt = step.now;
      const elapsedMs = (step.now - fx.startedAt) * 1000;
      const frame = cutInFrame(elapsedMs, CUT_IN_CHOREOGRAPHIES[fx.choreography]);
      view.sync(frame, fx.moment);
      if (frame.released && !fx.released) {
        fx.released = true;
        world.events.emit({ type: "fx-released", moment: fx.moment });
      }
      if (frame.finished) {
        world.events.emit({ type: "fx-finished", moment: fx.moment });
        world.fx = null;
        view.hide();
      }
    },
  };
}
