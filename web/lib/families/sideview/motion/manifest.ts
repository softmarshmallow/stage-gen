// What the `sideview/motion` family reads out of a manifest: the strips.
//
// The runner authors its avatar's motion set in `avatar` — one actor, one
// block — and the platformer authors its player's in `player` and its
// creatures' in `mobs`, because a platformer has a cast. Neither genre has a
// `motion` block and neither should: a motion belongs to the actor that wears
// it, so the family gates the actor's block rather than inventing a home.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type MotionBlockBinding = FamilyBlockBinding;
export type MotionBlockView = FamilyBlockView;

export function parseMotionBlock(
  blocks: BlockTable,
  binding: MotionBlockBinding,
): MotionBlockView {
  return gateFamilyBlock(blocks, binding);
}

/** Gate every block whose actors this genre draws motion for, in order. */
export function parseMotionBlocks(
  blocks: BlockTable,
  bindings: readonly MotionBlockBinding[],
): readonly MotionBlockView[] {
  return Object.freeze(bindings.map((binding) => parseMotionBlock(blocks, binding)));
}
