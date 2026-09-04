// The platformer's instantiation of the `effects` family.
//
// The vocabulary is two operations and the words the states are named in. Both
// are authored — a package publishes `[[effects]]` entries whose `operation` is
// one of these names, and `[[quests]]` whose lifecycle runs through them — so
// they are listed here, beside the block they come from, rather than being
// implied by whichever `if` happened to be written at the call site.

import { parseEffectsBlock, type EffectsBlockView } from "@/lib/families/effects";
import type { BlockTable } from "@/lib/manifest/blocks";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";

/** Every operation a prepared package may name. Sealed against the scene's handlers at boot. */
export const PLATFORMER_EFFECT_OPERATIONS = Object.freeze([
  "set_quest_state",
  "grant_item",
] as const);

/** The word this genre calls a quest that is running. */
export const PLATFORMER_QUEST_ACTIVE = "active";

/** The operation a quest completes with; anything else is refused at boot. */
export const PLATFORMER_QUEST_STATE_OPERATION = "set_quest_state";

export const PLATFORMER_EFFECTS_BLOCK = Object.freeze({
  block: "gameplay",
  version: PREPARED_RUNTIME_BLOCKS.gameplay,
});

/** Gate the platformer's effects block. Refuses by naming `gameplay`. */
export function parsePlatformerEffectsBlock(blocks: BlockTable): EffectsBlockView {
  return parseEffectsBlock(blocks, PLATFORMER_EFFECTS_BLOCK);
}
