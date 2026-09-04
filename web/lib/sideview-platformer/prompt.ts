// The platformer's instantiation of the `prompt` family.
//
// Two kinds, `talk` and `enter`, and both exist only because the package
// authored something to be near: `[[npc_placements]]` plus `[[interactions]]`
// for the first, `[[transitions]]` for the second. So the block the family
// gates is `gameplay`, the one that decides whether either affordance can be
// offered at all.

import { parsePromptBlock, type PromptBlockView } from "@/lib/families/prompt";
import type { BlockTable } from "@/lib/manifest/blocks";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";

/** The prompt kinds this genre offers. */
export const PLATFORMER_PROMPT_KINDS = Object.freeze(["talk", "enter"] as const);

export const PLATFORMER_PROMPT_BLOCK = Object.freeze({
  block: "gameplay",
  version: PREPARED_RUNTIME_BLOCKS.gameplay,
});

/** Gate the platformer's prompt block. Refuses by naming `gameplay`. */
export function parsePlatformerPromptBlock(blocks: BlockTable): PromptBlockView {
  return parsePromptBlock(blocks, PLATFORMER_PROMPT_BLOCK);
}
