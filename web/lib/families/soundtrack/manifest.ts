// What the `soundtrack` family reads out of a manifest: the tracks, and what
// the edges do to them.
//
// Both genres author the catalog in a block called `soundtrack`, and the family
// gates that one by name in both. The runner authors the *other* half — the
// actions each run edge performs, `[music.death]`, `[music.restart]`,
// `[music.hurt]` — inside `audio`, which is also the block `cues` reads. Two
// families depending on one authored file is exactly the case the block table
// was drawn for: each takes its own dependency, and a producer that moves
// `audio` hears about it from both consumers rather than from a parser standing
// in for either.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type SoundtrackBlockBinding = FamilyBlockBinding;
export type SoundtrackBlockView = FamilyBlockView;

export function parseSoundtrackBlock(
  blocks: BlockTable,
  binding: SoundtrackBlockBinding,
): SoundtrackBlockView {
  return gateFamilyBlock(blocks, binding);
}
