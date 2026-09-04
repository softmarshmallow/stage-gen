// What the `actor-ai` family reads out of a manifest: archetype names, and
// nothing else.
//
// The composition table says "archetype names only", and it is right in the
// strongest sense: the producer publishes a *word* per creature — `skittish`,
// `territorial`, `hunting`, `relentless` — and no numbers at all. Aggro radius,
// chase speed, cadence and damage are gameplay, so they live in the consumer
// and are tunable without regenerating an image. The authored surface is one
// closed vocabulary.
//
// The platformer authors that word in `mobs`. The bot authors nothing: it is a
// second profile over the same machinery, assembled in code, which is exactly
// what "profiles as genre content" means.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type ActorAiBlockBinding = FamilyBlockBinding;
export type ActorAiBlockView = FamilyBlockView;

export function parseActorAiBlock(
  blocks: BlockTable,
  binding: ActorAiBlockBinding,
): ActorAiBlockView {
  return gateFamilyBlock(blocks, binding);
}
