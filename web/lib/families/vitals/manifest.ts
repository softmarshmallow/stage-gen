// What the `vitals` family reads out of a manifest: the consequence table.
//
// Both genres author it in `gameplay`, in two vocabularies the plan intends to
// unify later: the runner names a consequence per source (`[run.consequences]`
// plus a `[run.vitals] profile`), and the platformer publishes a bare
// `starting_health` integer and a `contact_damage` boolean that the consumer
// maps onto the same table. Unifying the *authored* form is a contract bump
// and a separate decision; gating the block the table comes from is this
// family's own dependency, and it takes it by name.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type VitalsBlockBinding = FamilyBlockBinding;
export type VitalsBlockView = FamilyBlockView;

export function parseVitalsBlock(blocks: BlockTable, binding: VitalsBlockBinding): VitalsBlockView {
  return gateFamilyBlock(blocks, binding);
}
