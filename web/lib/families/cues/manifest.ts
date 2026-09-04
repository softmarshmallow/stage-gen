// What the `cues` family reads out of a manifest: the bindings, and the
// realizations they reach.
//
// `audio` is the block. `[bindings]` is the authored half of the rename table —
// which effect id a cue name reaches — and `[[effects]]` carries the
// realization each id resolves to, an oscillator sweep or a generated clip. A
// package that publishes neither has a runtime that says nothing out loud,
// which is an answer; one that publishes a version this build does not read is
// refused, and the refusal names `audio` rather than the run.
//
// The block is `soundtrack`'s second dependency as well — `[music.*]` lives in
// the same authored file — and both families gate it for themselves. That is
// the whole point of the per-block table: two consumers of one file, two
// refusals, neither speaking for the other.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type CuesBlockBinding = FamilyBlockBinding;
export type CuesBlockView = FamilyBlockView;

export function parseCuesBlock(blocks: BlockTable, binding: CuesBlockBinding): CuesBlockView {
  return gateFamilyBlock(blocks, binding);
}
