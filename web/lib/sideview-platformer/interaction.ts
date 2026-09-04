// The platformer's instantiation of the `interaction` family.
//
// `gameplay`, twice over: `[[interactions]]` binds an actor on a map to a
// scenario and says what each of its outcomes means, and `[[npc_placements]]`
// is what puts that actor somewhere to be near. An affordance with no binding
// is not an affordance, so the family takes the block those two tables live in
// by name.

import { parseInteractionBlock, type InteractionBlockView } from "@/lib/families/interaction";
import type { BlockTable } from "@/lib/manifest/blocks";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";

export const PLATFORMER_INTERACTION_BLOCK = Object.freeze({
  block: "gameplay",
  version: PREPARED_RUNTIME_BLOCKS.gameplay,
});

/** Gate the platformer's interaction block. Refuses by naming `gameplay`. */
export function parsePlatformerInteractionBlock(blocks: BlockTable): InteractionBlockView {
  return parseInteractionBlock(blocks, PLATFORMER_INTERACTION_BLOCK);
}
