// What the `intent` family reads out of a manifest: which actions a package has.
//
// The vocabulary is code, but *which of it a package answers for* is authored,
// and both genres author it in the same block. The runner's `[gameplay]
// duck_profile` is what makes `duck` a level this package has at all — a
// package with none has a key nothing can mean — and the platformer's
// `[gameplay] combat.enabled` is what makes `attack` an edge rather than one
// the controller suppresses. So `gameplay` is the block, and the family gates
// it by name for itself.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type IntentBlockBinding = FamilyBlockBinding;
export type IntentBlockView = FamilyBlockView;

export function parseIntentBlock(blocks: BlockTable, binding: IntentBlockBinding): IntentBlockView {
  return gateFamilyBlock(blocks, binding);
}
