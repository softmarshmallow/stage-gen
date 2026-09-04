// What the `clock` family reads out of a manifest: which holders a package has.
//
// The family has no block of its own — a hold is a runtime fact, not an
// authored one — but *whether a genre's holder can exist at all* is authored,
// and it is authored in a block somebody else owns: the runner's moment hold
// exists only for a package that published an `fx` block with a moment in it,
// and the platformer's hitstop hold exists only for a package whose `gameplay`
// block enables combat. So the family gates that one block itself, by name,
// through the per-block table, instead of trusting the genre parser to have
// gated everything up front on its behalf.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type ClockBlockBinding = FamilyBlockBinding;
export type ClockBlockView = FamilyBlockView;

/** Gate the one block this genre's clock holders are authored in. */
export function parseClockBlock(blocks: BlockTable, binding: ClockBlockBinding): ClockBlockView {
  return gateFamilyBlock(blocks, binding);
}
