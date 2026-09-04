// What the `prompt` family reads out of a manifest.
//
// The family authors no block of its own — the line of text is the runtime's
// word for a key, not the package's — but *whether a prompt can be offered at
// all* is authored, and that is what the family gates, the way `clock` gates
// the block that decides whether its holder can exist. In the platformer both
// affordances are `gameplay`'s: a talk prompt exists only where
// `[[npc_placements]]` and `[[interactions]]` put a villager with a scenario,
// and an enter prompt only where `[[transitions]]` put a door with somewhere
// behind it.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type PromptBlockBinding = FamilyBlockBinding;
export type PromptBlockView = FamilyBlockView;

export function parsePromptBlock(blocks: BlockTable, binding: PromptBlockBinding): PromptBlockView {
  return gateFamilyBlock(blocks, binding);
}
