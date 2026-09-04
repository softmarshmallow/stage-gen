// What the `session` family reads out of a manifest: the vocabulary a run can
// end with.
//
// A session's own machine is authored nowhere — three states and a lineage
// rule are code — but the *names* `endedBy` can carry are not: the runner's
// `[gameplay].consequences` is what decides that a run can end by `pit` at all,
// and the platformer authors its defeat under the same block. So `gameplay` is
// the block the family depends on, and it gates it by name for itself.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type SessionBlockBinding = FamilyBlockBinding;
export type SessionBlockView = FamilyBlockView;

export function parseSessionBlock(
  blocks: BlockTable,
  binding: SessionBlockBinding,
): SessionBlockView {
  return gateFamilyBlock(blocks, binding);
}
