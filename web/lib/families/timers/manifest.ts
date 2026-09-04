// What the `timers` family reads out of a manifest, and it is the family's own block.
//
// `[timers]` is the second of the two blocks the pipeline gained for this step,
// and like `[score]` it is optional in the strong sense: absent from the block
// table and absent from the document when a package authors none, so the family
// seals quiet rather than counting down from a default nobody wrote. Bellweather
// publishes none. The wave variant publishes one entry: ninety seconds, ending
// the session.
//
// Seconds in, milliseconds out. The authored unit is the one a person types and
// the runtime unit is the one the simulation counts in, and the conversion
// happens once, here, rather than at each of the places that would otherwise
// each divide by a thousand.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";
import type { TimersBlock } from "@/lib/manifest/prepared-manifest";
import type { TimerParams } from "./timers";

export type TimersBlockBinding = FamilyBlockBinding;
export type TimersBlockView = FamilyBlockView;

/**
 * Gate the block this family's countdowns are authored in.
 *
 * Refuses by naming the block: `manifest block "timers" is published as
 * platformer-timers-block-v2; this build reads platformer-timers-block-v1`.
 */
export function parseTimersBlock(
  blocks: BlockTable,
  binding: TimersBlockBinding,
): TimersBlockView {
  return gateFamilyBlock(blocks, binding);
}

/** The authored entries, as the family's parameters. No block is no timers. */
export function timerParamsFromBlock(block: TimersBlock | null): readonly TimerParams[] {
  if (block === null) return [];
  return Object.freeze(
    block.entries.map((entry) =>
      Object.freeze({
        timerId: entry.timer_id,
        durationMs: entry.seconds * 1000,
        onEnd: entry.on_end,
        shown: entry.display === "hud",
      }),
    ),
  );
}
