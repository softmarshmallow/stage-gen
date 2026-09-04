// What the `effects` family reads out of a manifest.
//
// The platformer authors both halves in `gameplay`: `[[effects]]` is the
// operation vocabulary itself — the *names* a package may use — and `[[quests]]`
// names the effect ids that start and finish each one. A vocabulary published at
// a version this build does not read is a set of names the dispatch would seal
// against the wrong handlers, which is precisely the refusal this gate is for.
//
// The room has no block table: its whole document is one versioned kind its own
// parser refuses on, and its four operations are fields of that document rather
// than a published vocabulary.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type EffectsBlockBinding = FamilyBlockBinding;
export type EffectsBlockView = FamilyBlockView;

export function parseEffectsBlock(
  blocks: BlockTable,
  binding: EffectsBlockBinding,
): EffectsBlockView {
  return gateFamilyBlock(blocks, binding);
}
