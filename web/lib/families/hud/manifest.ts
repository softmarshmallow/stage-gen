// What the `hud` family reads out of a manifest.
//
// Almost nothing, and the composition table says so in an unusual way: the
// block is `[combat_text]` and **not** `ui.toml`, because `ui.toml` is art
// direction — sheets, nine-slice geometry, icon grids — which is `ui`'s, and
// the runner does not publish it at all. What a HUD reads is whether a readout
// exists to be drawn: `[gameplay] combat_text.enabled` is what decides that
// damage numbers are drawn over an actor, and `[gameplay] progression.enabled`
// what decides the stat log has anything to say.
//
// The runner gates the same block for the mirror reason: `[gameplay]` is where
// its vitals profile lives, and a bar that can only ever read full is a promise
// about mistakes the player does not have — so whether the bar is drawn is an
// authored fact there too.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type HudBlockBinding = FamilyBlockBinding;
export type HudBlockView = FamilyBlockView;

export function parseHudBlock(blocks: BlockTable, binding: HudBlockBinding): HudBlockView {
  return gateFamilyBlock(blocks, binding);
}
