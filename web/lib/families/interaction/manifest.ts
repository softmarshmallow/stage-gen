// What the `interaction` family reads out of a manifest.
//
// `gameplay`, in the platformer, and it is two tables of that one block:
// `[[interactions]]` binds an actor on a map to a scenario and says what each
// of its outcomes means, and `[[npc_placements]]` is what puts the actor
// somewhere to be near. An affordance with no binding is not an affordance, so
// the family cannot go on without the block the bindings live in.
//
// The room authors its interactions inside its own versioned document rather
// than in a block table, so the family takes its dependency there at that
// grain, the same way `inventory` and `effects` do.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type InteractionBlockBinding = FamilyBlockBinding;
export type InteractionBlockView = FamilyBlockView;

export function parseInteractionBlock(
  blocks: BlockTable,
  binding: InteractionBlockBinding,
): InteractionBlockView {
  return gateFamilyBlock(blocks, binding);
}
