// What the `sideview/traversal` family reads out of a manifest.
//
// The composition table names the block `[navigation]`, and in neither genre is
// that a block of its own: the platformer authors it as `gameplay.navigation`
// (`allowed_movements`, `logical_world_wrap`, `fall_recovery`) and the runner
// authors the same subject as `gameplay.jump_profile`, `duck_profile`,
// `max_clear_gap_columns` and `max_rise_tiles` — the admission arithmetic the
// arc is derived from. One block name, two authored halves, which is the shape
// `intent` already has.
//
// The platformer takes a second block as well, and it is not a redundancy: the
// surface a body stands on is the map's authored occupancy, so `maps` is a
// dependency of the traversal core in that genre exactly as much as `gameplay`
// is, and a producer that moves either gets the refusal from the family that
// could not go on.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type TraversalBlockBinding = FamilyBlockBinding;
export type TraversalBlockView = FamilyBlockView;

export function parseTraversalBlock(
  blocks: BlockTable,
  binding: TraversalBlockBinding,
): TraversalBlockView {
  return gateFamilyBlock(blocks, binding);
}

/** Gate every block this genre's traversal depends on, in order. */
export function parseTraversalBlocks(
  blocks: BlockTable,
  bindings: readonly TraversalBlockBinding[],
): readonly TraversalBlockView[] {
  return Object.freeze(bindings.map((binding) => parseTraversalBlock(blocks, binding)));
}
