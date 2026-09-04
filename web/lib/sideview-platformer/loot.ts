// The platformer's instantiation of the `loot` family.
//
// The drop half is this genre's alone — the runner authors placements rather
// than rules — so the two blocks are `gameplay`, where `[[loot_rules]]` lives,
// and `items`, the catalog every rule's `item_id` resolves against and every
// drop is drawn from.

import { parseLootBlock, type LootBlockView } from "@/lib/families/loot";
import type { BlockTable } from "@/lib/manifest/blocks";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";

/**
 * The gap between two units of one stack, in pixels.
 *
 * Consumer-owned by the rule the runner's own file states: a number belongs to
 * the manifest iff a refusal depends on it, and nothing refuses over how far
 * apart two tarts land.
 */
export const LOOT_DROP_SPACING_PX = 28;

export const PLATFORMER_LOOT_BLOCKS = Object.freeze([
  Object.freeze({ block: "gameplay", version: PREPARED_RUNTIME_BLOCKS.gameplay }),
  Object.freeze({ block: "items", version: PREPARED_RUNTIME_BLOCKS.items }),
]);

/** Gate the platformer's loot blocks. Refuses by naming the block that moved. */
export function parsePlatformerLootBlocks(blocks: BlockTable): readonly LootBlockView[] {
  return PLATFORMER_LOOT_BLOCKS.map((binding) => parseLootBlock(blocks, binding));
}
