// What the `loot` family reads out of a manifest.
//
// Two blocks in each genre, and they are not the same two, which is the
// clearest statement available that the family really is two halves.
//
//   - The platformer authors the drop half in `gameplay` (`[[loot_rules]]`) and
//     names its items in `items`.
//   - The runner authors no drop rule at all: its pickups are *placements*
//     inside the streamed chunks, so the block that decides what there is to
//     collect is `segments`, and `items` is the catalog those placements name.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type LootBlockBinding = FamilyBlockBinding;
export type LootBlockView = FamilyBlockView;

export function parseLootBlock(blocks: BlockTable, binding: LootBlockBinding): LootBlockView {
  return gateFamilyBlock(blocks, binding);
}
