// The platformer's instantiation of the `inventory` family.
//
// The bag itself is the family's; what is here is the two blocks this genre
// authors it in, gated by name so a producer that moves either gets a refusal
// from the family that could not go on.
//
//   - `gameplay`, for `[inventory]` and `[player].starting_item_ids`: the bag
//     the run opens with, and the capacity the consumer still does not bind.
//   - `items`, for the catalog itself. Every name in the bag is an item id from
//     that catalog and every square on the panel is a *position* in it, so a
//     catalog published at a version this build does not read is a bag whose
//     contents cannot be drawn and whose quest counts cannot be resolved.

import { parseInventoryBlock, type InventoryBlockView } from "@/lib/families/inventory";
import type { BlockTable } from "@/lib/manifest/blocks";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";

export const PLATFORMER_INVENTORY_BLOCKS = Object.freeze([
  Object.freeze({ block: "gameplay", version: PREPARED_RUNTIME_BLOCKS.gameplay }),
  Object.freeze({ block: "items", version: PREPARED_RUNTIME_BLOCKS.items }),
]);

/** Gate the platformer's inventory blocks. Refuses by naming the block that moved. */
export function parsePlatformerInventoryBlocks(blocks: BlockTable): readonly InventoryBlockView[] {
  return PLATFORMER_INVENTORY_BLOCKS.map((binding) => parseInventoryBlock(blocks, binding));
}
