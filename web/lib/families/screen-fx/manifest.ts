// What the `screen-fx` family reads out of a manifest: the moments a package
// plays, and the sprite atlas its dust is cut from.
//
// `fx` is the family's own block — the only one of step 3's five that has one —
// and it is optional in both genres: a package that publishes no `fx` block
// plays no moment, which is an answer and not a refusal. What is refused is a
// package that publishes one at a version this build does not read, and the
// refusal names `fx` rather than the run.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type ScreenFxBlockBinding = FamilyBlockBinding;
export type ScreenFxBlockView = FamilyBlockView;

/** The version of the `fx` block this build reads. Shared: the block is not a genre's. */
export const SCREEN_FX_BLOCK: ScreenFxBlockBinding = Object.freeze({
  block: "fx",
  version: "fx-block-v1",
  optional: true,
});

export function parseScreenFxBlock(
  blocks: BlockTable,
  binding: ScreenFxBlockBinding = SCREEN_FX_BLOCK,
): ScreenFxBlockView {
  return gateFamilyBlock(blocks, binding);
}
