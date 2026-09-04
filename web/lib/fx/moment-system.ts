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

export type FxEvent =
  /** The simulation may resume; the overlay is tearing away. */
  | { readonly type: "fx-released"; readonly moment: string }
  /** The overlay is gone. */
  | { readonly type: "fx-finished"; readonly moment: string };

/** The one thing the system needs from a host's queue: somewhere to emit. */
export interface FxEmitter {
  emit(event: FxEvent): void;
}

/** What a world must carry to host the system: one slice and the shared queue. */
export interface FxWorld {
  fx: FxState | null;
  readonly events: FxEmitter;
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
): GameSystem<W> {
  return {
    id: FX_MOMENT_SYSTEM_ID,
    contractVersion: "fx-moment-system-v1",
    reads: [],
    writes: ["fx"],
    emits: ["fx-released", "fx-finished"],
    ...(options.after ? { after: options.after } : {}),
    update(world, step) {
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
