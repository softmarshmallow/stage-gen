// What the `score` family reads out of a manifest, and it is the family's own block.
//
// Most families gate a block somebody else owns — the clock gates `gameplay`
// because that is where its holders are authored, the camera gates `maps`
// because a follow axis is a map fact. This one has a block of its very own,
// `[score]`, and it is one of the two the pipeline gained for this step. That
// is the whole difference between a family and a genre's private arithmetic:
// the runner's `10` and `500` are compiled in, and a package that wants a
// different economy has to be a different build; an authored award table is a
// number a game states.
//
// The block is OPTIONAL, in the strong sense the plan's rule 6 gives the word:
// a package that publishes none is not a package whose awards are all zero, it
// is a package with no score, and the family seals quiet. Bellweather publishes
// none; the wave variant publishes one; the runner's manifest has no such block
// key at all, so the same gate answers "not published" there without a refusal.
//
// The numbers are the package's rather than the family's, and rule 7 says why
// that is not a contradiction of the runner keeping its own: a number belongs
// in the pipeline's table iff an offline refusal reads it. Nothing offline
// refuses on what a token is worth — so a genre that never authors one keeps
// its constants, and a genre that authors one is answered from the document.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";
import type { ScoreBlock, ScoreEvent } from "@/lib/manifest/prepared-manifest";
import type { ChainPolicy, ScoreParams } from "./score";

export type ScoreBlockBinding = FamilyBlockBinding;
export type ScoreBlockView = FamilyBlockView;

/**
 * Gate the block this family's awards are authored in.
 *
 * Refuses by naming the block: `manifest block "score" is published as
 * platformer-score-block-v2; this build reads platformer-score-block-v1`.
 */
export function parseScoreBlock(blocks: BlockTable, binding: ScoreBlockBinding): ScoreBlockView {
  return gateFamilyBlock(blocks, binding);
}

/**
 * The authored award table, as the family's parameters.
 *
 * `null` in, `null` out: an unauthored score is not a score of zero. The chain
 * is the caller's, because the authored vocabulary has no word for one — a
 * package states what an occurrence pays, and whether a run has a rhythm that
 * pays more is the genre's rule about its own play.
 */
export function scoreParamsFromBlock(
  block: ScoreBlock | null,
  chain: ChainPolicy<ScoreEvent> | null = null,
): ScoreParams<ScoreEvent> | null {
  if (block === null) return null;
  return Object.freeze({ awards: block.awards, chain });
}

/** Whether the authored block asks for the total to be drawn. */
export function scoreIsShown(block: ScoreBlock | null): boolean {
  return block !== null && block.display === "hud";
}
