// What the `inventory` family reads out of a manifest.
//
// The platformer authors it in `gameplay`: `[inventory]` carries the currency
// item and the starting capacity, and `[player].starting_item_ids` is the bag
// the run opens with. Which of those the consumer binds is the consumer's
// business — see `prepared-scene.ts` for why `starting_capacity` is still not
// bound — but the family cannot go on without the block at a version it reads,
// so it takes that dependency by name rather than inheriting the genre's.
//
// The room has no block table to gate. Its whole document is one versioned kind
// (`pointclick-room-runtime-v3`) refused by its own parser, so the family's
// dependency there is already answered at a coarser grain, and inventing a
// block for it would be authoring work rather than extraction.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type InventoryBlockBinding = FamilyBlockBinding;
export type InventoryBlockView = FamilyBlockView;

export function parseInventoryBlock(
  blocks: BlockTable,
  binding: InventoryBlockBinding,
): InventoryBlockView {
  return gateFamilyBlock(blocks, binding);
}
