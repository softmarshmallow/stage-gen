// The platformer's binding of the `clock` family: which things hold this genre.
//
// Two holders, and until this file they were two unrelated mechanisms. The
// conversation was a bare `return` at the top of every step below it, so
// "held" was re-decided twenty times a frame; the blow was a zero delta
// written by a step called `clock/hitstop`, which knew about the blow and
// nothing about the conversation. They are one fact — the simulation is not
// advancing — and now one system says so once.

import type { ClockHold } from "@/lib/families/clock/clock";
import { parseClockBlock, type ClockBlockView } from "@/lib/families/clock/manifest";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";
import type { BlockTable } from "@/lib/manifest/blocks";
import type { PlatformerFrameSteps, PlatformerFrameWorld } from "./frame-roster";

/**
 * The block this genre's holders are authored in.
 *
 * The hitstop hold exists only for a package whose `gameplay` block enables
 * combat — `ImpactSystem.hitstopActive` answers false outright when it does
 * not — so `gameplay` is the block the clock depends on, and the family gates
 * it by name rather than trusting the genre parser to have gated it first.
 */
export const PLATFORMER_CLOCK_BLOCK = Object.freeze({
  block: "gameplay",
  version: PREPARED_RUNTIME_BLOCKS.gameplay,
});

/** Gate the platformer's clock block. Refuses by naming `gameplay`. */
export function parsePlatformerClockBlock(blocks: BlockTable): ClockBlockView {
  return parseClockBlock(blocks, PLATFORMER_CLOCK_BLOCK);
}

/**
 * The holders, in the order the frame reports them.
 *
 * The conversation first: it is the outer hold, and a blow landed on the frame
 * a conversation opened is still inside one.
 */
export function platformerClockHolders(
  steps: PlatformerFrameSteps,
): readonly ClockHold<PlatformerFrameWorld>[] {
  return [
    // `hold` is this frame's, written by `dialogue/input`; the roster declares
    // the read so the sealer puts the clock after it.
    { name: "dialogue", held: (world) => world.hold },
    {
      // Feedback read of `impact`, undeclared: the hitstop deadline this asks
      // about was armed by a blow landed on an *earlier* frame, because the
      // systems that arm one — the player's swing and the shot pool — are
      // sealed after the clock. Declaring the read closes the cycle
      // clock/step -> player/update -> clock/step, which is refusal 1.
      //
      // Asked against `step.now` and not against the clock it is writing: the
      // deadline was armed from the frame clock, and a hold measured against
      // the clock it holds would never end.
      name: "hitstop",
      held: (_world, step) => steps.hitstopActive(step.now),
    },
  ];
}
