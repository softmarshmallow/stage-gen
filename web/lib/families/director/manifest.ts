// What the `director` family reads out of a manifest.
//
// Both genres author a set-piece and neither authors it in the same shape:
// `[[boss_encounters]]` is map-anchored and names a `mob_id`, `[encounter]` is
// a singleton naming a `boss_id` and an arena. Unifying the two authored forms
// is the contract bump the ruling defers; taking a dependency on the block each
// one lives in is not, and the family does it by name in both.
//
//   - the platformer's is `gameplay`, where `[[boss_encounters]]` sits, plus
//     `maps`, because the anchor a set-piece is armed at is a *map* fact — a
//     portal endpoint's normalized x — and an anchor that moves moves the gate.
//   - the runner's is `gameplay`, where `[encounter]` sits, plus `segments`,
//     because the arena the fight is fought over is a streamed chunk role.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type DirectorBlockBinding = FamilyBlockBinding;
export type DirectorBlockView = FamilyBlockView;

export function parseDirectorBlock(
  blocks: BlockTable,
  binding: DirectorBlockBinding,
): DirectorBlockView {
  return gateFamilyBlock(blocks, binding);
}
