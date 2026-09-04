// What the `particles` family reads out of a manifest: whether a package has
// art for its particles at all, and whether the thing that throws them exists.
//
// The family authors no block of its own — a puff is a runtime fact, the way a
// hold is — but what a genre may throw is authored somewhere. The runner's dust
// is cut from `fx`'s `[sprite.dust]` atlas, optional in every package: without
// it the run draws the procedural silhouette instead, which is an answer and
// not a refusal. The platformer's sparks exist only for a package whose
// `gameplay` block enables combat, because a blow is what throws them.
//
// So the family gates the block its genre's particles depend on, by name, and
// the two genres name two different blocks — the same shape the camera has.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type ParticlesBlockBinding = FamilyBlockBinding;
export type ParticlesBlockView = FamilyBlockView;

export function parseParticlesBlock(
  blocks: BlockTable,
  binding: ParticlesBlockBinding,
): ParticlesBlockView {
  return gateFamilyBlock(blocks, binding);
}
