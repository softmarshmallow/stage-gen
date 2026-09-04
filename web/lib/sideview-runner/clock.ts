// The runner's binding of the `clock` family: which things hold this genre.
//
// One holder today, and it is the one the runner has been getting wrong: a
// screen-FX moment in flight. The stage-start moment already stops the run by
// another route — `run.phase` is `intro` until `fx-released` — but a *boss*
// cut-in plays over a run that is already going, and nothing stopped the
// simulation under it. The avatar kept integrating, a jump pressed during the
// tear fired, and the audio sink reported the takeoff.
//
// The read of `fx` is a feedback read, undeclared and written down here: the
// fx system is sealed after the avatar (it has to be — the encounter director
// consumes the release it emits and the avatar is upstream of the director),
// so a clock that declared the read would have to run both before the systems
// it hands a delta to and after the system that raises the moment. The cost is
// that a hold begins on the frame after the moment does, which at 60Hz is one
// frame of the two seconds a cut-in lasts.
//
// The dead phase is deliberately *not* a holder. A hold is transient and the
// simulation resumes into the same run; `dead` is the session's own phase, the
// systems that skip under it are reading a lifecycle and not a clock, and the
// simulation clock keeps counting through it so that a moment playing over a
// restart is timed from a clock that never rewinds.

import { createClockSystem, type ClockState } from "@/lib/families/clock/clock";
import { parseClockBlock, type ClockBlockView } from "@/lib/families/clock/manifest";
import type { BlockTable } from "@/lib/manifest/blocks";
import type { GameSystem } from "@/lib/kernel/systems";
import { RUNNER_BLOCKS } from "./contract";
import type { RunnerWorld } from "./world";

/**
 * The block this genre's holders are authored in.
 *
 * A moment is the runner's only holder and a moment comes out of `fx`, which a
 * package need not publish at all — a track with no cut-in has nothing that
 * can hold it. Optional, therefore, and gated by name: a producer that moves
 * the fx block gets `manifest block "fx" is published as … ; this build reads
 * fx-block-v1` from the clock, not a silent hold that never fires.
 */
export const RUNNER_CLOCK_BLOCK = Object.freeze({
  block: "fx",
  version: RUNNER_BLOCKS.fx,
  optional: true,
});

/** Gate the runner's clock block. Refuses by naming `fx`. */
export function parseRunnerClockBlock(blocks: BlockTable): ClockBlockView {
  return parseClockBlock(blocks, RUNNER_CLOCK_BLOCK);
}

/** Whether a moment is playing and has not yet let the simulation go. */
export function momentHolds(world: Pick<RunnerWorld, "fx">): boolean {
  return world.fx !== null && !world.fx.released;
}

export function createRunnerClockSystem(): GameSystem<RunnerWorld> {
  return createClockSystem<RunnerWorld>({
    slice: "clock",
    holders: [{ name: "moment", held: momentHolds }],
  }) as GameSystem<RunnerWorld>;
}

export type { ClockState };
