// What the `checkpoints` family reads out of a manifest.
//
// `gameplay`, in the platformer, and three fields of it: `[[map_uses]].role` is
// what marks a place as safe, `entry_spawn_id` is the fallback home, and
// `[[spawns]]` is what either of them resolves to. `[navigation].fall_recovery`
// is in the same block and is still unread — see the family's own notes and the
// plan's step 6 evidence for why.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type CheckpointsBlockBinding = FamilyBlockBinding;
export type CheckpointsBlockView = FamilyBlockView;

export function parseCheckpointsBlock(
  blocks: BlockTable,
  binding: CheckpointsBlockBinding,
): CheckpointsBlockView {
  return gateFamilyBlock(blocks, binding);
}
