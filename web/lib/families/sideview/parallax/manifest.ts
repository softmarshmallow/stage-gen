// What the `sideview/parallax` family reads out of a manifest: the layers, and
// the datum they register against.
//
// Two blocks in two genres, and again the family does not pretend they are one.
// The runner authors its bands in a block of their own — `layers` — because a
// runner track is one endless place. The platformer authors them per map inside
// `maps`, beside the occupancy whose `walk_surface_row` is the ground datum a
// world-registered band meets, so for that genre the layers and the datum they
// resolve against are one authored fact and one block.
//
// Either way the refusal comes from the family that could not go on, by name.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type ParallaxBlockBinding = FamilyBlockBinding;
export type ParallaxBlockView = FamilyBlockView;

export function parseParallaxBlock(
  blocks: BlockTable,
  binding: ParallaxBlockBinding,
): ParallaxBlockView {
  return gateFamilyBlock(blocks, binding);
}
